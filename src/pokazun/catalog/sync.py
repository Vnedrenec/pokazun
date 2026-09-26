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
            conn = await lock_session.connection(
                execution_options={"isolation_level": "AUTOCOMMIT"}
            )
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
        if (
            state.last_full_sync_at is None
            or started - state.last_full_sync_at >= self._full_sync_interval
        ):
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
                Alert(
                    job="postgres",
                    message=f"sync state unavailable; sync error: {message}",
                    dedupe_key="postgres:sync",
                )
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
