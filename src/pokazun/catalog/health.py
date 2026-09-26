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
        last_label = last.isoformat() if last else "never"
        await alerts.send(
            Alert(
                job="airtable_sync",
                message=f"no successful catalog sync within {max_age}; last: {last_label}",
                dedupe_key="airtable_sync_stale",
            )
        )
