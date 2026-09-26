from datetime import UTC, datetime

import pytest
from aiogram.methods import SendMessage

from pokazun.bot import texts
from pokazun.bot.keyboards import RoomsCb
from tests.bot_harness import Harness, inline, of_type, reply, seed_search
from tests.tg import TG_USER_ID

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def h(sessionmaker) -> Harness:
    return Harness(sessionmaker, T0)


async def test_start_new_user(h):
    [msg] = of_type(await h.send("/start"), SendMessage)
    assert msg.text == texts.WELCOME
    assert reply(msg.reply_markup) == [texts.BTN_FIND, texts.BTN_SELL, texts.BTN_HELP]


async def test_start_with_deep_link_payload(h):
    [msg] = of_type(await h.send("/start promo"), SendMessage)
    assert msg.text == texts.WELCOME


async def test_start_user_with_search(h, sessionmaker):
    await seed_search(
        sessionmaker, TG_USER_ID, rooms=[2], conditions=["residential"], low=2, high=4, now=T0
    )
    [msg] = of_type(await h.send("/start"), SendMessage)
    assert reply(msg.reply_markup) == [
        texts.BTN_MY_SEARCH,
        texts.BTN_SAVED,
        texts.BTN_SELL,
        texts.BTN_HELP,
    ]


async def test_find_shows_rooms_step(h):
    [msg] = of_type(await h.send(texts.BTN_FIND), SendMessage)
    assert msg.text == texts.ROOMS_PROMPT
    assert [t for t, _ in inline(msg.reply_markup)] == [
        "👉 1 кімната",
        "👉 2 кімнати",
        "👉 3 кімнати",
        "👉 4+ кімнати",
    ]


async def test_find_resumes_draft(h):
    await h.send(texts.BTN_FIND)
    await h.click(RoomsCb(value=2, on=True).pack())
    [msg] = of_type(await h.send(texts.BTN_FIND), SendMessage)
    assert msg.text == texts.ROOMS_PROMPT
    assert ("✅ 2 кімнати", RoomsCb(value=2, on=False).pack()) in inline(msg.reply_markup)


async def test_find_with_active_search_opens_edit_menu(h, sessionmaker):
    await seed_search(
        sessionmaker, TG_USER_ID, rooms=[2], conditions=["residential"], low=2, high=4, now=T0
    )
    [msg] = of_type(await h.send(texts.BTN_FIND), SendMessage)
    assert msg.text.startswith("Ваші параметри пошуку:")


async def test_unknown_text_gets_menu_hint(h):
    [msg] = of_type(await h.send("привіт"), SendMessage)
    assert msg.text == texts.MENU_HINT
    assert reply(msg.reply_markup)[0] == texts.BTN_FIND
