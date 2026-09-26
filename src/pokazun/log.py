"""JSON logging for every process.

Phones and credentials are redacted before anything is written.
"""

import logging
import re
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any

import structlog

LOG_RETENTION_DAYS = 45  # spec requires at least 30

_BOT_TOKEN_RE = re.compile(r"(?<!\d)\d{6,12}:[A-Za-z0-9_-]{30,}")
_AIRTABLE_PAT_RE = re.compile(r"\bpat[A-Za-z0-9]{10,}\.[A-Za-z0-9]{20,}")
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._<>\-]+")
_PHONE_RE = re.compile(r"(?<!\w)(?:\+?38[\s\-()]*)?0(?:[\s\-()]*\d){9}(?!\d)")

get_logger = structlog.get_logger


def _mask_phone(match: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", match.group(0))
    return f"+380******{digits[-3:]}"


def redact_text(text: str) -> str:
    text = _BOT_TOKEN_RE.sub("<bot-token>", text)
    text = _AIRTABLE_PAT_RE.sub("<airtable-token>", text)
    text = _BEARER_RE.sub("Bearer <redacted>", text)
    return _PHONE_RE.sub(_mask_phone, text)


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: _redact_value(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [_redact_value(v) for v in value]
    return value


def _redact_processor(_logger: Any, _name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    return {k: _redact_value(v) for k, v in event_dict.items()}


def configure_logging(*, level: str, log_dir: Path | None, service: str) -> None:
    def add_service(_logger: Any, _name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
        event_dict.setdefault("service", service)
        return event_dict

    shared: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        add_service,
    ]
    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            _redact_processor,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
    )
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(
            TimedRotatingFileHandler(
                log_dir / f"{service}.log",
                when="midnight",
                backupCount=LOG_RETENTION_DAYS,
                utc=True,
                encoding="utf-8",
            )
        )
    root = logging.getLogger()
    for old in list(root.handlers):
        root.removeHandler(old)
        old.close()
    for handler in handlers:
        handler.setFormatter(formatter)
        root.addHandler(handler)
    root.setLevel(level)
