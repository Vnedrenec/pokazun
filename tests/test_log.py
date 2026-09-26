import json
import logging

import structlog

from pokazun.log import configure_logging, get_logger, redact_text

BOT_TOKEN = "7123456789:AAH" + "x" * 32
AIRTABLE_PAT = "patAbCdEfGhIjKlMn." + "0" * 64


def test_masks_ukrainian_phone_formats():
    for raw in ["+380501234123", "380501234123", "0501234123", "+38 (050) 123-41-23"]:
        assert redact_text(f"call {raw} now") == "call +380******123 now"


def test_does_not_mask_short_numbers_or_ids():
    assert (
        redact_text("object 620, price 55000, rec0Ab12345")
        == "object 620, price 55000, rec0Ab12345"
    )


def test_redacts_tokens():
    text = f"GET https://api.telegram.org/bot{BOT_TOKEN}/sendMessage Bearer {AIRTABLE_PAT}"
    out = redact_text(text)
    assert BOT_TOKEN not in out
    assert AIRTABLE_PAT not in out
    assert "<bot-token>" in out


def _flush() -> None:
    for handler in logging.getLogger().handlers:
        handler.flush()


def _read_lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_writes_json_file_with_service_and_context(tmp_path):
    configure_logging(level="INFO", log_dir=tmp_path, service="bot")
    with structlog.contextvars.bound_contextvars(update_id=77):
        get_logger("t").info("hello", user_id=5)
    _flush()
    [line] = _read_lines(tmp_path / "bot.log")
    assert line["event"] == "hello"
    assert line["service"] == "bot"
    assert line["update_id"] == 77
    assert line["user_id"] == 5
    assert line["level"] == "info"
    assert "timestamp" in line


def test_redacts_nested_and_exception(tmp_path):
    configure_logging(level="INFO", log_dir=tmp_path, service="worker")
    log = get_logger("t")
    try:
        raise RuntimeError("uspacy rejected phone +380501234123")
    except RuntimeError:
        log.exception("failed", payload={"phone": "0501234123", "items": ["+380671112233"]})
    logging.getLogger("aiogram").warning("token %s leaked", BOT_TOKEN)
    _flush()
    raw = (tmp_path / "worker.log").read_text(encoding="utf-8")
    assert "0501234123" not in raw
    assert "380501234123" not in raw
    assert "671112233" not in raw
    assert BOT_TOKEN not in raw
    assert "+380******123" in raw
    assert "+380******233" in raw
