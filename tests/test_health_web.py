import asyncio
import time
from datetime import UTC, datetime, timedelta

from aiogram.methods import SetWebhook
from aiohttp.test_utils import TestClient, TestServer
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from pokazun.alerts import AlertService
from pokazun.bot.factory import build_dispatcher
from pokazun.config import WEBHOOK_PATH, Settings
from pokazun.db.session import create_sessionmaker
from pokazun.health import HealthRegistry, read_backup_marker
from pokazun.web import build_web_app
from tests.tg import make_bot, message_update

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
SECRET = "s" * 32


def test_backup_marker(tmp_path):
    marker = tmp_path / "last_backup_at"
    assert read_backup_marker(marker) is None
    marker.write_text("2026-10-01T00:30:05Z\n")
    assert read_backup_marker(marker) == datetime(2026, 10, 1, 0, 30, 5, tzinfo=UTC)
    marker.write_text("garbage")
    assert read_backup_marker(marker) is None


async def test_healthz_ok_with_providers(sessionmaker, tmp_path):
    (tmp_path / "m").write_text("2026-10-01T00:30:00Z")
    health = HealthRegistry(
        sessionmaker,
        started_at=T0 - timedelta(seconds=90),
        backup_marker_path=tmp_path / "m",
        clock=lambda: T0,
    )

    async def provider(session):
        return {"eligible_object_count": 3}

    health.register(provider)
    async with TestClient(TestServer(build_web_app(health=health))) as client:
        resp = await client.get("/healthz")
        body = await resp.json()
    assert resp.status == 200
    assert body == {
        "db": "ok",
        "uptime_s": 90,
        "last_backup_at": "2026-10-01T00:30:00+00:00",
        "eligible_object_count": 3,
    }


async def test_healthz_db_down_returns_503(tmp_path):
    engine = create_async_engine(
        "postgresql+asyncpg://nobody:nothing@127.0.0.1:1/none", poolclass=NullPool
    )
    health = HealthRegistry(
        create_sessionmaker(engine), started_at=T0, backup_marker_path=None, db_timeout=2.0
    )
    async with TestClient(TestServer(build_web_app(health=health))) as client:
        resp = await client.get("/healthz")
        body = await resp.json()
    assert resp.status == 503
    assert body["db"] == "error"
    await engine.dispose()


class _HangingSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, *args, **kwargs):
        await asyncio.sleep(30)
        return None


class _HangingSessionmaker:
    def __call__(self):
        return _HangingSession()


async def test_healthz_slow_db_returns_503_within_timeout():
    health = HealthRegistry(
        _HangingSessionmaker(),  # type: ignore[arg-type]
        started_at=T0,
        backup_marker_path=None,
        db_timeout=0.2,
    )
    async with TestClient(TestServer(build_web_app(health=health))) as client:
        async with asyncio.timeout(5):
            start = time.monotonic()
            resp = await client.get("/healthz")
            body = await resp.json()
            elapsed = time.monotonic() - start
    assert resp.status == 503
    assert body["db"] == "error"
    assert elapsed < 5


async def test_webhook_rejects_wrong_secret_and_sets_webhook(sessionmaker):
    bot, session = make_bot()
    settings = Settings(
        env="dev",
        bot_token="42:TEST",
        database_url="postgresql+asyncpg://unused",
        public_base_url="https://bot.example",
        webhook_secret=SECRET,
    )
    dp = build_dispatcher(
        settings=settings,
        sessionmaker=sessionmaker,
        alerts=AlertService(None, None, "dev"),
        routers=[],
    )
    health = HealthRegistry(sessionmaker, started_at=T0, backup_marker_path=None)
    app = build_web_app(
        health=health, bot=bot, dispatcher=dp, webhook_secret=SECRET, handle_in_background=False
    )
    async with TestClient(TestServer(app)) as client:
        bad = await client.post(WEBHOOK_PATH, json={"update_id": 1})
        good = await client.post(
            WEBHOOK_PATH,
            json=message_update("/start").model_dump(mode="json", exclude_none=True),
            headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
        )
    assert bad.status == 401
    assert good.status == 200
    [hook] = session.sent(SetWebhook)
    assert hook.url == "https://bot.example" + WEBHOOK_PATH
    assert hook.secret_token == SECRET
