from datetime import UTC, datetime, timedelta

from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import SendMessage

from pokazun.alerts import Alert, AlertService, format_alert
from tests.tg import make_bot

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def test_format_contains_required_fields():
    text = format_alert(
        Alert(job="airtable_sync", message="timeout", ids={"object_id": "rec1"}),
        env="prod",
        now=T0,
    )
    assert "[prod]" in text
    assert "airtable_sync" in text
    assert "2026-10-01 12:00:00 UTC" in text
    assert "timeout" in text
    assert "object_id: rec1" in text


def test_alert_text_is_redacted():
    text = format_alert(
        Alert(job="uspacy", message="bad phone +380501234123 token 7123456789:" + "A" * 35),
        env="prod",
        now=T0,
    )
    assert "501234123" not in text
    assert "7123456789:" not in text


def test_long_message_truncated():
    text = format_alert(Alert(job="j", message="x" * 5000), env="prod", now=T0)
    assert len(text) < 1000


async def test_sends_to_chat():
    bot, session = make_bot()
    service = AlertService(bot, -100123, "staging", clock=Clock(T0))
    assert await service.send(Alert(job="j", message="boom")) is True
    [msg] = session.sent(SendMessage)
    assert msg.chat_id == -100123
    assert "[staging]" in msg.text


async def test_debounce_same_key():
    bot, session = make_bot()
    clock = Clock(T0)
    service = AlertService(bot, -1, "prod", clock=clock)
    alert = Alert(job="j", message="boom", dedupe_key="k")
    assert await service.send(alert) is True
    clock.now = T0 + timedelta(minutes=29)
    assert await service.send(alert) is False
    clock.now = T0 + timedelta(minutes=31)
    assert await service.send(alert) is True
    assert len(session.sent(SendMessage)) == 2


async def test_no_chat_configured_only_logs():
    bot, session = make_bot()
    service = AlertService(bot, None, "dev")
    assert await service.send(Alert(job="j", message="boom")) is False
    assert session.requests == []


async def test_send_failure_does_not_raise_and_is_retried_next_time():
    bot, session = make_bot()
    session.fail_with[SendMessage] = TelegramNetworkError(method=None, message="down")
    clock = Clock(T0)
    service = AlertService(bot, -1, "prod", clock=clock)
    alert = Alert(job="j", message="boom", dedupe_key="k")
    assert await service.send(alert) is False
    session.fail_with.clear()
    assert await service.send(alert) is True
