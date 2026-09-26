"""Health metrics for /healthz. Later stages register providers (sync, queue)."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pokazun.clock import utcnow
from pokazun.log import get_logger

log = get_logger(__name__)

HealthProvider = Callable[[AsyncSession], Awaitable[dict[str, Any]]]


def read_backup_marker(path: Path) -> datetime | None:
    try:
        raw = path.read_text(encoding="utf-8").strip()
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (OSError, ValueError):
        return None
    return value if value.tzinfo else None


class HealthRegistry:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        *,
        started_at: datetime,
        backup_marker_path: Path | None,
        clock: Callable[[], datetime] = utcnow,
        db_timeout: float = 3.0,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._started_at = started_at
        self._backup_marker_path = backup_marker_path
        self._clock = clock
        self._db_timeout = db_timeout
        self._providers: list[HealthProvider] = []

    def register(self, provider: HealthProvider) -> None:
        self._providers.append(provider)

    async def collect(self) -> tuple[bool, dict[str, Any]]:
        data: dict[str, Any] = {"db": "ok"}
        ok = True
        try:
            async with asyncio.timeout(self._db_timeout), self._sessionmaker() as session:
                await session.execute(text("SELECT 1"))
                for provider in self._providers:
                    data.update(await provider(session))
        except Exception:
            log.exception("health_db_check_failed")
            data["db"] = "error"
            ok = False
        data["uptime_s"] = int((self._clock() - self._started_at).total_seconds())
        if self._backup_marker_path is not None:
            marker = read_backup_marker(self._backup_marker_path)
            data["last_backup_at"] = marker.isoformat() if marker else None
        return ok, data
