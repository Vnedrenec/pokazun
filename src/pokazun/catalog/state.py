"""object_state maintenance and catalog transitions. Stage 10 turns transitions into events."""

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
