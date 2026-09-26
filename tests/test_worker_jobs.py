from datetime import UTC, datetime, timedelta

from aiogram.methods import SendMessage
from aiohttp import web
from aiohttp.test_utils import TestServer
from sqlalchemy import insert, select

from pokazun.alerts import AlertService
from pokazun.config import Settings
from pokazun.db.models import ProcessedUpdate
from pokazun.worker.jobs import (
    PublicHealthCheck,
    build_jobs,
    check_backup_freshness,
    cleanup_processed_updates,
)
from tests.tg import make_bot

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


async def test_cleanup_processed_updates(sessionmaker):
    async with sessionmaker() as s, s.begin():
        await s.execute(
            insert(ProcessedUpdate),
            [
                {"update_id": 1, "processed_at": T0 - timedelta(days=8)},
                {"update_id": 2, "processed_at": T0 - timedelta(days=1)},
            ],
        )
    assert await cleanup_processed_updates(sessionmaker, now=T0) == 1
    async with sessionmaker() as s:
        assert (await s.scalars(select(ProcessedUpdate.update_id))).all() == [2]


async def test_backup_missing_or_stale_alerts(tmp_path):
    bot, session = make_bot()
    alerts = AlertService(bot, -1, "prod", clock=lambda: T0, debounce=timedelta(0))
    marker = tmp_path / "last_backup_at"
    await check_backup_freshness(marker, alerts, now=T0)
    marker.write_text((T0 - timedelta(hours=27)).isoformat())
    await check_backup_freshness(marker, alerts, now=T0)
    marker.write_text((T0 - timedelta(hours=2)).isoformat())
    await check_backup_freshness(marker, alerts, now=T0)
    assert len(session.sent(SendMessage)) == 2


async def test_public_health_alerts_after_threshold_and_resets():
    status = {"code": 500}

    async def healthz(_: web.Request) -> web.Response:
        return web.json_response({}, status=status["code"])

    app = web.Application()
    app.router.add_get("/healthz", healthz)
    bot, session = make_bot()
    alerts = AlertService(bot, -1, "prod", debounce=timedelta(0))
    async with TestServer(app) as server:
        check = PublicHealthCheck(str(server.make_url("/healthz")), alerts, threshold=3)
        await check.run()
        await check.run()
        assert session.sent(SendMessage) == []
        await check.run()
        assert len(session.sent(SendMessage)) == 1
        status["code"] = 200
        await check.run()
        status["code"] = 500
        await check.run()
        assert len(session.sent(SendMessage)) == 1


def _settings(**kw) -> Settings:
    base = {
        "bot_token": "42:TEST",
        "database_url": "postgresql+asyncpg://unused",
        "public_base_url": "https://bot.example",
        "webhook_secret": "s" * 32,
    }
    return Settings(**{**base, **kw})


def test_build_jobs_prod(sessionmaker):
    jobs = build_jobs(
        _settings(env="prod", alert_chat_id=-1), sessionmaker, AlertService(None, None, "prod")
    )
    assert {j.name for j in jobs} == {
        "cleanup_processed_updates",
        "backup_freshness",
        "public_health",
    }


def test_build_jobs_dev_polling(sessionmaker):
    jobs = build_jobs(
        _settings(env="dev", telegram_mode="polling"), sessionmaker, AlertService(None, None, "dev")
    )
    assert {j.name for j in jobs} == {"cleanup_processed_updates"}
