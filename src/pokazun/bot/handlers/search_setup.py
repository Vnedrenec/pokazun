"""Start, menu, the three filters, summary, editing and search confirmation.

(Д1 §2–§5.2, §5.4; Д2 §7, §23).
"""

from collections.abc import Callable
from datetime import datetime
from enum import Enum

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from pokazun.bot import keyboards as kb
from pokazun.bot import texts
from pokazun.bot.keyboards import EMPTY_PRICE, ConditionCb, PriceCb, RoomsCb, StepAction, StepCb
from pokazun.bot.screens import draft_screen, results_screen
from pokazun.catalog.matching import count_matching
from pokazun.db.models import SearchDraft, User
from pokazun.log import get_logger
from pokazun.search.filters import ConditionGroup, PriceRange, RoomOption
from pokazun.search.service import (
    advance,
    close_edit_menu,
    confirm_draft,
    discard_draft,
    get_active_search,
    get_draft,
    open_edit_menu,
    open_filter,
    set_conditions,
    set_price,
    set_rooms,
    start_edit,
    start_or_resume,
    view,
)
from pokazun.search.steps import FILTER_STEPS, DraftMode, Step

log = get_logger(__name__)

_GOTO = {
    StepAction.GOTO_ROOMS: Step.ROOMS,
    StepAction.GOTO_CONDITION: Step.CONDITION,
    StepAction.GOTO_PRICE: Step.PRICE,
}


# --- rendering helpers ---


def _is_not_modified(exc: TelegramBadRequest) -> bool:
    return "message is not modified" in exc.message


async def _show(
    callback: CallbackQuery, bot: Bot, text: str, markup: InlineKeyboardMarkup | None
) -> None:
    """Replace the screen in place; fall back to a new message if the old one cannot be edited."""
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(text, reply_markup=markup)
            return
        except TelegramBadRequest as exc:
            if _is_not_modified(exc):
                return
            log.warning("edit_text_failed", error=exc.message)
    await bot.send_message(callback.from_user.id, text, reply_markup=markup)


async def _show_draft(callback: CallbackQuery, bot: Bot, draft: SearchDraft) -> None:
    text, markup = draft_screen(view(draft))
    await _show(callback, bot, text, markup)


async def _refresh_markup(callback: CallbackQuery, bot: Bot, draft: SearchDraft) -> None:
    text, markup = draft_screen(view(draft))
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_reply_markup(reply_markup=markup)
            return
        except TelegramBadRequest as exc:
            if _is_not_modified(exc):
                return
            log.warning("edit_markup_failed", error=exc.message)
    await bot.send_message(callback.from_user.id, text, reply_markup=markup)


async def _draft_at(
    callback: CallbackQuery, bot: Bot, session: AsyncSession, user: User, step: Step
) -> SearchDraft | None:
    """The locked draft if it is at `step`.

    Otherwise re-renders the real current step (stale keyboard).
    """
    draft = await get_draft(session, user.id, for_update=True)
    if draft is None:
        return None
    if draft.step is not step:
        await _show_draft(callback, bot, draft)
        return None
    return draft


def _enum[E: Enum](cls: type[E], value: object) -> E | None:
    try:
        return cls(value)
    except ValueError:
        return None


# --- messages ---


async def on_start(message: Message, session: AsyncSession, db_user: User) -> None:
    has_search = await get_active_search(session, db_user.id) is not None
    await message.answer(texts.WELCOME, reply_markup=kb.main_menu(has_search))


async def on_find(message: Message, session: AsyncSession, db_user: User) -> None:
    draft = await start_or_resume(session, db_user.id)
    text, markup = draft_screen(view(draft))
    await message.answer(text, reply_markup=markup)


# --- filter toggles ---


async def on_room(
    callback: CallbackQuery, callback_data: RoomsCb, session: AsyncSession, db_user: User, bot: Bot
) -> None:
    try:
        draft = await _draft_at(callback, bot, session, db_user, Step.ROOMS)
        option = _enum(RoomOption, callback_data.value)
        if draft is None or option is None:
            return
        current = view(draft).rooms
        updated = current | {option} if callback_data.on else current - {option}
        if updated != current:
            set_rooms(draft, updated)
            await _refresh_markup(callback, bot, draft)
    finally:
        await callback.answer()


async def on_condition(
    callback: CallbackQuery,
    callback_data: ConditionCb,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
) -> None:
    try:
        draft = await _draft_at(callback, bot, session, db_user, Step.CONDITION)
        group = _enum(ConditionGroup, callback_data.value)
        if draft is None or group is None:
            return
        current = view(draft).conditions
        updated = current | {group} if callback_data.on else current - {group}
        if updated != current:
            set_conditions(draft, updated)
            await _refresh_markup(callback, bot, draft)
    finally:
        await callback.answer()


async def on_price(
    callback: CallbackQuery, callback_data: PriceCb, session: AsyncSession, db_user: User, bot: Bot
) -> None:
    try:
        draft = await _draft_at(callback, bot, session, db_user, Step.PRICE)
        if draft is None:
            return
        if callback_data.low == EMPTY_PRICE and callback_data.high == EMPTY_PRICE:
            target = None
        else:
            try:
                target = PriceRange(callback_data.low, callback_data.high)
            except ValueError:
                return
        if target != view(draft).price:
            set_price(draft, target)
            await _refresh_markup(callback, bot, draft)
    finally:
        await callback.answer()


async def on_reset_price(
    callback: CallbackQuery, session: AsyncSession, db_user: User, bot: Bot
) -> None:
    try:
        draft = await _draft_at(callback, bot, session, db_user, Step.PRICE)
        if draft is not None and view(draft).price is not None:
            set_price(draft, None)
            await _refresh_markup(callback, bot, draft)
    finally:
        await callback.answer()


# --- navigation ---


async def on_next(callback: CallbackQuery, session: AsyncSession, db_user: User, bot: Bot) -> None:
    try:
        draft = await get_draft(session, db_user.id, for_update=True)
        if draft is None:
            return
        if draft.step not in FILTER_STEPS:
            await _show_draft(callback, bot, draft)
        elif advance(draft):
            await _show_draft(callback, bot, draft)
        else:
            await _refresh_markup(callback, bot, draft)
    finally:
        await callback.answer()


async def on_edit(callback: CallbackQuery, session: AsyncSession, db_user: User, bot: Bot) -> None:
    try:
        draft = await get_draft(session, db_user.id, for_update=True)
        if draft is None:
            if await get_active_search(session, db_user.id) is None:
                return
            draft = await start_edit(session, db_user.id)
        else:
            open_edit_menu(draft)
        await _show_draft(callback, bot, draft)
    finally:
        await callback.answer()


async def on_goto(
    callback: CallbackQuery, callback_data: StepCb, session: AsyncSession, db_user: User, bot: Bot
) -> None:
    try:
        draft = await get_draft(session, db_user.id, for_update=True)
        if draft is None:
            return
        open_filter(draft, _GOTO[callback_data.action])
        await _show_draft(callback, bot, draft)
    finally:
        await callback.answer()


async def on_save(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
    clock: Callable[[], datetime],
) -> None:
    try:
        draft = await get_draft(session, db_user.id, for_update=True)
        if draft is None:
            return
        if draft.step is Step.EDIT_MENU and draft.mode is DraftMode.EDIT:
            await _confirm_and_count(callback, bot, session, db_user, clock())
            return
        close_edit_menu(draft)
        await _show_draft(callback, bot, draft)
    finally:
        await callback.answer()


async def on_back(callback: CallbackQuery, session: AsyncSession, db_user: User, bot: Bot) -> None:
    try:
        draft = await get_draft(session, db_user.id, for_update=True)
        if draft is None:
            return
        if draft.step is Step.EDIT_MENU and draft.mode is DraftMode.EDIT:
            await discard_draft(session, draft)
            await _show(callback, bot, texts.EDIT_CANCELLED, None)
            return
        close_edit_menu(draft)
        await _show_draft(callback, bot, draft)
    finally:
        await callback.answer()


async def on_start_search(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
    clock: Callable[[], datetime],
) -> None:
    try:
        draft = await get_draft(session, db_user.id, for_update=True)
        if draft is None:
            return  # already confirmed: a repeated click does nothing
        if draft.step is Step.SUMMARY and draft.mode is DraftMode.CREATE:
            await _confirm_and_count(callback, bot, session, db_user, clock())
        else:
            await _show_draft(callback, bot, draft)
    finally:
        await callback.answer()


async def _confirm_and_count(
    callback: CallbackQuery, bot: Bot, session: AsyncSession, user: User, now: datetime
) -> None:
    result = await confirm_draft(session, user, now)
    if result is None:
        return
    chat_id = callback.from_user.id
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except TelegramBadRequest as exc:
            log.warning("remove_markup_failed", error=exc.message)
    await bot.send_message(chat_id, texts.SEARCHING, reply_markup=kb.main_menu(has_search=True))
    await bot.send_chat_action(chat_id, ChatAction.TYPING)
    count = await count_matching(session, result.search.criteria)
    log.info("search_confirmed", created=result.created, matches=count)
    text, markup = results_screen(count)
    await bot.send_message(chat_id, text, reply_markup=markup)


def build_router() -> Router:
    router = Router(name="search_setup")
    router.message.register(on_start, CommandStart())
    router.message.register(on_find, F.text == texts.BTN_FIND)
    router.callback_query.register(on_room, RoomsCb.filter())
    router.callback_query.register(on_condition, ConditionCb.filter())
    router.callback_query.register(on_price, PriceCb.filter())
    router.callback_query.register(
        on_reset_price, StepCb.filter(F.action == StepAction.RESET_PRICE)
    )
    router.callback_query.register(on_next, StepCb.filter(F.action == StepAction.NEXT))
    router.callback_query.register(on_edit, StepCb.filter(F.action == StepAction.EDIT))
    router.callback_query.register(on_goto, StepCb.filter(F.action.in_(set(_GOTO))))
    router.callback_query.register(on_save, StepCb.filter(F.action == StepAction.SAVE))
    router.callback_query.register(on_back, StepCb.filter(F.action == StepAction.BACK))
    router.callback_query.register(
        on_start_search, StepCb.filter(F.action == StepAction.START_SEARCH)
    )
    return router
