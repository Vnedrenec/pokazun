from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

import aiohttp
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pokazun.alerts import Alert, AlertService
from pokazun.clock import utcnow
from pokazun.config import Settings
from pokazun.db.models import ProcessedUpdate
from pokazun.health import read_backup_marker
from pokazun.log import get_logger
from pokazun.worker.scheduler import Job

log = get_logger(__name__)


async def cleanup_processed_updates(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    now: datetime,
    keep: timedelta = timedelta(days=7),
) -> int:
    async with sessionmaker() as session, session.begin():
        result = await session.execute(
            delete(ProcessedUpdate).where(ProcessedUpdate.processed_at < now - keep)
        )
    log.info("processed_updates_cleaned", deleted=result.rowcount)
    return result.rowcount


async def check_backup_freshness(
    marker_path: Path,
    alerts: AlertService,
    *,
    now: datetime,
    max_age: timedelta = timedelta(hours=26),
) -> None:
    last = read_backup_marker(marker_path)
    if last is None or now - last > max_age:
        await alerts.send(
            Alert(
                job="backup",
                message=(
                    f"no successful backup within {max_age}; "
                    f"last: {last.isoformat() if last else 'never'}"
                ),
                dedupe_key="backup_stale",
            )
        )


class PublicHealthCheck:
    """Probes the public HTTPS /healthz through the proxy; alerts after N consecutive failures."""

    def __init__(
        self, url: str, alerts: AlertService, *, threshold: int = 3, timeout: float = 10.0
    ) -> None:
        self._url = url
        self._alerts = alerts
        self._threshold = threshold
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._failures = 0

    async def run(self) -> None:
        error: str | None = None
        try:
            async with (
                aiohttp.ClientSession(timeout=self._timeout) as http,
                http.get(self._url) as resp,
            ):
                if resp.status != 200:
                    error = f"HTTP {resp.status}"
        except (aiohttp.ClientError, TimeoutError) as exc:
            error = f"{type(exc).__name__}: {exc}"
        if error is None:
            self._failures = 0
            return
        self._failures += 1
        log.warning("public_health_failed", failures=self._failures, error=error)
        if self._failures >= self._threshold:
            await self._alerts.send(
                Alert(
                    job="https_healthz",
                    message=f"{self._url} unavailable ({self._failures} checks): {error}",
                    dedupe_key="https_healthz",
                )
            )


def build_jobs(
    settings: Settings,
    sessionmaker: async_sessionmaker[AsyncSession],
    alerts: AlertService,
    *,
    clock: Callable[[], datetime] = utcnow,
) -> list[Job]:
    async def cleanup() -> None:
        await cleanup_processed_updates(sessionmaker, now=clock())

    jobs = [Job("cleanup_processed_updates", timedelta(hours=6), cleanup)]
    if settings.env == "prod":

        async def backup() -> None:
            await check_backup_freshness(settings.backup_marker_path, alerts, now=clock())

        jobs.append(Job("backup_freshness", timedelta(hours=1), backup, run_on_start=False))
    if settings.telegram_mode == "webhook":
        check = PublicHealthCheck(settings.public_base_url.rstrip("/") + "/healthz", alerts)
        jobs.append(Job("public_health", timedelta(minutes=5), check.run, run_on_start=False))
    return jobs
