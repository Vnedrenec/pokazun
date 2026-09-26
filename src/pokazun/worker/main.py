"""Worker process: background jobs (catalog sync from stage 4, notification queue from stage 10)."""

import asyncio
import signal

import aiohttp
from aiogram import Bot

from pokazun.alerts import AlertService
from pokazun.catalog.airtable import AirtableClient
from pokazun.clock import utcnow
from pokazun.config import Settings
from pokazun.db.session import create_engine, create_sessionmaker
from pokazun.log import configure_logging, get_logger
from pokazun.restarts import check_restart_loop
from pokazun.worker.jobs import build_jobs
from pokazun.worker.scheduler import Scheduler

log = get_logger(__name__)


async def run(settings: Settings) -> None:
    engine = create_engine(settings.database_url.get_secret_value())
    sessionmaker = create_sessionmaker(engine)
    bot = Bot(settings.bot_token.get_secret_value())
    alerts = AlertService(bot, settings.alert_chat_id, settings.env)
    await check_restart_loop(
        settings.state_dir / "worker-starts.json", alerts, service="worker", now=utcnow()
    )
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as http:
            airtable = (
                AirtableClient(
                    token=settings.airtable_token.get_secret_value(),
                    base_id=settings.airtable_base_id,
                    table_id=settings.airtable_table_id,
                    session=http,
                    api_url=settings.airtable_api_url,
                )
                if settings.airtable_token is not None
                else None
            )
            scheduler = Scheduler(alerts)
            for job in build_jobs(settings, sessionmaker, alerts, airtable=airtable):
                scheduler.add(job)
            log.info("worker_started", env=settings.env, airtable=airtable is not None)
            await scheduler.run(stop)
    finally:
        await bot.session.close()
        await engine.dispose()
        log.info("worker_stopped")


def main() -> None:
    settings = Settings()
    configure_logging(level=settings.log_level, log_dir=settings.log_dir, service="worker")
    asyncio.run(run(settings))


if __name__ == "__main__":
    main()
