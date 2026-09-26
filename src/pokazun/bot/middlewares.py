"""Update-level middlewares.

Order (outermost first): LogContext → DbSession → Access → Idempotency → Activity.
"""

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

import structlog
from aiogram import BaseMiddleware
from aiogram.enums import ChatType
from aiogram.types import Chat, TelegramObject, Update
from aiogram.types import User as TgUser
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pokazun.db.models import ProcessedUpdate
from pokazun.log import get_logger
from pokazun.users.repository import touch_user

log = get_logger(__name__)

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class LogContextMiddleware(BaseMiddleware):
    async def __call__(self, handler: Handler, event: Update, data: dict[str, Any]) -> Any:
        with structlog.contextvars.bound_contextvars(update_id=event.update_id):
            return await handler(event, data)


class DbSessionMiddleware(BaseMiddleware):
    """One transaction per update: committed after the handler, rolled back if it raises."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def __call__(self, handler: Handler, event: Update, data: dict[str, Any]) -> Any:
        async with self._sessionmaker() as session, session.begin():
            data["session"] = session
            return await handler(event, data)


class AccessMiddleware(BaseMiddleware):
    """Private chats with real users only; on staging, only allowlisted Telegram user_ids."""

    def __init__(self, allowlist: frozenset[int]) -> None:
        self._allowlist = allowlist

    async def __call__(self, handler: Handler, event: Update, data: dict[str, Any]) -> Any:
        user: TgUser | None = data.get("event_from_user")
        chat: Chat | None = data.get("event_chat")
        if user is None or user.is_bot:
            return None
        if chat is not None and chat.type != ChatType.PRIVATE:
            return None
        if self._allowlist and user.id not in self._allowlist:
            log.info("user_not_in_allowlist", telegram_user_id=user.id)
            return None
        return await handler(event, data)


class IdempotencyMiddleware(BaseMiddleware):
    """Skips an update_id that was already committed.

    The marker shares the handler's transaction.
    """

    async def __call__(self, handler: Handler, event: Update, data: dict[str, Any]) -> Any:
        session: AsyncSession = data["session"]
        inserted = await session.scalar(
            insert(ProcessedUpdate)
            .values(update_id=event.update_id)
            .on_conflict_do_nothing()
            .returning(ProcessedUpdate.update_id)
        )
        if inserted is None:
            log.info("duplicate_update_skipped")
            return None
        return await handler(event, data)


class ActivityMiddleware(BaseMiddleware):
    """A message or a button press is user activity (90-day timer, delivery unblock).

    Service updates are not.
    """

    def __init__(self, clock: Callable[[], datetime]) -> None:
        self._clock = clock

    async def __call__(self, handler: Handler, event: Update, data: dict[str, Any]) -> Any:
        if event.message or event.edited_message or event.callback_query:
            tg_user: TgUser = data["event_from_user"]
            user = await touch_user(
                data["session"],
                telegram_user_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
                now=self._clock(),
            )
            data["db_user"] = user
            structlog.contextvars.bind_contextvars(user_id=user.id)
        return await handler(event, data)
