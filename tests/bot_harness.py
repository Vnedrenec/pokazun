from datetime import datetime
from typing import Any

from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from aiogram.types import User as TgUser
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pokazun.alerts import AlertService
from pokazun.bot.factory import build_dispatcher
from pokazun.bot.handlers import build_routers
from pokazun.config import Settings
from pokazun.db.models import ObjectState, Search
from pokazun.users.repository import touch_user
from tests.tg import callback_update, make_bot, message_update

DEV_SETTINGS = {
    "env": "dev",
    "bot_token": "42:TEST",
    "database_url": "postgresql+asyncpg://unused",
    "telegram_mode": "polling",
}


class Harness:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], now: datetime) -> None:
        self.bot, self.tg = make_bot()
        self.now = now
        self.dp = build_dispatcher(
            settings=Settings(**DEV_SETTINGS),
            sessionmaker=sessionmaker,
            alerts=AlertService(None, None, "dev"),
            routers=build_routers(),
            clock=lambda: self.now,
        )

    async def feed(self, update: Update) -> list[Any]:
        start = len(self.tg.requests)
        await self.dp.feed_update(self.bot, update)
        return self.tg.requests[start:]

    async def send(self, text: str, *, user: TgUser | None = None) -> list[Any]:
        return await self.feed(message_update(text, user=user))

    async def click(
        self, data: str, *, user: TgUser | None = None, message_id: int = 777
    ) -> list[Any]:
        return await self.feed(callback_update(data, user=user, message_id=message_id))


def of_type(requests: list[Any], method_type: type) -> list[Any]:
    return [r for r in requests if isinstance(r, method_type)]


def inline(markup: InlineKeyboardMarkup | None) -> list[tuple[str, str]]:
    if markup is None:
        return []
    return [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row]


def reply(markup: ReplyKeyboardMarkup) -> list[str]:
    return [b.text for row in markup.keyboard for b in row]


async def seed_search(
    sessionmaker: async_sessionmaker[AsyncSession],
    telegram_user_id: int,
    *,
    rooms: list[int],
    conditions: list[str],
    low: int,
    high: int,
    now: datetime,
) -> int:
    async with sessionmaker() as s, s.begin():
        user = await touch_user(
            s, telegram_user_id=telegram_user_id, username=None, first_name=None, now=now
        )
        s.add(
            Search(
                user_id=user.id,
                rooms=rooms,
                conditions=conditions,
                price_low=low,
                price_high=high,
                baseline_at=now,
                confirmed_at=now,
            )
        )
        return user.id


async def seed_objects(
    sessionmaker: async_sessionmaker[AsyncSession], rows: list[dict[str, Any]]
) -> None:
    defaults = {"eligible": True, "public": {}}
    async with sessionmaker() as s, s.begin():
        await s.execute(
            insert(ObjectState),
            [
                {**defaults, "airtable_record_id": f"rec{i}", "object_code": i, **row}
                for i, row in enumerate(rows, 1)
            ],
        )
