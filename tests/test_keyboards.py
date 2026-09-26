from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup

from pokazun.bot import texts
from pokazun.bot.keyboards import (
    EMPTY_PRICE,
    PriceCb,
    RoomsCb,
    StepAction,
    StepCb,
    main_menu,
    price_keyboard,
    rooms_keyboard,
)
from pokazun.bot.screens import draft_screen, results_screen
from pokazun.search.filters import ConditionGroup, PriceRange, RoomOption
from pokazun.search.service import DraftView
from pokazun.search.steps import DraftMode, Step


def inline(markup: InlineKeyboardMarkup) -> list[tuple[str, str]]:
    return [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row]


def reply(markup: ReplyKeyboardMarkup) -> list[list[str]]:
    return [[b.text for b in row] for row in markup.keyboard]


def test_main_menu_variants():
    assert reply(main_menu(False)) == [[texts.BTN_FIND], [texts.BTN_SELL, texts.BTN_HELP]]
    assert reply(main_menu(True)) == [
        [texts.BTN_MY_SEARCH, texts.BTN_SAVED],
        [texts.BTN_SELL, texts.BTN_HELP],
    ]
    assert main_menu(True).resize_keyboard is True


def test_rooms_keyboard_marks_and_next():
    empty = inline(rooms_keyboard(frozenset()))
    assert [t for t, _ in empty] == [
        "👉 1 кімната",
        "👉 2 кімнати",
        "👉 3 кімнати",
        "👉 4+ кімнати",
    ]
    assert empty[1][1] == RoomsCb(value=2, on=True).pack()

    chosen = inline(rooms_keyboard(frozenset({RoomOption.TWO})))
    assert chosen[1] == ("✅ 2 кімнати", RoomsCb(value=2, on=False).pack())
    assert chosen[-1] == (texts.BTN_NEXT, StepCb(action=StepAction.NEXT).pack())


def test_price_keyboard_encodes_target_ranges():
    buttons = inline(price_keyboard(PriceRange(2, 4)))
    by_text = dict(buttons)
    assert by_text["✅ 21–30 тис. $"] == PriceCb(low=3, high=4).pack()  # edge narrows
    assert by_text["✅ 31–40 тис. $"] == PriceCb(low=2, high=4).pack()  # interior unchanged
    assert by_text["👉 71–100 тис. $"] == PriceCb(low=2, high=6).pack()  # extends
    assert by_text[texts.BTN_RESET_PRICE] == StepCb(action=StepAction.RESET_PRICE).pack()
    assert texts.BTN_NEXT in by_text

    single = dict(inline(price_keyboard(PriceRange(5, 5))))
    assert single["✅ 56–70 тис. $"] == PriceCb(low=EMPTY_PRICE, high=EMPTY_PRICE).pack()

    none = inline(price_keyboard(None))
    assert len(none) == 8
    assert texts.BTN_RESET_PRICE not in dict(none)


def test_callback_data_fits_telegram_limit():
    for markup in (rooms_keyboard(frozenset(RoomOption)), price_keyboard(PriceRange(0, 7))):
        for _, data in inline(markup):
            assert len(data.encode()) <= 64


def view(step, *, mode=DraftMode.CREATE, rooms=(), conditions=(), price=None):
    return DraftView(
        mode, step, frozenset(rooms), frozenset(conditions), price, reached_summary=False
    )


def test_draft_screens():
    text, _ = draft_screen(view(Step.ROOMS))
    assert text == texts.ROOMS_PROMPT
    text, _ = draft_screen(view(Step.CONDITION))
    assert text == texts.CONDITION_PROMPT
    text, _ = draft_screen(view(Step.PRICE))
    assert text == texts.PRICE_PROMPT
    full = dict(
        rooms={RoomOption.ONE}, conditions={ConditionGroup.DEVELOPER}, price=PriceRange(0, 0)
    )
    text, markup = draft_screen(view(Step.SUMMARY, **full))
    assert text.startswith("Ваш запит:")
    assert [t for t, _ in inline(markup)] == [texts.BTN_START_SEARCH, texts.BTN_EDIT_SEARCH]
    text, markup = draft_screen(view(Step.EDIT_MENU, **full))
    assert text.startswith("Ваші параметри пошуку:")
    assert [t for t, _ in inline(markup)] == [
        texts.BTN_EDIT_ROOMS,
        texts.BTN_EDIT_CONDITION,
        texts.BTN_EDIT_PRICE,
        texts.BTN_SAVE,
        texts.BTN_BACK,
    ]


def test_results_screens():
    text, markup = results_screen(3)
    assert text.startswith("Знайшли 3 квартири")
    assert inline(markup) == [
        (texts.BTN_VIEW_RESULTS, StepCb(action=StepAction.VIEW_RESULTS).pack())
    ]
    text, markup = results_screen(0)
    assert text == texts.NOT_FOUND
    assert inline(markup) == [(texts.BTN_EDIT_SEARCH, StepCb(action=StepAction.EDIT).pack())]
