"""Lowest-priority handlers: anything no other router took. Must stay last in build_routers()."""

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from pokazun.bot import keyboards as kb
from pokazun.bot import texts
from pokazun.db.models import User
from pokazun.search.service import get_active_search


async def on_unknown_text(message: Message, session: AsyncSession, db_user: User) -> None:
    has_search = await get_active_search(session, db_user.id) is not None
    await message.answer(texts.MENU_HINT, reply_markup=kb.main_menu(has_search))


async def on_unknown_callback(callback: CallbackQuery) -> None:
    await callback.answer()


def build_router() -> Router:
    router = Router(name="fallback")
    router.message.register(on_unknown_text, F.text)
    router.callback_query.register(on_unknown_callback)
    return router
