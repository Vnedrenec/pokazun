"""Search matching over object_state. Equivalent to SearchCriteria.matches (parity test)."""

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
