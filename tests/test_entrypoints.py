"""Supplementary wiring smoke test (not in the stage plan).

No plan test imports the process entrypoints, which left `app.py` and
`bot.handlers` at 0% and the total coverage below the required 85%.
This module only builds the app object and checks its routes; it adds
no product behavior and changes no plan test.
"""

from pokazun.bot.handlers import build_routers
from pokazun.config import Settings
from pokazun.health import HealthRegistry
from pokazun.web import HEALTH_KEY


def _settings(tmp_path) -> Settings:
    return Settings(
        env="dev",
        bot_token="42:TEST",
        database_url="postgresql+asyncpg://u:p@db/pokazun",
        telegram_mode="polling",
        state_dir=tmp_path,
        backup_marker_path=tmp_path / "marker",
    )


def test_build_routers_contains_search_setup_then_fallback():
    assert [router.name for router in build_routers()] == ["search_setup", "fallback"]


async def test_create_app_registers_healthz(tmp_path):
    from pokazun.app import create_app

    app = await create_app(_settings(tmp_path))
    try:
        assert isinstance(app[HEALTH_KEY], HealthRegistry)
        paths = {r.get_info().get("path") for r in app.router.resources()}
        assert "/healthz" in paths
    finally:
        await app.cleanup()
