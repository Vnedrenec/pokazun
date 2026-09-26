from datetime import UTC, datetime, timedelta

import pytest
from aiogram.enums import ChatAction
from aiogram.methods import EditMessageReplyMarkup, EditMessageText, SendChatAction, SendMessage
from sqlalchemy import func, select

from pokazun.bot import texts
from pokazun.bot.keyboards import ConditionCb, PriceCb, RoomsCb, StepAction, StepCb
from pokazun.db.models import Search, SearchDraft, SubscriptionState, User
from pokazun.search.filters import PriceRange
from tests.bot_harness import Harness, inline, of_type, reply, seed_objects, seed_search
from tests.tg import TG_USER_ID

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
T1 = T0 + timedelta(days=2)


def step(action: StepAction) -> str:
    return StepCb(action=action).pack()


async def reach_summary(h: Harness) -> list:
    await h.send(texts.BTN_FIND)
    await h.click(RoomsCb(value=2, on=True).pack())
    await h.click(RoomsCb(value=3, on=True).pack())
    await h.click(step(StepAction.NEXT))
    await h.click(ConditionCb(value="residential", on=True).pack())
    await h.click(step(StepAction.NEXT))
    await h.click(PriceCb(low=2, high=2).pack())
    await h.click(PriceCb(low=2, high=4).pack())
    return await h.click(step(StepAction.NEXT))


def objects(n_match: int) -> list[dict]:
    match = {"rooms": 2, "condition": "Євроремонт", "price_segment": 3, "synced_at": T0}
    miss = {"rooms": 1, "condition": "Євроремонт", "price_segment": 3, "synced_at": T0}
    return [match] * n_match + [miss]


@pytest.fixture
def h(sessionmaker) -> Harness:
    return Harness(sessionmaker, T0)


async def test_summary_screen_matches_spec(h):
    [edit] = of_type(await reach_summary(h), EditMessageText)
    assert edit.text == (
        "Ваш запит:\n\n"
        "👉 Кількість кімнат: 2 кімнати, 3 кімнати\n"
        "👉 Стан квартири: Житловий стан\n"
        "👉 Вартість: 21–55 тис. $\n\n"
        "Перевірте, чи все правильно. Якщо потрібно — змініть параметри пошуку."
    )
    assert [t for t, _ in inline(edit.reply_markup)] == [
        texts.BTN_START_SEARCH,
        texts.BTN_EDIT_SEARCH,
    ]


async def test_start_search_confirms_and_counts(h, sessionmaker):
    await seed_objects(sessionmaker, objects(3))
    await reach_summary(h)
    requests = await h.click(step(StepAction.START_SEARCH))

    [removed] = of_type(requests, EditMessageReplyMarkup)
    assert removed.reply_markup is None
    searching, found = of_type(requests, SendMessage)
    assert searching.text == texts.SEARCHING
    assert reply(searching.reply_markup)[:2] == [texts.BTN_MY_SEARCH, texts.BTN_SAVED]
    [typing] = of_type(requests, SendChatAction)
    assert typing.action == ChatAction.TYPING
    assert found.text.startswith("Знайшли 3 квартири за вашим запитом 🏠")
    assert inline(found.reply_markup) == [(texts.BTN_VIEW_RESULTS, step(StepAction.VIEW_RESULTS))]

    async with sessionmaker() as s:
        search = await s.scalar(select(Search))
        user = await s.scalar(select(User))
        assert await s.scalar(select(func.count()).select_from(SearchDraft)) == 0
    assert search.baseline_at == T0
    assert search.criteria.price == PriceRange(2, 4)
    assert user.subscription_state is SubscriptionState.ACTIVE


async def test_start_search_double_click(h, sessionmaker):
    await reach_summary(h)
    await h.click(step(StepAction.START_SEARCH))
    requests = await h.click(step(StepAction.START_SEARCH))
    assert of_type(requests, SendMessage) == []
    assert of_type(requests, EditMessageText) == []
    async with sessionmaker() as s:
        assert await s.scalar(select(func.count()).select_from(Search)) == 1


async def test_no_matches_message(h, sessionmaker):
    await reach_summary(h)
    requests = await h.click(step(StepAction.START_SEARCH))
    found = of_type(requests, SendMessage)[-1]
    assert found.text == texts.NOT_FOUND
    assert inline(found.reply_markup) == [(texts.BTN_EDIT_SEARCH, step(StepAction.EDIT))]


async def test_create_mode_edit_menu_roundtrip(h, sessionmaker):
    await reach_summary(h)
    [edit] = of_type(await h.click(step(StepAction.EDIT)), EditMessageText)
    assert edit.text.startswith("Ваші параметри пошуку:\n\n🛏 Кількість кімнат: 2, 3")
    [edit] = of_type(await h.click(step(StepAction.GOTO_ROOMS)), EditMessageText)
    assert edit.text == texts.ROOMS_PROMPT
    assert ("✅ 3 кімнати", RoomsCb(value=3, on=False).pack()) in inline(edit.reply_markup)
    await h.click(RoomsCb(value=3, on=False).pack())
    [edit] = of_type(await h.click(step(StepAction.NEXT)), EditMessageText)
    assert "🛏 Кількість кімнат: 2\n" in edit.text
    [edit] = of_type(await h.click(step(StepAction.SAVE)), EditMessageText)
    assert "👉 Кількість кімнат: 2 кімнати\n" in edit.text
    async with sessionmaker() as s:
        assert await s.scalar(select(func.count()).select_from(Search)) == 0


async def test_edit_active_search_and_save(h, sessionmaker):
    await seed_search(
        sessionmaker, TG_USER_ID, rooms=[2], conditions=["residential"], low=2, high=4, now=T0
    )
    await seed_objects(
        sessionmaker, [{"rooms": 2, "condition": "Євроремонт", "price_segment": 6, "synced_at": T0}]
    )
    h.now = T1
    [edit] = of_type(await h.click(step(StepAction.EDIT)), EditMessageText)
    assert edit.text.startswith("Ваші параметри пошуку:")
    await h.click(step(StepAction.GOTO_PRICE))
    await h.click(PriceCb(low=2, high=6).pack())
    [edit] = of_type(await h.click(step(StepAction.NEXT)), EditMessageText)
    assert "💰 Вартість: 21–100 тис. $" in edit.text
    requests = await h.click(step(StepAction.SAVE))
    assert of_type(requests, SendMessage)[-1].text.startswith("Знайшли 1 квартиру")
    async with sessionmaker() as s:
        search = await s.scalar(select(Search))
    assert search.criteria.price == PriceRange(2, 6)
    assert search.baseline_at == T1


async def test_edit_back_keeps_search(h, sessionmaker):
    await seed_search(
        sessionmaker, TG_USER_ID, rooms=[2], conditions=["residential"], low=2, high=4, now=T0
    )
    h.now = T1
    await h.click(step(StepAction.EDIT))
    await h.click(step(StepAction.GOTO_PRICE))
    await h.click(PriceCb(low=2, high=6).pack())
    await h.click(step(StepAction.NEXT))
    [edit] = of_type(await h.click(step(StepAction.BACK)), EditMessageText)
    assert edit.text == texts.EDIT_CANCELLED
    assert edit.reply_markup is None
    async with sessionmaker() as s:
        search = await s.scalar(select(Search))
        assert await s.scalar(select(func.count()).select_from(SearchDraft)) == 0
    assert search.criteria.price == PriceRange(2, 4)
    assert search.baseline_at == T0


async def test_edit_keeps_manual_pause(h, sessionmaker):
    user_id = await seed_search(
        sessionmaker, TG_USER_ID, rooms=[2], conditions=["residential"], low=2, high=4, now=T0
    )
    async with sessionmaker() as s, s.begin():
        (await s.get(User, user_id)).subscription_state = SubscriptionState.PAUSED_BY_USER
    await h.click(step(StepAction.EDIT))
    await h.click(step(StepAction.SAVE))
    async with sessionmaker() as s:
        user = await s.get(User, user_id)
    assert user.subscription_state is SubscriptionState.PAUSED_BY_USER


async def test_edit_without_search_or_draft_does_nothing(h):
    requests = await h.click(step(StepAction.EDIT))
    assert of_type(requests, EditMessageText) == []
    assert of_type(requests, SendMessage) == []
