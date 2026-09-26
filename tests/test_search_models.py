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
    row = dict(
        user_id=user_id,
        rooms=[1],
        conditions=["developer"],
        price_low=0,
        price_high=0,
        baseline_at=T0,
        confirmed_at=T0,
    )
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
            # S608 scope: only user_id from the local test fixture and fixed values
            # from pytest.mark.parametrize are interpolated to verify DB CHECK.
            await s.execute(
                text(
                    "INSERT INTO searches (user_id, rooms, conditions, "  # noqa: S608
                    "price_low, price_high, baseline_at, confirmed_at) "
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
