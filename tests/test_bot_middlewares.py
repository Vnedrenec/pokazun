from datetime import UTC, datetime

import pytest
from aiogram import Router
from aiogram.filters import Command
from aiogram.methods import SendMessage
from aiogram.types import InlineQuery, Message
from sqlalchemy import func, select, update

from pokazun.alerts import AlertService
from pokazun.bot.factory import build_dispatcher
from pokazun.config import Settings
from pokazun.db.models import DeliveryState, ProcessedUpdate, User
from tests.tg import (
    group_message_update,
    inline_query_update,
    make_bot,
    message_update,
    my_chat_member_update,
    tg_user,
)

NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


def settings(allowlist: str = "") -> Settings:
    return Settings(
        env="staging" if allowlist else "dev",
        bot_token="42:TEST",
        database_url="postgresql+asyncpg://unused",
        telegram_mode="polling",
        allowed_user_ids=allowlist,
        airtable_token="patTest1234567890.abcdefabcdefabcdefabcd",
    )


def probe_router(calls: list[str]) -> Router:
    router = Router()

    @router.message(Command("ping"))
    async def ping(message: Message, db_user: User) -> None:
        calls.append(f"ping:{db_user.telegram_user_id}")
        await message.answer("pong")

    @router.message(Command("boom"))
    async def boom(message: Message) -> None:
        calls.append("boom")
        raise RuntimeError("handler exploded")

    @router.inline_query()
    async def inline(inline_query: InlineQuery) -> None:
        calls.append(f"inline:{inline_query.from_user.id}")

    return router


@pytest.fixture
def env(sessionmaker):
    def _make(allowlist: str = ""):
        bot, session = make_bot()
        calls: list[str] = []
        alerts = AlertService(bot, -100999, "test")
        dp = build_dispatcher(
            settings=settings(allowlist),
            sessionmaker=sessionmaker,
            alerts=alerts,
            routers=[probe_router(calls)],
            clock=lambda: NOW,
        )
        return dp, bot, session, calls

    return _make


async def count(sessionmaker, model) -> int:
    async with sessionmaker() as s:
        return await s.scalar(select(func.count()).select_from(model))


async def test_user_upserted_on_message(env, sessionmaker):
    dp, bot, session, calls = env()
    await dp.feed_update(bot, message_update("/ping", user=tg_user(username="first")))
    await dp.feed_update(bot, message_update("/ping", user=tg_user(username="renamed")))
    assert calls == [f"ping:{tg_user().id}", f"ping:{tg_user().id}"]
    async with sessionmaker() as s:
        user = await s.scalar(select(User))
    assert user.username == "renamed"
    assert user.last_activity_at == NOW
    assert len(session.sent(SendMessage)) == 2


async def test_activity_unblocks_delivery(env, sessionmaker):
    dp, bot, _, _ = env()
    await dp.feed_update(bot, message_update("/ping"))
    async with sessionmaker() as s, s.begin():
        await s.execute(update(User).values(telegram_delivery_state=DeliveryState.BLOCKED))
    await dp.feed_update(bot, message_update("/ping"))
    async with sessionmaker() as s:
        user = await s.scalar(select(User))
    assert user.telegram_delivery_state is DeliveryState.ACTIVE


async def test_duplicate_update_processed_once(env, sessionmaker):
    dp, bot, _, calls = env()
    await dp.feed_update(bot, message_update("/ping", update_id=900))
    await dp.feed_update(bot, message_update("/ping", update_id=900))
    assert len(calls) == 1
    assert await count(sessionmaker, ProcessedUpdate) == 1


async def test_allowlist_blocks_strangers(env, sessionmaker):
    dp, bot, session, calls = env(allowlist="1,2")
    await dp.feed_update(bot, message_update("/ping", user=tg_user(user_id=3)))
    assert calls == []
    assert session.requests == []
    assert await count(sessionmaker, User) == 0


async def test_allowlist_admits_listed(env, sessionmaker):
    dp, bot, _, calls = env(allowlist="3")
    await dp.feed_update(bot, message_update("/ping", user=tg_user(user_id=3)))
    assert calls == ["ping:3"]


async def test_group_chats_ignored(env, sessionmaker):
    dp, bot, _, calls = env()
    await dp.feed_update(bot, group_message_update("/ping"))
    assert calls == []
    assert await count(sessionmaker, User) == 0


async def test_chatless_update_blocked_without_allowlist(env, sessionmaker):
    dp, bot, _, calls = env()
    await dp.feed_update(bot, inline_query_update())
    assert calls == []
    assert await count(sessionmaker, User) == 0


async def test_chatless_update_blocked_with_allowlist(env, sessionmaker):
    dp, bot, _, calls = env(allowlist="5001")
    await dp.feed_update(bot, inline_query_update(user=tg_user(user_id=5001)))
    assert calls == []
    assert await count(sessionmaker, User) == 0


async def test_my_chat_member_is_not_activity(env, sessionmaker):
    dp, bot, _, _ = env()
    await dp.feed_update(bot, message_update("/ping"))
    async with sessionmaker() as s, s.begin():
        await s.execute(update(User).values(telegram_delivery_state=DeliveryState.BLOCKED))
    await dp.feed_update(bot, my_chat_member_update("kicked"))
    async with sessionmaker() as s:
        user = await s.scalar(select(User))
    assert user.telegram_delivery_state is DeliveryState.BLOCKED


async def test_handler_error_rolls_back_and_alerts(env, sessionmaker):
    dp, bot, session, calls = env()
    await dp.feed_update(bot, message_update("/boom", update_id=950))
    assert calls == ["boom"]
    assert await count(sessionmaker, ProcessedUpdate) == 0
    assert await count(sessionmaker, User) == 0
    [alert] = session.sent(SendMessage)
    assert alert.chat_id == -100999
    assert "RuntimeError" in alert.text
    assert "950" in alert.text
