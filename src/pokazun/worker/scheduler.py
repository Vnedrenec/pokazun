import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta

import structlog

from pokazun.alerts import Alert, AlertService
from pokazun.log import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class Job:
    name: str
    interval: timedelta
    func: Callable[[], Awaitable[None]]
    run_on_start: bool = True
    alert_on_failure: bool = True


class Scheduler:
    """Runs each job in its own loop; a failing job never stops the others."""

    def __init__(self, alerts: AlertService) -> None:
        self._alerts = alerts
        self._jobs: list[Job] = []

    def add(self, job: Job) -> None:
        self._jobs.append(job)

    async def run_once(self, job: Job) -> bool:
        with structlog.contextvars.bound_contextvars(job=job.name, run_id=uuid.uuid4().hex):
            try:
                await job.func()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.exception("job_failed")
                if job.alert_on_failure:
                    await self._alerts.send(
                        Alert(
                            job=job.name,
                            message=f"{type(exc).__name__}: {exc}",
                            dedupe_key=f"job:{job.name}:{type(exc).__name__}",
                        )
                    )
                return False
            return True

    async def _loop(self, job: Job, stop: asyncio.Event) -> None:
        if not job.run_on_start and await self._sleep(job, stop):
            return
        while not stop.is_set():
            await self.run_once(job)
            if await self._sleep(job, stop):
                return

    @staticmethod
    async def _sleep(job: Job, stop: asyncio.Event) -> bool:
        """Waits one interval; returns True when stop was requested."""
        try:
            await asyncio.wait_for(stop.wait(), timeout=job.interval.total_seconds())
        except TimeoutError:
            return False
        return True

    async def run(self, stop: asyncio.Event) -> None:
        await asyncio.gather(*(self._loop(job, stop) for job in self._jobs))
