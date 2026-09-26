import pytest

from pokazun.search.filters import (
    CONDITION_GROUP_VALUES,
    PRICE_SEGMENTS,
    SEGMENT_INDEX_BY_AIRTABLE,
    ConditionGroup,
    PriceRange,
    RoomOption,
    SearchCriteria,
    click_price,
)


def test_rooms_mapping():
    assert RoomOption.ONE.matches(1) and not RoomOption.ONE.matches(2)
    assert RoomOption.THREE.matches(3)
    assert all(RoomOption.FOUR_PLUS.matches(n) for n in (4, 5, 9))
    assert not RoomOption.FOUR_PLUS.matches(3)


def test_condition_groups_match_spec():
    assert CONDITION_GROUP_VALUES[ConditionGroup.RESIDENTIAL] == {
        "Житловий стан",
        "Косметичний ремонт",
        "Євроремонт",
        "Авторський проект",
        "Аварійний стан",
    }
    assert CONDITION_GROUP_VALUES[ConditionGroup.DEVELOPER] == {
        "Після будівельників",
        "Під чистову обробку",
    }


def test_price_segments_match_airtable_values():
    assert [s.airtable_value for s in PRICE_SEGMENTS] == [
        "до 15 тис",
        "16-20 тис.",
        "21 - 30 тис.",
        "31 - 40 тис.",
        "41 - 55 тис.",
        "56 - 70 тис.",
        "71 - 100 тис.",
        "101 тис і вище",
    ]
    assert [s.label for s in PRICE_SEGMENTS] == [
        "До 15 тис. $",
        "16–20 тис. $",
        "21–30 тис. $",
        "31–40 тис. $",
        "41–55 тис. $",
        "56–70 тис. $",
        "71–100 тис. $",
        "101 тис. $ і вище",
    ]
    assert [s.index for s in PRICE_SEGMENTS] == list(range(8))
    assert SEGMENT_INDEX_BY_AIRTABLE["41 - 55 тис."] == 4


def test_price_range_validation():
    with pytest.raises(ValueError):
        PriceRange(3, 2)
    with pytest.raises(ValueError):
        PriceRange(0, 8)


def test_click_fills_gap_like_spec_example():
    # Д1 §3.3: «21–30» + «41–55» → «31–40» включається автоматично
    r = click_price(None, 2)
    assert r == PriceRange(2, 2)
    r = click_price(r, 4)
    assert r == PriceRange(2, 4)
    assert [s.label for s in r.segments] == ["21–30 тис. $", "31–40 тис. $", "41–55 тис. $"]


def test_click_extends_both_directions():
    assert click_price(PriceRange(2, 4), 6) == PriceRange(2, 6)
    assert click_price(PriceRange(2, 4), 0) == PriceRange(0, 4)


def test_click_edges_narrow_interior_keeps():
    assert click_price(PriceRange(2, 4), 2) == PriceRange(3, 4)
    assert click_price(PriceRange(2, 4), 4) == PriceRange(2, 3)
    assert click_price(PriceRange(2, 4), 3) == PriceRange(2, 4)
    assert click_price(PriceRange(5, 5), 5) is None


def test_click_rejects_bad_index():
    with pytest.raises(ValueError):
        click_price(None, 8)


def criteria(rooms, conditions, low, high) -> SearchCriteria:
    return SearchCriteria(frozenset(rooms), frozenset(conditions), PriceRange(low, high))


def test_criteria_matches():
    c = criteria({RoomOption.TWO, RoomOption.FOUR_PLUS}, {ConditionGroup.DEVELOPER}, 2, 4)
    assert c.matches(rooms=2, condition="Під чистову обробку", price_segment=3)
    assert c.matches(rooms=6, condition="Після будівельників", price_segment=4)
    assert not c.matches(rooms=3, condition="Після будівельників", price_segment=3)
    assert not c.matches(rooms=2, condition="Євроремонт", price_segment=3)
    assert not c.matches(rooms=2, condition="Після будівельників", price_segment=5)
    assert not c.matches(rooms=None, condition="Після будівельників", price_segment=3)
    assert not c.matches(rooms=2, condition="Після будівельників", price_segment=None)


def test_criteria_requires_values():
    with pytest.raises(ValueError):
        criteria(set(), {ConditionGroup.DEVELOPER}, 0, 0)
    with pytest.raises(ValueError):
        criteria({RoomOption.ONE}, set(), 0, 0)
