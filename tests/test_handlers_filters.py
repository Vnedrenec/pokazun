from datetime import UTC, datetime

import pytest
from aiogram.methods import (
    AnswerCallbackQuery,
    EditMessageReplyMarkup,
    EditMessageText,
    SendMessage,
)
from sqlalchemy import select

from pokazun.bot import texts
from pokazun.bot.keyboards import ConditionCb, PriceCb, RoomsCb, StepAction, StepCb
from pokazun.db.models import User
from pokazun.search.filters import ConditionGroup, PriceRange, RoomOption
from pokazun.search.service import get_draft, view
from pokazun.search.steps import Step
from tests.bot_harness import Harness, inline, of_type
from tests.tg import inaccessible_callback_update

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
NEXT = StepCb(action=StepAction.NEXT).pack()


@pytest.fixture
async def h(sessionmaker) -> Harness:
    harness = Harness(sessionmaker, T0)
    await harness.send(texts.BTN_FIND)
    return harness


async def draft_view(sessionmaker):
    async with sessionmaker() as s:
        user = await s.scalar(select(User))
        return view(await get_draft(s, user.id))


async def test_room_toggle_updates_markup_only(h, sessionmaker):
    requests = await h.click(RoomsCb(value=2, on=True).pack())
    [edit] = of_type(requests, EditMessageReplyMarkup)
    assert edit.message_id == 777
    buttons = inline(edit.reply_markup)
    assert ("✅ 2 кімнати", RoomsCb(value=2, on=False).pack()) in buttons
    assert (texts.BTN_NEXT, NEXT) in buttons
    assert of_type(requests, EditMessageText) == []
    assert len(of_type(requests, AnswerCallbackQuery)) == 1

    [edit] = of_type(await h.click(RoomsCb(value=2, on=False).pack()), EditMessageReplyMarkup)
    assert (texts.BTN_NEXT, NEXT) not in inline(edit.reply_markup)


async def test_duplicate_click_is_idempotent(h, sessionmaker):
    await h.click(RoomsCb(value=2, on=True).pack())
    requests = await h.click(RoomsCb(value=2, on=True).pack())
    assert of_type(requests, EditMessageReplyMarkup) == []
    assert (await draft_view(sessionmaker)).rooms == {RoomOption.TWO}


async def test_next_without_selection_stays(h, sessionmaker):
    await h.click(NEXT)
    assert (await draft_view(sessionmaker)).step is Step.ROOMS


async def test_next_moves_to_condition_then_price(h, sessionmaker):
    await h.click(RoomsCb(value=1, on=True).pack())
    [edit] = of_type(await h.click(NEXT), EditMessageText)
    assert edit.text == texts.CONDITION_PROMPT
    assert [t for t, _ in inline(edit.reply_markup)] == ["👉 Житловий стан", "👉 Після забудовника"]

    await h.click(ConditionCb(value="developer", on=True).pack())
    await h.click(ConditionCb(value="residential", on=True).pack())
    [edit] = of_type(await h.click(NEXT), EditMessageText)
    assert edit.text == texts.PRICE_PROMPT
    v = await draft_view(sessionmaker)
    assert v.conditions == {ConditionGroup.DEVELOPER, ConditionGroup.RESIDENTIAL}


async def go_to_price(h):
    await h.click(RoomsCb(value=1, on=True).pack())
    await h.click(NEXT)
    await h.click(ConditionCb(value="residential", on=True).pack())
    await h.click(NEXT)


async def test_price_gap_fill_and_edges(h, sessionmaker):
    await go_to_price(h)
    [edit] = of_type(await h.click(PriceCb(low=2, high=2).pack()), EditMessageReplyMarkup)
    by_text = dict(inline(edit.reply_markup))
    assert texts.BTN_RESET_PRICE in by_text
    [edit] = of_type(await h.click(by_text["👉 41–55 тис. $"]), EditMessageReplyMarkup)
    labels = [t for t, _ in inline(edit.reply_markup)]
    assert {"✅ 21–30 тис. $", "✅ 31–40 тис. $", "✅ 41–55 тис. $"} <= set(labels)
    assert (await draft_view(sessionmaker)).price == PriceRange(2, 4)

    interior = dict(inline(edit.reply_markup))["✅ 31–40 тис. $"]
    requests = await h.click(interior)
    assert of_type(requests, EditMessageReplyMarkup) == []
    assert (await draft_view(sessionmaker)).price == PriceRange(2, 4)

    edge = dict(inline(edit.reply_markup))["✅ 21–30 тис. $"]
    await h.click(edge)
    assert (await draft_view(sessionmaker)).price == PriceRange(3, 4)

    await h.click(StepCb(action=StepAction.RESET_PRICE).pack())
    assert (await draft_view(sessionmaker)).price is None


async def test_invalid_price_payload_ignored(h, sessionmaker):
    await go_to_price(h)
    await h.click(PriceCb(low=5, high=2).pack())
    assert (await draft_view(sessionmaker)).price is None


async def test_stale_keyboard_rerenders_current_step(h, sessionmaker):
    await h.click(RoomsCb(value=1, on=True).pack())
    await h.click(NEXT)
    [edit] = of_type(await h.click(RoomsCb(value=3, on=True).pack()), EditMessageText)
    assert edit.text == texts.CONDITION_PROMPT
    v = await draft_view(sessionmaker)
    assert v.rooms == {RoomOption.ONE} and v.step is Step.CONDITION


async def test_inaccessible_message_gets_new_message(h):
    requests = await h.feed(inaccessible_callback_update(RoomsCb(value=2, on=True).pack()))
    [msg] = of_type(requests, SendMessage)
    assert msg.text == texts.ROOMS_PROMPT
    assert ("✅ 2 кімнати", RoomsCb(value=2, on=False).pack()) in inline(msg.reply_markup)
