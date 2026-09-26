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
        frozenset(c) for k in range(1, 5) for c in itertools.combinations(list(RoomOption), k)
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
    base = {
        "eligible": True,
        "rooms": 2,
        "condition": "Євроремонт",
        "price_segment": 3,
        "public": {},
        "synced_at": T0,
    }
    async with sessionmaker() as s, s.begin():
        await s.execute(
            insert(ObjectState),
            [
                {
                    **base,
                    "airtable_record_id": "recOld",
                    "object_code": 900,
                    "registered_at": T0 - timedelta(days=9),
                },
                {
                    **base,
                    "airtable_record_id": "recNewLow",
                    "object_code": 100,
                    "registered_at": T0,
                },
                {
                    **base,
                    "airtable_record_id": "recNewHigh",
                    "object_code": 200,
                    "registered_at": T0,
                },
                {
                    **base,
                    "airtable_record_id": "recNoDate",
                    "object_code": 999,
                    "registered_at": None,
                },
            ],
        )
    criteria = SearchCriteria(
        frozenset({RoomOption.TWO}), frozenset({ConditionGroup.RESIDENTIAL}), PriceRange(3, 3)
    )
    async with sessionmaker() as s:
        assert await matching_record_ids(s, criteria) == [
            "recNewHigh",
            "recNewLow",
            "recOld",
            "recNoDate",
        ]
