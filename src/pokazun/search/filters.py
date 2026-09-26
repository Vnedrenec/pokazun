"""Search filters shared by the bot, SQL matching and catalog events. Mapping per Д2 §5."""

from dataclasses import dataclass
from enum import IntEnum, StrEnum


class RoomOption(IntEnum):
    ONE = 1
    TWO = 2
    THREE = 3
    FOUR_PLUS = 4

    def matches(self, rooms: int) -> bool:
        return rooms >= 4 if self is RoomOption.FOUR_PLUS else rooms == self.value


class ConditionGroup(StrEnum):
    RESIDENTIAL = "residential"
    DEVELOPER = "developer"


CONDITION_GROUP_VALUES: dict[ConditionGroup, frozenset[str]] = {
    ConditionGroup.RESIDENTIAL: frozenset(
        {"Житловий стан", "Косметичний ремонт", "Євроремонт", "Авторський проект", "Аварійний стан"}
    ),
    ConditionGroup.DEVELOPER: frozenset({"Після будівельників", "Під чистову обробку"}),
}
KNOWN_CONDITIONS: frozenset[str] = frozenset().union(*CONDITION_GROUP_VALUES.values())


@dataclass(frozen=True)
class PriceSegment:
    index: int
    airtable_value: str
    label: str
    low_k: int | None  # thousands of USD, inclusive; None = open lower bound
    high_k: int | None  # None = open upper bound


PRICE_SEGMENTS: tuple[PriceSegment, ...] = (
    PriceSegment(0, "до 15 тис", "До 15 тис. $", None, 15),
    PriceSegment(1, "16-20 тис.", "16–20 тис. $", 16, 20),
    PriceSegment(2, "21 - 30 тис.", "21–30 тис. $", 21, 30),
    PriceSegment(3, "31 - 40 тис.", "31–40 тис. $", 31, 40),
    PriceSegment(4, "41 - 55 тис.", "41–55 тис. $", 41, 55),
    PriceSegment(5, "56 - 70 тис.", "56–70 тис. $", 56, 70),
    PriceSegment(6, "71 - 100 тис.", "71–100 тис. $", 71, 100),
    PriceSegment(7, "101 тис і вище", "101 тис. $ і вище", 101, None),
)
SEGMENT_INDEX_BY_AIRTABLE: dict[str, int] = {s.airtable_value: s.index for s in PRICE_SEGMENTS}


@dataclass(frozen=True)
class PriceRange:
    """Always contiguous: every segment between low and high (segment indexes) is included."""

    low: int
    high: int

    def __post_init__(self) -> None:
        if not 0 <= self.low <= self.high < len(PRICE_SEGMENTS):
            raise ValueError(f"invalid price range {self.low}..{self.high}")

    def contains(self, index: int) -> bool:
        return self.low <= index <= self.high

    @property
    def segments(self) -> tuple[PriceSegment, ...]:
        return PRICE_SEGMENTS[self.low : self.high + 1]


def click_price(current: PriceRange | None, index: int) -> PriceRange | None:
    """Unselected segment extends the range; an edge narrows it; interior changes nothing."""
    if not 0 <= index < len(PRICE_SEGMENTS):
        raise ValueError(f"invalid price segment {index}")
    if current is None:
        return PriceRange(index, index)
    if not current.contains(index):
        return PriceRange(min(current.low, index), max(current.high, index))
    if current.low == current.high:
        return None
    if index == current.low:
        return PriceRange(current.low + 1, current.high)
    if index == current.high:
        return PriceRange(current.low, current.high - 1)
    return current


@dataclass(frozen=True)
class SearchCriteria:
    rooms: frozenset[RoomOption]
    conditions: frozenset[ConditionGroup]
    price: PriceRange

    def __post_init__(self) -> None:
        if not self.rooms:
            raise ValueError("rooms must not be empty")
        if not self.conditions:
            raise ValueError("conditions must not be empty")

    @property
    def condition_values(self) -> frozenset[str]:
        return frozenset().union(*(CONDITION_GROUP_VALUES[g] for g in self.conditions))

    def matches(
        self, *, rooms: int | None, condition: str | None, price_segment: int | None
    ) -> bool:
        return (
            rooms is not None
            and any(option.matches(rooms) for option in self.rooms)
            and condition in self.condition_values
            and price_segment is not None
            and self.price.contains(price_segment)
        )
