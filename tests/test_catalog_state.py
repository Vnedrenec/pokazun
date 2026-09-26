from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from pokazun.catalog.record import parse_record
from pokazun.catalog.state import (
    PreviousState,
    apply_record,
    detect_transitions,
    load_states,
    mark_missing_as_left,
)
from pokazun.catalog.state import (
    TransitionKind as K,
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
