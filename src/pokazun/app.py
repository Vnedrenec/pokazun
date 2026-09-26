"""Bot process: Telegram webhook (or polling in dev) and /healthz."""

import asyncio

from aiogram import Bot
from aiohttp import web

from pokazun.alerts import AlertService
from pokazun.bot.factory import build_dispatcher
from pokazun.bot.handlers import build_routers
from pokazun.clock import utcnow
from pokazun.config import Settings
from pokazun.db.session import create_engine, create_sessionmaker
from pokazun.health import HealthRegistry
from pokazun.log import configure_logging, get_logger
from pokazun.restarts import check_restart_loop
from pokazun.web import build_web_app

log = get_logger(__name__)


async def create_app(settings: Settings) -> web.Application:
    engine = create_engine(settings.database_url.get_secret_value())
    sessionmaker = create_sessionmaker(engine)
    bot = Bot(settings.bot_token.get_secret_value())
    alerts = AlertService(bot, settings.alert_chat_id, settings.env)
    await check_restart_loop(
        settings.state_dir / "bot-starts.json", alerts, service="bot", now=utcnow()
    )
    dp = build_dispatcher(
        settings=settings, sessionmaker=sessionmaker, alerts=alerts, routers=build_routers()
    )
    health = HealthRegistry(
        sessionmaker, started_at=utcnow(), backup_marker_path=settings.backup_marker_path
    )
    app = build_web_app(
        health=health,
        bot=bot,
        dispatcher=dp,
        webhook_secret=settings.webhook_secret.get_secret_value()
        if settings.webhook_secret
        else None,
    )

    async def _dispose(_: web.Application) -> None:
        await engine.dispose()

    app.on_cleanup.append(_dispose)
    return app


async def run_polling(settings: Settings) -> None:
    """Local development only (config forbids polling in prod)."""
    engine = create_engine(settings.database_url.get_secret_value())
    bot = Bot(settings.bot_token.get_secret_value())
    alerts = AlertService(bot, settings.alert_chat_id, settings.env)
    dp = build_dispatcher(
        settings=settings,
        sessionmaker=create_sessionmaker(engine),
        alerts=alerts,
        routers=build_routers(),
    )
    await bot.delete_webhook(drop_pending_updates=False)
    try:
        await dp.start_polling(bot)
    finally:
        await engine.dispose()


def main() -> None:
    settings = Settings()
    configure_logging(level=settings.log_level, log_dir=settings.log_dir, service="bot")
    log.info("starting", env=settings.env, mode=settings.telegram_mode)
    if settings.telegram_mode == "polling":
        asyncio.run(run_polling(settings))
    else:
        web.run_app(
            create_app(settings),
            host=settings.web_host,
            port=settings.web_port,
            access_log=None,
            print=None,
        )


if __name__ == "__main__":
    main()
