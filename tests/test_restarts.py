from datetime import UTC, datetime, timedelta

from aiogram.methods import SendMessage

from pokazun.alerts import AlertService
from pokazun.restarts import check_restart_loop, record_start
from tests.tg import make_bot

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def test_record_start_counts_window(tmp_path):
    path = tmp_path / "starts.json"
    assert record_start(path, T0) == 1
    assert record_start(path, T0 + timedelta(minutes=2)) == 2
    assert record_start(path, T0 + timedelta(minutes=15)) == 1


def test_corrupted_state_file_is_reset(tmp_path):
    path = tmp_path / "starts.json"
    path.write_text("{not json")
    assert record_start(path, T0) == 1


async def test_alert_on_third_start(tmp_path):
    bot, session = make_bot()
    alerts = AlertService(bot, -1, "prod", clock=lambda: T0)
    path = tmp_path / "starts.json"
    for minute in range(3):
        await check_restart_loop(path, alerts, service="bot", now=T0 + timedelta(minutes=minute))
    [msg] = session.sent(SendMessage)
    assert "restart loop" in msg.text
