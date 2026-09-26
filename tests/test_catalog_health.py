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
    assert data == {
        "last_successful_sync_at": None,
        "eligible_object_count": 0,
        "sync_consecutive_failures": 0,
    }


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
