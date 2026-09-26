"""Offline Telegram: records every Bot API call and fabricates minimal successful responses."""

import itertools
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import TelegramMethod
from aiogram.types import (
    CallbackQuery,
    Chat,
    ChatMemberBanned,
    ChatMemberMember,
    ChatMemberUpdated,
    Message,
    Update,
    User,
)

BOT_ID = 42
TG_USER_ID = 5001
_update_ids = itertools.count(1)
_message_ids = itertools.count(1)


class FakeSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list[TelegramMethod[Any]] = []
        self.fail_with: dict[type, Exception] = {}
        self._next_message_id = 10_000

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[Any],
        timeout: int | None = None,  # noqa: ASYNC109 — name imposed by aiogram BaseSession
    ):
        self.requests.append(method)
        exc = self.fail_with.get(type(method))
        if exc is not None:
            raise exc
        returning = method.__returning__
        if returning is Message:
            self._next_message_id += 1
            chat_id = int(getattr(method, "chat_id", 0) or 0)
            return Message(
                message_id=self._next_message_id,
                date=datetime.now(UTC),
                chat=Chat(id=chat_id, type="private"),
                text=getattr(method, "text", None),
            )
        if returning is User:
            return User(id=BOT_ID, is_bot=True, first_name="Pokazun", username="pokazun_test_bot")
        return True

    async def close(self) -> None:
        return None

    async def stream_content(
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: int = 30,  # noqa: ASYNC109 — parameter name imposed by aiogram BaseSession
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes, None]:
        raise NotImplementedError("FakeSession does not download files")
        yield b""  # pragma: no cover

    def sent(self, method_type: type) -> list[Any]:
        return [r for r in self.requests if isinstance(r, method_type)]


def make_bot() -> tuple[Bot, FakeSession]:
    session = FakeSession()
    return Bot(token=f"{BOT_ID}:TEST", session=session), session


def tg_user(
    user_id: int = TG_USER_ID, username: str | None = "buyer", first_name: str = "Оксана"
) -> User:
    return User(id=user_id, is_bot=False, first_name=first_name, username=username)


def _bot_user() -> User:
    return User(id=BOT_ID, is_bot=True, first_name="Pokazun")


def message_update(text: str, *, user: User | None = None, update_id: int | None = None) -> Update:
    user = user or tg_user()
    return Update(
        update_id=update_id if update_id is not None else next(_update_ids),
        message=Message(
            message_id=next(_message_ids),
            date=datetime.now(UTC),
            chat=Chat(id=user.id, type="private"),
            from_user=user,
            text=text,
        ),
    )


def group_message_update(text: str, *, user: User | None = None) -> Update:
    user = user or tg_user()
    return Update(
        update_id=next(_update_ids),
        message=Message(
            message_id=next(_message_ids),
            date=datetime.now(UTC),
            chat=Chat(id=-100500, type="supergroup", title="group"),
            from_user=user,
            text=text,
        ),
    )


def callback_update(
    data: str,
    *,
    user: User | None = None,
    message_id: int = 777,
    update_id: int | None = None,
) -> Update:
    user = user or tg_user()
    return Update(
        update_id=update_id if update_id is not None else next(_update_ids),
        callback_query=CallbackQuery(
            id=f"cb{next(_update_ids)}",
            from_user=user,
            chat_instance="ci",
            data=data,
            message=Message(
                message_id=message_id,
                date=datetime.now(UTC),
                chat=Chat(id=user.id, type="private"),
                from_user=_bot_user(),
                text="…",
            ),
        ),
    )


def my_chat_member_update(status: str, *, user: User | None = None) -> Update:
    user = user or tg_user()
    old = ChatMemberMember(user=_bot_user())
    new = ChatMemberBanned(user=_bot_user(), until_date=0) if status == "kicked" else old
    return Update(
        update_id=next(_update_ids),
        my_chat_member=ChatMemberUpdated(
            chat=Chat(id=user.id, type="private"),
            from_user=user,
            date=datetime.now(UTC),
            old_chat_member=old,
            new_chat_member=new,
        ),
    )
