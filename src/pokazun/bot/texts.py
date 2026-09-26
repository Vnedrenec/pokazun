"""Every user-facing bot text (Ukrainian only). Source: Д1 verbatim.

Lines marked NEW await client approval.
"""

from pokazun.search.filters import (
    PRICE_SEGMENTS,
    ConditionGroup,
    PriceRange,
    RoomOption,
    SearchCriteria,
)

# --- start and menu (Д1 §2) ---
WELCOME = (
    "Вітаємо! Це бот пошуку квартир у Чернігові від “Практик Нерухомість”. "
    "Тут ви можете знайти квартиру для купівлі або зв’язатися з нами, якщо хочете продати свою."
)
MENU_HINT = "Скористайтеся кнопками меню нижче 👇"  # NEW
BTN_FIND = "🔎 Знайти квартиру"
BTN_SELL = "🏠 Продати квартиру"
BTN_MY_SEARCH = "Мій пошук"
BTN_SAVED = "Збережені ❤️"
BTN_HELP = "Допомога"  # NEW wording of «допомога / зв’язок з агентством»

# --- filters (Д1 §3) ---
MARK_OFF = "👉"
MARK_ON = "✅"
BTN_NEXT = "Далі ➡️"
BTN_RESET_PRICE = "Обнулити вибір 🔄"
ROOMS_PROMPT = "Оберіть, скільки кімнат ви шукаєте. Можна вибрати кілька варіантів."
CONDITION_PROMPT = "Який стан квартири вас цікавить? Оберіть один або кілька варіантів."
PRICE_PROMPT = "На яку вартість квартири ви розраховуєте? Оберіть один або кілька діапазонів."
ROOM_LABELS: dict[RoomOption, str] = {
    RoomOption.ONE: "1 кімната",
    RoomOption.TWO: "2 кімнати",
    RoomOption.THREE: "3 кімнати",
    RoomOption.FOUR_PLUS: "4+ кімнати",
}
ROOM_SHORT: dict[RoomOption, str] = {
    RoomOption.ONE: "1",
    RoomOption.TWO: "2",
    RoomOption.THREE: "3",
    RoomOption.FOUR_PLUS: "4+",
}
CONDITION_LABELS: dict[ConditionGroup, str] = {
    ConditionGroup.RESIDENTIAL: "Житловий стан",
    ConditionGroup.DEVELOPER: "Після забудовника",
}
PRICE_ANY = "Будь-яка вартість"  # NEW

# --- summary and edit (Д1 §4, §4.1) ---
SUMMARY = (
    "Ваш запит:\n\n"
    "👉 Кількість кімнат: {rooms}\n"
    "👉 Стан квартири: {conditions}\n"
    "👉 Вартість: {price}\n\n"
    "Перевірте, чи все правильно. Якщо потрібно — змініть параметри пошуку."
)
BTN_START_SEARCH = "🔎 Почати пошук"
BTN_EDIT_SEARCH = "✏️ Змінити параметри пошуку"
EDIT_MENU = (
    "Ваші параметри пошуку:\n\n"
    "🛏 Кількість кімнат: {rooms}\n"
    "🏠 Стан квартири: {conditions}\n"
    "💰 Вартість: {price}\n\n"
    "Оберіть параметр, який хочете змінити."
)
BTN_EDIT_ROOMS = "🛏 Змінити кількість кімнат"
BTN_EDIT_CONDITION = "🏠 Змінити стан квартири"
BTN_EDIT_PRICE = "💰 Змінити вартість"
BTN_SAVE = "✅ Зберегти"
BTN_BACK = "⬅️ Назад"
EDIT_CANCELLED = "Параметри пошуку не змінено."  # NEW

# --- search start (Д1 §5.1, §5.2, §5.4) ---
SEARCHING = "🔎 Шукаємо квартири за вашими параметрами…"
FOUND = (
    "Знайшли {count} {apartments} за вашим запитом 🏠\n\n"
    "Ми зберегли ваш пошук і надсилатимемо нові відповідні квартири, щойно вони з’являться.\n\n"
    "Натисніть кнопку нижче, щоб переглянути знайдені варіанти."
)
BTN_VIEW_RESULTS = "Переглянути варіанти ➡️"
NOT_FOUND = (
    "Зараз немає квартир, які відповідають вашим параметрам.\n\n"
    "Ми зберегли ваш запит і повідомимо, щойно з’явиться відповідний варіант.\n\n"
    "Ви можете змінити параметри пошуку, щоб переглянути більше квартир."
)


def plural_uk(n: int, one: str, few: str, many: str) -> str:
    last, last_two = n % 10, n % 100
    if last == 1 and last_two != 11:
        return one
    if 2 <= last <= 4 and not 12 <= last_two <= 14:
        return few
    return many


def rooms_label(rooms: frozenset[RoomOption]) -> str:
    return ", ".join(ROOM_LABELS[r] for r in sorted(rooms))


def rooms_short(rooms: frozenset[RoomOption]) -> str:
    return ", ".join(ROOM_SHORT[r] for r in sorted(rooms))


def conditions_label(conditions: frozenset[ConditionGroup]) -> str:
    return ", ".join(CONDITION_LABELS[g] for g in ConditionGroup if g in conditions)


def price_label(price: PriceRange) -> str:
    low, high = PRICE_SEGMENTS[price.low], PRICE_SEGMENTS[price.high]
    if price.low == price.high:
        return low.label
    if low.low_k is None and high.high_k is None:
        return PRICE_ANY
    if low.low_k is None:
        return f"До {high.high_k} тис. $"
    if high.high_k is None:
        return f"{low.low_k} тис. $ і вище"
    return f"{low.low_k}–{high.high_k} тис. $"


def summary_text(c: SearchCriteria) -> str:
    return SUMMARY.format(
        rooms=rooms_label(c.rooms),
        conditions=conditions_label(c.conditions),
        price=price_label(c.price),
    )


def edit_menu_text(c: SearchCriteria) -> str:
    return EDIT_MENU.format(
        rooms=rooms_short(c.rooms),
        conditions=conditions_label(c.conditions),
        price=price_label(c.price),
    )


def found_text(count: int) -> str:
    return FOUND.format(count=count, apartments=plural_uk(count, "квартиру", "квартири", "квартир"))
