from aiogram.types import InlineKeyboardMarkup

from pokazun.bot import keyboards as kb
from pokazun.bot import texts
from pokazun.search.service import DraftView
from pokazun.search.steps import Step


def draft_screen(v: DraftView) -> tuple[str, InlineKeyboardMarkup]:
    if v.step is Step.ROOMS:
        return texts.ROOMS_PROMPT, kb.rooms_keyboard(v.rooms)
    if v.step is Step.CONDITION:
        return texts.CONDITION_PROMPT, kb.conditions_keyboard(v.conditions)
    if v.step is Step.PRICE:
        return texts.PRICE_PROMPT, kb.price_keyboard(v.price)
    criteria = v.criteria
    if criteria is None:
        raise RuntimeError(f"draft at step {v.step} must be complete")
    if v.step is Step.SUMMARY:
        return texts.summary_text(criteria), kb.summary_keyboard()
    return texts.edit_menu_text(criteria), kb.edit_menu_keyboard()


def results_screen(count: int) -> tuple[str, InlineKeyboardMarkup]:
    if count == 0:
        return texts.NOT_FOUND, kb.not_found_keyboard()
    return texts.found_text(count), kb.found_keyboard()
