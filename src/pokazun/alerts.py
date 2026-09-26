"""Critical alerts to the «Парсер + Показун» Telegram group, with per-key debounce."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from aiogram import Bot

from pokazun.clock import utcnow
from pokazun.log import get_logger, redact_text

log = get_logger(__name__)

MAX_MESSAGE_CHARS = 500


@dataclass(frozen=True)
class Alert:
    job: str
    message: str
    level: Literal["critical", "warning"] = "critical"
    ids: Mapping[str, str | int] = field(default_factory=dict)
    dedupe_key: str | None = None


def format_alert(alert: Alert, *, env: str, now: datetime) -> str:
    icon = "🔴" if alert.level == "critical" else "🟠"
    message = redact_text(alert.message)
    if len(message) > MAX_MESSAGE_CHARS:
        message = message[:MAX_MESSAGE_CHARS] + "…"
    lines = [
        f"{icon} [{env}] {alert.job}",
        f"{now:%Y-%m-%d %H:%M:%S} UTC",
        message,
    ]
    lines += [f"{key}: {redact_text(str(value))}" for key, value in alert.ids.items()]
    return "\n".join(lines)


class AlertService:
    def __init__(
        self,
        bot: Bot | None,
        chat_id: int | None,
        env: str,
        *,
        debounce: timedelta = timedelta(minutes=30),
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._bot = bot
        self._chat_id = chat_id
        self._env = env
        self._debounce = debounce
        self._clock = clock
        self._last_sent: dict[str, datetime] = {}

    async def send(self, alert: Alert) -> bool:
        now = self._clock()
        key = alert.dedupe_key or f"{alert.job}:{alert.message}"
        last = self._last_sent.get(key)
        if last is not None and now - last < self._debounce:
            log.info("alert_debounced", job=alert.job, dedupe_key=key)
            return False
        log.error(
            "alert", job=alert.job, alert_message=alert.message, level=alert.level, **alert.ids
        )
        if self._bot is None or self._chat_id is None:
            return False
        try:
            await self._bot.send_message(self._chat_id, format_alert(alert, env=self._env, now=now))
        except Exception:
            log.exception("alert_send_failed", job=alert.job)
            return False
        self._last_sent[key] = now
        return True
