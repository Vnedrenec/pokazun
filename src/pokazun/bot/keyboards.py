"""Keyboards and callback data.

Callback data carries the target state, so repeated clicks are idempotent.
"""

from enum import StrEnum

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from pokazun.bot import texts
from pokazun.search.filters import (
    PRICE_SEGMENTS,
    ConditionGroup,
    PriceRange,
    RoomOption,
    click_price,
)

EMPTY_PRICE = -1


class StepAction(StrEnum):
    NEXT = "next"
    RESET_PRICE = "reset_price"
    EDIT = "edit"
    GOTO_ROOMS = "goto_rooms"
    GOTO_CONDITION = "goto_condition"
    GOTO_PRICE = "goto_price"
    SAVE = "save"
    BACK = "back"
    START_SEARCH = "start_search"
    VIEW_RESULTS = "view_results"


class RoomsCb(CallbackData, prefix="rm"):
    value: int
    on: bool


class ConditionCb(CallbackData, prefix="cd"):
    value: str
    on: bool


class PriceCb(CallbackData, prefix="pr"):
    low: int
    high: int


class StepCb(CallbackData, prefix="st"):
    action: StepAction


def _button(text: str, data: CallbackData) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data.pack())


def _step(text: str, action: StepAction) -> list[InlineKeyboardButton]:
    return [_button(text, StepCb(action=action))]


def _mark(selected: bool) -> str:
    return texts.MARK_ON if selected else texts.MARK_OFF


def main_menu(has_search: bool) -> ReplyKeyboardMarkup:
    first_row = [texts.BTN_MY_SEARCH, texts.BTN_SAVED] if has_search else [texts.BTN_FIND]
    rows = [first_row, [texts.BTN_SELL, texts.BTN_HELP]]
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t) for t in row] for row in rows],
        resize_keyboard=True,
        is_persistent=True,
    )


def rooms_keyboard(selected: frozenset[RoomOption]) -> InlineKeyboardMarkup:
    rows = [
        [
            _button(
                f"{_mark(option in selected)} {texts.ROOM_LABELS[option]}",
                RoomsCb(value=option.value, on=option not in selected),
            )
        ]
        for option in RoomOption
    ]
    if selected:
        rows.append(_step(texts.BTN_NEXT, StepAction.NEXT))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def conditions_keyboard(selected: frozenset[ConditionGroup]) -> InlineKeyboardMarkup:
    rows = [
        [
            _button(
                f"{_mark(group in selected)} {texts.CONDITION_LABELS[group]}",
                ConditionCb(value=group.value, on=group not in selected),
            )
        ]
        for group in ConditionGroup
    ]
    if selected:
        rows.append(_step(texts.BTN_NEXT, StepAction.NEXT))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def price_keyboard(price: PriceRange | None) -> InlineKeyboardMarkup:
    buttons = []
    for segment in PRICE_SEGMENTS:
        target = click_price(price, segment.index)
        data = (
            PriceCb(low=target.low, high=target.high)
            if target is not None
            else PriceCb(low=EMPTY_PRICE, high=EMPTY_PRICE)
        )
        selected = price is not None and price.contains(segment.index)
        buttons.append(_button(f"{_mark(selected)} {segment.label}", data))
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    if price is not None:
        rows.append(_step(texts.BTN_RESET_PRICE, StepAction.RESET_PRICE))
        rows.append(_step(texts.BTN_NEXT, StepAction.NEXT))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def summary_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            _step(texts.BTN_START_SEARCH, StepAction.START_SEARCH),
            _step(texts.BTN_EDIT_SEARCH, StepAction.EDIT),
        ]
    )


def edit_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            _step(texts.BTN_EDIT_ROOMS, StepAction.GOTO_ROOMS),
            _step(texts.BTN_EDIT_CONDITION, StepAction.GOTO_CONDITION),
            _step(texts.BTN_EDIT_PRICE, StepAction.GOTO_PRICE),
            _step(texts.BTN_SAVE, StepAction.SAVE),
            _step(texts.BTN_BACK, StepAction.BACK),
        ]
    )


def found_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[_step(texts.BTN_VIEW_RESULTS, StepAction.VIEW_RESULTS)]
    )


def not_found_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[_step(texts.BTN_EDIT_SEARCH, StepAction.EDIT)])
