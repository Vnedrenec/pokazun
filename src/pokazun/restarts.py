"""Detects crash/restart loops across process restarts.

State lives in a small file on a persistent volume.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

from pokazun.alerts import Alert, AlertService


def record_start(path: Path, now: datetime, *, window: timedelta = timedelta(minutes=10)) -> int:
    try:
        starts = [datetime.fromisoformat(s) for s in json.loads(path.read_text(encoding="utf-8"))]
    except (OSError, ValueError, TypeError):
        starts = []
    recent = [s for s in starts if now - s < window] + [now]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([s.isoformat() for s in recent]), encoding="utf-8")
    return len(recent)


async def check_restart_loop(
    path: Path, alerts: AlertService, *, service: str, now: datetime, threshold: int = 3
) -> None:
    starts = record_start(path, now)
    if starts >= threshold:
        await alerts.send(
            Alert(
                job=f"{service}_restart",
                message=f"restart loop: {starts} starts within 10 minutes",
                dedupe_key=f"restart_loop:{service}",
            )
        )
