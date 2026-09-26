from enum import StrEnum


class DraftMode(StrEnum):
    CREATE = "create"
    EDIT = "edit"


class Step(StrEnum):
    ROOMS = "rooms"
    CONDITION = "condition"
    PRICE = "price"
    SUMMARY = "summary"
    EDIT_MENU = "edit_menu"


FILTER_STEPS: tuple[Step, ...] = (Step.ROOMS, Step.CONDITION, Step.PRICE)
