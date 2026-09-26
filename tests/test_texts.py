import pytest

from pokazun.bot import texts
from pokazun.search.filters import ConditionGroup, PriceRange, RoomOption, SearchCriteria

D1_CRITERIA = SearchCriteria(
    frozenset({RoomOption.THREE, RoomOption.TWO}),
    frozenset({ConditionGroup.RESIDENTIAL}),
    PriceRange(2, 4),
)


@pytest.mark.parametrize(
    ("price", "label"),
    [
        (PriceRange(2, 4), "21–55 тис. $"),
        (PriceRange(3, 3), "31–40 тис. $"),
        (PriceRange(0, 0), "До 15 тис. $"),
        (PriceRange(0, 2), "До 30 тис. $"),
        (PriceRange(5, 7), "56 тис. $ і вище"),
        (PriceRange(7, 7), "101 тис. $ і вище"),
        (PriceRange(0, 7), "Будь-яка вартість"),
    ],
)
def test_price_label(price, label):
    assert texts.price_label(price) == label


@pytest.mark.parametrize(
    ("n", "word"),
    [
        (1, "квартиру"),
        (2, "квартири"),
        (4, "квартири"),
        (5, "квартир"),
        (11, "квартир"),
        (12, "квартир"),
        (21, "квартиру"),
        (22, "квартири"),
        (47, "квартир"),
        (111, "квартир"),
    ],
)
def test_plural(n, word):
    assert texts.plural_uk(n, "квартиру", "квартири", "квартир") == word


def test_summary_matches_spec_example():
    assert texts.summary_text(D1_CRITERIA) == (
        "Ваш запит:\n\n"
        "👉 Кількість кімнат: 2 кімнати, 3 кімнати\n"
        "👉 Стан квартири: Житловий стан\n"
        "👉 Вартість: 21–55 тис. $\n\n"
        "Перевірте, чи все правильно. Якщо потрібно — змініть параметри пошуку."
    )


def test_edit_menu_matches_spec_example():
    assert texts.edit_menu_text(D1_CRITERIA) == (
        "Ваші параметри пошуку:\n\n"
        "🛏 Кількість кімнат: 2, 3\n"
        "🏠 Стан квартири: Житловий стан\n"
        "💰 Вартість: 21–55 тис. $\n\n"
        "Оберіть параметр, який хочете змінити."
    )


def test_labels_order_is_stable():
    assert texts.rooms_short(frozenset(RoomOption)) == "1, 2, 3, 4+"
    assert texts.conditions_label(frozenset(ConditionGroup)) == "Житловий стан, Після забудовника"


def test_found_text():
    assert texts.found_text(47).startswith("Знайшли 47 квартир за вашим запитом 🏠\n\n")
    assert texts.found_text(1).startswith("Знайшли 1 квартиру ")
