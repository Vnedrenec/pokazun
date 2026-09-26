# Етап 4. Каталог: sync, eligibility, matching — план реалізації

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Актуальний локальний стан каталогу (`object_state`) з Airtable: read-only polling кожні 5 хв + повне reconciliation раз на добу, bootstrap без розсилки, фіксація переходів (вхід / вихід / зниження ціни / повернення) для етапу 10, мапінг фільтрів і пошук збігів у PostgreSQL.

**Architecture:** `AirtableClient` читає лише поля з allowlist за field ID (`returnFieldsByFieldId=true`), без посилань на назви полів. `parse_record` будує публічну модель тільки з дозволених полів і рахує eligibility. `CatalogSync` (у процесі worker) під advisory lock вибирає режим (bootstrap / full / incremental), тягне записи з Airtable поза транзакцією, а потім в одній транзакції застосовує їх до `object_state`, передає переходи в `TransitionSink` і просуває watermark. Падіння будь-де → транзакція відкочується, наступний цикл повторює те саме без дублів. Фільтри пошуку — чиста доменна модель у `pokazun/search/filters.py`, спільна для бота, SQL-пошуку і подій.

**Tech Stack:** як на етапі 3 (aiohttp-клієнт, SQLAlchemy 2 async, PostgreSQL JSONB).

**Spec:** `docs/plans/2026-09-25-pokazun-roadmap.md` (етап 4) + Д2 §3–§5, §8, §9, §10 (сортування), §11 (правила переходів), §17 (некоректні дані), §19 (data-quality warnings).

**Передумова:** етап 3 виконано (`docs/plans/2026-09-26-stage-3-foundation.md`). Використовуються: `Settings`, `get_logger`, `redact_text`, `Alert`, `AlertService`, `Base`, фікстури `sessionmaker` / `engine`, `tests.tg`, `Job`, `build_jobs`, `HealthRegistry`.

## Global Constraints

- Усі правила етапу 3 (production-якість, секрети лише в env, UTC `timestamptz`, `now` параметром, без «MVP»).
- Airtable лише читаємо: тільки `GET /v0/{base}/{table}`; жодних POST / PATCH / DELETE. Токен — read-only (`data.records:read`, `schema.bases:read`) (Д2 §20).
- Base `appLx30Y68Qy0I9Au`, table `tblgO046VTYnqOgZa` (Д2 §3).
- Eligibility рівно: `Тип_Нерухомості = Квартири` AND `Населений пункт = Чернігів` AND `Етап = Відзнято` AND `Статус = Активний продаж`. «Статус зйомки» не запитується і не впливає (Д2 §3).
- Запитуються й читаються лише field ID з Д2 §4. Телефони / ім’я власника, нотатки та інші поля не потрапляють ні в `object_state`, ні в логи (Д2 §4).
- Кімнати: 1, 2, 3; «4+» = усі значення ≥ 4. «Житловий стан» = Житловий стан, Косметичний ремонт, Євроремонт, Авторський проект, Аварійний стан; «Після забудовника» = Після будівельників, Під чистову обробку. Ціна — за single-select «Діапазон цін» (8 значень, точні рядки з Д2 §5.3), безперервний діапазон (Д2 §5).
- Сортування видачі: «Дата реєстрації» DESC → «Код об’єкту» DESC (Д2 §10).
- Інтервал sync — 5 хв; повне reconciliation — не рідше 1 разу на добу (Д2 §8).
- Bootstrap не створює подій / розсилок (Д2 §8).
- Повернення в каталог ≥ 30 днів → `REACTIVATED_30D`; < 30 днів → лише ручна доступність (Д2 §9, §11.3).
- Некоректний запис не валить sync: пропускається або зберігається частково + data-quality warning у лог (Д2 §17, §19).
- Алерт після 3+ невдалих sync поспіль, з debounce (Д2 §18).

## Review Focus

- Поле eligibility прийшло з Airtable як lookup / multiple select (список рядків), а не рядок → об’єкт однаково коректно визнається eligible. Тест: Task 2 `test_eligibility_accepts_list_values`.
- Запис видалили з Airtable (а не змінили статус) → інкрементальний sync його не бачить, але найближче повне reconciliation переводить його в `CATALOG_LEFT`. Тест: Task 6 `test_full_reconcile_marks_deleted_as_left`.
- Sync упав після часткового застосування (помилка в sink / БД) → нічого не збережено наполовину, watermark не зсунувся, наступний цикл дає ті самі переходи рівно один раз. Тест: Task 6 `test_failure_mid_apply_rolls_back_and_retries_cleanly`.
- Два запуски sync перекрилися (повільний цикл + наступний тик, або два воркери після помилкового деплою) → другий пропускається, стан не псується. Тест: Task 6 `test_concurrent_run_is_skipped`.
- Airtable відповів 429 (ліміт 5 запитів/с) → клієнт чекає 30 с і продовжує, sync не вважається невдалим. Тест: Task 4 `test_retries_after_rate_limit`.

---

## Структура файлів

```
src/pokazun/search/__init__.py
src/pokazun/search/filters.py        RoomOption, ConditionGroup, PriceSegment, PriceRange, click_price, SearchCriteria
src/pokazun/catalog/__init__.py
src/pokazun/catalog/fields.py        field ID з Д2 §4, FETCH_FIELDS, ELIGIBILITY
src/pokazun/catalog/record.py        CatalogRecord, ParseResult, parse_record, is_eligible
src/pokazun/catalog/airtable.py      AirtableClient, AirtableError, modified_after_formula
src/pokazun/catalog/state.py         Transition*, detect_transitions, load_states, apply_record, mark_missing_as_left
src/pokazun/catalog/sync.py          CatalogSync, SyncMode, SyncReport, RecordSource, TransitionSink
src/pokazun/catalog/matching.py      criteria_clause, count_matching, matching_record_ids
src/pokazun/catalog/health.py        catalog_health, check_sync_freshness
src/pokazun/db/models/catalog.py     ObjectState, SyncState
migrations/versions/0002_catalog.py
Modify: src/pokazun/db/models/__init__.py, src/pokazun/config.py, src/pokazun/worker/jobs.py,
        src/pokazun/worker/main.py, src/pokazun/app.py, .env.example
tests/clock.py, tests/catalog_factory.py, tests/test_filters.py, tests/test_record.py,
tests/test_airtable_client.py, tests/test_catalog_state.py, tests/test_catalog_sync.py,
tests/test_matching.py, tests/test_catalog_health.py
Modify: tests/test_config.py, tests/test_worker_jobs.py, tests/test_bot_middlewares.py
```

---

### Task 1: Доменна модель фільтрів

**Files:**
- Create: `src/pokazun/search/__init__.py` (порожній), `src/pokazun/search/filters.py`
- Test: `tests/test_filters.py`

**Interfaces:**
- Produces:
  - `RoomOption(IntEnum)`: `ONE=1`, `TWO=2`, `THREE=3`, `FOUR_PLUS=4`; `.matches(rooms: int) -> bool`.
  - `ConditionGroup(StrEnum)`: `RESIDENTIAL="residential"`, `DEVELOPER="developer"`; `CONDITION_GROUP_VALUES: dict[ConditionGroup, frozenset[str]]`; `KNOWN_CONDITIONS: frozenset[str]`.
  - `PriceSegment(index: int, airtable_value: str, label: str, low_k: int | None, high_k: int | None)`; `PRICE_SEGMENTS: tuple[PriceSegment, ...]` (індекси 0–7); `SEGMENT_INDEX_BY_AIRTABLE: dict[str, int]`.
  - `PriceRange(low: int, high: int)` — індекси сегментів, `low <= high`; `.contains(index) -> bool`; `.segments -> tuple[PriceSegment, ...]`.
  - `click_price(current: PriceRange | None, index: int) -> PriceRange | None`.
  - `SearchCriteria(rooms: frozenset[RoomOption], conditions: frozenset[ConditionGroup], price: PriceRange)`; `.condition_values -> frozenset[str]`; `.matches(*, rooms: int | None, condition: str | None, price_segment: int | None) -> bool`.

- [ ] **Step 1: Тест**

`tests/test_filters.py`:

```python
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
```

- [ ] **Step 2: Запустити — має впасти**

Run: `uv run pytest tests/test_filters.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pokazun.search'`.

- [ ] **Step 3: Реалізація**

`src/pokazun/search/filters.py`:

```python
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
    """Unselected segment extends the range; an edge segment narrows it; an interior one changes nothing."""
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

    def matches(self, *, rooms: int | None, condition: str | None, price_segment: int | None) -> bool:
        return (
            rooms is not None
            and any(option.matches(rooms) for option in self.rooms)
            and condition in self.condition_values
            and price_segment is not None
            and self.price.contains(price_segment)
        )
```

- [ ] **Step 4: Запустити — має пройти**

Run: `uv run pytest tests/test_filters.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pokazun/search tests/test_filters.py
git commit -m "feat: search filter domain model with contiguous price ranges"
```

---

### Task 2: Allowlist полів, розбір запису Airtable, eligibility

**Files:**
- Create: `src/pokazun/catalog/__init__.py` (порожній), `src/pokazun/catalog/fields.py`, `src/pokazun/catalog/record.py`
- Create: `tests/catalog_factory.py`
- Test: `tests/test_record.py`

**Interfaces:**
- Consumes: `KNOWN_CONDITIONS`, `SEGMENT_INDEX_BY_AIRTABLE` (Task 1).
- Produces:
  - `pokazun.catalog.fields`: константи field ID, `FETCH_FIELDS: tuple[str, ...]`, `ELIGIBILITY: dict[str, str]`.
  - `CatalogRecord(record_id: str, code: int, eligible: bool, rooms: int | None, condition: str | None, price_segment: int | None, price_usd: Decimal | None, registered_at: datetime | None, modified_at: datetime | None, public: dict[str, Any])`.
  - `ParseResult(record_id: str, record: CatalogRecord | None, warnings: tuple[str, ...])`.
  - `parse_record(raw: Mapping[str, Any]) -> ParseResult`; `is_eligible(fields: Mapping[str, Any]) -> bool`.
  - Ключі `CatalogRecord.public`: `title`, `description`, `district`, `street`, `floor`, `floors_total`, `area_m2`, `video_url`, `photos` (список `{"id", "url", "filename", "width", "height"}`).
  - Коди warnings: `missing_code`, `invalid_rooms`, `missing_condition`, `unknown_condition`, `empty_price_segment`, `unknown_price_segment`, `missing_price`, `missing_registered_at`, `no_photo`.
  - `tests.catalog_factory.raw_record(...) -> dict` — сирий запис у форматі Airtable API.

- [ ] **Step 1: Фабрика тестових записів**

`tests/catalog_factory.py`:

```python
from typing import Any

from pokazun.catalog import fields as f

OWNER_PHONE_FIELD = "fldOwnerPhoneXXXX"  # not in the allowlist: must never leak
SHOOTING_STATUS_FIELD = "fldShootingStatus"  # «Статус зйомки»: must be ignored


def raw_record(
    record_id: str = "rec001",
    code: Any = 620,
    *,
    property_type: Any = "Квартири",
    city: Any = "Чернігів",
    stage: Any = "Відзнято",
    status: Any = "Активний продаж",
    rooms: Any = 2,
    condition: Any = "Євроремонт",
    segment: Any = "41 - 55 тис.",
    price: Any = 55000,
    registered: Any = "2026-09-01",
    photos: int = 2,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    values = {
        f.CODE: code,
        f.PROPERTY_TYPE: property_type,
        f.CITY: city,
        f.STAGE: stage,
        f.STATUS: status,
        f.ROOMS: rooms,
        f.CONDITION: condition,
        f.PRICE_SEGMENT: segment,
        f.PRICE_USD: price,
        f.REGISTERED_AT: registered,
        f.DISTRICT: "Центр",
        f.STREET: "вул. П’ятницька",
        f.FLOOR: 1,
        f.FLOORS_TOTAL: 9,
        f.AREA: 68,
        f.TITLE: "2-кімнатна квартира",
        f.DESCRIPTION: "Світла квартира біля парку.",
        f.LAST_MODIFIED: "2026-09-20T10:00:00.000Z",
        f.PHOTOS: [
            {
                "id": f"att{i}",
                "url": f"https://v5.airtableusercontent.com/{record_id}/{i}.jpg",
                "filename": f"{i}.jpg",
                "width": 1280,
                "height": 960,
                "type": "image/jpeg",
            }
            for i in range(photos)
        ],
        OWNER_PHONE_FIELD: "+380671112233",
        SHOOTING_STATUS_FIELD: "Не розміщено",
    }
    values.update(extra or {})
    return {
        "id": record_id,
        "createdTime": "2026-09-01T08:00:00.000Z",
        "fields": {k: v for k, v in values.items() if v is not None},
    }
```

- [ ] **Step 2: Тест**

`tests/test_record.py`:

```python
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from pokazun.catalog import fields as f
from pokazun.catalog.record import parse_record
from tests.catalog_factory import OWNER_PHONE_FIELD, raw_record


def test_parses_eligible_record():
    result = parse_record(raw_record())
    rec = result.record
    assert result.warnings == ()
    assert rec.record_id == "rec001"
    assert rec.code == 620
    assert rec.eligible is True
    assert rec.rooms == 2
    assert rec.condition == "Євроремонт"
    assert rec.price_segment == 4
    assert rec.price_usd == Decimal("55000")
    assert rec.registered_at == datetime(2026, 9, 1, tzinfo=UTC)
    assert rec.modified_at == datetime(2026, 9, 20, 10, 0, tzinfo=UTC)
    assert rec.public["street"] == "вул. П’ятницька"
    assert rec.public["photos"][0] == {
        "id": "att0",
        "url": "https://v5.airtableusercontent.com/rec001/0.jpg",
        "filename": "0.jpg",
        "width": 1280,
        "height": 960,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("property_type", "Будинки"),
        ("city", "Київ"),
        ("stage", "Не відзнято"),
        ("status", "Продано"),
    ],
)
def test_each_eligibility_condition_required(field, value):
    assert parse_record(raw_record(**{field: value})).record.eligible is False


def test_shooting_status_is_ignored():
    rec = parse_record(raw_record()).record
    assert rec.eligible is True  # factory sets «Статус зйомки» = «Не розміщено»


def test_eligibility_accepts_list_values():
    raw = raw_record(property_type=["Квартири"], city=["Чернігів"], stage=["Відзнято"], status=["Активний продаж"])
    assert parse_record(raw).record.eligible is True


def test_missing_eligibility_field_means_not_eligible():
    assert parse_record(raw_record(status=None)).record.eligible is False


def test_missing_code_skips_record():
    result = parse_record(raw_record(code=None))
    assert result.record is None
    assert result.warnings == ("missing_code",)


def test_code_as_string_and_float():
    assert parse_record(raw_record(code="621")).record.code == 621
    assert parse_record(raw_record(code=622.0)).record.code == 622


def test_private_fields_never_leak():
    raw = raw_record()
    rec = parse_record(raw).record
    assert "+380671112233" not in repr(rec)
    assert OWNER_PHONE_FIELD not in repr(rec)
    assert set(rec.public) == {
        "title",
        "description",
        "district",
        "street",
        "floor",
        "floors_total",
        "area_m2",
        "video_url",
        "photos",
    }


def test_all_price_segments_map():
    values = ["до 15 тис", "16-20 тис.", "21 - 30 тис.", "31 - 40 тис.", "41 - 55 тис.", "56 - 70 тис.", "71 - 100 тис.", "101 тис і вище"]
    assert [parse_record(raw_record(segment=v)).record.price_segment for v in values] == list(range(8))


def test_data_quality_warnings_for_eligible():
    result = parse_record(
        raw_record(rooms=None, condition="Щось нове", segment=None, price=None, registered=None, photos=0)
    )
    assert result.record is not None
    assert set(result.warnings) == {
        "invalid_rooms",
        "unknown_condition",
        "empty_price_segment",
        "missing_price",
        "missing_registered_at",
        "no_photo",
    }
    assert result.record.price_segment is None


def test_unknown_segment_and_missing_condition():
    result = parse_record(raw_record(segment="200+ тис.", condition=None))
    assert set(result.warnings) == {"unknown_price_segment", "missing_condition"}


def test_no_warnings_for_ineligible_record():
    result = parse_record(raw_record(status="Продано", rooms=None, segment=None, photos=0))
    assert result.warnings == ()


def test_fetch_fields_are_exactly_the_allowlist_we_use():
    assert set(f.FETCH_FIELDS) == {
        f.CODE, f.REGISTERED_AT, f.PROPERTY_TYPE, f.CITY, f.DISTRICT, f.STREET, f.ROOMS,
        f.FLOOR, f.FLOORS_TOTAL, f.CONDITION, f.STATUS, f.STAGE, f.PRICE_USD,
        f.PRICE_SEGMENT, f.AREA, f.TITLE, f.DESCRIPTION, f.VIDEO_URL, f.PHOTOS, f.LAST_MODIFIED,
    }
```

- [ ] **Step 3: Запустити — має впасти**

Run: `uv run pytest tests/test_record.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pokazun.catalog'`.

- [ ] **Step 4: Реалізація `fields.py`**

```python
"""Airtable field IDs from Д2 §4. Only these IDs are requested (fields[]) and read."""

CODE = "fldMylKHvRpyGlPyy"  # Код об'єкту — public object number
REGISTERED_AT = "fld9Fcm7SADagTobq"  # Дата реєстрації — sort key
PROPERTY_TYPE = "fldMMzu2NwGIwxGST"  # Тип_Нерухомості — eligibility
CITY = "fldPUJfWnYgeCYldL"  # Населений пункт — eligibility
DISTRICT = "fldXbiZpZGEpB4w8X"  # Район — card
STREET = "fldO5g8VzY94rnU9q"  # Вулиця — card
ROOMS = "fldjFTHg2mbioBVry"  # К-ть кімнат — filter + card
FLOOR = "fldEljxNazof4GawA"  # Поверх — card
FLOORS_TOTAL = "fldsJn1p29TDO8gpZ"  # Поверховість — card
CONDITION = "fldTjxCEHidcYjtD1"  # Стан нерухомості — filter + card
STATUS = "fldGYbuztVNjfLZUe"  # Статус — eligibility
STAGE = "fldxM11IWXSDkzptj"  # Етап — eligibility
PRICE_USD = "fldNnqL9CYwOv0g2V"  # Ціна (USD) — card + price-drop events
PRICE_SEGMENT = "fldvk07K5MGxyBNpz"  # Діапазон цін — price filter
AREA = "fldZ2CAZ7LyIOEroD"  # Загальна S (м2) — card
TITLE = "flduOsuSjp6gobDKu"  # Заголовок (для сайту)
DESCRIPTION = "fldbWvcRiP62Baccw"  # Опис (для сайту)
VIDEO_URL = "fld2wkj61Es2ilMtV"  # Відео Link
PHOTOS = "fldWVzagTDkNuzOty"  # Photo
LAST_MODIFIED = "fld90A1d5WOBrowyQ"  # Last Modified Time
# Allowlisted in Д2 §4 but not fetched until a feature needs them:
REALTOR = "fldojdt3iwj67qkUW"  # Рієлтор — service context
RECORD_ID = "fldgfV9EWXjO5Z86l"  # Record ID — duplicates API record.id

FETCH_FIELDS: tuple[str, ...] = (
    CODE, REGISTERED_AT, PROPERTY_TYPE, CITY, DISTRICT, STREET, ROOMS, FLOOR, FLOORS_TOTAL,
    CONDITION, STATUS, STAGE, PRICE_USD, PRICE_SEGMENT, AREA, TITLE, DESCRIPTION, VIDEO_URL,
    PHOTOS, LAST_MODIFIED,
)

ELIGIBILITY: dict[str, str] = {
    PROPERTY_TYPE: "Квартири",
    CITY: "Чернігів",
    STAGE: "Відзнято",
    STATUS: "Активний продаж",
}
```

- [ ] **Step 5: Реалізація `record.py`**

```python
"""Airtable record → CatalogRecord. Reads allowlisted field IDs only; never raises on bad data."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from pokazun.catalog import fields as f
from pokazun.search.filters import KNOWN_CONDITIONS, SEGMENT_INDEX_BY_AIRTABLE


@dataclass(frozen=True)
class CatalogRecord:
    record_id: str
    code: int
    eligible: bool
    rooms: int | None
    condition: str | None
    price_segment: int | None
    price_usd: Decimal | None
    registered_at: datetime | None
    modified_at: datetime | None
    public: dict[str, Any]


@dataclass(frozen=True)
class ParseResult:
    record_id: str
    record: CatalogRecord | None
    warnings: tuple[str, ...]


def _texts(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value.strip()}
    if isinstance(value, list):
        return {v.strip() for v in value if isinstance(v, str)}
    return set()


def _text(value: Any) -> str | None:
    if isinstance(value, list) and len(value) == 1:
        value = value[0]
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            return Decimal(value.strip())
        except InvalidOperation:
            return None
    return None


def _datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        if len(value) == 10:
            d = date.fromisoformat(value)
            return datetime(d.year, d.month, d.day, tzinfo=UTC)
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else None


def _scalar(value: Any) -> str | int | float | None:
    if isinstance(value, list) and len(value) == 1:
        value = value[0]
    if isinstance(value, bool):
        return None
    return value if isinstance(value, str | int | float) else None


def _photos(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        {
            "id": item.get("id"),
            "url": item["url"],
            "filename": item.get("filename"),
            "width": item.get("width"),
            "height": item.get("height"),
        }
        for item in value
        if isinstance(item, dict) and isinstance(item.get("url"), str)
    ]


def is_eligible(fields: Mapping[str, Any]) -> bool:
    return all(expected in _texts(fields.get(fid)) for fid, expected in f.ELIGIBILITY.items())


def parse_record(raw: Mapping[str, Any]) -> ParseResult:
    record_id = str(raw["id"])
    fields: Mapping[str, Any] = raw.get("fields") or {}

    code = _int(fields.get(f.CODE))
    if code is None:
        return ParseResult(record_id, None, ("missing_code",))

    eligible = is_eligible(fields)
    rooms = _int(fields.get(f.ROOMS))
    if rooms is not None and rooms < 1:
        rooms = None
    condition = _text(fields.get(f.CONDITION))
    segment_text = _text(fields.get(f.PRICE_SEGMENT))
    segment = SEGMENT_INDEX_BY_AIRTABLE.get(segment_text) if segment_text else None
    price = _decimal(fields.get(f.PRICE_USD))
    registered_at = _datetime(fields.get(f.REGISTERED_AT))
    photos = _photos(fields.get(f.PHOTOS))

    warnings: list[str] = []
    if eligible:
        if rooms is None:
            warnings.append("invalid_rooms")
        if condition is None:
            warnings.append("missing_condition")
        elif condition not in KNOWN_CONDITIONS:
            warnings.append("unknown_condition")
        if segment_text is None:
            warnings.append("empty_price_segment")
        elif segment is None:
            warnings.append("unknown_price_segment")
        if price is None:
            warnings.append("missing_price")
        if registered_at is None:
            warnings.append("missing_registered_at")
        if not photos:
            warnings.append("no_photo")

    public = {
        "title": _text(fields.get(f.TITLE)),
        "description": _text(fields.get(f.DESCRIPTION)),
        "district": _text(fields.get(f.DISTRICT)),
        "street": _text(fields.get(f.STREET)),
        "floor": _scalar(fields.get(f.FLOOR)),
        "floors_total": _scalar(fields.get(f.FLOORS_TOTAL)),
        "area_m2": _scalar(fields.get(f.AREA)),
        "video_url": _text(fields.get(f.VIDEO_URL)),
        "photos": photos,
    }
    record = CatalogRecord(
        record_id=record_id,
        code=code,
        eligible=eligible,
        rooms=rooms,
        condition=condition,
        price_segment=segment,
        price_usd=price,
        registered_at=registered_at,
        modified_at=_datetime(fields.get(f.LAST_MODIFIED)),
        public=public,
    )
    return ParseResult(record_id, record, tuple(warnings))
```

- [ ] **Step 6: Запустити — має пройти**

Run: `uv run pytest tests/test_record.py -v`
Expected: 16 passed.

- [ ] **Step 7: Commit**

```bash
git add src/pokazun/catalog tests/catalog_factory.py tests/test_record.py
git commit -m "feat: airtable field allowlist, record parsing and eligibility"
```

---

### Task 3: Моделі `object_state` і `sync_state`

**Files:**
- Create: `src/pokazun/db/models/catalog.py`, `migrations/versions/0002_catalog.py`
- Modify: `src/pokazun/db/models/__init__.py`
- Test: `tests/test_catalog_models.py`

**Interfaces:**
- Produces:
  - `ObjectState`: `id`, `airtable_record_id` (unique), `object_code`, `eligible`, `rooms`, `condition`, `price_segment`, `price_usd` (остання збережена ціна), `registered_at`, `airtable_modified_at`, `public` (JSONB), `catalog_entered_at` (перший вхід у каталог), `eligible_since` (початок поточного перебування), `inactive_since` (коли вийшов; `None`, поки eligible), `synced_at`, `created_at`, `updated_at`.
  - `SyncState`: `source` (PK), `watermark`, `last_successful_sync_at`, `last_full_sync_at`, `bootstrapped_at`, `consecutive_failures`, `last_error`, `updated_at`.

- [ ] **Step 1: Тест**

`tests/test_catalog_models.py`:

```python
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from pokazun.db.models import ObjectState, SyncState

T0 = datetime(2026, 10, 1, tzinfo=UTC)


async def test_object_state_roundtrip(sessionmaker):
    async with sessionmaker() as s, s.begin():
        s.add(
            ObjectState(
                airtable_record_id="rec1",
                object_code=620,
                eligible=True,
                price_usd=Decimal("55000.50"),
                public={"street": "вул. П’ятницька", "photos": []},
                synced_at=T0,
            )
        )
        s.add(SyncState(source="airtable_objects"))
    async with sessionmaker() as s:
        row = await s.scalar(select(ObjectState))
        state = await s.get(SyncState, "airtable_objects")
    assert row.public["street"] == "вул. П’ятницька"
    assert row.price_usd == Decimal("55000.50")
    assert state.consecutive_failures == 0


async def test_record_id_unique(sessionmaker):
    async with sessionmaker() as s:
        s.add_all(
            [
                ObjectState(airtable_record_id="rec1", object_code=1, synced_at=T0),
                ObjectState(airtable_record_id="rec1", object_code=2, synced_at=T0),
            ]
        )
        with pytest.raises(IntegrityError):
            await s.flush()
```

- [ ] **Step 2: Запустити — має впасти**

Run: `uv run pytest tests/test_catalog_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'ObjectState'`.

- [ ] **Step 3: Модель**

`src/pokazun/db/models/catalog.py`:

```python
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Identity, Index, Integer, Numeric, SmallInteger, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pokazun.db.base import Base


class ObjectState(Base):
    """Technical snapshot of an Airtable object for search and events. Airtable stays the source of truth."""

    __tablename__ = "object_state"
    __table_args__ = (
        Index(
            "ix_object_state_catalog_order",
            "registered_at",
            "object_code",
            postgresql_where=text("eligible"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    airtable_record_id: Mapped[str] = mapped_column(String(32), unique=True)
    object_code: Mapped[int] = mapped_column(Integer, index=True)
    eligible: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    rooms: Mapped[int | None] = mapped_column(SmallInteger)
    condition: Mapped[str | None] = mapped_column(String(64))
    price_segment: Mapped[int | None] = mapped_column(SmallInteger)
    price_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    registered_at: Mapped[datetime | None]
    airtable_modified_at: Mapped[datetime | None]
    public: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    catalog_entered_at: Mapped[datetime | None]
    eligible_since: Mapped[datetime | None]
    inactive_since: Mapped[datetime | None]
    synced_at: Mapped[datetime]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class SyncState(Base):
    __tablename__ = "sync_state"

    source: Mapped[str] = mapped_column(String(32), primary_key=True)
    watermark: Mapped[datetime | None]
    last_successful_sync_at: Mapped[datetime | None]
    last_full_sync_at: Mapped[datetime | None]
    bootstrapped_at: Mapped[datetime | None]
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    last_error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
```

`src/pokazun/db/models/__init__.py` — повна нова версія:

```python
"""Importing this package registers every model on Base.metadata (used by Alembic and tests)."""

from pokazun.db.models.catalog import ObjectState, SyncState
from pokazun.db.models.system import ProcessedUpdate
from pokazun.db.models.users import DeliveryState, SubscriptionState, User

__all__ = [
    "DeliveryState",
    "ObjectState",
    "ProcessedUpdate",
    "SubscriptionState",
    "SyncState",
    "User",
]
```

- [ ] **Step 4: Міграція**

`migrations/versions/0002_catalog.py`:

```python
"""object_state and sync_state

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "object_state",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("airtable_record_id", sa.String(32), nullable=False),
        sa.Column("object_code", sa.Integer(), nullable=False),
        sa.Column("eligible", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("rooms", sa.SmallInteger(), nullable=True),
        sa.Column("condition", sa.String(64), nullable=True),
        sa.Column("price_segment", sa.SmallInteger(), nullable=True),
        sa.Column("price_usd", sa.Numeric(12, 2), nullable=True),
        sa.Column("registered_at", TS, nullable=True),
        sa.Column("airtable_modified_at", TS, nullable=True),
        sa.Column(
            "public",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("catalog_entered_at", TS, nullable=True),
        sa.Column("eligible_since", TS, nullable=True),
        sa.Column("inactive_since", TS, nullable=True),
        sa.Column("synced_at", TS, nullable=False),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_object_state"),
        sa.UniqueConstraint("airtable_record_id", name="uq_object_state_airtable_record_id"),
    )
    op.create_index("ix_object_state_object_code", "object_state", ["object_code"])
    op.create_index(
        "ix_object_state_catalog_order",
        "object_state",
        ["registered_at", "object_code"],
        postgresql_where=sa.text("eligible"),
    )
    op.create_table(
        "sync_state",
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("watermark", TS, nullable=True),
        sa.Column("last_successful_sync_at", TS, nullable=True),
        sa.Column("last_full_sync_at", TS, nullable=True),
        sa.Column("bootstrapped_at", TS, nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("source", name="pk_sync_state"),
    )


def downgrade() -> None:
    op.drop_table("sync_state")
    op.drop_index("ix_object_state_catalog_order", table_name="object_state")
    op.drop_index("ix_object_state_object_code", table_name="object_state")
    op.drop_table("object_state")
```

- [ ] **Step 5: Запустити — має пройти (разом із тестом дрейфу)**

Run: `uv run pytest tests/test_catalog_models.py tests/test_db_migrations.py -v`
Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add src/pokazun/db/models migrations/versions/0002_catalog.py tests/test_catalog_models.py
git commit -m "feat: object_state and sync_state tables"
```

---

### Task 4: Read-only клієнт Airtable

**Files:**
- Create: `src/pokazun/catalog/airtable.py`
- Test: `tests/test_airtable_client.py`

**Interfaces:**
- Consumes: `get_logger` (етап 3).
- Produces:
  - `AIRTABLE_API_URL = "https://api.airtable.com/v0"`.
  - `AirtableError(status: int | None, message: str)` з атрибутом `.status`.
  - `modified_after_formula(ts: datetime) -> str`.
  - `AirtableClient(*, token: str, base_id: str, table_id: str, session: aiohttp.ClientSession, api_url: str = AIRTABLE_API_URL, min_interval: float = 0.25, max_attempts: int = 5, rate_limit_pause: float = 30.0, sleep=asyncio.sleep, monotonic=time.monotonic)`.
  - `AirtableClient.iter_records(*, fields: Sequence[str], modified_after: datetime | None = None, page_size: int = 100) -> AsyncIterator[dict[str, Any]]` — задовольняє протокол `RecordSource` з Task 6.

Інкрементальна вибірка використовує `LAST_MODIFIED_TIME()` (час зміни будь-якого поля запису), а не назву поля «Last Modified Time»: формула не зламається від перейменування поля і не пропустить зміни в полях, які це поле не відстежує. Повні вибірки йдуть без `filterByFormula` — eligibility рахується в коді за field ID, тож перейменування полів в Airtable не ламає sync.

- [ ] **Step 1: Тест**

`tests/test_airtable_client.py`:

```python
from datetime import UTC, datetime, timedelta, timezone

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from pokazun.catalog.airtable import AirtableClient, AirtableError, modified_after_formula

TOKEN = "patTEST1234567890.abcdefabcdefabcdefabcdef"


class FakeAirtable:
    def __init__(self) -> None:
        self.requests: list[web.Request] = []
        self.responses: list[tuple[int, dict]] = []

    async def handle(self, request: web.Request) -> web.Response:
        self.requests.append(request)
        status, body = self.responses.pop(0)
        return web.json_response(body, status=status)


class FakeSleep:
    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


@pytest.fixture
async def airtable():
    fake = FakeAirtable()
    app = web.Application()
    app.router.add_get("/v0/{base}/{table}", fake.handle)
    async with TestServer(app) as server, aiohttp.ClientSession() as http:
        sleep = FakeSleep()
        client = AirtableClient(
            token=TOKEN,
            base_id="appBASE",
            table_id="tblTABLE",
            session=http,
            api_url=str(server.make_url("/v0")),
            sleep=sleep,
            monotonic=lambda: 1000.0,
        )
        yield fake, client, sleep


async def collect(client, **kw):
    return [r async for r in client.iter_records(fields=["fldA", "fldB"], **kw)]


async def test_paginates_with_allowlisted_fields(airtable):
    fake, client, _ = airtable
    fake.responses = [
        (200, {"records": [{"id": "rec1"}], "offset": "itr1/rec1"}),
        (200, {"records": [{"id": "rec2"}]}),
    ]
    assert [r["id"] for r in await collect(client)] == ["rec1", "rec2"]
    first, second = fake.requests
    assert first.match_info["base"] == "appBASE" and first.match_info["table"] == "tblTABLE"
    assert first.query.getall("fields[]") == ["fldA", "fldB"]
    assert first.query["returnFieldsByFieldId"] == "true"
    assert first.query["pageSize"] == "100"
    assert "filterByFormula" not in first.query
    assert first.headers["Authorization"] == f"Bearer {TOKEN}"
    assert second.query["offset"] == "itr1/rec1"


async def test_modified_after_uses_formula(airtable):
    fake, client, _ = airtable
    fake.responses = [(200, {"records": []})]
    await collect(client, modified_after=datetime(2026, 10, 1, 9, 58, tzinfo=UTC))
    assert fake.requests[0].query["filterByFormula"] == (
        "IS_AFTER(LAST_MODIFIED_TIME(), DATETIME_PARSE('2026-10-01T09:58:00.000Z'))"
    )


def test_formula_converts_to_utc():
    kyiv = timezone(timedelta(hours=3))
    assert "2026-10-01T09:00:00.000Z" in modified_after_formula(datetime(2026, 10, 1, 12, 0, tzinfo=kyiv))


async def test_retries_after_rate_limit(airtable):
    fake, client, sleep = airtable
    fake.responses = [(429, {"error": "RATE_LIMIT_REACHED"}), (200, {"records": [{"id": "rec1"}]})]
    assert [r["id"] for r in await collect(client)] == ["rec1"]
    assert 30.0 in sleep.calls


async def test_retries_server_errors(airtable):
    fake, client, sleep = airtable
    fake.responses = [(502, {}), (503, {}), (200, {"records": []})]
    assert await collect(client) == []
    assert len(fake.requests) == 3
    assert 2 in sleep.calls and 4 in sleep.calls


async def test_client_error_not_retried(airtable):
    fake, client, _ = airtable
    fake.responses = [(422, {"error": {"type": "INVALID_FILTER_BY_FORMULA"}})]
    with pytest.raises(AirtableError) as err:
        await collect(client)
    assert err.value.status == 422
    assert len(fake.requests) == 1


async def test_gives_up_after_max_attempts(airtable):
    fake, client, _ = airtable
    fake.responses = [(500, {})] * 5
    with pytest.raises(AirtableError, match="gave up"):
        await collect(client)
    assert len(fake.requests) == 5


async def test_throttles_requests(airtable):
    fake, client, sleep = airtable
    fake.responses = [(200, {"records": [], "offset": "o"}), (200, {"records": []})]
    await collect(client)
    assert 0.25 in sleep.calls


async def test_token_not_in_error_message(airtable):
    fake, client, _ = airtable
    fake.responses = [(403, {"error": "INVALID_PERMISSIONS"})]
    with pytest.raises(AirtableError) as err:
        await collect(client)
    assert TOKEN not in str(err.value)
```

- [ ] **Step 2: Запустити — має впасти**

Run: `uv run pytest tests/test_airtable_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pokazun.catalog.airtable'`.

- [ ] **Step 3: Реалізація**

`src/pokazun/catalog/airtable.py`:

```python
"""Read-only Airtable REST client: list records only, allowlisted field IDs, throttled, with retries."""

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from datetime import UTC, datetime
from typing import Any

import aiohttp

from pokazun.log import get_logger

log = get_logger(__name__)

AIRTABLE_API_URL = "https://api.airtable.com/v0"


class AirtableError(Exception):
    def __init__(self, status: int | None, message: str) -> None:
        super().__init__(f"Airtable {status}: {message}")
        self.status = status


def modified_after_formula(ts: datetime) -> str:
    stamp = ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return f"IS_AFTER(LAST_MODIFIED_TIME(), DATETIME_PARSE('{stamp}'))"


class AirtableClient:
    def __init__(
        self,
        *,
        token: str,
        base_id: str,
        table_id: str,
        session: aiohttp.ClientSession,
        api_url: str = AIRTABLE_API_URL,
        min_interval: float = 0.25,  # Airtable allows 5 requests/s per base; stay below
        max_attempts: int = 5,
        rate_limit_pause: float = 30.0,  # Airtable asks to wait 30 s after a 429
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._url = f"{api_url.rstrip('/')}/{base_id}/{table_id}"
        self._headers = {"Authorization": f"Bearer {token}"}
        self._session = session
        self._min_interval = min_interval
        self._max_attempts = max_attempts
        self._rate_limit_pause = rate_limit_pause
        self._sleep = sleep
        self._monotonic = monotonic
        self._last_request: float | None = None

    async def iter_records(
        self,
        *,
        fields: Sequence[str],
        modified_after: datetime | None = None,
        page_size: int = 100,
    ) -> AsyncIterator[dict[str, Any]]:
        base_params: list[tuple[str, str]] = [
            ("pageSize", str(page_size)),
            ("returnFieldsByFieldId", "true"),
            *(("fields[]", field) for field in fields),
        ]
        if modified_after is not None:
            base_params.append(("filterByFormula", modified_after_formula(modified_after)))
        offset: str | None = None
        while True:
            params = base_params + ([("offset", offset)] if offset else [])
            page = await self._get(params)
            for record in page.get("records", []):
                yield record
            offset = page.get("offset")
            if not offset:
                return

    async def _throttle(self) -> None:
        if self._last_request is not None:
            wait = self._last_request + self._min_interval - self._monotonic()
            if wait > 0:
                await self._sleep(wait)
        self._last_request = self._monotonic()

    async def _get(self, params: list[tuple[str, str]]) -> dict[str, Any]:
        last_error = "no attempts made"
        for attempt in range(1, self._max_attempts + 1):
            await self._throttle()
            try:
                async with self._session.get(self._url, params=params, headers=self._headers) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    body = (await resp.text())[:300]
                    if resp.status == 429:
                        last_error = "HTTP 429 rate limited"
                        log.warning("airtable_rate_limited", attempt=attempt)
                        await self._sleep(self._rate_limit_pause)
                        continue
                    if resp.status < 500:
                        raise AirtableError(resp.status, body)
                    last_error = f"HTTP {resp.status}: {body}"
            except (aiohttp.ClientError, TimeoutError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            log.warning("airtable_retry", attempt=attempt, error=last_error)
            await self._sleep(min(2**attempt, 30))
        raise AirtableError(None, f"gave up after {self._max_attempts} attempts: {last_error}")
```

Примітка: у `test_throttles_requests` фейковий `monotonic` завжди повертає 1000.0, тож перед другим запитом очікування дорівнює рівно `min_interval` = 0.25.

- [ ] **Step 4: Запустити — має пройти**

Run: `uv run pytest tests/test_airtable_client.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pokazun/catalog/airtable.py tests/test_airtable_client.py
git commit -m "feat: read-only airtable client with throttling and retries"
```

---

### Task 5: Стан об’єктів і переходи каталогу

**Files:**
- Create: `src/pokazun/catalog/state.py`, `tests/clock.py`
- Test: `tests/test_catalog_state.py`

**Interfaces:**
- Consumes: `CatalogRecord` (Task 2), `ObjectState` (Task 3).
- Produces:
  - `REACTIVATION_GAP = timedelta(days=30)`.
  - `TransitionKind(StrEnum)`: `CATALOG_ENTERED`, `CATALOG_LEFT`, `PRICE_DECREASED`, `RETURNED` (< 30 днів, без розсилки), `REACTIVATED_30D`.
  - `Transition(kind, record_id: str, object_code: int, at: datetime, old_price: Decimal | None = None, new_price: Decimal | None = None)`.
  - `PreviousState(eligible: bool, catalog_entered_at: datetime | None, inactive_since: datetime | None, price_usd: Decimal | None)`.
  - `detect_transitions(prev: PreviousState | None, rec: CatalogRecord, now: datetime) -> list[Transition]` — чиста функція.
  - `await load_states(session, record_ids: Collection[str]) -> dict[str, ObjectState]`.
  - `apply_record(session, states: dict[str, ObjectState], rec: CatalogRecord, now: datetime) -> list[Transition]` — синхронна, лише змінює ORM-об’єкти в сесії.
  - `await mark_missing_as_left(session, seen_ids: set[str], now: datetime) -> list[Transition]`.
  - `tests.clock.Clock(now)` — керований годинник (`clock()` повертає `clock.now`).

Правила (Д2 §9, §11):
- Уперше eligible → `CATALOG_ENTERED` (новим об’єкт стає в момент входу в каталог, а не створення запису в Airtable).
- Був eligible → став ні → `CATALOG_LEFT`, `inactive_since = now`.
- Повернувся: поза каталогом ≥ 30 днів → `REACTIVATED_30D` (з old/new ціною, щоб етап 10 надіслав одне повідомлення, а не два); інакше `RETURNED`.
- Eligible і до, і після, нова ціна < збереженої → `PRICE_DECREASED` (одна подія від збереженої ціни до поточної, скільки б правок не було між циклами). Підвищення — нічого.
- Зміна фото / опису — нічого.
- Невідомий і не eligible запис у `object_state` не записується.

- [ ] **Step 1: Годинник для тестів**

`tests/clock.py`:

```python
from datetime import datetime


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now
```

- [ ] **Step 2: Тест**

`tests/test_catalog_state.py`:

```python
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from pokazun.catalog.record import parse_record
from pokazun.catalog.state import (
    PreviousState,
    TransitionKind as K,
    apply_record,
    detect_transitions,
    load_states,
    mark_missing_as_left,
)
from pokazun.db.models import ObjectState
from tests.catalog_factory import raw_record

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def rec(**kw):
    return parse_record(raw_record(**kw)).record


def prev(eligible=True, entered=T0, inactive=None, price="55000"):
    return PreviousState(eligible, entered, inactive, Decimal(price) if price else None)


def kinds(transitions):
    return [t.kind for t in transitions]


def test_first_entry():
    assert kinds(detect_transitions(None, rec(), T0)) == [K.CATALOG_ENTERED]
    assert detect_transitions(None, rec(status="Продано"), T0) == []


def test_left():
    [t] = detect_transitions(prev(), rec(status="Продано"), T0)
    assert t.kind is K.CATALOG_LEFT and t.object_code == 620 and t.at == T0


def test_return_before_30_days():
    [t] = detect_transitions(prev(eligible=False, inactive=T0 - timedelta(days=29)), rec(), T0)
    assert t.kind is K.RETURNED


def test_reactivation_after_30_days_carries_prices():
    [t] = detect_transitions(
        prev(eligible=False, inactive=T0 - timedelta(days=30), price="60000"), rec(price=55000), T0
    )
    assert t.kind is K.REACTIVATED_30D
    assert (t.old_price, t.new_price) == (Decimal("60000"), Decimal("55000"))


def test_price_decrease_only():
    [t] = detect_transitions(prev(price="60000"), rec(price=55000), T0)
    assert t.kind is K.PRICE_DECREASED
    assert (t.old_price, t.new_price) == (Decimal("60000"), Decimal("55000"))
    assert detect_transitions(prev(price="50000"), rec(price=55000), T0) == []
    assert detect_transitions(prev(price=None), rec(price=55000), T0) == []
    assert detect_transitions(prev(), rec(price=None), T0) == []


def test_content_change_is_not_an_event():
    changed = rec(photos=5, extra={})
    assert detect_transitions(prev(), changed, T0) == []


async def test_apply_creates_and_updates_rows(sessionmaker):
    async with sessionmaker() as s, s.begin():
        states = await load_states(s, {"rec001"})
        assert kinds(apply_record(s, states, rec(), T0)) == [K.CATALOG_ENTERED]
    async with sessionmaker() as s:
        row = await s.scalar(select(ObjectState))
    assert row.eligible is True
    assert row.catalog_entered_at == T0 and row.eligible_since == T0 and row.inactive_since is None
    assert row.price_segment == 4 and row.condition == "Євроремонт" and row.rooms == 2
    assert row.public["street"] == "вул. П’ятницька"

    later = T0 + timedelta(days=1)
    async with sessionmaker() as s, s.begin():
        states = await load_states(s, {"rec001"})
        assert kinds(apply_record(s, states, rec(status="Продано"), later)) == [K.CATALOG_LEFT]
    async with sessionmaker() as s:
        row = await s.scalar(select(ObjectState))
    assert row.eligible is False and row.inactive_since == later
    assert row.catalog_entered_at == T0

    back = later + timedelta(days=31)
    async with sessionmaker() as s, s.begin():
        states = await load_states(s, {"rec001"})
        assert kinds(apply_record(s, states, rec(), back)) == [K.REACTIVATED_30D]
    async with sessionmaker() as s:
        row = await s.scalar(select(ObjectState))
    assert row.eligible is True and row.inactive_since is None and row.eligible_since == back
    assert row.catalog_entered_at == T0


async def test_unknown_ineligible_record_not_stored(sessionmaker):
    async with sessionmaker() as s, s.begin():
        states = await load_states(s, {"rec001"})
        assert apply_record(s, states, rec(status="Продано"), T0) == []
    async with sessionmaker() as s:
        assert await s.scalar(select(ObjectState)) is None


async def test_mark_missing_as_left(sessionmaker):
    async with sessionmaker() as s, s.begin():
        states = await load_states(s, set())
        apply_record(s, states, rec(record_id="recA", code=1), T0)
        apply_record(s, states, rec(record_id="recB", code=2), T0)
    async with sessionmaker() as s, s.begin():
        left = await mark_missing_as_left(s, {"recA"}, T0 + timedelta(hours=1))
    assert [(t.kind, t.record_id, t.object_code) for t in left] == [(K.CATALOG_LEFT, "recB", 2)]
    async with sessionmaker() as s:
        row = await s.scalar(select(ObjectState).where(ObjectState.airtable_record_id == "recB"))
    assert row.eligible is False and row.inactive_since == T0 + timedelta(hours=1)
```

- [ ] **Step 3: Запустити — має впасти**

Run: `uv run pytest tests/test_catalog_state.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pokazun.catalog.state'`.

- [ ] **Step 4: Реалізація**

`src/pokazun/catalog/state.py`:

```python
"""object_state maintenance and catalog transitions (Д2 §9, §11). Stage 10 turns transitions into events."""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pokazun.catalog.record import CatalogRecord
from pokazun.db.models import ObjectState

REACTIVATION_GAP = timedelta(days=30)
_LOAD_CHUNK = 5000


class TransitionKind(StrEnum):
    CATALOG_ENTERED = "catalog_entered"
    CATALOG_LEFT = "catalog_left"
    PRICE_DECREASED = "price_decreased"
    RETURNED = "returned"
    REACTIVATED_30D = "reactivated_30d"


@dataclass(frozen=True)
class Transition:
    kind: TransitionKind
    record_id: str
    object_code: int
    at: datetime
    old_price: Decimal | None = None
    new_price: Decimal | None = None


@dataclass(frozen=True)
class PreviousState:
    eligible: bool
    catalog_entered_at: datetime | None
    inactive_since: datetime | None
    price_usd: Decimal | None


def detect_transitions(
    prev: PreviousState | None, rec: CatalogRecord, now: datetime
) -> list[Transition]:
    def make(kind: TransitionKind, **prices: Decimal | None) -> Transition:
        return Transition(kind, rec.record_id, rec.code, now, **prices)

    if prev is None or prev.catalog_entered_at is None:
        return [make(TransitionKind.CATALOG_ENTERED)] if rec.eligible else []
    if prev.eligible and not rec.eligible:
        return [make(TransitionKind.CATALOG_LEFT)]
    if not prev.eligible and rec.eligible:
        left_at = prev.inactive_since or prev.catalog_entered_at
        kind = (
            TransitionKind.REACTIVATED_30D
            if now - left_at >= REACTIVATION_GAP
            else TransitionKind.RETURNED
        )
        return [make(kind, old_price=prev.price_usd, new_price=rec.price_usd)]
    if (
        prev.eligible
        and rec.eligible
        and prev.price_usd is not None
        and rec.price_usd is not None
        and rec.price_usd < prev.price_usd
    ):
        return [
            make(TransitionKind.PRICE_DECREASED, old_price=prev.price_usd, new_price=rec.price_usd)
        ]
    return []


async def load_states(session: AsyncSession, record_ids: Collection[str]) -> dict[str, ObjectState]:
    ids = list(record_ids)
    states: dict[str, ObjectState] = {}
    for start in range(0, len(ids), _LOAD_CHUNK):
        chunk = ids[start : start + _LOAD_CHUNK]
        rows = await session.scalars(
            select(ObjectState).where(ObjectState.airtable_record_id.in_(chunk))
        )
        states.update({row.airtable_record_id: row for row in rows})
    return states


def apply_record(
    session: AsyncSession,
    states: dict[str, ObjectState],
    rec: CatalogRecord,
    now: datetime,
) -> list[Transition]:
    row = states.get(rec.record_id)
    if row is None and not rec.eligible:
        return []
    previous = (
        None
        if row is None
        else PreviousState(row.eligible, row.catalog_entered_at, row.inactive_since, row.price_usd)
    )
    transitions = detect_transitions(previous, rec, now)
    if row is None:
        row = ObjectState(airtable_record_id=rec.record_id, eligible=False)
        session.add(row)
        states[rec.record_id] = row

    was_eligible = row.eligible
    if rec.eligible:
        if row.catalog_entered_at is None:
            row.catalog_entered_at = now
        if not was_eligible:
            row.eligible_since = now
            row.inactive_since = None
    elif was_eligible:
        row.inactive_since = now

    row.eligible = rec.eligible
    row.object_code = rec.code
    row.rooms = rec.rooms
    row.condition = rec.condition
    row.price_segment = rec.price_segment
    row.price_usd = rec.price_usd
    row.registered_at = rec.registered_at
    row.airtable_modified_at = rec.modified_at
    row.public = rec.public
    row.synced_at = now
    return transitions


async def mark_missing_as_left(
    session: AsyncSession, seen_ids: set[str], now: datetime
) -> list[Transition]:
    """Full reconciliation: eligible objects absent from Airtable (deleted) leave the catalog."""
    rows = await session.scalars(select(ObjectState).where(ObjectState.eligible.is_(True)))
    transitions: list[Transition] = []
    for row in rows:
        if row.airtable_record_id in seen_ids:
            continue
        row.eligible = False
        row.inactive_since = now
        row.synced_at = now
        transitions.append(
            Transition(TransitionKind.CATALOG_LEFT, row.airtable_record_id, row.object_code, now)
        )
    return transitions
```

- [ ] **Step 5: Запустити — має пройти**

Run: `uv run pytest tests/test_catalog_state.py -v`
Expected: 9 passed.

- [ ] **Step 6: Commit**

```bash
git add src/pokazun/catalog/state.py tests/clock.py tests/test_catalog_state.py
git commit -m "feat: object state maintenance and catalog transition detection"
```

---

### Task 6: Сервіс синхронізації

**Files:**
- Create: `src/pokazun/catalog/sync.py`
- Test: `tests/test_catalog_sync.py`

**Interfaces:**
- Consumes: `FETCH_FIELDS` (Task 2), `parse_record` (Task 2), `SyncState` (Task 3), `load_states`, `apply_record`, `mark_missing_as_left`, `Transition` (Task 5), `Alert`, `AlertService`, `redact_text`, `utcnow`.
- Produces:
  - `SOURCE = "airtable_objects"`, `SYNC_LOCK_KEY: int`.
  - `SyncMode(StrEnum)`: `BOOTSTRAP`, `FULL`, `INCREMENTAL`.
  - `RecordSource` (Protocol): `iter_records(*, fields: Sequence[str], modified_after: datetime | None = None) -> AsyncIterator[dict[str, Any]]`.
  - `TransitionSink = Callable[[AsyncSession, Sequence[Transition]], Awaitable[None]]`; `log_transitions` — sink за замовчуванням (етап 10 передасть свій, що пише в `notification_queue` у тій самій транзакції).
  - `SyncReport(mode: SyncMode, fetched: int = 0, skipped: int = 0, warnings: int = 0, transitions: Counter[str], locked_out: bool = False)`.
  - `CatalogSync(*, source: RecordSource, sessionmaker, alerts: AlertService, sink: TransitionSink = log_transitions, full_sync_interval: timedelta = timedelta(hours=24), overlap: timedelta = timedelta(minutes=2), failure_alert_threshold: int = 3, clock=utcnow)`; `await CatalogSync.run() -> SyncReport`.

Алгоритм `run()`:
1. Session-level `pg_try_advisory_lock(SYNC_LOCK_KEY)` на окремому з’єднанні в AUTOCOMMIT. Не вдалося → `SyncReport(locked_out=True)`, лог `sync_already_running`.
2. Режим: немає `bootstrapped_at` → `BOOTSTRAP`; немає `last_full_sync_at` або минуло ≥ `full_sync_interval` → `FULL`; інакше `INCREMENTAL` з `modified_after = watermark`.
3. Записи з Airtable тягнемо до відкриття транзакції (мережа не тримає транзакцію БД).
4. Одна транзакція: розбір, data-quality warnings у лог, `apply_record` для кожного, `mark_missing_as_left` для BOOTSTRAP / FULL, sink (крім BOOTSTRAP — там переходи лише логуються як пригнічені), оновлення `sync_state`: `watermark = started - overlap`, `last_successful_sync_at`, `last_full_sync_at` (BOOTSTRAP / FULL), `bootstrapped_at` (BOOTSTRAP), `consecutive_failures = 0`.
5. Будь-яка помилка → транзакцію відкочено; окремою транзакцією `consecutive_failures += 1`, `last_error` (redacted); при ≥ порогу — алерт `airtable_sync` (debounce); виняток прокидається далі (планувальник його логує).

- [ ] **Step 1: Тест**

`tests/test_catalog_sync.py`:

```python
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from aiogram.methods import SendMessage
from sqlalchemy import func, select, text
from structlog.testing import capture_logs

from pokazun.alerts import AlertService
from pokazun.catalog.state import TransitionKind as K
from pokazun.catalog.sync import SOURCE, SYNC_LOCK_KEY, CatalogSync, SyncMode
from pokazun.db.models import ObjectState, SyncState
from tests.catalog_factory import raw_record
from tests.clock import Clock
from tests.tg import make_bot

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


class FakeSource:
    def __init__(self) -> None:
        self.records: dict[str, tuple[dict[str, Any], datetime]] = {}
        self.calls: list[datetime | None] = []
        self.fail: Exception | None = None

    def put(self, raw: dict[str, Any], modified_at: datetime) -> None:
        self.records[raw["id"]] = (raw, modified_at)

    def delete(self, record_id: str) -> None:
        del self.records[record_id]

    async def iter_records(self, *, fields, modified_after=None):
        self.calls.append(modified_after)
        if self.fail is not None:
            raise self.fail
        for raw, modified_at in list(self.records.values()):
            if modified_after is None or modified_at > modified_after:
                yield raw


class RecordingSink:
    def __init__(self) -> None:
        self.batches: list[list] = []
        self.fail: Exception | None = None

    async def __call__(self, session, transitions) -> None:
        if self.fail is not None:
            raise self.fail
        self.batches.append(list(transitions))

    def kinds(self) -> list[tuple[K, int]]:
        return [(t.kind, t.object_code) for batch in self.batches for t in batch]


@pytest.fixture
def world(sessionmaker):
    bot, tg = make_bot()
    clock = Clock(T0)
    source = FakeSource()
    sink = RecordingSink()
    alerts = AlertService(bot, -1, "test", clock=clock)
    sync = CatalogSync(source=source, sessionmaker=sessionmaker, alerts=alerts, sink=sink, clock=clock)
    return sync, source, sink, clock, tg


async def eligible_codes(sessionmaker) -> set[int]:
    async with sessionmaker() as s:
        return set((await s.scalars(select(ObjectState.object_code).where(ObjectState.eligible))).all())


async def sync_state(sessionmaker) -> SyncState:
    async with sessionmaker() as s:
        return await s.get(SyncState, SOURCE)


async def bootstrap(world, sessionmaker):
    sync, source, sink, clock, _ = world
    source.put(raw_record("rec1", 1), T0 - timedelta(days=5))
    source.put(raw_record("rec2", 2), T0 - timedelta(days=5))
    source.put(raw_record("rec3", 3, status="Продано"), T0 - timedelta(days=5))
    report = await sync.run()
    assert report.mode is SyncMode.BOOTSTRAP
    return report


async def test_bootstrap_imports_without_events(world, sessionmaker):
    sync, source, sink, clock, _ = world
    report = await bootstrap(world, sessionmaker)
    assert report.fetched == 3
    assert sink.batches == []
    assert await eligible_codes(sessionmaker) == {1, 2}
    state = await sync_state(sessionmaker)
    assert state.bootstrapped_at == T0
    assert state.last_full_sync_at == T0
    assert state.watermark == T0 - timedelta(minutes=2)
    assert source.calls == [None]


async def test_incremental_new_object_enters(world, sessionmaker):
    sync, source, sink, clock, _ = world
    await bootstrap(world, sessionmaker)
    clock.now = T0 + timedelta(minutes=5)
    source.put(raw_record("rec4", 4), T0 + timedelta(minutes=3))
    report = await sync.run()
    assert report.mode is SyncMode.INCREMENTAL
    assert source.calls[-1] == T0 - timedelta(minutes=2)
    assert sink.kinds() == [(K.CATALOG_ENTERED, 4)]
    assert await eligible_codes(sessionmaker) == {1, 2, 4}


async def test_incremental_status_change_leaves(world, sessionmaker):
    sync, source, sink, clock, _ = world
    await bootstrap(world, sessionmaker)
    clock.now = T0 + timedelta(minutes=5)
    source.put(raw_record("rec1", 1, status="Продано"), T0 + timedelta(minutes=4))
    await sync.run()
    assert sink.kinds() == [(K.CATALOG_LEFT, 1)]


async def test_price_decrease_and_increase(world, sessionmaker):
    sync, source, sink, clock, _ = world
    await bootstrap(world, sessionmaker)
    clock.now = T0 + timedelta(minutes=5)
    source.put(raw_record("rec1", 1, price=50000), T0 + timedelta(minutes=1))
    source.put(raw_record("rec2", 2, price=70000), T0 + timedelta(minutes=1))
    await sync.run()
    [[drop]] = sink.batches
    assert (drop.kind, drop.object_code, drop.old_price, drop.new_price) == (
        K.PRICE_DECREASED, 1, 55000, 50000,
    )


async def test_content_change_is_silent(world, sessionmaker):
    sync, source, sink, clock, _ = world
    await bootstrap(world, sessionmaker)
    clock.now = T0 + timedelta(minutes=5)
    source.put(raw_record("rec1", 1, photos=7), T0 + timedelta(minutes=1))
    await sync.run()
    assert sink.kinds() == []


async def test_full_reconcile_marks_deleted_as_left(world, sessionmaker):
    sync, source, sink, clock, _ = world
    await bootstrap(world, sessionmaker)
    source.delete("rec2")
    clock.now = T0 + timedelta(minutes=5)
    await sync.run()  # incremental cannot see deletions
    assert sink.kinds() == []
    clock.now = T0 + timedelta(hours=24)
    report = await sync.run()
    assert report.mode is SyncMode.FULL
    assert source.calls[-1] is None
    assert sink.kinds() == [(K.CATALOG_LEFT, 2)]
    assert (await sync_state(sessionmaker)).last_full_sync_at == T0 + timedelta(hours=24)


async def test_reactivation_rules(world, sessionmaker):
    sync, source, sink, clock, _ = world
    await bootstrap(world, sessionmaker)
    clock.now = T0 + timedelta(minutes=5)
    source.put(raw_record("rec1", 1, status="Продано"), clock.now)
    source.put(raw_record("rec2", 2, status="Продано"), clock.now)
    await sync.run()
    clock.now = T0 + timedelta(days=10)
    source.put(raw_record("rec1", 1), clock.now)
    await sync.run()
    clock.now = T0 + timedelta(days=31)
    source.put(raw_record("rec2", 2, price=50000), clock.now)
    await sync.run()
    assert sink.kinds() == [
        (K.CATALOG_LEFT, 1), (K.CATALOG_LEFT, 2), (K.RETURNED, 1), (K.REACTIVATED_30D, 2),
    ]
    reactivated = sink.batches[-1][0]
    assert (reactivated.old_price, reactivated.new_price) == (55000, 50000)


async def test_failure_mid_apply_rolls_back_and_retries_cleanly(world, sessionmaker):
    sync, source, sink, clock, _ = world
    await bootstrap(world, sessionmaker)
    before = await sync_state(sessionmaker)
    clock.now = T0 + timedelta(minutes=5)
    source.put(raw_record("rec4", 4), T0 + timedelta(minutes=3))
    sink.fail = RuntimeError("queue write failed")
    with pytest.raises(RuntimeError):
        await sync.run()
    assert await eligible_codes(sessionmaker) == {1, 2}
    after = await sync_state(sessionmaker)
    assert after.watermark == before.watermark
    assert after.consecutive_failures == 1
    sink.fail = None
    clock.now = T0 + timedelta(minutes=10)
    await sync.run()
    assert sink.kinds() == [(K.CATALOG_ENTERED, 4)]
    assert (await sync_state(sessionmaker)).consecutive_failures == 0


async def test_alert_after_three_consecutive_failures(world, sessionmaker):
    sync, source, sink, clock, tg = world
    await bootstrap(world, sessionmaker)
    source.fail = TimeoutError("airtable timeout")
    for minute in (5, 10):
        clock.now = T0 + timedelta(minutes=minute)
        with pytest.raises(TimeoutError):
            await sync.run()
    assert tg.sent(SendMessage) == []
    clock.now = T0 + timedelta(minutes=15)
    with pytest.raises(TimeoutError):
        await sync.run()
    [alert] = tg.sent(SendMessage)
    assert "airtable_sync" in alert.text and "consecutive_failures: 3" in alert.text
    state = await sync_state(sessionmaker)
    assert state.last_error == "TimeoutError: airtable timeout"


async def test_concurrent_run_is_skipped(world, sessionmaker, engine):
    sync, source, sink, clock, _ = world
    async with engine.connect() as other:
        await other.execute(text(f"SELECT pg_advisory_lock({SYNC_LOCK_KEY})"))
        report = await sync.run()
        await other.execute(text(f"SELECT pg_advisory_unlock({SYNC_LOCK_KEY})"))
    assert report.locked_out is True
    assert source.calls == []


async def test_data_quality_warnings_logged_and_record_kept(world, sessionmaker):
    sync, source, sink, clock, _ = world
    source.put(raw_record("rec9", 9, segment=None), T0)
    with capture_logs() as logs:
        report = await sync.run()
    assert report.warnings == 1
    assert {
        (e["event"], e["issue"], e["object_code"]) for e in logs if e["event"] == "data_quality"
    } == {("data_quality", "empty_price_segment", 9)}
    async with sessionmaker() as s:
        row = await s.scalar(select(ObjectState))
    assert row.eligible is True and row.price_segment is None


async def test_record_without_code_is_skipped(world, sessionmaker):
    sync, source, sink, clock, _ = world
    source.put(raw_record("recX", None), T0)
    report = await sync.run()
    assert report.skipped == 1
    async with sessionmaker() as s:
        assert await s.scalar(select(func.count()).select_from(ObjectState)) == 0
```

- [ ] **Step 2: Запустити — має впасти**

Run: `uv run pytest tests/test_catalog_sync.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pokazun.catalog.sync'`.

- [ ] **Step 3: Реалізація**

`src/pokazun/catalog/sync.py`:

```python
"""Airtable → object_state synchronisation (Д2 §8). Runs in the worker every 5 minutes."""

from collections import Counter
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pokazun.alerts import Alert, AlertService
from pokazun.catalog.fields import FETCH_FIELDS
from pokazun.catalog.record import parse_record
from pokazun.catalog.state import Transition, apply_record, load_states, mark_missing_as_left
from pokazun.clock import utcnow
from pokazun.db.models import SyncState
from pokazun.log import get_logger, redact_text

log = get_logger(__name__)

SOURCE = "airtable_objects"
SYNC_LOCK_KEY = 0x504B5A01  # pg advisory lock id reserved for catalog sync


class SyncMode(StrEnum):
    BOOTSTRAP = "bootstrap"
    FULL = "full"
    INCREMENTAL = "incremental"


class RecordSource(Protocol):
    def iter_records(
        self, *, fields: Sequence[str], modified_after: datetime | None = None
    ) -> AsyncIterator[dict[str, Any]]: ...


TransitionSink = Callable[[AsyncSession, Sequence[Transition]], Awaitable[None]]


async def log_transitions(session: AsyncSession, transitions: Sequence[Transition]) -> None:
    for t in transitions:
        log.info(
            "catalog_transition",
            kind=t.kind.value,
            record_id=t.record_id,
            object_code=t.object_code,
            old_price=str(t.old_price) if t.old_price is not None else None,
            new_price=str(t.new_price) if t.new_price is not None else None,
        )


@dataclass
class SyncReport:
    mode: SyncMode
    fetched: int = 0
    skipped: int = 0
    warnings: int = 0
    transitions: Counter[str] = field(default_factory=Counter)
    locked_out: bool = False


class CatalogSync:
    def __init__(
        self,
        *,
        source: RecordSource,
        sessionmaker: async_sessionmaker[AsyncSession],
        alerts: AlertService,
        sink: TransitionSink = log_transitions,
        full_sync_interval: timedelta = timedelta(hours=24),
        overlap: timedelta = timedelta(minutes=2),
        failure_alert_threshold: int = 3,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._source = source
        self._sessionmaker = sessionmaker
        self._alerts = alerts
        self._sink = sink
        self._full_sync_interval = full_sync_interval
        self._overlap = overlap
        self._failure_alert_threshold = failure_alert_threshold
        self._clock = clock

    async def run(self) -> SyncReport:
        async with self._sessionmaker() as lock_session:
            conn = await lock_session.connection(execution_options={"isolation_level": "AUTOCOMMIT"})
            if not await conn.scalar(select(func.pg_try_advisory_lock(SYNC_LOCK_KEY))):
                log.warning("sync_already_running")
                return SyncReport(mode=SyncMode.INCREMENTAL, locked_out=True)
            try:
                return await self._run_locked()
            finally:
                await conn.scalar(select(func.pg_advisory_unlock(SYNC_LOCK_KEY)))

    def _plan(self, state: SyncState | None, started: datetime) -> tuple[SyncMode, datetime | None]:
        if state is None or state.bootstrapped_at is None:
            return SyncMode.BOOTSTRAP, None
        if state.last_full_sync_at is None or started - state.last_full_sync_at >= self._full_sync_interval:
            return SyncMode.FULL, None
        return SyncMode.INCREMENTAL, state.watermark

    async def _run_locked(self) -> SyncReport:
        started = self._clock()
        try:
            async with self._sessionmaker() as session:
                mode, modified_after = self._plan(await session.get(SyncState, SOURCE), started)
            raws = [
                raw
                async for raw in self._source.iter_records(
                    fields=FETCH_FIELDS, modified_after=modified_after
                )
            ]
            report = SyncReport(mode=mode, fetched=len(raws))
            async with self._sessionmaker() as session, session.begin():
                await self._apply(session, raws, mode, started, report)
        except Exception as exc:
            await self._record_failure(exc)
            raise
        log.info(
            "sync_finished",
            mode=mode.value,
            fetched=report.fetched,
            skipped=report.skipped,
            warnings=report.warnings,
            transitions=dict(report.transitions),
        )
        return report

    async def _apply(
        self,
        session: AsyncSession,
        raws: list[dict[str, Any]],
        mode: SyncMode,
        started: datetime,
        report: SyncReport,
    ) -> None:
        state = await session.get(SyncState, SOURCE, with_for_update=True)
        if state is None:
            state = SyncState(source=SOURCE, consecutive_failures=0)
            session.add(state)

        parsed = [parse_record(raw) for raw in raws]
        states = await load_states(session, {p.record_id for p in parsed if p.record is not None})
        transitions: list[Transition] = []
        for result in parsed:
            for issue in result.warnings:
                report.warnings += 1
                log.warning(
                    "data_quality",
                    record_id=result.record_id,
                    object_code=result.record.code if result.record else None,
                    issue=issue,
                )
            if result.record is None:
                report.skipped += 1
                continue
            transitions += apply_record(session, states, result.record, started)
        if mode is not SyncMode.INCREMENTAL:
            transitions += await mark_missing_as_left(
                session, {p.record_id for p in parsed}, started
            )
        report.transitions.update(t.kind.value for t in transitions)

        if mode is SyncMode.BOOTSTRAP:
            log.info("bootstrap_snapshot", suppressed_transitions=len(transitions))
        else:
            await self._sink(session, transitions)

        state.watermark = started - self._overlap
        state.last_successful_sync_at = self._clock()
        if mode is not SyncMode.INCREMENTAL:
            state.last_full_sync_at = started
        if mode is SyncMode.BOOTSTRAP:
            state.bootstrapped_at = started
        state.consecutive_failures = 0
        state.last_error = None

    async def _record_failure(self, exc: Exception) -> None:
        message = redact_text(f"{type(exc).__name__}: {exc}")[:1000]
        try:
            async with self._sessionmaker() as session, session.begin():
                state = await session.get(SyncState, SOURCE, with_for_update=True)
                if state is None:
                    state = SyncState(source=SOURCE, consecutive_failures=0)
                    session.add(state)
                state.consecutive_failures = (state.consecutive_failures or 0) + 1
                state.last_error = message
                failures = state.consecutive_failures
        except Exception:
            log.exception("sync_failure_not_recorded")
            await self._alerts.send(
                Alert(job="postgres", message=f"sync state unavailable; sync error: {message}", dedupe_key="postgres:sync")
            )
            return
        log.error("sync_failed", consecutive_failures=failures, error=message)
        if failures >= self._failure_alert_threshold:
            await self._alerts.send(
                Alert(
                    job="airtable_sync",
                    message=message,
                    ids={"consecutive_failures": failures},
                    dedupe_key="airtable_sync_failing",
                )
            )
```

- [ ] **Step 4: Запустити — має пройти**

Run: `uv run pytest tests/test_catalog_sync.py -v`
Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pokazun/catalog/sync.py tests/test_catalog_sync.py
git commit -m "feat: catalog sync with bootstrap, incremental and full reconciliation"
```

---

### Task 7: Пошук збігів у PostgreSQL

**Files:**
- Create: `src/pokazun/catalog/matching.py`
- Test: `tests/test_matching.py`

**Interfaces:**
- Consumes: `SearchCriteria`, `RoomOption` (Task 1), `ObjectState` (Task 3).
- Produces:
  - `criteria_clause(criteria: SearchCriteria) -> ColumnElement[bool]` (включає `eligible`).
  - `CATALOG_ORDER` — `(registered_at DESC NULLS LAST, object_code DESC)`.
  - `await count_matching(session, criteria) -> int`.
  - `await matching_record_ids(session, criteria) -> list[str]` — `airtable_record_id` у порядку видачі (етап 6 бере з нього знімок для пагінації).
  - Гарантія: SQL-відбір рівно збігається з `SearchCriteria.matches(...)` + `eligible` (перевіряється тестом паритету). Етап 10 використовує `SearchCriteria.matches` для подій — однакова логіка в обох місцях.

- [ ] **Step 1: Тест**

`tests/test_matching.py`:

```python
import itertools
from datetime import UTC, datetime, timedelta

from sqlalchemy import insert

from pokazun.catalog.matching import count_matching, matching_record_ids
from pokazun.db.models import ObjectState
from pokazun.search.filters import (
    KNOWN_CONDITIONS,
    ConditionGroup,
    PriceRange,
    RoomOption,
    SearchCriteria,
)

T0 = datetime(2026, 10, 1, tzinfo=UTC)
ROOMS = [None, 1, 2, 3, 4, 5]
CONDITIONS = [None, "Невідомий стан", *sorted(KNOWN_CONDITIONS)]
SEGMENTS = [None, *range(8)]


def grid_rows():
    rows = []
    for n, (rooms, condition, segment, eligible) in enumerate(
        itertools.product(ROOMS, CONDITIONS, SEGMENTS, [True, False])
    ):
        rows.append(
            {
                "airtable_record_id": f"rec{n:05d}",
                "object_code": n,
                "eligible": eligible,
                "rooms": rooms,
                "condition": condition,
                "price_segment": segment,
                "public": {},
                "synced_at": T0,
            }
        )
    return rows


def all_criteria():
    room_sets = [
        frozenset(c)
        for k in range(1, 5)
        for c in itertools.combinations(list(RoomOption), k)
    ]
    condition_sets = [
        frozenset({ConditionGroup.RESIDENTIAL}),
        frozenset({ConditionGroup.DEVELOPER}),
        frozenset(ConditionGroup),
    ]
    ranges = [PriceRange(0, 0), PriceRange(2, 4), PriceRange(5, 7), PriceRange(0, 7)]
    for rooms, conditions, price in itertools.product(room_sets, condition_sets, ranges):
        yield SearchCriteria(rooms, conditions, price)


async def test_sql_matches_python_rules(sessionmaker):
    rows = grid_rows()
    async with sessionmaker() as s, s.begin():
        await s.execute(insert(ObjectState), rows)
    async with sessionmaker() as s:
        for criteria in all_criteria():
            expected = sum(
                1
                for r in rows
                if r["eligible"]
                and criteria.matches(
                    rooms=r["rooms"], condition=r["condition"], price_segment=r["price_segment"]
                )
            )
            assert await count_matching(s, criteria) == expected, criteria


async def test_order_registered_desc_then_code_desc(sessionmaker):
    base = {"eligible": True, "rooms": 2, "condition": "Євроремонт", "price_segment": 3, "public": {}, "synced_at": T0}
    async with sessionmaker() as s, s.begin():
        await s.execute(
            insert(ObjectState),
            [
                {**base, "airtable_record_id": "recOld", "object_code": 900, "registered_at": T0 - timedelta(days=9)},
                {**base, "airtable_record_id": "recNewLow", "object_code": 100, "registered_at": T0},
                {**base, "airtable_record_id": "recNewHigh", "object_code": 200, "registered_at": T0},
                {**base, "airtable_record_id": "recNoDate", "object_code": 999, "registered_at": None},
            ],
        )
    criteria = SearchCriteria(
        frozenset({RoomOption.TWO}), frozenset({ConditionGroup.RESIDENTIAL}), PriceRange(3, 3)
    )
    async with sessionmaker() as s:
        assert await matching_record_ids(s, criteria) == ["recNewHigh", "recNewLow", "recOld", "recNoDate"]
```

- [ ] **Step 2: Запустити — має впасти**

Run: `uv run pytest tests/test_matching.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pokazun.catalog.matching'`.

- [ ] **Step 3: Реалізація**

`src/pokazun/catalog/matching.py`:

```python
"""Search matching over object_state. Must stay equivalent to SearchCriteria.matches (parity test)."""

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from pokazun.db.models import ObjectState
from pokazun.search.filters import RoomOption, SearchCriteria

CATALOG_ORDER = (
    ObjectState.registered_at.desc().nulls_last(),
    ObjectState.object_code.desc(),
)


def criteria_clause(criteria: SearchCriteria) -> ColumnElement[bool]:
    exact_rooms = sorted(r.value for r in criteria.rooms if r is not RoomOption.FOUR_PLUS)
    room_clauses: list[ColumnElement[bool]] = []
    if exact_rooms:
        room_clauses.append(ObjectState.rooms.in_(exact_rooms))
    if RoomOption.FOUR_PLUS in criteria.rooms:
        room_clauses.append(ObjectState.rooms >= 4)
    return and_(
        ObjectState.eligible.is_(True),
        or_(*room_clauses),
        ObjectState.condition.in_(sorted(criteria.condition_values)),
        ObjectState.price_segment.between(criteria.price.low, criteria.price.high),
    )


async def count_matching(session: AsyncSession, criteria: SearchCriteria) -> int:
    stmt = select(func.count()).select_from(ObjectState).where(criteria_clause(criteria))
    return (await session.scalar(stmt)) or 0


async def matching_record_ids(session: AsyncSession, criteria: SearchCriteria) -> list[str]:
    stmt = (
        select(ObjectState.airtable_record_id)
        .where(criteria_clause(criteria))
        .order_by(*CATALOG_ORDER)
    )
    return list((await session.scalars(stmt)).all())
```

- [ ] **Step 4: Запустити — має пройти**

Run: `uv run pytest tests/test_matching.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pokazun/catalog/matching.py tests/test_matching.py
git commit -m "feat: sql search matching with catalog ordering"
```

---

### Task 8: Підключення sync до воркера, конфіг, health

**Files:**
- Create: `src/pokazun/catalog/health.py`
- Modify: `src/pokazun/config.py`, `.env.example`, `src/pokazun/worker/jobs.py`, `src/pokazun/worker/main.py`, `src/pokazun/app.py`
- Modify tests: `tests/test_config.py`, `tests/test_worker_jobs.py`, `tests/test_bot_middlewares.py`
- Test: `tests/test_catalog_health.py`

**Interfaces:**
- Consumes: `CatalogSync`, `SOURCE` (Task 6), `AirtableClient`, `AIRTABLE_API_URL` (Task 4), `ObjectState`, `SyncState`, `HealthRegistry.register` (етап 3).
- Produces:
  - Нові поля `Settings`: `airtable_token: SecretStr | None = None` (обов’язковий для `prod` і `staging`), `airtable_base_id: str = "appLx30Y68Qy0I9Au"`, `airtable_table_id: str = "tblgO046VTYnqOgZa"`, `airtable_api_url: str = AIRTABLE_API_URL`, `sync_interval_s: int = 300`, `full_sync_interval_h: int = 24`.
  - `await catalog_health(session) -> dict[str, Any]` з ключами `last_successful_sync_at`, `eligible_object_count`, `sync_consecutive_failures`.
  - `await check_sync_freshness(sessionmaker, alerts, *, now: datetime, max_age: timedelta = timedelta(minutes=15)) -> None`.
  - Нова сигнатура: `build_jobs(settings, sessionmaker, alerts, *, airtable: RecordSource | None = None, clock=utcnow) -> list[Job]`; з `airtable` додаються задачі `catalog_sync` (кожні `sync_interval_s`, `alert_on_failure=False`) і `sync_freshness` (кожні 5 хв).

- [ ] **Step 1: Тест health**

`tests/test_catalog_health.py`:

```python
from datetime import UTC, datetime, timedelta

from aiogram.methods import SendMessage

from pokazun.alerts import AlertService
from pokazun.catalog.health import catalog_health, check_sync_freshness
from pokazun.catalog.sync import SOURCE
from pokazun.db.models import ObjectState, SyncState
from tests.tg import make_bot

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


async def seed(sessionmaker, last_sync):
    async with sessionmaker() as s, s.begin():
        s.add(SyncState(source=SOURCE, last_successful_sync_at=last_sync, consecutive_failures=2))
        s.add(ObjectState(airtable_record_id="rec1", object_code=1, eligible=True, synced_at=T0))
        s.add(ObjectState(airtable_record_id="rec2", object_code=2, eligible=False, synced_at=T0))


async def test_catalog_health(sessionmaker):
    await seed(sessionmaker, T0)
    async with sessionmaker() as s:
        data = await catalog_health(s)
    assert data == {
        "last_successful_sync_at": T0.isoformat(),
        "eligible_object_count": 1,
        "sync_consecutive_failures": 2,
    }


async def test_catalog_health_before_first_sync(sessionmaker):
    async with sessionmaker() as s:
        data = await catalog_health(s)
    assert data == {"last_successful_sync_at": None, "eligible_object_count": 0, "sync_consecutive_failures": 0}


async def test_freshness_alerts_when_stale_or_never(sessionmaker):
    bot, tg = make_bot()
    alerts = AlertService(bot, -1, "prod", debounce=timedelta(0))
    await check_sync_freshness(sessionmaker, alerts, now=T0)  # never synced
    await seed(sessionmaker, T0 - timedelta(minutes=16))
    await check_sync_freshness(sessionmaker, alerts, now=T0)  # stale
    assert len(tg.sent(SendMessage)) == 2


async def test_freshness_ok(sessionmaker):
    bot, tg = make_bot()
    await seed(sessionmaker, T0 - timedelta(minutes=6))
    await check_sync_freshness(sessionmaker, AlertService(bot, -1, "prod"), now=T0)
    assert tg.sent(SendMessage) == []
```

- [ ] **Step 2: Запустити — має впасти**

Run: `uv run pytest tests/test_catalog_health.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pokazun.catalog.health'`.

- [ ] **Step 3: Реалізація `catalog/health.py`**

```python
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pokazun.alerts import Alert, AlertService
from pokazun.catalog.sync import SOURCE
from pokazun.db.models import ObjectState, SyncState


async def catalog_health(session: AsyncSession) -> dict[str, Any]:
    state = await session.get(SyncState, SOURCE)
    eligible = await session.scalar(
        select(func.count()).select_from(ObjectState).where(ObjectState.eligible.is_(True))
    )
    last = state.last_successful_sync_at if state else None
    return {
        "last_successful_sync_at": last.isoformat() if last else None,
        "eligible_object_count": eligible or 0,
        "sync_consecutive_failures": state.consecutive_failures if state else 0,
    }


async def check_sync_freshness(
    sessionmaker: async_sessionmaker[AsyncSession],
    alerts: AlertService,
    *,
    now: datetime,
    max_age: timedelta = timedelta(minutes=15),
) -> None:
    async with sessionmaker() as session:
        state = await session.get(SyncState, SOURCE)
    last = state.last_successful_sync_at if state else None
    if last is None or now - last > max_age:
        await alerts.send(
            Alert(
                job="airtable_sync",
                message=f"no successful catalog sync within {max_age}; last: {last.isoformat() if last else 'never'}",
                dedupe_key="airtable_sync_stale",
            )
        )
```

- [ ] **Step 4: Конфіг**

У `src/pokazun/config.py`:

1. Додати імпорт `from pokazun.catalog.airtable import AIRTABLE_API_URL`.
2. Після поля `web_port` додати поля:

```python
    airtable_token: SecretStr | None = None
    airtable_base_id: str = "appLx30Y68Qy0I9Au"
    airtable_table_id: str = "tblgO046VTYnqOgZa"
    airtable_api_url: str = AIRTABLE_API_URL
    sync_interval_s: int = 300
    full_sync_interval_h: int = 24
```

3. У `_validate` перед `return self` додати:

```python
        if self.env in ("prod", "staging") and self.airtable_token is None:
            raise ValueError(f"{self.env} requires POKAZUN_AIRTABLE_TOKEN")
```

У `.env.example` до блоку application додати:

```dotenv
# read-only service token: data.records:read + schema.bases:read, base appLx30Y68Qy0I9Au only
POKAZUN_AIRTABLE_TOKEN=
```

- [ ] **Step 5: Оновити тести етапу 3 під нове обов’язкове поле**

`tests/test_config.py`: у словник `BASE` додати `"airtable_token": "patTest1234567890.abcdefabcdefabcdefabcd",`; у `test_loads_from_env` додати `monkeypatch.setenv("POKAZUN_AIRTABLE_TOKEN", "patTest1234567890.abcdefabcdefabcdefabcd")`; додати тест:

```python
def test_prod_and_staging_require_airtable_token():
    for env, extra in (("prod", {"alert_chat_id": -1}), ("staging", {"allowed_user_ids": "1"})):
        with pytest.raises(ValidationError, match="AIRTABLE_TOKEN"):
            make(env=env, airtable_token=None, **extra)
```

`tests/test_worker_jobs.py`: у `_settings` до `base` додати `"airtable_token": "patTest1234567890.abcdefabcdefabcdefabcd",`; додати тест:

```python
def test_build_jobs_with_airtable(sessionmaker):
    class NoSource:
        async def iter_records(self, *, fields, modified_after=None):
            return
            yield

    jobs = build_jobs(
        _settings(env="prod", alert_chat_id=-1),
        sessionmaker,
        AlertService(None, None, "prod"),
        airtable=NoSource(),
    )
    by_name = {j.name: j for j in jobs}
    assert {"catalog_sync", "sync_freshness"} <= set(by_name)
    assert by_name["catalog_sync"].interval == timedelta(minutes=5)
    assert by_name["catalog_sync"].alert_on_failure is False
```

(`timedelta` уже імпортовано в цьому файлі.)

`tests/test_bot_middlewares.py`: у функції `settings()` додати аргумент `airtable_token="patTest1234567890.abcdefabcdefabcdefabcd",` (staging тепер вимагає токен).

- [ ] **Step 6: `build_jobs` і воркер**

У `src/pokazun/worker/jobs.py` додати імпорти:

```python
from pokazun.catalog.health import check_sync_freshness
from pokazun.catalog.sync import CatalogSync, RecordSource
```

і замінити `build_jobs` повністю:

```python
def build_jobs(
    settings: Settings,
    sessionmaker: async_sessionmaker[AsyncSession],
    alerts: AlertService,
    *,
    airtable: RecordSource | None = None,
    clock: Callable[[], datetime] = utcnow,
) -> list[Job]:
    async def cleanup() -> None:
        await cleanup_processed_updates(sessionmaker, now=clock())

    jobs = [Job("cleanup_processed_updates", timedelta(hours=6), cleanup)]
    if settings.env == "prod":

        async def backup() -> None:
            await check_backup_freshness(settings.backup_marker_path, alerts, now=clock())

        jobs.append(Job("backup_freshness", timedelta(hours=1), backup, run_on_start=False))
    if settings.telegram_mode == "webhook":
        check = PublicHealthCheck(settings.public_base_url.rstrip("/") + "/healthz", alerts)
        jobs.append(Job("public_health", timedelta(minutes=5), check.run, run_on_start=False))
    if airtable is not None:
        sync = CatalogSync(
            source=airtable,
            sessionmaker=sessionmaker,
            alerts=alerts,
            full_sync_interval=timedelta(hours=settings.full_sync_interval_h),
            clock=clock,
        )

        async def run_sync() -> None:
            await sync.run()

        async def freshness() -> None:
            await check_sync_freshness(sessionmaker, alerts, now=clock())

        jobs.append(
            Job("catalog_sync", timedelta(seconds=settings.sync_interval_s), run_sync, alert_on_failure=False)
        )
        jobs.append(Job("sync_freshness", timedelta(minutes=5), freshness, run_on_start=False))
    return jobs
```

У `src/pokazun/worker/main.py` замінити функцію `run` повністю (і додати імпорти `import aiohttp` та `from pokazun.catalog.airtable import AirtableClient`):

```python
async def run(settings: Settings) -> None:
    engine = create_engine(settings.database_url.get_secret_value())
    sessionmaker = create_sessionmaker(engine)
    bot = Bot(settings.bot_token.get_secret_value())
    alerts = AlertService(bot, settings.alert_chat_id, settings.env)
    await check_restart_loop(
        settings.state_dir / "worker-starts.json", alerts, service="worker", now=utcnow()
    )
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as http:
            airtable = (
                AirtableClient(
                    token=settings.airtable_token.get_secret_value(),
                    base_id=settings.airtable_base_id,
                    table_id=settings.airtable_table_id,
                    session=http,
                    api_url=settings.airtable_api_url,
                )
                if settings.airtable_token is not None
                else None
            )
            scheduler = Scheduler(alerts)
            for job in build_jobs(settings, sessionmaker, alerts, airtable=airtable):
                scheduler.add(job)
            log.info("worker_started", env=settings.env, airtable=airtable is not None)
            await scheduler.run(stop)
    finally:
        await bot.session.close()
        await engine.dispose()
        log.info("worker_stopped")
```

У `src/pokazun/app.py` у `create_app` після створення `health` додати:

```python
    health.register(catalog_health)
```

та імпорт `from pokazun.catalog.health import catalog_health`.

- [ ] **Step 7: Запустити весь набір**

Run: `uv run pytest -v && uv run ruff check . && uv run ruff format --check .`
Expected: усі тести зелені, включно з `tests/test_catalog_health.py` (4), оновленими `tests/test_config.py` (13) і `tests/test_worker_jobs.py` (6).

- [ ] **Step 8: Перевірка на реальній Airtable (staging, коли є read-only токен)**

1. Додати `POKAZUN_AIRTABLE_TOKEN` у `/opt/pokazun/staging/.env`, `deploy/deploy.sh staging`.
2. `docker compose ... logs worker | grep -E "bootstrap_snapshot|sync_finished|data_quality"` — перший запуск `mode: bootstrap`, далі кожні 5 хв `incremental`.
3. `curl https://staging-bot.praktik.cn.ua/healthz` — `eligible_object_count` дорівнює кількості записів у представленні Airtable з 4 умовами eligibility (звірити вручну з фільтром в інтерфейсі Airtable).
4. Змінити в Airtable статус тестового об’єкта на інший і назад — у логах `catalog_transition` `catalog_left`, потім `returned` протягом ≤ 5 хв кожен.
5. Переглянути `data_quality` — надіслати замовнику список об’єктів із порожнім «Діапазон цін» / без фото.

Якщо eligibility-поля приходять як linked records (`["rec…"]` замість назв), `is_eligible` поверне `False` для всіх — це буде видно одразу як `eligible_object_count: 0`. Тоді: у тому ж PR додати в `fields.py` lookup-поля з назвами (field ID отримати з замовником) і тест на цей формат.

- [ ] **Step 9: Commit**

```bash
git add src/pokazun/catalog/health.py src/pokazun/config.py .env.example src/pokazun/worker src/pokazun/app.py tests/test_config.py tests/test_worker_jobs.py tests/test_bot_middlewares.py tests/test_catalog_health.py
git commit -m "feat: run catalog sync in the worker, expose sync health and freshness alerts"
```

---

## Готово, коли

- `uv run pytest` зелений, ruff чистий, CI зелений.
- На staging: bootstrap без подій; інкрементальні цикли кожні 5 хв; `/healthz` показує `last_successful_sync_at` і `eligible_object_count`, що збігається з Airtable; перехід статусу видно в логах ≤ 5 хв; 3 невдалі sync поспіль (тимчасово невірний токен) дають один алерт у групу.
- Жодних запитів до Airtable, крім `GET` list records з `fields[]` з allowlist.
