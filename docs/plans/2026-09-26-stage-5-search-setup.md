# Етап 5. Старт, меню, фільтри, підсумок — план реалізації

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Користувач проходить `/start` → «🔎 Знайти квартиру» → три фільтри → підсумок → редагування → «🔎 Почати пошук» і отримує лічильник збігів; чернетка переживає перерву; зміна активного пошуку атомарна і ставить новий baseline.

**Architecture:** Доменний сервіс `pokazun/search/service.py` (чернетки, підтвердження, baseline) не знає про Telegram і тестується напряму на БД. Telegram-шар — тонкі хендлери, які лише читають / змінюють чернетку через сервіс і рендерять екрани (`screens.py`) з текстів (`texts.py`) і клавіатур (`keyboards.py`). Callback-дані несуть **цільовий стан** (не «перемкнути»), тому подвійний клік і повтор апдейта ідемпотентні. Роутери створюються фабриками (новий екземпляр на кожен диспетчер).

**Tech Stack:** aiogram 3 (CallbackData, inline / reply keyboards), SQLAlchemy 2 async, PostgreSQL ARRAY.

**Spec:** `docs/plans/2026-09-25-pokazun-roadmap.md` (етап 5) + Д1 §2, §3, §4, §5.1, §5.2, §5.4, §13 («Не вибрано жодного значення», «Користувач повернувся», «перервав налаштування»), Д2 §6 (`searches`, `search_drafts`), §7, §23.

**Передумови:** етапи 3 і 4 виконані (`2026-09-26-stage-3-foundation.md`, `2026-09-26-stage-4-catalog-sync.md`). Використовуються: `build_dispatcher`, `build_routers`, middleware-дані `session` / `db_user` / `clock`, `User`, `SubscriptionState`, `str_enum`, `touch_user`, `SearchCriteria`, `PriceRange`, `RoomOption`, `ConditionGroup`, `PRICE_SEGMENTS`, `click_price`, `count_matching`, `ObjectState`, `tests.tg`, `tests.clock.Clock`.

**Межа з етапом 6:** цей етап закінчується повідомленням «Знайшли N квартир…» з кнопкою «Переглянути варіанти ➡️» (`st:view_results`). Обробник цієї кнопки, видача карток і пагінація — етап 6. До нього кнопка відповідає порожнім `answerCallbackQuery` (fallback-роутер). Кнопки меню «Мій пошук», «Збережені ❤️», «Допомога», «🏠 Продати квартиру» тимчасово ведуть у fallback (підказка + меню) до етапів 10, 8, 11.

## Global Constraints

- Усі правила етапів 3–4 (production-якість, UTC, `now` параметром, без «MVP»).
- Усі тексти — в `src/pokazun/bot/texts.py`; у хендлерах, клавіатурах і екранах немає літеральних рядків для користувача.
- Тексти з Д1 — дослівно. Тексти, яких немає в Д1, позначені в коді `# NEW` і перелічені в розділі «Тексти на погодження» нижче.
- Один підтверджений активний пошук на користувача (unique `searches.user_id`); редагування не створює паралельний пошук (Д2 §6).
- До «🔎 Почати пошук» / «✅ Зберегти» параметри — лише чернетка; активний пошук не змінюється частково (Д2 §7, §23).
- Підтвердження атомарно замінює параметри, ставить `baseline_at = now`, видаляє чернетку в одній транзакції (Д2 §23).
- Перше підтвердження → `subscription_state = active`; редагування ручну паузу не знімає.
- «Далі ➡️» показується лише при ≥ 1 виборі; без вибору — жодного повідомлення про помилку (Д1 §3, §13).
- Ціна — завжди безперервний діапазон; проміжні сегменти позначені ✅; «Обнулити вибір 🔄» після першого вибору (Д1 §3.3).
- Перемикання кнопок — `editMessageReplyMarkup`; перехід між кроками — `editMessageText` того самого повідомлення (roadmap етап 5).
- Лічильник у «Знайшли N…» — фактична кількість актуальних збігів з `object_state` (Д1 §5.2).

## Тексти на погодження (немає в Д1)

| Константа | Текст | Де |
|---|---|---|
| `MENU_HINT` | «Скористайтеся кнопками меню нижче 👇» | Відповідь на довільний текст |
| `EDIT_CANCELLED` | «Параметри пошуку не змінено.» | «⬅️ Назад» при редагуванні активного пошуку |
| `PRICE_ANY` | «Будь-яка вартість» | Підсумок, коли обрано всі 8 сегментів |
| `BTN_HELP` | «Допомога» | Нижнє меню (Д1: «допомога / зв’язок з агентством») |

Надіслати замовнику разом з текстами етапу 2; до погодження лишаються як є.

## Review Focus

- Натискання на застарілу клавіатуру (попередній крок або після підтвердження) → стан не псується: поточний крок перемальовується / клік ігнорується. Тест: Task 6 `test_stale_keyboard_rerenders_current_step`, Task 7 `test_start_search_double_click`.
- Подвійний клік «🔎 Почати пошук» → рівно один пошук і одне повідомлення з результатом. Тест: Task 7 `test_start_search_double_click`.
- Користувач почав редагувати активний пошук і вийшов («⬅️ Назад» або просто кинув) → активний пошук і його baseline не змінились. Тести: Task 3 `test_edit_draft_does_not_touch_active_search`, Task 7 `test_edit_back_keeps_search`.
- Callback прийшов під повідомленням, старшим за 48 год (Telegram віддає `InaccessibleMessage`) → бот надсилає новий екран замість падіння на редагуванні. Тест: Task 6 `test_inaccessible_message_gets_new_message`.
- Клік по внутрішньому (не крайньому) сегменту ціни → діапазон не змінюється, без помилок і зайвих запитів. Тест: Task 6 `test_price_gap_fill_and_edges`.

---

## Структура файлів

```
src/pokazun/search/steps.py              DraftMode, Step, FILTER_STEPS
src/pokazun/search/service.py            чернетки, DraftView, confirm_draft, get_active_search
src/pokazun/db/models/search.py          Search, SearchDraft
migrations/versions/0003_searches.py
src/pokazun/bot/texts.py                 усі тексти + форматування підсумків
src/pokazun/bot/keyboards.py             CallbackData, меню, клавіатури фільтрів
src/pokazun/bot/screens.py               draft_screen, results_screen
src/pokazun/bot/handlers/search_setup.py build_router() — старт, фільтри, підсумок, підтвердження
src/pokazun/bot/handlers/fallback.py     build_router() — невідомий текст / callback
Modify: src/pokazun/db/models/__init__.py, src/pokazun/bot/handlers/__init__.py, tests/tg.py
tests/bot_harness.py, tests/test_search_models.py, tests/test_texts.py, tests/test_search_service.py,
tests/test_keyboards.py, tests/test_handlers_start.py, tests/test_handlers_filters.py,
tests/test_handlers_confirm.py
```

---

### Task 1: Моделі `searches` і `search_drafts`

**Files:**
- Create: `src/pokazun/search/steps.py`, `src/pokazun/db/models/search.py`, `migrations/versions/0003_searches.py`
- Modify: `src/pokazun/db/models/__init__.py`
- Test: `tests/test_search_models.py`

**Interfaces:**
- Produces:
  - `DraftMode(StrEnum)`: `CREATE="create"`, `EDIT="edit"`; `Step(StrEnum)`: `ROOMS`, `CONDITION`, `PRICE`, `SUMMARY`, `EDIT_MENU` (значення — нижній регістр назви); `FILTER_STEPS = (Step.ROOMS, Step.CONDITION, Step.PRICE)`.
  - `Search`: `id`, `user_id` (unique, FK users), `rooms: list[int]`, `conditions: list[str]`, `price_low`, `price_high`, `baseline_at`, `confirmed_at`, `created_at`, `updated_at`; властивість `criteria -> SearchCriteria`.
  - `SearchDraft`: `user_id` (PK, FK users), `mode: DraftMode`, `step: Step`, `rooms: list[int]`, `conditions: list[str]`, `price_low`, `price_high` (обидва `None` — ціну не обрано), `reached_summary: bool`, `updated_at`.

- [ ] **Step 1: Тест**

`tests/test_search_models.py`:

```python
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from pokazun.db.models import Search, SearchDraft
from pokazun.search.filters import ConditionGroup, PriceRange, RoomOption
from pokazun.search.steps import DraftMode, Step
from pokazun.users.repository import touch_user

T0 = datetime(2026, 10, 1, tzinfo=UTC)


async def make_user(sessionmaker) -> int:
    async with sessionmaker() as s, s.begin():
        user = await touch_user(s, telegram_user_id=1, username=None, first_name=None, now=T0)
        return user.id


async def test_search_criteria_roundtrip(sessionmaker):
    user_id = await make_user(sessionmaker)
    async with sessionmaker() as s, s.begin():
        s.add(
            Search(
                user_id=user_id,
                rooms=[2, 4],
                conditions=["residential"],
                price_low=2,
                price_high=4,
                baseline_at=T0,
                confirmed_at=T0,
            )
        )
    async with sessionmaker() as s:
        search = await s.scalar(select(Search))
    c = search.criteria
    assert c.rooms == {RoomOption.TWO, RoomOption.FOUR_PLUS}
    assert c.conditions == {ConditionGroup.RESIDENTIAL}
    assert c.price == PriceRange(2, 4)


async def test_one_search_per_user(sessionmaker):
    user_id = await make_user(sessionmaker)
    row = dict(user_id=user_id, rooms=[1], conditions=["developer"], price_low=0, price_high=0, baseline_at=T0, confirmed_at=T0)
    async with sessionmaker() as s:
        s.add_all([Search(**row), Search(**row)])
        with pytest.raises(IntegrityError):
            await s.flush()


@pytest.mark.parametrize(
    "values",
    ["'{}', '{developer}', 0, 0", "'{1}', '{}', 0, 0", "'{1}', '{developer}', 3, 2"],
)
async def test_search_check_constraints(sessionmaker, values):
    user_id = await make_user(sessionmaker)
    async with sessionmaker() as s:
        with pytest.raises(IntegrityError):
            await s.execute(
                text(
                    "INSERT INTO searches (user_id, rooms, conditions, price_low, price_high, baseline_at, confirmed_at) "
                    f"VALUES ({user_id}, {values}, now(), now())"
                )
            )


async def test_draft_defaults(sessionmaker):
    user_id = await make_user(sessionmaker)
    async with sessionmaker() as s, s.begin():
        s.add(SearchDraft(user_id=user_id, mode=DraftMode.CREATE, step=Step.ROOMS))
    async with sessionmaker() as s:
        draft = await s.get(SearchDraft, user_id)
    assert draft.rooms == [] and draft.conditions == []
    assert draft.price_low is None and draft.reached_summary is False
    assert draft.mode is DraftMode.CREATE and draft.step is Step.ROOMS
```

- [ ] **Step 2: Запустити — має впасти**

Run: `uv run pytest tests/test_search_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'Search'`.

- [ ] **Step 3: Реалізація**

`src/pokazun/search/steps.py`:

```python
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
```

`src/pokazun/db/models/search.py`:

```python
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Identity, SmallInteger, String, func, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from pokazun.db.base import Base
from pokazun.db.models.users import str_enum
from pokazun.search.filters import ConditionGroup, PriceRange, RoomOption, SearchCriteria
from pokazun.search.steps import DraftMode, Step


class Search(Base):
    """The user's single confirmed search. Replaced atomically on edit (Д2 §23)."""

    __tablename__ = "searches"
    __table_args__ = (
        CheckConstraint("price_low <= price_high", name="price_range"),
        CheckConstraint("cardinality(rooms) > 0", name="rooms_not_empty"),
        CheckConstraint("cardinality(conditions) > 0", name="conditions_not_empty"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    rooms: Mapped[list[int]] = mapped_column(ARRAY(SmallInteger))
    conditions: Mapped[list[str]] = mapped_column(ARRAY(String(32)))
    price_low: Mapped[int] = mapped_column(SmallInteger)
    price_high: Mapped[int] = mapped_column(SmallInteger)
    baseline_at: Mapped[datetime]
    confirmed_at: Mapped[datetime]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    @property
    def criteria(self) -> SearchCriteria:
        return SearchCriteria(
            rooms=frozenset(RoomOption(r) for r in self.rooms),
            conditions=frozenset(ConditionGroup(c) for c in self.conditions),
            price=PriceRange(self.price_low, self.price_high),
        )


class SearchDraft(Base):
    """Unfinished setup or edit of a search (Д1 §3.4). Not an active search."""

    __tablename__ = "search_drafts"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    mode: Mapped[DraftMode] = mapped_column(str_enum(DraftMode))
    step: Mapped[Step] = mapped_column(str_enum(Step))
    rooms: Mapped[list[int]] = mapped_column(
        ARRAY(SmallInteger), default=list, server_default=text("'{}'")
    )
    conditions: Mapped[list[str]] = mapped_column(
        ARRAY(String(32)), default=list, server_default=text("'{}'")
    )
    price_low: Mapped[int | None] = mapped_column(SmallInteger)
    price_high: Mapped[int | None] = mapped_column(SmallInteger)
    reached_summary: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
```

`src/pokazun/db/models/__init__.py` — повна нова версія:

```python
"""Importing this package registers every model on Base.metadata (used by Alembic and tests)."""

from pokazun.db.models.catalog import ObjectState, SyncState
from pokazun.db.models.search import Search, SearchDraft
from pokazun.db.models.system import ProcessedUpdate
from pokazun.db.models.users import DeliveryState, SubscriptionState, User

__all__ = [
    "DeliveryState",
    "ObjectState",
    "ProcessedUpdate",
    "Search",
    "SearchDraft",
    "SubscriptionState",
    "SyncState",
    "User",
]
```

`migrations/versions/0003_searches.py`:

```python
"""searches and search_drafts

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "searches",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("rooms", postgresql.ARRAY(sa.SmallInteger()), nullable=False),
        sa.Column("conditions", postgresql.ARRAY(sa.String(32)), nullable=False),
        sa.Column("price_low", sa.SmallInteger(), nullable=False),
        sa.Column("price_high", sa.SmallInteger(), nullable=False),
        sa.Column("baseline_at", TS, nullable=False),
        sa.Column("confirmed_at", TS, nullable=False),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_searches"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_searches_user_id_users", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("user_id", name="uq_searches_user_id"),
        sa.CheckConstraint("price_low <= price_high", name="ck_searches_price_range"),
        sa.CheckConstraint("cardinality(rooms) > 0", name="ck_searches_rooms_not_empty"),
        sa.CheckConstraint("cardinality(conditions) > 0", name="ck_searches_conditions_not_empty"),
    )
    op.create_table(
        "search_drafts",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("step", sa.String(32), nullable=False),
        sa.Column(
            "rooms", postgresql.ARRAY(sa.SmallInteger()), server_default=sa.text("'{}'"), nullable=False
        ),
        sa.Column(
            "conditions", postgresql.ARRAY(sa.String(32)), server_default=sa.text("'{}'"), nullable=False
        ),
        sa.Column("price_low", sa.SmallInteger(), nullable=True),
        sa.Column("price_high", sa.SmallInteger(), nullable=True),
        sa.Column("reached_summary", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", name="pk_search_drafts"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_search_drafts_user_id_users", ondelete="CASCADE"
        ),
        sa.CheckConstraint("mode IN ('create', 'edit')", name="ck_search_drafts_mode"),
        sa.CheckConstraint(
            "step IN ('rooms', 'condition', 'price', 'summary', 'edit_menu')",
            name="ck_search_drafts_step",
        ),
    )


def downgrade() -> None:
    op.drop_table("search_drafts")
    op.drop_table("searches")
```

- [ ] **Step 4: Запустити — має пройти (разом із тестом дрейфу)**

Run: `uv run pytest tests/test_search_models.py tests/test_db_migrations.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pokazun/search/steps.py src/pokazun/db/models migrations/versions/0003_searches.py tests/test_search_models.py
git commit -m "feat: searches and search_drafts tables"
```

---

### Task 2: Тексти бота

**Files:**
- Create: `src/pokazun/bot/texts.py`
- Test: `tests/test_texts.py`

**Interfaces:**
- Consumes: `RoomOption`, `ConditionGroup`, `PriceRange`, `PRICE_SEGMENTS`, `SearchCriteria` (етап 4).
- Produces: константи (`WELCOME`, `MENU_HINT`, `BTN_*`, `MARK_ON`, `MARK_OFF`, `ROOMS_PROMPT`, `CONDITION_PROMPT`, `PRICE_PROMPT`, `ROOM_LABELS`, `CONDITION_LABELS`, `SEARCHING`, `NOT_FOUND`, `EDIT_CANCELLED`, `PRICE_ANY`) і функції `plural_uk(n, one, few, many) -> str`, `rooms_label(rooms) -> str`, `rooms_short(rooms) -> str`, `conditions_label(conditions) -> str`, `price_label(price: PriceRange) -> str`, `summary_text(c: SearchCriteria) -> str`, `edit_menu_text(c: SearchCriteria) -> str`, `found_text(count: int) -> str`.

- [ ] **Step 1: Тест**

`tests/test_texts.py`:

```python
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
    [(1, "квартиру"), (2, "квартири"), (4, "квартири"), (5, "квартир"), (11, "квартир"),
     (12, "квартир"), (21, "квартиру"), (22, "квартири"), (47, "квартир"), (111, "квартир")],
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
```

- [ ] **Step 2: Запустити — має впасти**

Run: `uv run pytest tests/test_texts.py -v`
Expected: FAIL — `ImportError: cannot import name 'texts'`.

- [ ] **Step 3: Реалізація**

`src/pokazun/bot/texts.py`:

```python
"""Every user-facing bot text (Ukrainian only). Source: Д1 verbatim; lines marked NEW await client approval."""

from pokazun.search.filters import PRICE_SEGMENTS, ConditionGroup, PriceRange, RoomOption, SearchCriteria

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
        rooms=rooms_label(c.rooms), conditions=conditions_label(c.conditions), price=price_label(c.price)
    )


def edit_menu_text(c: SearchCriteria) -> str:
    return EDIT_MENU.format(
        rooms=rooms_short(c.rooms), conditions=conditions_label(c.conditions), price=price_label(c.price)
    )


def found_text(count: int) -> str:
    return FOUND.format(count=count, apartments=plural_uk(count, "квартиру", "квартири", "квартир"))
```

- [ ] **Step 4: Запустити — має пройти**

Run: `uv run pytest tests/test_texts.py -v`
Expected: 21 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pokazun/bot/texts.py tests/test_texts.py
git commit -m "feat: bot texts module with summary formatting"
```

---

### Task 3: Сервіс чернеток і підтвердження пошуку

**Files:**
- Create: `src/pokazun/search/service.py`
- Test: `tests/test_search_service.py`

**Interfaces:**
- Consumes: `Search`, `SearchDraft`, `User`, `SubscriptionState` (Task 1, етап 3), фільтри (етап 4), `DraftMode`, `Step`, `FILTER_STEPS` (Task 1).
- Produces:
  - `DraftError(Exception)`.
  - `DraftView(mode, step, rooms: frozenset[RoomOption], conditions: frozenset[ConditionGroup], price: PriceRange | None, reached_summary: bool)`; `.criteria -> SearchCriteria | None`.
  - `view(draft: SearchDraft) -> DraftView`.
  - `ConfirmResult(search: Search, created: bool)`.
  - `await get_active_search(session, user_id, *, for_update=False) -> Search | None`.
  - `await get_draft(session, user_id, *, for_update=False) -> SearchDraft | None`.
  - `await start_or_resume(session, user_id) -> SearchDraft` — наявна чернетка; інакше, якщо є активний пошук, — чернетка редагування; інакше нова чернетка на кроці `ROOMS`.
  - `await start_edit(session, user_id) -> SearchDraft` — копія активного пошуку, крок `EDIT_MENU`; `DraftError`, якщо пошуку немає.
  - `set_rooms(draft, rooms)`, `set_conditions(draft, conditions)`, `set_price(draft, price | None)`.
  - `advance(draft) -> bool` — «Далі»: `False`, якщо на поточному кроці нічого не обрано; після першого досягнення підсумку повертає в `EDIT_MENU`.
  - `open_edit_menu(draft) -> bool` (з `SUMMARY`), `open_filter(draft, step) -> bool` (з `EDIT_MENU`), `close_edit_menu(draft) -> bool` (`EDIT_MENU` → `SUMMARY`, лише режим `CREATE`).
  - `await discard_draft(session, draft) -> None`.
  - `await confirm_draft(session, user: User, now: datetime) -> ConfirmResult | None` — `None`, якщо чернетки немає (повторний клік); `DraftError`, якщо крок не той або чернетка неповна.

- [ ] **Step 1: Тест**

`tests/test_search_service.py`:

```python
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from pokazun.db.models import Search, SearchDraft, SubscriptionState, User
from pokazun.search.filters import ConditionGroup, PriceRange, RoomOption
from pokazun.search.service import (
    DraftError,
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
from pokazun.search.steps import DraftMode, Step
from pokazun.users.repository import touch_user

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
T1 = T0 + timedelta(days=3)


@pytest.fixture
async def user_id(sessionmaker) -> int:
    async with sessionmaker() as s, s.begin():
        return (await touch_user(s, telegram_user_id=1, username=None, first_name=None, now=T0)).id


async def fill_and_confirm(sessionmaker, user_id, now=T0):
    async with sessionmaker() as s, s.begin():
        draft = await start_or_resume(s, user_id)
        set_rooms(draft, frozenset({RoomOption.TWO}))
        assert advance(draft)
        set_conditions(draft, frozenset({ConditionGroup.RESIDENTIAL}))
        assert advance(draft)
        set_price(draft, PriceRange(2, 4))
        assert advance(draft)
        assert draft.step is Step.SUMMARY
        user = await s.get(User, user_id)
        return await confirm_draft(s, user, now)


async def test_new_draft_and_resume(sessionmaker, user_id):
    async with sessionmaker() as s, s.begin():
        draft = await start_or_resume(s, user_id)
        assert (draft.mode, draft.step) == (DraftMode.CREATE, Step.ROOMS)
        set_rooms(draft, frozenset({RoomOption.ONE, RoomOption.FOUR_PLUS}))
        assert advance(draft)
    async with sessionmaker() as s, s.begin():
        resumed = await start_or_resume(s, user_id)
        v = view(resumed)
    assert v.step is Step.CONDITION
    assert v.rooms == {RoomOption.ONE, RoomOption.FOUR_PLUS}


async def test_advance_requires_selection(sessionmaker, user_id):
    async with sessionmaker() as s, s.begin():
        draft = await start_or_resume(s, user_id)
        assert advance(draft) is False
        assert draft.step is Step.ROOMS


async def test_after_summary_filters_return_to_edit_menu(sessionmaker, user_id):
    async with sessionmaker() as s, s.begin():
        draft = await start_or_resume(s, user_id)
        set_rooms(draft, frozenset({RoomOption.TWO}))
        advance(draft)
        set_conditions(draft, frozenset({ConditionGroup.DEVELOPER}))
        advance(draft)
        set_price(draft, PriceRange(0, 1))
        advance(draft)
        assert draft.step is Step.SUMMARY and draft.reached_summary
        assert open_edit_menu(draft) and draft.step is Step.EDIT_MENU
        assert open_filter(draft, Step.ROOMS) and draft.step is Step.ROOMS
        set_rooms(draft, frozenset({RoomOption.THREE}))
        assert advance(draft) and draft.step is Step.EDIT_MENU
        assert close_edit_menu(draft) and draft.step is Step.SUMMARY


async def test_invalid_transitions_rejected(sessionmaker, user_id):
    async with sessionmaker() as s, s.begin():
        draft = await start_or_resume(s, user_id)
        assert open_edit_menu(draft) is False
        assert open_filter(draft, Step.PRICE) is False
        assert close_edit_menu(draft) is False
        with pytest.raises(DraftError):
            await confirm_draft(s, await s.get(User, user_id), T0)


async def test_confirm_creates_search_with_baseline(sessionmaker, user_id):
    result = await fill_and_confirm(sessionmaker, user_id)
    assert result.created is True
    async with sessionmaker() as s:
        search = await get_active_search(s, user_id)
        user = await s.get(User, user_id)
        assert await get_draft(s, user_id) is None
    assert search.baseline_at == T0 and search.confirmed_at == T0
    assert search.criteria.price == PriceRange(2, 4)
    assert user.subscription_state is SubscriptionState.ACTIVE


async def test_confirm_without_draft_returns_none(sessionmaker, user_id):
    async with sessionmaker() as s, s.begin():
        assert await confirm_draft(s, await s.get(User, user_id), T0) is None


async def test_find_with_active_search_opens_edit(sessionmaker, user_id):
    await fill_and_confirm(sessionmaker, user_id)
    async with sessionmaker() as s, s.begin():
        draft = await start_or_resume(s, user_id)
        v = view(draft)
    assert (v.mode, v.step, v.reached_summary) == (DraftMode.EDIT, Step.EDIT_MENU, True)
    assert v.price == PriceRange(2, 4) and v.rooms == {RoomOption.TWO}


async def test_edit_draft_does_not_touch_active_search(sessionmaker, user_id):
    await fill_and_confirm(sessionmaker, user_id)
    async with sessionmaker() as s, s.begin():
        draft = await start_edit(s, user_id)
        open_filter(draft, Step.PRICE)
        set_price(draft, PriceRange(6, 7))
    async with sessionmaker() as s:
        search = await get_active_search(s, user_id)
    assert search.criteria.price == PriceRange(2, 4)
    assert search.baseline_at == T0


async def test_confirm_edit_replaces_atomically_and_rebaselines(sessionmaker, user_id):
    await fill_and_confirm(sessionmaker, user_id)
    async with sessionmaker() as s, s.begin():
        user = await s.get(User, user_id)
        user.subscription_state = SubscriptionState.PAUSED_BY_USER
    async with sessionmaker() as s, s.begin():
        draft = await start_edit(s, user_id)
        open_filter(draft, Step.PRICE)
        set_price(draft, PriceRange(6, 7))
        advance(draft)
        result = await confirm_draft(s, await s.get(User, user_id), T1)
    assert result.created is False
    async with sessionmaker() as s:
        assert await s.scalar(select(func.count()).select_from(Search)) == 1
        search = await get_active_search(s, user_id)
        user = await s.get(User, user_id)
    assert search.criteria.price == PriceRange(6, 7)
    assert search.baseline_at == T1
    assert user.subscription_state is SubscriptionState.PAUSED_BY_USER


async def test_edit_mode_confirm_only_from_edit_menu(sessionmaker, user_id):
    await fill_and_confirm(sessionmaker, user_id)
    async with sessionmaker() as s, s.begin():
        draft = await start_edit(s, user_id)
        open_filter(draft, Step.ROOMS)
        with pytest.raises(DraftError):
            await confirm_draft(s, await s.get(User, user_id), T1)


async def test_discard(sessionmaker, user_id):
    async with sessionmaker() as s, s.begin():
        draft = await start_or_resume(s, user_id)
        await discard_draft(s, draft)
    async with sessionmaker() as s:
        assert await s.scalar(select(func.count()).select_from(SearchDraft)) == 0


async def test_start_edit_without_search_fails(sessionmaker, user_id):
    async with sessionmaker() as s, s.begin():
        with pytest.raises(DraftError):
            await start_edit(s, user_id)
```

- [ ] **Step 2: Запустити — має впасти**

Run: `uv run pytest tests/test_search_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pokazun.search.service'`.

- [ ] **Step 3: Реалізація**

`src/pokazun/search/service.py`:

```python
"""Search draft lifecycle and confirmation (Д1 §3.4, §4; Д2 §6, §7, §23). No Telegram dependencies."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pokazun.db.models import Search, SearchDraft, SubscriptionState, User
from pokazun.search.filters import ConditionGroup, PriceRange, RoomOption, SearchCriteria
from pokazun.search.steps import FILTER_STEPS, DraftMode, Step

_NEXT_STEP = {Step.ROOMS: Step.CONDITION, Step.CONDITION: Step.PRICE, Step.PRICE: Step.SUMMARY}


class DraftError(Exception):
    pass


@dataclass(frozen=True)
class DraftView:
    mode: DraftMode
    step: Step
    rooms: frozenset[RoomOption]
    conditions: frozenset[ConditionGroup]
    price: PriceRange | None
    reached_summary: bool

    @property
    def criteria(self) -> SearchCriteria | None:
        if not self.rooms or not self.conditions or self.price is None:
            return None
        return SearchCriteria(self.rooms, self.conditions, self.price)


@dataclass(frozen=True)
class ConfirmResult:
    search: Search
    created: bool


def view(draft: SearchDraft) -> DraftView:
    price = (
        PriceRange(draft.price_low, draft.price_high)
        if draft.price_low is not None and draft.price_high is not None
        else None
    )
    return DraftView(
        mode=draft.mode,
        step=draft.step,
        rooms=frozenset(RoomOption(r) for r in draft.rooms),
        conditions=frozenset(ConditionGroup(c) for c in draft.conditions),
        price=price,
        reached_summary=draft.reached_summary,
    )


async def get_active_search(
    session: AsyncSession, user_id: int, *, for_update: bool = False
) -> Search | None:
    stmt = select(Search).where(Search.user_id == user_id)
    if for_update:
        stmt = stmt.with_for_update()
    return await session.scalar(stmt)


async def get_draft(
    session: AsyncSession, user_id: int, *, for_update: bool = False
) -> SearchDraft | None:
    return await session.get(SearchDraft, user_id, with_for_update=for_update)


def set_rooms(draft: SearchDraft, rooms: frozenset[RoomOption]) -> None:
    draft.rooms = sorted(r.value for r in rooms)


def set_conditions(draft: SearchDraft, conditions: frozenset[ConditionGroup]) -> None:
    draft.conditions = sorted(c.value for c in conditions)


def set_price(draft: SearchDraft, price: PriceRange | None) -> None:
    draft.price_low = price.low if price else None
    draft.price_high = price.high if price else None


def _fill(
    draft: SearchDraft,
    *,
    mode: DraftMode,
    step: Step,
    rooms: frozenset[RoomOption],
    conditions: frozenset[ConditionGroup],
    price: PriceRange | None,
    reached_summary: bool,
) -> None:
    draft.mode = mode
    draft.step = step
    set_rooms(draft, rooms)
    set_conditions(draft, conditions)
    set_price(draft, price)
    draft.reached_summary = reached_summary


async def start_or_resume(session: AsyncSession, user_id: int) -> SearchDraft:
    draft = await get_draft(session, user_id, for_update=True)
    if draft is not None:
        return draft
    if await get_active_search(session, user_id) is not None:
        return await start_edit(session, user_id)
    draft = SearchDraft(user_id=user_id)
    _fill(
        draft,
        mode=DraftMode.CREATE,
        step=Step.ROOMS,
        rooms=frozenset(),
        conditions=frozenset(),
        price=None,
        reached_summary=False,
    )
    session.add(draft)
    await session.flush()
    return draft


async def start_edit(session: AsyncSession, user_id: int) -> SearchDraft:
    search = await get_active_search(session, user_id)
    if search is None:
        raise DraftError("no active search to edit")
    criteria = search.criteria
    draft = await get_draft(session, user_id, for_update=True)
    if draft is None:
        draft = SearchDraft(user_id=user_id)
        session.add(draft)
    _fill(
        draft,
        mode=DraftMode.EDIT,
        step=Step.EDIT_MENU,
        rooms=criteria.rooms,
        conditions=criteria.conditions,
        price=criteria.price,
        reached_summary=True,
    )
    await session.flush()
    return draft


def advance(draft: SearchDraft) -> bool:
    current = view(draft)
    filled = {
        Step.ROOMS: bool(current.rooms),
        Step.CONDITION: bool(current.conditions),
        Step.PRICE: current.price is not None,
    }
    if not filled.get(draft.step, False):
        return False
    if draft.reached_summary:
        draft.step = Step.EDIT_MENU
        return True
    draft.step = _NEXT_STEP[draft.step]
    if draft.step is Step.SUMMARY:
        draft.reached_summary = True
    return True


def open_edit_menu(draft: SearchDraft) -> bool:
    if draft.step is not Step.SUMMARY:
        return False
    draft.step = Step.EDIT_MENU
    return True


def open_filter(draft: SearchDraft, step: Step) -> bool:
    if draft.step is not Step.EDIT_MENU or step not in FILTER_STEPS:
        return False
    draft.step = step
    return True


def close_edit_menu(draft: SearchDraft) -> bool:
    if draft.step is not Step.EDIT_MENU or draft.mode is not DraftMode.CREATE:
        return False
    draft.step = Step.SUMMARY
    return True


async def discard_draft(session: AsyncSession, draft: SearchDraft) -> None:
    await session.delete(draft)
    await session.flush()


async def confirm_draft(session: AsyncSession, user: User, now: datetime) -> ConfirmResult | None:
    """Atomically turns the draft into the active search and sets a new baseline (Д2 §23)."""
    draft = await get_draft(session, user.id, for_update=True)
    if draft is None:
        return None
    expected = Step.SUMMARY if draft.mode is DraftMode.CREATE else Step.EDIT_MENU
    if draft.step is not expected:
        raise DraftError(f"cannot confirm a {draft.mode} draft at step {draft.step}")
    criteria = view(draft).criteria
    if criteria is None:
        raise DraftError("draft is incomplete")

    search = await get_active_search(session, user.id, for_update=True)
    created = search is None
    if search is None:
        search = Search(user_id=user.id)
        session.add(search)
        user.subscription_state = SubscriptionState.ACTIVE
    search.rooms = sorted(r.value for r in criteria.rooms)
    search.conditions = sorted(c.value for c in criteria.conditions)
    search.price_low = criteria.price.low
    search.price_high = criteria.price.high
    search.baseline_at = now
    search.confirmed_at = now
    await session.delete(draft)
    await session.flush()
    return ConfirmResult(search=search, created=created)
```

- [ ] **Step 4: Запустити — має пройти**

Run: `uv run pytest tests/test_search_service.py -v`
Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pokazun/search/service.py tests/test_search_service.py
git commit -m "feat: search draft lifecycle and atomic confirmation with baseline"
```

---

### Task 4: Клавіатури і екрани

**Files:**
- Create: `src/pokazun/bot/keyboards.py`, `src/pokazun/bot/screens.py`
- Test: `tests/test_keyboards.py`

**Interfaces:**
- Consumes: `texts` (Task 2), `DraftView` (Task 3), `Step` (Task 1), фільтри і `click_price` (етап 4).
- Produces:
  - `StepAction(StrEnum)`: `NEXT`, `RESET_PRICE`, `EDIT`, `GOTO_ROOMS`, `GOTO_CONDITION`, `GOTO_PRICE`, `SAVE`, `BACK`, `START_SEARCH`, `VIEW_RESULTS` (значення — нижній регістр назви).
  - CallbackData: `RoomsCb(prefix="rm", value: int, on: bool)`, `ConditionCb(prefix="cd", value: str, on: bool)`, `PriceCb(prefix="pr", low: int, high: int)` (`EMPTY_PRICE = -1` для обох — «нічого не обрано»), `StepCb(prefix="st", action: StepAction)`.
  - `main_menu(has_search: bool) -> ReplyKeyboardMarkup`; `rooms_keyboard(selected)`, `conditions_keyboard(selected)`, `price_keyboard(price | None)`, `summary_keyboard()`, `edit_menu_keyboard()`, `found_keyboard()`, `not_found_keyboard()` → `InlineKeyboardMarkup`.
  - `draft_screen(v: DraftView) -> tuple[str, InlineKeyboardMarkup]`; `results_screen(count: int) -> tuple[str, InlineKeyboardMarkup]`.
  - Етап 6 обробляє `StepCb(action=StepAction.VIEW_RESULTS)`.

- [ ] **Step 1: Тест**

`tests/test_keyboards.py`:

```python
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
    assert [t for t, _ in empty] == ["👉 1 кімната", "👉 2 кімнати", "👉 3 кімнати", "👉 4+ кімнати"]
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
    return DraftView(mode, step, frozenset(rooms), frozenset(conditions), price, reached_summary=False)


def test_draft_screens():
    text, _ = draft_screen(view(Step.ROOMS))
    assert text == texts.ROOMS_PROMPT
    text, _ = draft_screen(view(Step.CONDITION))
    assert text == texts.CONDITION_PROMPT
    text, _ = draft_screen(view(Step.PRICE))
    assert text == texts.PRICE_PROMPT
    full = dict(rooms={RoomOption.ONE}, conditions={ConditionGroup.DEVELOPER}, price=PriceRange(0, 0))
    text, markup = draft_screen(view(Step.SUMMARY, **full))
    assert text.startswith("Ваш запит:")
    assert [t for t, _ in inline(markup)] == [texts.BTN_START_SEARCH, texts.BTN_EDIT_SEARCH]
    text, markup = draft_screen(view(Step.EDIT_MENU, **full))
    assert text.startswith("Ваші параметри пошуку:")
    assert [t for t, _ in inline(markup)] == [
        texts.BTN_EDIT_ROOMS, texts.BTN_EDIT_CONDITION, texts.BTN_EDIT_PRICE, texts.BTN_SAVE, texts.BTN_BACK,
    ]


def test_results_screens():
    text, markup = results_screen(3)
    assert text.startswith("Знайшли 3 квартири")
    assert inline(markup) == [(texts.BTN_VIEW_RESULTS, StepCb(action=StepAction.VIEW_RESULTS).pack())]
    text, markup = results_screen(0)
    assert text == texts.NOT_FOUND
    assert inline(markup) == [(texts.BTN_EDIT_SEARCH, StepCb(action=StepAction.EDIT).pack())]
```

- [ ] **Step 2: Запустити — має впасти**

Run: `uv run pytest tests/test_keyboards.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pokazun.bot.keyboards'`.

- [ ] **Step 3: Реалізація `keyboards.py`**

```python
"""Keyboards and callback data. Callback data carries the target state, so repeated clicks are idempotent."""

from enum import StrEnum

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from pokazun.bot import texts
from pokazun.search.filters import PRICE_SEGMENTS, ConditionGroup, PriceRange, RoomOption, click_price

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
    return InlineKeyboardMarkup(inline_keyboard=[_step(texts.BTN_VIEW_RESULTS, StepAction.VIEW_RESULTS)])


def not_found_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[_step(texts.BTN_EDIT_SEARCH, StepAction.EDIT)])
```

- [ ] **Step 4: Реалізація `screens.py`**

```python
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
```

- [ ] **Step 5: Запустити — має пройти**

Run: `uv run pytest tests/test_keyboards.py -v`
Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add src/pokazun/bot/keyboards.py src/pokazun/bot/screens.py tests/test_keyboards.py
git commit -m "feat: idempotent callback keyboards and draft screens"
```

---

### Task 5: Хендлери старту, меню і fallback; тестовий стенд бота

**Files:**
- Create: `src/pokazun/bot/handlers/search_setup.py`, `src/pokazun/bot/handlers/fallback.py`
- Modify: `src/pokazun/bot/handlers/__init__.py`, `tests/tg.py`
- Create: `tests/bot_harness.py`
- Test: `tests/test_handlers_start.py`

**Interfaces:**
- Consumes: сервіс (Task 3), екрани й клавіатури (Task 4), тексти (Task 2), middleware-дані `session`, `db_user`, `bot`, `clock` (етап 3).
- Produces:
  - `pokazun.bot.handlers.search_setup.build_router() -> Router`; `pokazun.bot.handlers.fallback.build_router() -> Router`.
  - `build_routers()` повертає `[search_setup.build_router(), fallback.build_router()]`. Правило для етапів 6+: нові роутери вставляються **перед** fallback.
  - `tests.bot_harness.Harness(sessionmaker, now)`: `.send(text, user=None) -> list[TelegramMethod]`, `.click(data, user=None, message_id=777) -> list`, `.feed(update) -> list`, `.now`; функції `of_type(requests, method_type)`, `inline(markup)`, `reply(markup)`, `seed_search(sessionmaker, telegram_user_id, *, rooms, conditions, low, high, now)`, `seed_objects(sessionmaker, rows)`.
  - `tests.tg.inaccessible_callback_update(data, user=None) -> Update`.

Роутери створюються фабриками: aiogram не дозволяє під’єднати один екземпляр `Router` до двох диспетчерів, а тести створюють диспетчер на кожен тест.

- [ ] **Step 1: Доповнити `tests/tg.py`**

Додати в імпорти `InaccessibleMessage` і в кінець файлу:

```python
def inaccessible_callback_update(data: str, *, user: User | None = None) -> Update:
    user = user or tg_user()
    return Update(
        update_id=next(_update_ids),
        callback_query=CallbackQuery(
            id=f"cb{next(_update_ids)}",
            from_user=user,
            chat_instance="ci",
            data=data,
            message=InaccessibleMessage(chat=Chat(id=user.id, type="private"), message_id=1, date=0),
        ),
    )
```

- [ ] **Step 2: Тестовий стенд**

`tests/bot_harness.py`:

```python
from datetime import datetime
from typing import Any

from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, Update, User as TgUser
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pokazun.alerts import AlertService
from pokazun.bot.factory import build_dispatcher
from pokazun.bot.handlers import build_routers
from pokazun.config import Settings
from pokazun.db.models import ObjectState, Search
from pokazun.users.repository import touch_user
from tests.tg import callback_update, make_bot, message_update

DEV_SETTINGS = {
    "env": "dev",
    "bot_token": "42:TEST",
    "database_url": "postgresql+asyncpg://unused",
    "telegram_mode": "polling",
}


class Harness:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], now: datetime) -> None:
        self.bot, self.tg = make_bot()
        self.now = now
        self.dp = build_dispatcher(
            settings=Settings(**DEV_SETTINGS),
            sessionmaker=sessionmaker,
            alerts=AlertService(None, None, "dev"),
            routers=build_routers(),
            clock=lambda: self.now,
        )

    async def feed(self, update: Update) -> list[Any]:
        start = len(self.tg.requests)
        await self.dp.feed_update(self.bot, update)
        return self.tg.requests[start:]

    async def send(self, text: str, *, user: TgUser | None = None) -> list[Any]:
        return await self.feed(message_update(text, user=user))

    async def click(self, data: str, *, user: TgUser | None = None, message_id: int = 777) -> list[Any]:
        return await self.feed(callback_update(data, user=user, message_id=message_id))


def of_type(requests: list[Any], method_type: type) -> list[Any]:
    return [r for r in requests if isinstance(r, method_type)]


def inline(markup: InlineKeyboardMarkup | None) -> list[tuple[str, str]]:
    if markup is None:
        return []
    return [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row]


def reply(markup: ReplyKeyboardMarkup) -> list[str]:
    return [b.text for row in markup.keyboard for b in row]


async def seed_search(
    sessionmaker: async_sessionmaker[AsyncSession],
    telegram_user_id: int,
    *,
    rooms: list[int],
    conditions: list[str],
    low: int,
    high: int,
    now: datetime,
) -> int:
    async with sessionmaker() as s, s.begin():
        user = await touch_user(s, telegram_user_id=telegram_user_id, username=None, first_name=None, now=now)
        s.add(
            Search(
                user_id=user.id, rooms=rooms, conditions=conditions, price_low=low, price_high=high,
                baseline_at=now, confirmed_at=now,
            )
        )
        return user.id


async def seed_objects(sessionmaker: async_sessionmaker[AsyncSession], rows: list[dict[str, Any]]) -> None:
    defaults = {"eligible": True, "public": {}}
    async with sessionmaker() as s, s.begin():
        await s.execute(
            insert(ObjectState),
            [{**defaults, "airtable_record_id": f"rec{i}", "object_code": i, **row} for i, row in enumerate(rows, 1)],
        )
```

Кожен рядок `seed_objects` має містити `synced_at`.

- [ ] **Step 3: Тест**

`tests/test_handlers_start.py`:

```python
from datetime import UTC, datetime

import pytest
from aiogram.methods import SendMessage

from pokazun.bot import texts
from pokazun.bot.keyboards import RoomsCb
from tests.bot_harness import Harness, inline, of_type, reply, seed_search
from tests.tg import TG_USER_ID

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def h(sessionmaker) -> Harness:
    return Harness(sessionmaker, T0)


async def test_start_new_user(h):
    [msg] = of_type(await h.send("/start"), SendMessage)
    assert msg.text == texts.WELCOME
    assert reply(msg.reply_markup) == [texts.BTN_FIND, texts.BTN_SELL, texts.BTN_HELP]


async def test_start_with_deep_link_payload(h):
    [msg] = of_type(await h.send("/start promo"), SendMessage)
    assert msg.text == texts.WELCOME


async def test_start_user_with_search(h, sessionmaker):
    await seed_search(sessionmaker, TG_USER_ID, rooms=[2], conditions=["residential"], low=2, high=4, now=T0)
    [msg] = of_type(await h.send("/start"), SendMessage)
    assert reply(msg.reply_markup) == [texts.BTN_MY_SEARCH, texts.BTN_SAVED, texts.BTN_SELL, texts.BTN_HELP]


async def test_find_shows_rooms_step(h):
    [msg] = of_type(await h.send(texts.BTN_FIND), SendMessage)
    assert msg.text == texts.ROOMS_PROMPT
    assert [t for t, _ in inline(msg.reply_markup)] == [
        "👉 1 кімната", "👉 2 кімнати", "👉 3 кімнати", "👉 4+ кімнати",
    ]


async def test_find_resumes_draft(h):
    await h.send(texts.BTN_FIND)
    await h.click(RoomsCb(value=2, on=True).pack())
    [msg] = of_type(await h.send(texts.BTN_FIND), SendMessage)
    assert msg.text == texts.ROOMS_PROMPT
    assert ("✅ 2 кімнати", RoomsCb(value=2, on=False).pack()) in inline(msg.reply_markup)


async def test_find_with_active_search_opens_edit_menu(h, sessionmaker):
    await seed_search(sessionmaker, TG_USER_ID, rooms=[2], conditions=["residential"], low=2, high=4, now=T0)
    [msg] = of_type(await h.send(texts.BTN_FIND), SendMessage)
    assert msg.text.startswith("Ваші параметри пошуку:")


async def test_unknown_text_gets_menu_hint(h):
    [msg] = of_type(await h.send("привіт"), SendMessage)
    assert msg.text == texts.MENU_HINT
    assert reply(msg.reply_markup)[0] == texts.BTN_FIND
```

- [ ] **Step 4: Запустити — має впасти**

Run: `uv run pytest tests/test_handlers_start.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pokazun.bot.handlers.search_setup'`.

- [ ] **Step 5: Реалізація хендлерів**

`src/pokazun/bot/handlers/search_setup.py`:

```python
"""Start, menu, the three filters, summary, editing and search confirmation (Д1 §2–§5.2, §5.4; Д2 §7, §23)."""

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
    """The locked draft if it is at `step`; otherwise re-renders the real current step (stale keyboard)."""
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
    callback: CallbackQuery, callback_data: ConditionCb, session: AsyncSession, db_user: User, bot: Bot
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
    router.callback_query.register(on_reset_price, StepCb.filter(F.action == StepAction.RESET_PRICE))
    router.callback_query.register(on_next, StepCb.filter(F.action == StepAction.NEXT))
    router.callback_query.register(on_edit, StepCb.filter(F.action == StepAction.EDIT))
    router.callback_query.register(on_goto, StepCb.filter(F.action.in_(set(_GOTO))))
    router.callback_query.register(on_save, StepCb.filter(F.action == StepAction.SAVE))
    router.callback_query.register(on_back, StepCb.filter(F.action == StepAction.BACK))
    router.callback_query.register(on_start_search, StepCb.filter(F.action == StepAction.START_SEARCH))
    return router
```

`src/pokazun/bot/handlers/fallback.py`:

```python
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
```

`src/pokazun/bot/handlers/__init__.py` — повна нова версія:

```python
from aiogram import Router

from pokazun.bot.handlers import fallback, search_setup


def build_routers() -> list[Router]:
    """Production routers in priority order. New feature routers go before the fallback router."""
    return [search_setup.build_router(), fallback.build_router()]
```

- [ ] **Step 6: Запустити — має пройти**

Run: `uv run pytest tests/test_handlers_start.py -v`
Expected: 7 passed.

- [ ] **Step 7: Commit**

```bash
git add src/pokazun/bot/handlers tests/tg.py tests/bot_harness.py tests/test_handlers_start.py
git commit -m "feat: start, main menu and search setup handlers"
```

---

### Task 6: Хендлери фільтрів — поведінка кліків

**Files:**
- Test: `tests/test_handlers_filters.py`
- (Код — з Task 5; тут перевіряємо поведінку фільтрів і правимо хендлери, якщо тест виявить розбіжність.)

**Interfaces:**
- Consumes: `Harness` і хелпери (Task 5), CallbackData (Task 4), `get_draft`, `view` (Task 3).

- [ ] **Step 1: Тест**

`tests/test_handlers_filters.py`:

```python
from datetime import UTC, datetime

import pytest
from aiogram.methods import AnswerCallbackQuery, EditMessageReplyMarkup, EditMessageText, SendMessage
from sqlalchemy import select

from pokazun.bot import texts
from pokazun.bot.keyboards import ConditionCb, PriceCb, RoomsCb, StepAction, StepCb
from pokazun.db.models import User
from pokazun.search.filters import ConditionGroup, PriceRange, RoomOption
from pokazun.search.service import get_draft, view
from pokazun.search.steps import Step
from tests.bot_harness import Harness, inline, of_type
from tests.tg import inaccessible_callback_update

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
NEXT = StepCb(action=StepAction.NEXT).pack()


@pytest.fixture
async def h(sessionmaker) -> Harness:
    harness = Harness(sessionmaker, T0)
    await harness.send(texts.BTN_FIND)
    return harness


async def draft_view(sessionmaker):
    async with sessionmaker() as s:
        user = await s.scalar(select(User))
        return view(await get_draft(s, user.id))


async def test_room_toggle_updates_markup_only(h, sessionmaker):
    requests = await h.click(RoomsCb(value=2, on=True).pack())
    [edit] = of_type(requests, EditMessageReplyMarkup)
    assert edit.message_id == 777
    buttons = inline(edit.reply_markup)
    assert ("✅ 2 кімнати", RoomsCb(value=2, on=False).pack()) in buttons
    assert (texts.BTN_NEXT, NEXT) in buttons
    assert of_type(requests, EditMessageText) == []
    assert len(of_type(requests, AnswerCallbackQuery)) == 1

    [edit] = of_type(await h.click(RoomsCb(value=2, on=False).pack()), EditMessageReplyMarkup)
    assert (texts.BTN_NEXT, NEXT) not in inline(edit.reply_markup)


async def test_duplicate_click_is_idempotent(h, sessionmaker):
    await h.click(RoomsCb(value=2, on=True).pack())
    requests = await h.click(RoomsCb(value=2, on=True).pack())
    assert of_type(requests, EditMessageReplyMarkup) == []
    assert (await draft_view(sessionmaker)).rooms == {RoomOption.TWO}


async def test_next_without_selection_stays(h, sessionmaker):
    await h.click(NEXT)
    assert (await draft_view(sessionmaker)).step is Step.ROOMS


async def test_next_moves_to_condition_then_price(h, sessionmaker):
    await h.click(RoomsCb(value=1, on=True).pack())
    [edit] = of_type(await h.click(NEXT), EditMessageText)
    assert edit.text == texts.CONDITION_PROMPT
    assert [t for t, _ in inline(edit.reply_markup)] == ["👉 Житловий стан", "👉 Після забудовника"]

    await h.click(ConditionCb(value="developer", on=True).pack())
    await h.click(ConditionCb(value="residential", on=True).pack())
    [edit] = of_type(await h.click(NEXT), EditMessageText)
    assert edit.text == texts.PRICE_PROMPT
    v = await draft_view(sessionmaker)
    assert v.conditions == {ConditionGroup.DEVELOPER, ConditionGroup.RESIDENTIAL}


async def go_to_price(h):
    await h.click(RoomsCb(value=1, on=True).pack())
    await h.click(NEXT)
    await h.click(ConditionCb(value="residential", on=True).pack())
    await h.click(NEXT)


async def test_price_gap_fill_and_edges(h, sessionmaker):
    await go_to_price(h)
    [edit] = of_type(await h.click(PriceCb(low=2, high=2).pack()), EditMessageReplyMarkup)
    by_text = dict(inline(edit.reply_markup))
    assert texts.BTN_RESET_PRICE in by_text
    [edit] = of_type(await h.click(by_text["👉 41–55 тис. $"]), EditMessageReplyMarkup)
    labels = [t for t, _ in inline(edit.reply_markup)]
    assert {"✅ 21–30 тис. $", "✅ 31–40 тис. $", "✅ 41–55 тис. $"} <= set(labels)
    assert (await draft_view(sessionmaker)).price == PriceRange(2, 4)

    interior = dict(inline(edit.reply_markup))["✅ 31–40 тис. $"]
    requests = await h.click(interior)
    assert of_type(requests, EditMessageReplyMarkup) == []
    assert (await draft_view(sessionmaker)).price == PriceRange(2, 4)

    edge = dict(inline(edit.reply_markup))["✅ 21–30 тис. $"]
    await h.click(edge)
    assert (await draft_view(sessionmaker)).price == PriceRange(3, 4)

    await h.click(StepCb(action=StepAction.RESET_PRICE).pack())
    assert (await draft_view(sessionmaker)).price is None


async def test_invalid_price_payload_ignored(h, sessionmaker):
    await go_to_price(h)
    await h.click(PriceCb(low=5, high=2).pack())
    assert (await draft_view(sessionmaker)).price is None


async def test_stale_keyboard_rerenders_current_step(h, sessionmaker):
    await h.click(RoomsCb(value=1, on=True).pack())
    await h.click(NEXT)
    [edit] = of_type(await h.click(RoomsCb(value=3, on=True).pack()), EditMessageText)
    assert edit.text == texts.CONDITION_PROMPT
    v = await draft_view(sessionmaker)
    assert v.rooms == {RoomOption.ONE} and v.step is Step.CONDITION


async def test_inaccessible_message_gets_new_message(h):
    requests = await h.feed(inaccessible_callback_update(RoomsCb(value=2, on=True).pack()))
    [msg] = of_type(requests, SendMessage)
    assert msg.text == texts.ROOMS_PROMPT
    assert ("✅ 2 кімнати", RoomsCb(value=2, on=False).pack()) in inline(msg.reply_markup)
```

- [ ] **Step 2: Запустити**

Run: `uv run pytest tests/test_handlers_filters.py -v`
Expected: 8 passed. Якщо якийсь тест падає — виправити хендлер у `search_setup.py` (не тест), доки всі не пройдуть.

- [ ] **Step 3: Commit**

```bash
git add tests/test_handlers_filters.py src/pokazun/bot/handlers/search_setup.py
git commit -m "test: filter click behaviour, stale keyboards and inaccessible messages"
```

---

### Task 7: Підсумок, редагування, підтвердження і лічильник

**Files:**
- Test: `tests/test_handlers_confirm.py`
- (Код — з Task 5; правити хендлери, якщо тест виявить розбіжність.)

**Interfaces:**
- Consumes: `Harness`, `seed_search`, `seed_objects` (Task 5), `get_active_search` (Task 3).

- [ ] **Step 1: Тест**

`tests/test_handlers_confirm.py`:

```python
from datetime import UTC, datetime, timedelta

import pytest
from aiogram.enums import ChatAction
from aiogram.methods import EditMessageReplyMarkup, EditMessageText, SendChatAction, SendMessage
from sqlalchemy import func, select

from pokazun.bot import texts
from pokazun.bot.keyboards import ConditionCb, PriceCb, RoomsCb, StepAction, StepCb
from pokazun.db.models import Search, SearchDraft, SubscriptionState, User
from pokazun.search.filters import PriceRange
from tests.bot_harness import Harness, inline, of_type, reply, seed_objects, seed_search
from tests.tg import TG_USER_ID

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
T1 = T0 + timedelta(days=2)


def step(action: StepAction) -> str:
    return StepCb(action=action).pack()


async def reach_summary(h: Harness) -> list:
    await h.send(texts.BTN_FIND)
    await h.click(RoomsCb(value=2, on=True).pack())
    await h.click(RoomsCb(value=3, on=True).pack())
    await h.click(step(StepAction.NEXT))
    await h.click(ConditionCb(value="residential", on=True).pack())
    await h.click(step(StepAction.NEXT))
    await h.click(PriceCb(low=2, high=2).pack())
    await h.click(PriceCb(low=2, high=4).pack())
    return await h.click(step(StepAction.NEXT))


def objects(n_match: int) -> list[dict]:
    match = {"rooms": 2, "condition": "Євроремонт", "price_segment": 3, "synced_at": T0}
    miss = {"rooms": 1, "condition": "Євроремонт", "price_segment": 3, "synced_at": T0}
    return [match] * n_match + [miss]


@pytest.fixture
def h(sessionmaker) -> Harness:
    return Harness(sessionmaker, T0)


async def test_summary_screen_matches_spec(h):
    [edit] = of_type(await reach_summary(h), EditMessageText)
    assert edit.text == (
        "Ваш запит:\n\n"
        "👉 Кількість кімнат: 2 кімнати, 3 кімнати\n"
        "👉 Стан квартири: Житловий стан\n"
        "👉 Вартість: 21–55 тис. $\n\n"
        "Перевірте, чи все правильно. Якщо потрібно — змініть параметри пошуку."
    )
    assert [t for t, _ in inline(edit.reply_markup)] == [texts.BTN_START_SEARCH, texts.BTN_EDIT_SEARCH]


async def test_start_search_confirms_and_counts(h, sessionmaker):
    await seed_objects(sessionmaker, objects(3))
    await reach_summary(h)
    requests = await h.click(step(StepAction.START_SEARCH))

    [removed] = of_type(requests, EditMessageReplyMarkup)
    assert removed.reply_markup is None
    searching, found = of_type(requests, SendMessage)
    assert searching.text == texts.SEARCHING
    assert reply(searching.reply_markup)[:2] == [texts.BTN_MY_SEARCH, texts.BTN_SAVED]
    [typing] = of_type(requests, SendChatAction)
    assert typing.action == ChatAction.TYPING
    assert found.text.startswith("Знайшли 3 квартири за вашим запитом 🏠")
    assert inline(found.reply_markup) == [(texts.BTN_VIEW_RESULTS, step(StepAction.VIEW_RESULTS))]

    async with sessionmaker() as s:
        search = await s.scalar(select(Search))
        user = await s.scalar(select(User))
        assert await s.scalar(select(func.count()).select_from(SearchDraft)) == 0
    assert search.baseline_at == T0
    assert search.criteria.price == PriceRange(2, 4)
    assert user.subscription_state is SubscriptionState.ACTIVE


async def test_start_search_double_click(h, sessionmaker):
    await reach_summary(h)
    await h.click(step(StepAction.START_SEARCH))
    requests = await h.click(step(StepAction.START_SEARCH))
    assert of_type(requests, SendMessage) == []
    assert of_type(requests, EditMessageText) == []
    async with sessionmaker() as s:
        assert await s.scalar(select(func.count()).select_from(Search)) == 1


async def test_no_matches_message(h, sessionmaker):
    await reach_summary(h)
    requests = await h.click(step(StepAction.START_SEARCH))
    found = of_type(requests, SendMessage)[-1]
    assert found.text == texts.NOT_FOUND
    assert inline(found.reply_markup) == [(texts.BTN_EDIT_SEARCH, step(StepAction.EDIT))]


async def test_create_mode_edit_menu_roundtrip(h, sessionmaker):
    await reach_summary(h)
    [edit] = of_type(await h.click(step(StepAction.EDIT)), EditMessageText)
    assert edit.text.startswith("Ваші параметри пошуку:\n\n🛏 Кількість кімнат: 2, 3")
    [edit] = of_type(await h.click(step(StepAction.GOTO_ROOMS)), EditMessageText)
    assert edit.text == texts.ROOMS_PROMPT
    assert ("✅ 3 кімнати", RoomsCb(value=3, on=False).pack()) in inline(edit.reply_markup)
    await h.click(RoomsCb(value=3, on=False).pack())
    [edit] = of_type(await h.click(step(StepAction.NEXT)), EditMessageText)
    assert "🛏 Кількість кімнат: 2\n" in edit.text
    [edit] = of_type(await h.click(step(StepAction.SAVE)), EditMessageText)
    assert "👉 Кількість кімнат: 2 кімнати\n" in edit.text
    async with sessionmaker() as s:
        assert await s.scalar(select(func.count()).select_from(Search)) == 0


async def test_edit_active_search_and_save(h, sessionmaker):
    await seed_search(sessionmaker, TG_USER_ID, rooms=[2], conditions=["residential"], low=2, high=4, now=T0)
    await seed_objects(sessionmaker, [{"rooms": 2, "condition": "Євроремонт", "price_segment": 6, "synced_at": T0}])
    h.now = T1
    [edit] = of_type(await h.click(step(StepAction.EDIT)), EditMessageText)
    assert edit.text.startswith("Ваші параметри пошуку:")
    await h.click(step(StepAction.GOTO_PRICE))
    await h.click(PriceCb(low=2, high=6).pack())
    [edit] = of_type(await h.click(step(StepAction.NEXT)), EditMessageText)
    assert "💰 Вартість: 21–100 тис. $" in edit.text
    requests = await h.click(step(StepAction.SAVE))
    assert of_type(requests, SendMessage)[-1].text.startswith("Знайшли 1 квартиру")
    async with sessionmaker() as s:
        search = await s.scalar(select(Search))
    assert search.criteria.price == PriceRange(2, 6)
    assert search.baseline_at == T1


async def test_edit_back_keeps_search(h, sessionmaker):
    await seed_search(sessionmaker, TG_USER_ID, rooms=[2], conditions=["residential"], low=2, high=4, now=T0)
    h.now = T1
    await h.click(step(StepAction.EDIT))
    await h.click(step(StepAction.GOTO_PRICE))
    await h.click(PriceCb(low=2, high=6).pack())
    await h.click(step(StepAction.NEXT))
    [edit] = of_type(await h.click(step(StepAction.BACK)), EditMessageText)
    assert edit.text == texts.EDIT_CANCELLED
    assert edit.reply_markup is None
    async with sessionmaker() as s:
        search = await s.scalar(select(Search))
        assert await s.scalar(select(func.count()).select_from(SearchDraft)) == 0
    assert search.criteria.price == PriceRange(2, 4)
    assert search.baseline_at == T0


async def test_edit_keeps_manual_pause(h, sessionmaker):
    user_id = await seed_search(sessionmaker, TG_USER_ID, rooms=[2], conditions=["residential"], low=2, high=4, now=T0)
    async with sessionmaker() as s, s.begin():
        (await s.get(User, user_id)).subscription_state = SubscriptionState.PAUSED_BY_USER
    await h.click(step(StepAction.EDIT))
    await h.click(step(StepAction.SAVE))
    async with sessionmaker() as s:
        user = await s.get(User, user_id)
    assert user.subscription_state is SubscriptionState.PAUSED_BY_USER


async def test_edit_without_search_or_draft_does_nothing(h):
    requests = await h.click(step(StepAction.EDIT))
    assert of_type(requests, EditMessageText) == []
    assert of_type(requests, SendMessage) == []
```

- [ ] **Step 2: Запустити**

Run: `uv run pytest tests/test_handlers_confirm.py -v`
Expected: 9 passed. Якщо падає — виправити `search_setup.py` / `service.py`, не тест.

- [ ] **Step 3: Повний прогін**

Run: `uv run pytest && uv run ruff check . && uv run ruff format --check .`
Expected: усе зелене.

- [ ] **Step 4: Commit**

```bash
git add tests/test_handlers_confirm.py src/pokazun
git commit -m "test: summary, edit flows and search confirmation"
```

---

### Task 8: Ручна перевірка на staging

**Files:** немає змін коду (лише якщо перевірка виявить дефект — тоді тест + фікс окремим комітом).

- [ ] **Step 1:** `deploy/deploy.sh staging origin/main`.
- [ ] **Step 2:** З телефона тестувальника з allowlist пройти сценарії й відмітити:
  - `/start` → привітання Д1 §2, меню «🔎 Знайти квартиру / 🏠 Продати квартиру / Допомога».
  - Кімнати: 👉 → ✅, «Далі ➡️» з’являється / зникає; повідомлення не дублюються (редагується те саме).
  - Стан: обидві групи, мультивибір.
  - Ціна: «21–30» + «41–55» → «31–40» автоматично ✅; «Обнулити вибір 🔄»; зняття крайніх.
  - Закрити Telegram посеред кроку ціни → відкрити → «🔎 Знайти квартиру» → той самий крок і вибір.
  - Підсумок як у Д1 §4; «✏️ Змінити параметри пошуку» → Д1 §4.1; зміна одного параметра → повернення в меню редагування; «✅ Зберегти» → підсумок.
  - «🔎 Почати пошук» → «🔎 Шукаємо…», меню змінилось на «Мій пошук / Збережені ❤️», «Знайшли N квартир…» (N звірити з `eligible_object_count` / фільтром в Airtable).
  - Порожній результат → текст Д1 §5.4 з «✏️ Змінити параметри пошуку».
  - iOS, Android, Desktop — однаково.
- [ ] **Step 3:** Результат перевірки (ОК / дефекти) записати в PR етапу 5.

---

## Готово, коли

- `uv run pytest` зелений, ruff чистий, CI зелений.
- На staging пройдено чек-лист Task 8 на iOS, Android і Desktop.
- Тексти з таблиці «Тексти на погодження» надіслані замовнику.
