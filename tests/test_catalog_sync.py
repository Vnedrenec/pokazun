from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from aiogram.methods import SendMessage
from sqlalchemy import func, select, text
from structlog.testing import capture_logs

from pokazun.alerts import AlertService
from pokazun.catalog.record import parse_record
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
    sync = CatalogSync(
        source=source, sessionmaker=sessionmaker, alerts=alerts, sink=sink, clock=clock
    )
    return sync, source, sink, clock, tg


async def eligible_codes(sessionmaker) -> set[int]:
    async with sessionmaker() as s:
        rows = await s.scalars(select(ObjectState.object_code).where(ObjectState.eligible))
        return set(rows.all())


async def sync_state(sessionmaker) -> SyncState:
    async with sessionmaker() as s:
        return await s.get(SyncState, SOURCE)


async def bootstrap(world, sessionmaker):
    sync, source, _sink, _clock, _ = world
    source.put(raw_record("rec1", 1), T0 - timedelta(days=5))
    source.put(raw_record("rec2", 2), T0 - timedelta(days=5))
    source.put(raw_record("rec3", 3, status="Продано"), T0 - timedelta(days=5))
    report = await sync.run()
    assert report.mode is SyncMode.BOOTSTRAP
    return report


async def test_bootstrap_imports_without_events(world, sessionmaker):
    _sync, source, sink, _clock, _ = world
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
        K.PRICE_DECREASED,
        1,
        55000,
        50000,
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
        (K.CATALOG_LEFT, 1),
        (K.CATALOG_LEFT, 2),
        (K.RETURNED, 1),
        (K.REACTIVATED_30D, 2),
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
    sync, source, _sink, clock, tg = world
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
    sync, source, _sink, _clock, _ = world
    async with engine.connect() as other:
        await other.execute(text(f"SELECT pg_advisory_lock({SYNC_LOCK_KEY})"))
        report = await sync.run()
        await other.execute(text(f"SELECT pg_advisory_unlock({SYNC_LOCK_KEY})"))
    assert report.locked_out is True
    assert source.calls == []


async def test_data_quality_warnings_logged_and_record_kept(world, sessionmaker):
    sync, source, _sink, _clock, _ = world
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


async def test_raw_airtable_payload_never_logged(world, sessionmaker):
    sync, source, _sink, _clock, _ = world
    raw = raw_record("rec9", 9, segment=None)
    assert "+380671112233" in repr(raw)
    with capture_logs() as logs:
        parse_record(raw)
        source.put(raw, T0)
        report = await sync.run()
    assert report.warnings >= 1
    assert any(e.get("event") == "data_quality" for e in logs)
    assert "+380671112233" not in repr(logs)


async def test_record_without_code_is_skipped(world, sessionmaker):
    sync, source, _sink, _clock, _ = world
    source.put(raw_record("recX", None), T0)
    report = await sync.run()
    assert report.skipped == 1
    async with sessionmaker() as s:
        assert await s.scalar(select(func.count()).select_from(ObjectState)) == 0
