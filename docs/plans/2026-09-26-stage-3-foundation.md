# Етап 3. Каркас, інфраструктура, деплой — план реалізації

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Робочий production-каркас Показуна: Python-пакет, конфіг, structured-логи з маскуванням, PostgreSQL + Alembic, aiogram-диспетчер з middleware (ідемпотентність, доступ, активність), алерти в «Парсер + Показун», health-ендпоінт, воркер із планувальником, Docker Compose для prod/staging, HTTPS-проксі, щоденний backup.

**Architecture:** Два процеси з одного образу: `bot` (aiohttp: Telegram webhook + `/healthz`, згодом сторінки об’єктів) і `worker` (планувальник фонових задач: sync Airtable, черга сповіщень, службові перевірки). Стан — лише в PostgreSQL. Доменна логіка не залежить від aiogram; Telegram-шар тонкий. Кожне середовище (prod / staging) — окремий Compose-проєкт з власною БД; спільний лише Caddy-проксі.

**Tech Stack:** Python 3.12, uv, aiogram 3, aiohttp, SQLAlchemy 2 (async) + asyncpg, Alembic, pydantic-settings, structlog, pytest + pytest-asyncio, ruff, Docker Compose, Caddy, PostgreSQL 16, rclone.

**Spec:** `docs/plans/2026-09-25-pokazun-roadmap.md` (етап 3) + Д2 §2, §18–22, §24 (#12–16), §27. Д1 / Д2 — Google Docs `1bWVYsZVkq6uIKkQ91EDj1lpW1eJ4Hlbe` / `1GjZHxXSOUemdOKKZyK0xwRHHXzxh6iks`.

**Наступні плани:** `2026-09-26-stage-4-catalog-sync.md`, `2026-09-26-stage-5-search-setup.md`. Порядок виконання: 3 → 4 → 5.

## Global Constraints

- Це production-продукт. Жодних заглушок «на потім», `TODO`, вимкнених тестів чи `except: pass`.
- Python `>=3.12,<3.13`; залежності фіксуються в `uv.lock`; `uv sync --frozen` у CI і Docker.
- Секрети (bot token, Airtable PAT, DB password, Uspacy credentials) — лише в env на VPS (`/opt/pokazun/<env>/.env`, `chmod 600`), ніколи в git, логах, алертах, документах.
- Production і staging: різні bot tokens, різні БД і DB credentials (Д2 §2, §20).
- Staging обслуговує лише Telegram user_id з allowlist (Д2 §2).
- PostgreSQL не публікує порт назовні (Д2 §20).
- Телефон у логах маскується як `+380******123` (Д2 §19).
- Логи зберігаються ≥ 30 днів з ротацією (Д2 §19).
- Алерт містить: середовище, час, job / інтеграцію, коротку помилку, object_id / user_id / request_id; без секретів і дампів приватних даних; з debounce (Д2 §18).
- Backup prod: щодня, retention 14 днів, копія поза VPS, ручний backup перед міграцією, перевірений restore (Д2 §21).
- Deploy: staging → smoke test → prod; міграції контрольовано перед стартом; deploy не скидає чергу, sync cursor, стан користувачів (Д2 §22).
- Усі сервіси: `restart: unless-stopped`, стартують після перезавантаження VPS (Д2 §21, §27.8).
- Час у БД — `timestamptz` у UTC. Бізнес-функції приймають `now: datetime` параметром (детерміновані тести).
- Мова бота — лише українська; тексти бота — в `src/pokazun/bot/texts.py` (створюється на етапі 5), не в хендлерах.
- Слова «MVP» у коді, коментарях, комітах і документації не використовуємо.

## Review Focus

- Telegram повторно доставив той самий `update_id` (рестарт polling, retry webhook) → обробляється рівно один раз. Тест: Task 6 `test_duplicate_update_processed_once`.
- Хендлер упав посеред обробки → транзакція відкочена, маркер `processed_updates` не збережений (повтор пройде), алерт надіслано. Тест: Task 6 `test_handler_error_rolls_back_and_alerts`.
- Користувач заблокував бота → приходить `my_chat_member` (kicked); це НЕ активність, `telegram_delivery_state` не повертається в `active`. Тест: Task 6 `test_my_chat_member_is_not_activity`.
- PostgreSQL недоступний → `/healthz` швидко віддає 503 з `"db": "error"`, а не висить чи падає 500. Тест: Task 7 `test_healthz_db_down_returns_503`.
- Телефон або токен у тексті винятку / вкладеному полі логу / алерті → замасковані. Тести: Task 3 `test_redacts_nested_and_exception`, Task 5 `test_alert_text_is_redacted`.

---

## Структура файлів

```
pyproject.toml, uv.lock, alembic.ini, compose.dev.yml, .env.example, .gitignore, Dockerfile, .dockerignore
.github/workflows/ci.yml
src/pokazun/
  __init__.py            версія
  clock.py               utcnow()
  config.py              Settings (env POKAZUN_*)
  log.py                 structlog + redaction (телефони, токени)
  alerts.py              AlertService: форматування, debounce, відправка в групу
  health.py              HealthRegistry: метрики для /healthz
  restarts.py            детектор restart loop
  web.py                 aiohttp-застосунок: /healthz, Telegram webhook
  app.py                 entrypoint процесу bot
  db/
    base.py              DeclarativeBase + naming convention
    session.py           engine / sessionmaker
    models/__init__.py   імпорт усіх моделей (для Alembic)
    models/users.py      User, SubscriptionState, DeliveryState
    models/system.py     ProcessedUpdate
  users/repository.py    touch_user()
  bot/
    factory.py           build_dispatcher()
    middlewares.py       LogContext, DbSession, Access, Idempotency, Activity
    handlers/__init__.py build_routers()
  worker/
    scheduler.py         Job, Scheduler
    jobs.py              службові задачі
    main.py              entrypoint процесу worker
migrations/env.py, migrations/script.py.mako, migrations/versions/0001_users.py
deploy/compose.yml, deploy/proxy/compose.yml, deploy/proxy/Caddyfile
deploy/backup/Dockerfile, deploy/backup/backup.sh, deploy/backup/backup-loop.sh
deploy/deploy.sh, deploy/restore-test.sh
docs/ops/runbook.md
tests/__init__.py, tests/conftest.py, tests/tg.py, tests/test_*.py
```

---

### Task 1: Каркас пакета, інструменти, CI

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `compose.dev.yml`, `.github/workflows/ci.yml`
- Create: `src/pokazun/__init__.py`, `src/pokazun/clock.py`
- Test: `tests/__init__.py`, `tests/test_smoke.py`

**Interfaces:**
- Produces: пакет `pokazun`; `pokazun.clock.utcnow() -> datetime` (aware, UTC); команди `uv run pytest`, `uv run ruff check .`; env `TEST_DATABASE_URL` для тестів з БД.

- [ ] **Step 1: Створити `pyproject.toml`**

```toml
[project]
name = "pokazun"
version = "0.1.0"
description = "Pokazun — Telegram bot for apartment search (Praktik Real Estate, Chernihiv)"
requires-python = ">=3.12,<3.13"
dependencies = [
    "aiogram>=3.15,<4",
    "aiohttp>=3.10",
    "sqlalchemy[asyncio]>=2.0.36,<2.1",
    "asyncpg>=0.30",
    "alembic>=1.14",
    "pydantic-settings>=2.6",
    "structlog>=24.4",
    "tzdata>=2024.2",
]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "ruff>=0.8",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/pokazun"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
testpaths = ["tests"]
addopts = "-ra --strict-markers"

[tool.ruff]
line-length = 100
target-version = "py312"
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "ASYNC", "RUF", "S", "DTZ"]
ignore = ["S101", "RUF001", "RUF002", "RUF003"]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S105", "S106", "S311"]
```

`RUF001–003` вимкнені, бо українські тексти містять кириличні символи, схожі на латиницю. `DTZ` забороняє naive datetime.

- [ ] **Step 2: Створити `.gitignore`**

```gitignore
__pycache__/
*.py[cod]
.venv/
.pytest_cache/
.ruff_cache/
.env
.env.*
!.env.example
*.dump
```

- [ ] **Step 3: Створити `compose.dev.yml` (локальна БД для тестів)**

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: pokazun
      POSTGRES_PASSWORD: pokazun
      POSTGRES_DB: pokazun_test
    ports:
      - "127.0.0.1:5432:5432"
```

- [ ] **Step 4: Написати тест, що падає**

`tests/__init__.py` — порожній файл.

`tests/test_smoke.py`:

```python
from datetime import UTC

import pokazun
from pokazun.clock import utcnow


def test_package_has_version():
    assert pokazun.__version__ == "0.1.0"


def test_utcnow_is_aware_utc():
    now = utcnow()
    assert now.tzinfo is UTC
```

- [ ] **Step 5: Запустити — має впасти**

Run: `uv sync && uv run pytest tests/test_smoke.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pokazun'`.

- [ ] **Step 6: Реалізація**

`src/pokazun/__init__.py`:

```python
__version__ = "0.1.0"
```

`src/pokazun/clock.py`:

```python
from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)
```

- [ ] **Step 7: Запустити — має пройти**

Run: `uv sync && uv run pytest tests/test_smoke.py -v && uv run ruff check . && uv run ruff format --check .`
Expected: 2 passed; ruff без помилок.

- [ ] **Step 8: CI**

`.github/workflows/ci.yml`:

```yaml
name: ci
on:
  push:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: pokazun
          POSTGRES_PASSWORD: pokazun
          POSTGRES_DB: pokazun_test
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U pokazun"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10
    env:
      TEST_DATABASE_URL: postgresql+asyncpg://pokazun:pokazun@localhost:5432/pokazun_test
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - run: uv sync --frozen
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run pytest
```

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml uv.lock .gitignore compose.dev.yml .github src tests
git commit -m "chore: project skeleton, tooling and CI"
```

---

### Task 2: Конфігурація

**Files:**
- Create: `src/pokazun/config.py`, `.env.example`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `pokazun.config.Settings` (поля нижче), `Settings.allowlist -> frozenset[int]`, `Settings.webhook_url -> str`, константа `WEBHOOK_PATH = "/tg/webhook"`.

- [ ] **Step 1: Тест**

`tests/test_config.py`:

```python
import pytest
from pydantic import ValidationError

from pokazun.config import WEBHOOK_PATH, Settings

BASE = {
    "bot_token": "123456:" + "A" * 35,
    "database_url": "postgresql+asyncpg://u:p@db/pokazun",
    "public_base_url": "https://bot.praktik.cn.ua",
    "webhook_secret": "s" * 32,
}


def make(**overrides) -> Settings:
    return Settings(**{**BASE, **overrides})


def test_prod_valid():
    s = make(env="prod", alert_chat_id=-100123)
    assert s.allowlist == frozenset()
    assert s.webhook_url == "https://bot.praktik.cn.ua" + WEBHOOK_PATH


def test_prod_requires_alert_chat():
    with pytest.raises(ValidationError, match="ALERT_CHAT_ID"):
        make(env="prod")


def test_prod_rejects_allowlist():
    with pytest.raises(ValidationError, match="must not set"):
        make(env="prod", alert_chat_id=-1, allowed_user_ids="1")


def test_prod_rejects_polling():
    with pytest.raises(ValidationError, match="webhook mode"):
        make(env="prod", alert_chat_id=-1, telegram_mode="polling")


def test_staging_requires_allowlist():
    with pytest.raises(ValidationError, match="ALLOWED_USER_IDS"):
        make(env="staging", alert_chat_id=-1)


def test_allowlist_parsing():
    s = make(env="staging", allowed_user_ids=" 11, 22,33 ")
    assert s.allowlist == frozenset({11, 22, 33})


def test_allowlist_rejects_garbage():
    with pytest.raises(ValidationError, match="integers"):
        make(env="staging", allowed_user_ids="11,abc")


def test_webhook_requires_https():
    with pytest.raises(ValidationError, match="https"):
        make(env="dev", public_base_url="http://bot.praktik.cn.ua")


def test_webhook_secret_format():
    with pytest.raises(ValidationError, match="WEBHOOK_SECRET"):
        make(env="dev", webhook_secret="short")


def test_polling_dev_needs_no_webhook_fields():
    s = Settings(
        env="dev",
        bot_token=BASE["bot_token"],
        database_url=BASE["database_url"],
        telegram_mode="polling",
    )
    assert s.telegram_mode == "polling"


def test_secrets_not_in_repr():
    s = make(env="prod", alert_chat_id=-1)
    assert BASE["bot_token"] not in repr(s)
    assert "u:p@" not in repr(s)


def test_loads_from_env(monkeypatch):
    monkeypatch.setenv("POKAZUN_ENV", "staging")
    monkeypatch.setenv("POKAZUN_BOT_TOKEN", BASE["bot_token"])
    monkeypatch.setenv("POKAZUN_DATABASE_URL", BASE["database_url"])
    monkeypatch.setenv("POKAZUN_TELEGRAM_MODE", "polling")
    monkeypatch.setenv("POKAZUN_ALLOWED_USER_IDS", "7")
    assert Settings().allowlist == frozenset({7})
```

- [ ] **Step 2: Запустити — має впасти**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pokazun.config'`.

- [ ] **Step 3: Реалізація**

`src/pokazun/config.py`:

```python
"""Runtime configuration. Every value comes from environment variables with the POKAZUN_ prefix."""

import re
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

WEBHOOK_PATH = "/tg/webhook"
_SECRET_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{16,256}$")


def _parse_ids(raw: str) -> frozenset[int]:
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    try:
        return frozenset(int(p) for p in parts)
    except ValueError as exc:
        raise ValueError("POKAZUN_ALLOWED_USER_IDS must be comma-separated integers") from exc


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="POKAZUN_", extra="ignore")

    env: Literal["prod", "staging", "dev"]
    bot_token: SecretStr
    database_url: SecretStr
    telegram_mode: Literal["webhook", "polling"] = "webhook"
    public_base_url: str = ""
    webhook_secret: SecretStr | None = None
    alert_chat_id: int | None = None
    allowed_user_ids: str = ""
    log_level: str = "INFO"
    log_dir: Path | None = None
    state_dir: Path = Path("/var/lib/pokazun")
    backup_marker_path: Path = Path("/backups/last_backup_at")
    web_host: str = "0.0.0.0"  # noqa: S104 — container-internal bind, the proxy is the only entrypoint
    web_port: int = 8080

    @model_validator(mode="after")
    def _validate(self) -> "Settings":
        allowlist = _parse_ids(self.allowed_user_ids)
        if self.telegram_mode == "webhook":
            if not self.public_base_url.startswith("https://"):
                raise ValueError("POKAZUN_PUBLIC_BASE_URL must be an https:// URL in webhook mode")
            secret = self.webhook_secret.get_secret_value() if self.webhook_secret else ""
            if not _SECRET_TOKEN_RE.match(secret):
                raise ValueError(
                    "POKAZUN_WEBHOOK_SECRET must be 16-256 chars of A-Z, a-z, 0-9, _ or -"
                )
        if self.env == "staging" and not allowlist:
            raise ValueError("staging requires POKAZUN_ALLOWED_USER_IDS")
        if self.env == "prod":
            if allowlist:
                raise ValueError("prod must not set POKAZUN_ALLOWED_USER_IDS")
            if self.alert_chat_id is None:
                raise ValueError("prod requires POKAZUN_ALERT_CHAT_ID")
            if self.telegram_mode != "webhook":
                raise ValueError("prod must run in webhook mode")
        return self

    @property
    def allowlist(self) -> frozenset[int]:
        return _parse_ids(self.allowed_user_ids)

    @property
    def webhook_url(self) -> str:
        return self.public_base_url.rstrip("/") + WEBHOOK_PATH
```

`.env.example` (шаблон; реальні значення — лише на VPS):

```dotenv
# --- compose ---
POKAZUN_ENV=staging
POKAZUN_ENV_FILE=/opt/pokazun/staging/.env
POSTGRES_PASSWORD=change-me
# prod only: enables the backup service
COMPOSE_PROFILES=
# rclone remote for the off-VPS backup copy, e.g. offsite:pokazun-backups/prod
BACKUP_REMOTE=
# RCLONE_CONFIG_OFFSITE_TYPE=s3
# RCLONE_CONFIG_OFFSITE_PROVIDER=...
# RCLONE_CONFIG_OFFSITE_ACCESS_KEY_ID=...
# RCLONE_CONFIG_OFFSITE_SECRET_ACCESS_KEY=...
# RCLONE_CONFIG_OFFSITE_ENDPOINT=...

# --- application ---
POKAZUN_BOT_TOKEN=
POKAZUN_DATABASE_URL=postgresql+asyncpg://pokazun:change-me@db:5432/pokazun
POKAZUN_TELEGRAM_MODE=webhook
POKAZUN_PUBLIC_BASE_URL=https://staging-bot.praktik.cn.ua
POKAZUN_WEBHOOK_SECRET=
POKAZUN_ALERT_CHAT_ID=
POKAZUN_ALLOWED_USER_IDS=
POKAZUN_LOG_DIR=/var/log/pokazun
POKAZUN_LOG_LEVEL=INFO
```

- [ ] **Step 4: Запустити — має пройти**

Run: `uv run pytest tests/test_config.py -v`
Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pokazun/config.py .env.example tests/test_config.py
git commit -m "feat: environment-based settings with prod/staging guards"
```

---

### Task 3: Structured-логи з маскуванням

**Files:**
- Create: `src/pokazun/log.py`
- Test: `tests/test_log.py`

**Interfaces:**
- Produces: `redact_text(text: str) -> str`; `configure_logging(*, level: str, log_dir: Path | None, service: str) -> None`; `get_logger = structlog.get_logger`. Кореляційні ID додаються через `structlog.contextvars.bind_contextvars(...)` / `bound_contextvars(...)`.

- [ ] **Step 1: Тест**

`tests/test_log.py`:

```python
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
    assert redact_text("object 620, price 55000, rec0Ab12345") == "object 620, price 55000, rec0Ab12345"


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
```

- [ ] **Step 2: Запустити — має впасти**

Run: `uv run pytest tests/test_log.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pokazun.log'`.

- [ ] **Step 3: Реалізація**

`src/pokazun/log.py`:

```python
"""JSON logging for every process. Phones and credentials are redacted before anything is written."""

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
```

- [ ] **Step 4: Запустити — має пройти**

Run: `uv run pytest tests/test_log.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pokazun/log.py tests/test_log.py
git commit -m "feat: JSON logging with phone and credential redaction"
```

---

### Task 4: PostgreSQL, моделі, Alembic, тестові фікстури БД

**Files:**
- Create: `src/pokazun/db/__init__.py` (порожній), `src/pokazun/db/base.py`, `src/pokazun/db/session.py`
- Create: `src/pokazun/db/models/__init__.py`, `src/pokazun/db/models/users.py`, `src/pokazun/db/models/system.py`
- Create: `alembic.ini`, `migrations/env.py`, `migrations/script.py.mako`, `migrations/versions/0001_users.py`
- Create: `tests/conftest.py`
- Test: `tests/test_db_migrations.py`

**Interfaces:**
- Produces:
  - `pokazun.db.base.Base` (DeclarativeBase, naming convention, `datetime` → `timestamptz`).
  - `pokazun.db.session.create_engine(url: str, **kw) -> AsyncEngine`, `create_sessionmaker(engine) -> async_sessionmaker[AsyncSession]` (`expire_on_commit=False`).
  - `pokazun.db.models.users`: `User`, `SubscriptionState` (`ACTIVE`, `PAUSED_BY_USER`, `PAUSED_INACTIVITY`), `DeliveryState` (`ACTIVE`, `BLOCKED`), `str_enum(enum_cls) -> sqlalchemy.Enum` (non-native, зберігає `.value`).
  - `pokazun.db.models.system.ProcessedUpdate(update_id, processed_at)`.
  - Фікстури pytest: `migrated_db -> str` (session), `engine -> AsyncEngine` (усі таблиці очищені), `sessionmaker -> async_sessionmaker`.
  - Правило для наступних етапів: кожна нова модель імпортується в `db/models/__init__.py`, кожна зміна схеми — нова ручна міграція `migrations/versions/NNNN_*.py`; тест дрейфу `test_models_match_migrations` мусить лишатися зеленим.

- [ ] **Step 1: Базові модулі БД**

`src/pokazun/db/base.py`:

```python
from datetime import datetime

from sqlalchemy import DateTime, MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {datetime: DateTime(timezone=True)}
```

`src/pokazun/db/session.py`:

```python
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def create_engine(url: str, **kwargs: Any) -> AsyncEngine:
    return create_async_engine(url, pool_pre_ping=True, **kwargs)


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
```

`src/pokazun/db/models/users.py`:

```python
from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, Enum, Identity, String, func
from sqlalchemy.orm import Mapped, mapped_column

from pokazun.db.base import Base


def str_enum(enum_cls: type[StrEnum]) -> Enum:
    """Store a StrEnum as VARCHAR(32) holding its value; the CHECK constraint lives in the migration."""
    return Enum(
        enum_cls,
        native_enum=False,
        create_constraint=False,
        length=32,
        values_callable=lambda members: [m.value for m in members],
        validate_strings=True,
    )


class SubscriptionState(StrEnum):
    ACTIVE = "active"
    PAUSED_BY_USER = "paused_by_user"
    PAUSED_INACTIVITY = "paused_inactivity"


class DeliveryState(StrEnum):
    ACTIVE = "active"
    BLOCKED = "blocked"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(256))
    phone: Mapped[str | None] = mapped_column(String(32))
    subscription_state: Mapped[SubscriptionState] = mapped_column(
        str_enum(SubscriptionState), server_default=SubscriptionState.ACTIVE.value
    )
    telegram_delivery_state: Mapped[DeliveryState] = mapped_column(
        str_enum(DeliveryState), server_default=DeliveryState.ACTIVE.value
    )
    last_activity_at: Mapped[datetime]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
```

`src/pokazun/db/models/system.py`:

```python
from datetime import datetime

from sqlalchemy import BigInteger, func
from sqlalchemy.orm import Mapped, mapped_column

from pokazun.db.base import Base


class ProcessedUpdate(Base):
    """Telegram update_id already handled; protects against re-delivery after restarts."""

    __tablename__ = "processed_updates"

    update_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    processed_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)
```

`src/pokazun/db/models/__init__.py`:

```python
"""Importing this package registers every model on Base.metadata (used by Alembic and tests)."""

from pokazun.db.models.system import ProcessedUpdate
from pokazun.db.models.users import DeliveryState, SubscriptionState, User

__all__ = ["DeliveryState", "ProcessedUpdate", "SubscriptionState", "User"]
```

- [ ] **Step 2: Alembic**

`alembic.ini`:

```ini
[alembic]
script_location = migrations
file_template = %%(rev)s_%%(slug)s
```

`migrations/script.py.mako`:

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
"""

import sqlalchemy as sa
from alembic import op
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = None
depends_on = None


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

`migrations/env.py`:

```python
import asyncio
import os

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

import pokazun.db.models  # noqa: F401 — registers models on the metadata
from pokazun.db.base import Base

target_metadata = Base.metadata


def _database_url() -> str:
    url = os.environ.get("POKAZUN_DATABASE_URL")
    if not url:
        raise RuntimeError("POKAZUN_DATABASE_URL is not set")
    return url


def _run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async() -> None:
    engine = create_async_engine(_database_url())
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("Offline migrations are not supported; run against a database")
asyncio.run(_run_async())
```

`migrations/versions/0001_users.py`:

```python
"""users and processed_updates

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("first_name", sa.String(256), nullable=True),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("subscription_state", sa.String(32), server_default="active", nullable=False),
        sa.Column("telegram_delivery_state", sa.String(32), server_default="active", nullable=False),
        sa.Column("last_activity_at", TS, nullable=False),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("telegram_user_id", name="uq_users_telegram_user_id"),
        sa.CheckConstraint(
            "subscription_state IN ('active', 'paused_by_user', 'paused_inactivity')",
            name="ck_users_subscription_state",
        ),
        sa.CheckConstraint(
            "telegram_delivery_state IN ('active', 'blocked')",
            name="ck_users_telegram_delivery_state",
        ),
    )
    op.create_table(
        "processed_updates",
        sa.Column("update_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("processed_at", TS, server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("update_id", name="pk_processed_updates"),
    )
    op.create_index(
        "ix_processed_updates_processed_at", "processed_updates", ["processed_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_processed_updates_processed_at", table_name="processed_updates")
    op.drop_table("processed_updates")
    op.drop_table("users")
```

- [ ] **Step 3: Фікстури БД**

`tests/conftest.py`:

```python
import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import pokazun.db.models  # noqa: F401
from pokazun.db.base import Base
from pokazun.db.session import create_sessionmaker

ROOT = Path(__file__).resolve().parents[1]


def _test_database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.fail(
            "TEST_DATABASE_URL is not set. Start Postgres with "
            "`docker compose -f compose.dev.yml up -d` and export "
            "TEST_DATABASE_URL=postgresql+asyncpg://pokazun:pokazun@localhost:5432/pokazun_test",
            pytrace=False,
        )
    return url


def alembic_config(url: str) -> Config:
    os.environ["POKAZUN_DATABASE_URL"] = url
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    return cfg


@pytest.fixture(scope="session")
def migrated_db() -> str:
    url = _test_database_url()
    cfg = alembic_config(url)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    return url


@pytest.fixture
async def engine(migrated_db: str) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(migrated_db, poolclass=NullPool)
    tables = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
    async with eng.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    yield eng
    await eng.dispose()


@pytest.fixture
def sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return create_sessionmaker(engine)
```

- [ ] **Step 4: Тест**

`tests/test_db_migrations.py`:

```python
import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from pokazun.clock import utcnow
from pokazun.db.base import Base
from pokazun.db.models import DeliveryState, SubscriptionState, User
from tests.conftest import alembic_config


async def test_models_match_migrations(engine):
    def diff(sync_conn):
        ctx = MigrationContext.configure(sync_conn, opts={"compare_type": True})
        return compare_metadata(ctx, Base.metadata)

    async with engine.connect() as conn:
        assert await conn.run_sync(diff) == []


def test_migrations_roundtrip(migrated_db):
    cfg = alembic_config(migrated_db)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


async def test_user_defaults_and_enums(sessionmaker):
    async with sessionmaker() as s, s.begin():
        s.add(User(telegram_user_id=1, last_activity_at=utcnow()))
    async with sessionmaker() as s:
        user = await s.scalar(select(User))
        assert user.subscription_state is SubscriptionState.ACTIVE
        assert user.telegram_delivery_state is DeliveryState.ACTIVE
        assert user.created_at.tzinfo is not None


async def test_check_constraint_rejects_unknown_state(sessionmaker):
    async with sessionmaker() as s:
        with pytest.raises(IntegrityError):
            await s.execute(
                text(
                    "INSERT INTO users (telegram_user_id, last_activity_at, subscription_state) "
                    "VALUES (2, now(), 'bogus')"
                )
            )
```

- [ ] **Step 5: Запустити — має пройти**

Run: `docker compose -f compose.dev.yml up -d && export TEST_DATABASE_URL=postgresql+asyncpg://pokazun:pokazun@localhost:5432/pokazun_test && uv run pytest tests/test_db_migrations.py -v`
Expected: 4 passed. Якщо `test_models_match_migrations` показує різницю — виправити міграцію або модель, доки список не стане порожнім.

- [ ] **Step 6: Commit**

```bash
git add alembic.ini migrations src/pokazun/db tests/conftest.py tests/test_db_migrations.py
git commit -m "feat: database models, alembic migrations and test fixtures"
```

---

### Task 5: Алерти в «Парсер + Показун»

**Files:**
- Create: `src/pokazun/alerts.py`
- Create: `tests/tg.py` (фейкова Telegram-сесія і конструктори апдейтів — потрібні й для Task 6–8 та етапів 4–5)
- Test: `tests/test_alerts.py`

**Interfaces:**
- Consumes: `redact_text` (Task 3), `utcnow` (Task 1).
- Produces:
  - `Alert(job: str, message: str, level: Literal["critical", "warning"] = "critical", ids: Mapping[str, str | int] = {}, dedupe_key: str | None = None)`.
  - `AlertService(bot: Bot | None, chat_id: int | None, env: str, *, debounce: timedelta = timedelta(minutes=30), clock: Callable[[], datetime] = utcnow)`; `await AlertService.send(alert) -> bool` (True — реально відправлено). Ніколи не кидає виняток.
  - `format_alert(alert, *, env: str, now: datetime) -> str`.
  - `tests.tg`: `FakeSession`, `make_bot() -> tuple[Bot, FakeSession]`, `tg_user(...)`, `message_update(text, ...)`, `callback_update(data, ...)`, `my_chat_member_update(status, ...)`, `group_message_update(text)`.

- [ ] **Step 1: Тестові хелпери Telegram**

`tests/tg.py`:

```python
"""Offline Telegram: records every Bot API call and fabricates minimal successful responses."""

import itertools
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import TelegramMethod
from aiogram.types import (
    CallbackQuery,
    Chat,
    ChatMemberBanned,
    ChatMemberMember,
    ChatMemberUpdated,
    Message,
    Update,
    User,
)

BOT_ID = 42
TG_USER_ID = 5001
_update_ids = itertools.count(1)
_message_ids = itertools.count(1)


class FakeSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list[TelegramMethod[Any]] = []
        self.fail_with: dict[type, Exception] = {}
        self._next_message_id = 10_000

    async def make_request(self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None):
        self.requests.append(method)
        exc = self.fail_with.get(type(method))
        if exc is not None:
            raise exc
        returning = method.__returning__
        if returning is Message:
            self._next_message_id += 1
            chat_id = int(getattr(method, "chat_id", 0) or 0)
            return Message(
                message_id=self._next_message_id,
                date=datetime.now(UTC),
                chat=Chat(id=chat_id, type="private"),
                text=getattr(method, "text", None),
            )
        if returning is User:
            return User(id=BOT_ID, is_bot=True, first_name="Pokazun", username="pokazun_test_bot")
        return True

    async def close(self) -> None:
        return None

    async def stream_content(
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: int = 30,
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes, None]:
        raise NotImplementedError("FakeSession does not download files")
        yield b""  # pragma: no cover

    def sent(self, method_type: type) -> list[Any]:
        return [r for r in self.requests if isinstance(r, method_type)]


def make_bot() -> tuple[Bot, FakeSession]:
    session = FakeSession()
    return Bot(token=f"{BOT_ID}:TEST", session=session), session


def tg_user(user_id: int = TG_USER_ID, username: str | None = "buyer", first_name: str = "Оксана") -> User:
    return User(id=user_id, is_bot=False, first_name=first_name, username=username)


def _bot_user() -> User:
    return User(id=BOT_ID, is_bot=True, first_name="Pokazun")


def message_update(text: str, *, user: User | None = None, update_id: int | None = None) -> Update:
    user = user or tg_user()
    return Update(
        update_id=update_id if update_id is not None else next(_update_ids),
        message=Message(
            message_id=next(_message_ids),
            date=datetime.now(UTC),
            chat=Chat(id=user.id, type="private"),
            from_user=user,
            text=text,
        ),
    )


def group_message_update(text: str, *, user: User | None = None) -> Update:
    user = user or tg_user()
    return Update(
        update_id=next(_update_ids),
        message=Message(
            message_id=next(_message_ids),
            date=datetime.now(UTC),
            chat=Chat(id=-100500, type="supergroup", title="group"),
            from_user=user,
            text=text,
        ),
    )


def callback_update(
    data: str,
    *,
    user: User | None = None,
    message_id: int = 777,
    update_id: int | None = None,
) -> Update:
    user = user or tg_user()
    return Update(
        update_id=update_id if update_id is not None else next(_update_ids),
        callback_query=CallbackQuery(
            id=f"cb{next(_update_ids)}",
            from_user=user,
            chat_instance="ci",
            data=data,
            message=Message(
                message_id=message_id,
                date=datetime.now(UTC),
                chat=Chat(id=user.id, type="private"),
                from_user=_bot_user(),
                text="…",
            ),
        ),
    )


def my_chat_member_update(status: str, *, user: User | None = None) -> Update:
    user = user or tg_user()
    old = ChatMemberMember(user=_bot_user())
    new = ChatMemberBanned(user=_bot_user(), until_date=0) if status == "kicked" else old
    return Update(
        update_id=next(_update_ids),
        my_chat_member=ChatMemberUpdated(
            chat=Chat(id=user.id, type="private"),
            from_user=user,
            date=datetime.now(UTC),
            old_chat_member=old,
            new_chat_member=new,
        ),
    )
```

- [ ] **Step 2: Тест**

`tests/test_alerts.py`:

```python
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
```

- [ ] **Step 3: Запустити — має впасти**

Run: `uv run pytest tests/test_alerts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pokazun.alerts'`.

- [ ] **Step 4: Реалізація**

`src/pokazun/alerts.py`:

```python
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
        log.error("alert", job=alert.job, alert_message=alert.message, level=alert.level, **alert.ids)
        if self._bot is None or self._chat_id is None:
            return False
        try:
            await self._bot.send_message(self._chat_id, format_alert(alert, env=self._env, now=now))
        except Exception:
            log.exception("alert_send_failed", job=alert.job)
            return False
        self._last_sent[key] = now
        return True
```

- [ ] **Step 5: Запустити — має пройти**

Run: `uv run pytest tests/test_alerts.py -v`
Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add src/pokazun/alerts.py tests/tg.py tests/test_alerts.py
git commit -m "feat: debounced critical alerts to the ops Telegram group"
```

---

### Task 6: Диспетчер aiogram і middleware

**Files:**
- Create: `src/pokazun/users/__init__.py` (порожній), `src/pokazun/users/repository.py`
- Create: `src/pokazun/bot/__init__.py` (порожній), `src/pokazun/bot/middlewares.py`, `src/pokazun/bot/factory.py`, `src/pokazun/bot/handlers/__init__.py`
- Test: `tests/test_bot_middlewares.py`

**Interfaces:**
- Consumes: `Settings` (Task 2), моделі (Task 4), `AlertService`, `Alert` (Task 5), `tests.tg` (Task 5).
- Produces:
  - `touch_user(session, *, telegram_user_id: int, username: str | None, first_name: str | None, now: datetime) -> User` — upsert, `last_activity_at = now`, `telegram_delivery_state = active`.
  - `build_dispatcher(*, settings: Settings, sessionmaker: async_sessionmaker[AsyncSession], alerts: AlertService, routers: Sequence[Router], clock: Callable[[], datetime] = utcnow) -> Dispatcher`.
  - У data хендлера доступні: `session: AsyncSession` (відкрита транзакція, commit після хендлера), `db_user: User` (лише для message / edited_message / callback_query), `settings: Settings`, `alerts: AlertService`, `clock: Callable[[], datetime]`.
  - `pokazun.bot.handlers.build_routers() -> list[Router]` — список production-роутерів (етап 5 його наповнює).

- [ ] **Step 1: Тест**

`tests/test_bot_middlewares.py`:

```python
from datetime import UTC, datetime

import pytest
from aiogram import Router
from aiogram.filters import Command
from aiogram.methods import SendMessage
from aiogram.types import Message
from sqlalchemy import func, select, update

from pokazun.alerts import AlertService
from pokazun.bot.factory import build_dispatcher
from pokazun.config import Settings
from pokazun.db.models import DeliveryState, ProcessedUpdate, User
from tests.tg import group_message_update, make_bot, message_update, my_chat_member_update, tg_user

NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


def settings(allowlist: str = "") -> Settings:
    return Settings(
        env="staging" if allowlist else "dev",
        bot_token="42:TEST",
        database_url="postgresql+asyncpg://unused",
        telegram_mode="polling",
        allowed_user_ids=allowlist,
    )


def probe_router(calls: list[str]) -> Router:
    router = Router()

    @router.message(Command("ping"))
    async def ping(message: Message, db_user: User) -> None:
        calls.append(f"ping:{db_user.telegram_user_id}")
        await message.answer("pong")

    @router.message(Command("boom"))
    async def boom(message: Message) -> None:
        calls.append("boom")
        raise RuntimeError("handler exploded")

    return router


@pytest.fixture
def env(sessionmaker):
    def _make(allowlist: str = ""):
        bot, session = make_bot()
        calls: list[str] = []
        alerts = AlertService(bot, -100999, "test")
        dp = build_dispatcher(
            settings=settings(allowlist),
            sessionmaker=sessionmaker,
            alerts=alerts,
            routers=[probe_router(calls)],
            clock=lambda: NOW,
        )
        return dp, bot, session, calls

    return _make


async def count(sessionmaker, model) -> int:
    async with sessionmaker() as s:
        return await s.scalar(select(func.count()).select_from(model))


async def test_user_upserted_on_message(env, sessionmaker):
    dp, bot, session, calls = env()
    await dp.feed_update(bot, message_update("/ping", user=tg_user(username="first")))
    await dp.feed_update(bot, message_update("/ping", user=tg_user(username="renamed")))
    assert calls == [f"ping:{tg_user().id}", f"ping:{tg_user().id}"]
    async with sessionmaker() as s:
        user = await s.scalar(select(User))
    assert user.username == "renamed"
    assert user.last_activity_at == NOW
    assert len(session.sent(SendMessage)) == 2


async def test_activity_unblocks_delivery(env, sessionmaker):
    dp, bot, _, _ = env()
    await dp.feed_update(bot, message_update("/ping"))
    async with sessionmaker() as s, s.begin():
        await s.execute(update(User).values(telegram_delivery_state=DeliveryState.BLOCKED))
    await dp.feed_update(bot, message_update("/ping"))
    async with sessionmaker() as s:
        user = await s.scalar(select(User))
    assert user.telegram_delivery_state is DeliveryState.ACTIVE


async def test_duplicate_update_processed_once(env, sessionmaker):
    dp, bot, _, calls = env()
    await dp.feed_update(bot, message_update("/ping", update_id=900))
    await dp.feed_update(bot, message_update("/ping", update_id=900))
    assert len(calls) == 1
    assert await count(sessionmaker, ProcessedUpdate) == 1


async def test_allowlist_blocks_strangers(env, sessionmaker):
    dp, bot, session, calls = env(allowlist="1,2")
    await dp.feed_update(bot, message_update("/ping", user=tg_user(user_id=3)))
    assert calls == []
    assert session.requests == []
    assert await count(sessionmaker, User) == 0


async def test_allowlist_admits_listed(env):
    dp, bot, _, calls = env(allowlist="3")
    await dp.feed_update(bot, message_update("/ping", user=tg_user(user_id=3)))
    assert calls == ["ping:3"]


async def test_group_chats_ignored(env, sessionmaker):
    dp, bot, _, calls = env()
    await dp.feed_update(bot, group_message_update("/ping"))
    assert calls == []
    assert await count(sessionmaker, User) == 0


async def test_my_chat_member_is_not_activity(env, sessionmaker):
    dp, bot, _, _ = env()
    await dp.feed_update(bot, message_update("/ping"))
    async with sessionmaker() as s, s.begin():
        await s.execute(update(User).values(telegram_delivery_state=DeliveryState.BLOCKED))
    await dp.feed_update(bot, my_chat_member_update("kicked"))
    async with sessionmaker() as s:
        user = await s.scalar(select(User))
    assert user.telegram_delivery_state is DeliveryState.BLOCKED


async def test_handler_error_rolls_back_and_alerts(env, sessionmaker):
    dp, bot, session, calls = env()
    await dp.feed_update(bot, message_update("/boom", update_id=950))
    assert calls == ["boom"]
    assert await count(sessionmaker, ProcessedUpdate) == 0
    assert await count(sessionmaker, User) == 0
    [alert] = session.sent(SendMessage)
    assert alert.chat_id == -100999
    assert "RuntimeError" in alert.text
    assert "950" in alert.text
```

- [ ] **Step 2: Запустити — має впасти**

Run: `uv run pytest tests/test_bot_middlewares.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pokazun.bot'`.

- [ ] **Step 3: Репозиторій користувачів**

`src/pokazun/users/repository.py`:

```python
from datetime import datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from pokazun.db.models import DeliveryState, User


async def touch_user(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    username: str | None,
    first_name: str | None,
    now: datetime,
) -> User:
    """Create or refresh the user on any user action; any action also restores Telegram delivery."""
    stmt = (
        insert(User)
        .values(
            telegram_user_id=telegram_user_id,
            username=username,
            first_name=first_name,
            last_activity_at=now,
            telegram_delivery_state=DeliveryState.ACTIVE,
        )
        .on_conflict_do_update(
            index_elements=[User.telegram_user_id],
            set_={
                "username": username,
                "first_name": first_name,
                "last_activity_at": now,
                "telegram_delivery_state": DeliveryState.ACTIVE.value,
                "updated_at": now,
            },
        )
        .returning(User)
    )
    result = await session.scalars(stmt, execution_options={"populate_existing": True})
    return result.one()
```

- [ ] **Step 4: Middleware**

`src/pokazun/bot/middlewares.py`:

```python
"""Update-level middlewares. Order (outermost first): LogContext → DbSession → Access → Idempotency → Activity."""

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

import structlog
from aiogram import BaseMiddleware
from aiogram.enums import ChatType
from aiogram.types import Chat, TelegramObject, Update, User as TgUser
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pokazun.db.models import ProcessedUpdate
from pokazun.log import get_logger
from pokazun.users.repository import touch_user

log = get_logger(__name__)

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class LogContextMiddleware(BaseMiddleware):
    async def __call__(self, handler: Handler, event: Update, data: dict[str, Any]) -> Any:
        with structlog.contextvars.bound_contextvars(update_id=event.update_id):
            return await handler(event, data)


class DbSessionMiddleware(BaseMiddleware):
    """One transaction per update: committed after the handler, rolled back if it raises."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def __call__(self, handler: Handler, event: Update, data: dict[str, Any]) -> Any:
        async with self._sessionmaker() as session, session.begin():
            data["session"] = session
            return await handler(event, data)


class AccessMiddleware(BaseMiddleware):
    """Private chats with real users only; on staging, only allowlisted Telegram user_ids."""

    def __init__(self, allowlist: frozenset[int]) -> None:
        self._allowlist = allowlist

    async def __call__(self, handler: Handler, event: Update, data: dict[str, Any]) -> Any:
        user: TgUser | None = data.get("event_from_user")
        chat: Chat | None = data.get("event_chat")
        if user is None or user.is_bot:
            return None
        if chat is not None and chat.type != ChatType.PRIVATE:
            return None
        if self._allowlist and user.id not in self._allowlist:
            log.info("user_not_in_allowlist", telegram_user_id=user.id)
            return None
        return await handler(event, data)


class IdempotencyMiddleware(BaseMiddleware):
    """Skips an update_id that was already committed. The marker shares the handler's transaction."""

    async def __call__(self, handler: Handler, event: Update, data: dict[str, Any]) -> Any:
        session: AsyncSession = data["session"]
        inserted = await session.scalar(
            insert(ProcessedUpdate)
            .values(update_id=event.update_id)
            .on_conflict_do_nothing()
            .returning(ProcessedUpdate.update_id)
        )
        if inserted is None:
            log.info("duplicate_update_skipped")
            return None
        return await handler(event, data)


class ActivityMiddleware(BaseMiddleware):
    """A message or a button press is user activity (90-day timer, delivery unblock). Service updates are not."""

    def __init__(self, clock: Callable[[], datetime]) -> None:
        self._clock = clock

    async def __call__(self, handler: Handler, event: Update, data: dict[str, Any]) -> Any:
        if event.message or event.edited_message or event.callback_query:
            tg_user: TgUser = data["event_from_user"]
            user = await touch_user(
                data["session"],
                telegram_user_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
                now=self._clock(),
            )
            data["db_user"] = user
            structlog.contextvars.bind_contextvars(user_id=user.id)
        return await handler(event, data)
```

- [ ] **Step 5: Фабрика диспетчера і реєстр роутерів**

`src/pokazun/bot/handlers/__init__.py`:

```python
from aiogram import Router


def build_routers() -> list[Router]:
    """Production routers in priority order. Stage 5 adds the search setup routers here."""
    return []
```

`src/pokazun/bot/factory.py`:

```python
from collections.abc import Callable, Sequence
from datetime import datetime

from aiogram import Dispatcher, Router
from aiogram.types import ErrorEvent
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pokazun.alerts import Alert, AlertService
from pokazun.bot.middlewares import (
    AccessMiddleware,
    ActivityMiddleware,
    DbSessionMiddleware,
    IdempotencyMiddleware,
    LogContextMiddleware,
)
from pokazun.clock import utcnow
from pokazun.config import Settings
from pokazun.log import get_logger

log = get_logger(__name__)


def build_dispatcher(
    *,
    settings: Settings,
    sessionmaker: async_sessionmaker[AsyncSession],
    alerts: AlertService,
    routers: Sequence[Router],
    clock: Callable[[], datetime] = utcnow,
) -> Dispatcher:
    dp = Dispatcher(settings=settings, alerts=alerts, clock=clock)
    dp.update.outer_middleware(LogContextMiddleware())
    dp.update.outer_middleware(DbSessionMiddleware(sessionmaker))
    dp.update.outer_middleware(AccessMiddleware(settings.allowlist))
    dp.update.outer_middleware(IdempotencyMiddleware())
    dp.update.outer_middleware(ActivityMiddleware(clock))
    dp.errors.register(_on_error)
    for router in routers:
        dp.include_router(router)
    return dp


async def _on_error(event: ErrorEvent, alerts: AlertService) -> bool:
    exc = event.exception
    job = "postgres" if isinstance(exc, DBAPIError) else "bot_handler"
    log.error("update_failed", exc_info=exc)
    await alerts.send(
        Alert(
            job=job,
            message=f"{type(exc).__name__}: {exc}",
            ids={"update_id": event.update.update_id},
            dedupe_key=f"{job}:{type(exc).__name__}",
        )
    )
    return True
```

- [ ] **Step 6: Запустити — має пройти**

Run: `uv run pytest tests/test_bot_middlewares.py -v`
Expected: 8 passed.

- [ ] **Step 7: Commit**

```bash
git add src/pokazun/users src/pokazun/bot tests/test_bot_middlewares.py
git commit -m "feat: dispatcher with db session, access, idempotency and activity middlewares"
```

---

### Task 7: Health, веб-застосунок, entrypoint бота, детектор restart loop

**Files:**
- Create: `src/pokazun/health.py`, `src/pokazun/web.py`, `src/pokazun/restarts.py`, `src/pokazun/app.py`
- Test: `tests/test_health_web.py`, `tests/test_restarts.py`

**Interfaces:**
- Consumes: `Settings`, `WEBHOOK_PATH` (Task 2), `configure_logging` (Task 3), `create_engine`, `create_sessionmaker` (Task 4), `AlertService`, `Alert` (Task 5), `build_dispatcher`, `build_routers` (Task 6).
- Produces:
  - `HealthProvider = Callable[[AsyncSession], Awaitable[dict[str, Any]]]`.
  - `HealthRegistry(sessionmaker, *, started_at: datetime, backup_marker_path: Path | None, clock=utcnow, db_timeout: float = 3.0)`; `.register(provider)`; `await .collect() -> tuple[bool, dict[str, Any]]`.
  - `read_backup_marker(path: Path) -> datetime | None`.
  - `build_web_app(*, health: HealthRegistry, bot: Bot | None = None, dispatcher: Dispatcher | None = None, webhook_secret: str | None = None, handle_in_background: bool = True) -> web.Application`. Маршрути: `GET /healthz`, `POST /tg/webhook`.
  - `record_start(path: Path, now: datetime, *, window: timedelta = timedelta(minutes=10)) -> int`; `await check_restart_loop(path, alerts, *, service: str, now: datetime, threshold: int = 3) -> None`.
  - `python -m pokazun.app` — процес bot.

- [ ] **Step 1: Тести**

`tests/test_health_web.py`:

```python
from datetime import UTC, datetime, timedelta

from aiogram.methods import SetWebhook
from aiohttp.test_utils import TestClient, TestServer
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from pokazun.alerts import AlertService
from pokazun.bot.factory import build_dispatcher
from pokazun.config import WEBHOOK_PATH, Settings
from pokazun.db.session import create_sessionmaker
from pokazun.health import HealthRegistry, read_backup_marker
from pokazun.web import build_web_app
from tests.tg import make_bot, message_update

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
SECRET = "s" * 32


def test_backup_marker(tmp_path):
    marker = tmp_path / "last_backup_at"
    assert read_backup_marker(marker) is None
    marker.write_text("2026-10-01T00:30:05Z\n")
    assert read_backup_marker(marker) == datetime(2026, 10, 1, 0, 30, 5, tzinfo=UTC)
    marker.write_text("garbage")
    assert read_backup_marker(marker) is None


async def test_healthz_ok_with_providers(sessionmaker, tmp_path):
    (tmp_path / "m").write_text("2026-10-01T00:30:00Z")
    health = HealthRegistry(
        sessionmaker,
        started_at=T0 - timedelta(seconds=90),
        backup_marker_path=tmp_path / "m",
        clock=lambda: T0,
    )

    async def provider(session):
        return {"eligible_object_count": 3}

    health.register(provider)
    async with TestClient(TestServer(build_web_app(health=health))) as client:
        resp = await client.get("/healthz")
        body = await resp.json()
    assert resp.status == 200
    assert body == {
        "db": "ok",
        "uptime_s": 90,
        "last_backup_at": "2026-10-01T00:30:00+00:00",
        "eligible_object_count": 3,
    }


async def test_healthz_db_down_returns_503(tmp_path):
    engine = create_async_engine(
        "postgresql+asyncpg://nobody:nothing@127.0.0.1:1/none", poolclass=NullPool
    )
    health = HealthRegistry(
        create_sessionmaker(engine), started_at=T0, backup_marker_path=None, db_timeout=2.0
    )
    async with TestClient(TestServer(build_web_app(health=health))) as client:
        resp = await client.get("/healthz")
        body = await resp.json()
    assert resp.status == 503
    assert body["db"] == "error"
    await engine.dispose()


async def test_webhook_rejects_wrong_secret_and_sets_webhook(sessionmaker):
    bot, session = make_bot()
    settings = Settings(
        env="dev",
        bot_token="42:TEST",
        database_url="postgresql+asyncpg://unused",
        public_base_url="https://bot.example",
        webhook_secret=SECRET,
    )
    dp = build_dispatcher(
        settings=settings,
        sessionmaker=sessionmaker,
        alerts=AlertService(None, None, "dev"),
        routers=[],
    )
    health = HealthRegistry(sessionmaker, started_at=T0, backup_marker_path=None)
    app = build_web_app(
        health=health, bot=bot, dispatcher=dp, webhook_secret=SECRET, handle_in_background=False
    )
    async with TestClient(TestServer(app)) as client:
        bad = await client.post(WEBHOOK_PATH, json={"update_id": 1})
        good = await client.post(
            WEBHOOK_PATH,
            json=message_update("/start").model_dump(mode="json", exclude_none=True),
            headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
        )
    assert bad.status == 401
    assert good.status == 200
    [hook] = session.sent(SetWebhook)
    assert hook.url == "https://bot.example" + WEBHOOK_PATH
    assert hook.secret_token == SECRET
```

`tests/test_restarts.py`:

```python
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
```

- [ ] **Step 2: Запустити — має впасти**

Run: `uv run pytest tests/test_health_web.py tests/test_restarts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pokazun.health'`.

- [ ] **Step 3: Реалізація `health.py`**

```python
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
```

- [ ] **Step 4: Реалізація `web.py`**

```python
from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from pokazun.config import WEBHOOK_PATH, Settings
from pokazun.health import HealthRegistry

HEALTH_KEY = web.AppKey("health", HealthRegistry)


async def _healthz(request: web.Request) -> web.Response:
    ok, data = await request.app[HEALTH_KEY].collect()
    return web.json_response(data, status=200 if ok else 503)


async def _set_webhook(bot: Bot, dispatcher: Dispatcher, settings: Settings) -> None:
    secret = settings.webhook_secret.get_secret_value() if settings.webhook_secret else None
    await bot.set_webhook(
        url=settings.webhook_url,
        secret_token=secret,
        allowed_updates=dispatcher.resolve_used_update_types(),
        drop_pending_updates=False,
    )


def build_web_app(
    *,
    health: HealthRegistry,
    bot: Bot | None = None,
    dispatcher: Dispatcher | None = None,
    webhook_secret: str | None = None,
    handle_in_background: bool = True,
) -> web.Application:
    app = web.Application()
    app[HEALTH_KEY] = health
    app.router.add_get("/healthz", _healthz)
    if bot is not None and dispatcher is not None:
        dispatcher.startup.register(_set_webhook)
        SimpleRequestHandler(
            dispatcher=dispatcher,
            bot=bot,
            secret_token=webhook_secret,
            handle_in_background=handle_in_background,
        ).register(app, path=WEBHOOK_PATH)
        setup_application(app, dispatcher, bot=bot)
    return app
```

`allowed_updates` з `resolve_used_update_types()` покриває лише ті типи апдейтів, для яких є хендлери. Етап 10 додає хендлер `my_chat_member`, тож цей тип підхопиться автоматично.

- [ ] **Step 5: Реалізація `restarts.py`**

```python
"""Detects crash/restart loops across process restarts via a small state file on a persistent volume."""

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
```

- [ ] **Step 6: Реалізація `app.py` (процес bot)**

```python
"""Bot process: Telegram webhook (or polling in dev) and /healthz."""

import asyncio

from aiogram import Bot
from aiohttp import web

from pokazun.alerts import AlertService
from pokazun.bot.factory import build_dispatcher
from pokazun.bot.handlers import build_routers
from pokazun.clock import utcnow
from pokazun.config import Settings
from pokazun.db.session import create_engine, create_sessionmaker
from pokazun.health import HealthRegistry
from pokazun.log import configure_logging, get_logger
from pokazun.restarts import check_restart_loop
from pokazun.web import build_web_app

log = get_logger(__name__)


async def create_app(settings: Settings) -> web.Application:
    engine = create_engine(settings.database_url.get_secret_value())
    sessionmaker = create_sessionmaker(engine)
    bot = Bot(settings.bot_token.get_secret_value())
    alerts = AlertService(bot, settings.alert_chat_id, settings.env)
    await check_restart_loop(
        settings.state_dir / "bot-starts.json", alerts, service="bot", now=utcnow()
    )
    dp = build_dispatcher(
        settings=settings, sessionmaker=sessionmaker, alerts=alerts, routers=build_routers()
    )
    health = HealthRegistry(
        sessionmaker, started_at=utcnow(), backup_marker_path=settings.backup_marker_path
    )
    app = build_web_app(
        health=health,
        bot=bot,
        dispatcher=dp,
        webhook_secret=settings.webhook_secret.get_secret_value() if settings.webhook_secret else None,
    )

    async def _dispose(_: web.Application) -> None:
        await engine.dispose()

    app.on_cleanup.append(_dispose)
    return app


async def run_polling(settings: Settings) -> None:
    """Local development only (config forbids polling in prod)."""
    engine = create_engine(settings.database_url.get_secret_value())
    bot = Bot(settings.bot_token.get_secret_value())
    alerts = AlertService(bot, settings.alert_chat_id, settings.env)
    dp = build_dispatcher(
        settings=settings,
        sessionmaker=create_sessionmaker(engine),
        alerts=alerts,
        routers=build_routers(),
    )
    await bot.delete_webhook(drop_pending_updates=False)
    try:
        await dp.start_polling(bot)
    finally:
        await engine.dispose()


def main() -> None:
    settings = Settings()
    configure_logging(level=settings.log_level, log_dir=settings.log_dir, service="bot")
    log.info("starting", env=settings.env, mode=settings.telegram_mode)
    if settings.telegram_mode == "polling":
        asyncio.run(run_polling(settings))
    else:
        web.run_app(
            create_app(settings),
            host=settings.web_host,
            port=settings.web_port,
            access_log=None,
            print=None,
        )


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Запустити — має пройти**

Run: `uv run pytest tests/test_health_web.py tests/test_restarts.py -v`
Expected: 7 passed.

- [ ] **Step 8: Commit**

```bash
git add src/pokazun/health.py src/pokazun/web.py src/pokazun/restarts.py src/pokazun/app.py tests/test_health_web.py tests/test_restarts.py
git commit -m "feat: web app with healthz and telegram webhook, restart loop detection"
```

---

### Task 8: Воркер: планувальник і службові задачі

**Files:**
- Create: `src/pokazun/worker/__init__.py` (порожній), `src/pokazun/worker/scheduler.py`, `src/pokazun/worker/jobs.py`, `src/pokazun/worker/main.py`
- Test: `tests/test_scheduler.py`, `tests/test_worker_jobs.py`

**Interfaces:**
- Consumes: `AlertService`, `Alert`, `read_backup_marker`, `ProcessedUpdate`, `Settings`, `check_restart_loop`.
- Produces:
  - `Job(name: str, interval: timedelta, func: Callable[[], Awaitable[None]], run_on_start: bool = True, alert_on_failure: bool = True)`.
  - `Scheduler(alerts: AlertService)`; `.add(job)`; `await .run_once(job) -> bool`; `await .run(stop: asyncio.Event) -> None`.
  - `await cleanup_processed_updates(sessionmaker, *, now: datetime, keep: timedelta = timedelta(days=7)) -> int`.
  - `await check_backup_freshness(marker_path: Path, alerts: AlertService, *, now: datetime, max_age: timedelta = timedelta(hours=26)) -> None`.
  - `PublicHealthCheck(url: str, alerts: AlertService, *, threshold: int = 3, timeout: float = 10.0)`; `await .run() -> None`.
  - `build_jobs(settings, sessionmaker, alerts, *, clock=utcnow) -> list[Job]` — етап 4 додає сюди sync.
  - `python -m pokazun.worker.main` — процес worker.

- [ ] **Step 1: Тести**

`tests/test_scheduler.py`:

```python
import asyncio
from datetime import timedelta

from aiogram.methods import SendMessage

from pokazun.alerts import AlertService
from pokazun.worker.scheduler import Job, Scheduler
from tests.tg import make_bot


async def test_failure_alerts_and_loop_continues():
    bot, session = make_bot()
    scheduler = Scheduler(AlertService(bot, -1, "prod"))
    runs = 0
    stop = asyncio.Event()

    async def flaky() -> None:
        nonlocal runs
        runs += 1
        if runs >= 3:
            stop.set()
        raise ValueError("nope")

    scheduler.add(Job("flaky", timedelta(milliseconds=5), flaky))
    await asyncio.wait_for(scheduler.run(stop), timeout=2)
    assert runs == 3
    [alert] = session.sent(SendMessage)  # debounced: one alert per error kind
    assert "flaky" in alert.text and "ValueError" in alert.text


async def test_alert_on_failure_disabled():
    bot, session = make_bot()
    scheduler = Scheduler(AlertService(bot, -1, "prod"))

    async def fails() -> None:
        raise ValueError("handled by the job itself")

    ok = await scheduler.run_once(Job("sync", timedelta(minutes=5), fails, alert_on_failure=False))
    assert ok is False
    assert session.requests == []


async def test_run_on_start_false_waits_first_interval():
    scheduler = Scheduler(AlertService(None, None, "dev"))
    calls = 0
    stop = asyncio.Event()

    async def job() -> None:
        nonlocal calls
        calls += 1

    scheduler.add(Job("late", timedelta(seconds=10), job, run_on_start=False))
    task = asyncio.create_task(scheduler.run(stop))
    await asyncio.sleep(0.05)
    stop.set()
    await asyncio.wait_for(task, timeout=1)
    assert calls == 0
```

`tests/test_worker_jobs.py`:

```python
from datetime import UTC, datetime, timedelta

from aiogram.methods import SendMessage
from aiohttp import web
from aiohttp.test_utils import TestServer
from sqlalchemy import insert, select

from pokazun.alerts import AlertService
from pokazun.config import Settings
from pokazun.db.models import ProcessedUpdate
from pokazun.worker.jobs import (
    PublicHealthCheck,
    build_jobs,
    check_backup_freshness,
    cleanup_processed_updates,
)
from tests.tg import make_bot

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


async def test_cleanup_processed_updates(sessionmaker):
    async with sessionmaker() as s, s.begin():
        await s.execute(
            insert(ProcessedUpdate),
            [
                {"update_id": 1, "processed_at": T0 - timedelta(days=8)},
                {"update_id": 2, "processed_at": T0 - timedelta(days=1)},
            ],
        )
    assert await cleanup_processed_updates(sessionmaker, now=T0) == 1
    async with sessionmaker() as s:
        assert (await s.scalars(select(ProcessedUpdate.update_id))).all() == [2]


async def test_backup_missing_or_stale_alerts(tmp_path):
    bot, session = make_bot()
    alerts = AlertService(bot, -1, "prod", clock=lambda: T0, debounce=timedelta(0))
    marker = tmp_path / "last_backup_at"
    await check_backup_freshness(marker, alerts, now=T0)
    marker.write_text((T0 - timedelta(hours=27)).isoformat())
    await check_backup_freshness(marker, alerts, now=T0)
    marker.write_text((T0 - timedelta(hours=2)).isoformat())
    await check_backup_freshness(marker, alerts, now=T0)
    assert len(session.sent(SendMessage)) == 2


async def test_public_health_alerts_after_threshold_and_resets():
    status = {"code": 500}

    async def healthz(_: web.Request) -> web.Response:
        return web.json_response({}, status=status["code"])

    app = web.Application()
    app.router.add_get("/healthz", healthz)
    bot, session = make_bot()
    alerts = AlertService(bot, -1, "prod", debounce=timedelta(0))
    async with TestServer(app) as server:
        check = PublicHealthCheck(str(server.make_url("/healthz")), alerts, threshold=3)
        await check.run()
        await check.run()
        assert session.sent(SendMessage) == []
        await check.run()
        assert len(session.sent(SendMessage)) == 1
        status["code"] = 200
        await check.run()
        status["code"] = 500
        await check.run()
        assert len(session.sent(SendMessage)) == 1


def _settings(**kw) -> Settings:
    base = {
        "bot_token": "42:TEST",
        "database_url": "postgresql+asyncpg://unused",
        "public_base_url": "https://bot.example",
        "webhook_secret": "s" * 32,
    }
    return Settings(**{**base, **kw})


def test_build_jobs_prod(sessionmaker):
    jobs = build_jobs(_settings(env="prod", alert_chat_id=-1), sessionmaker, AlertService(None, None, "prod"))
    assert {j.name for j in jobs} == {"cleanup_processed_updates", "backup_freshness", "public_health"}


def test_build_jobs_dev_polling(sessionmaker):
    jobs = build_jobs(
        _settings(env="dev", telegram_mode="polling"), sessionmaker, AlertService(None, None, "dev")
    )
    assert {j.name for j in jobs} == {"cleanup_processed_updates"}
```

- [ ] **Step 2: Запустити — має впасти**

Run: `uv run pytest tests/test_scheduler.py tests/test_worker_jobs.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pokazun.worker'`.

- [ ] **Step 3: Реалізація `worker/scheduler.py`**

```python
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
```

- [ ] **Step 4: Реалізація `worker/jobs.py`**

```python
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
                message=f"no successful backup within {max_age}; last: {last.isoformat() if last else 'never'}",
                dedupe_key="backup_stale",
            )
        )


class PublicHealthCheck:
    """Probes the public HTTPS /healthz through the proxy; alerts after N consecutive failures."""

    def __init__(self, url: str, alerts: AlertService, *, threshold: int = 3, timeout: float = 10.0) -> None:
        self._url = url
        self._alerts = alerts
        self._threshold = threshold
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._failures = 0

    async def run(self) -> None:
        error: str | None = None
        try:
            async with aiohttp.ClientSession(timeout=self._timeout) as http, http.get(self._url) as resp:
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
```

- [ ] **Step 5: Реалізація `worker/main.py`**

```python
"""Worker process: background jobs (catalog sync from stage 4, notification queue from stage 10)."""

import asyncio
import signal

from aiogram import Bot

from pokazun.alerts import AlertService
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
    scheduler = Scheduler(alerts)
    for job in build_jobs(settings, sessionmaker, alerts):
        scheduler.add(job)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    log.info("worker_started", env=settings.env)
    try:
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
```

- [ ] **Step 6: Запустити — має пройти**

Run: `uv run pytest tests/test_scheduler.py tests/test_worker_jobs.py -v`
Expected: 8 passed.

- [ ] **Step 7: Commit**

```bash
git add src/pokazun/worker tests/test_scheduler.py tests/test_worker_jobs.py
git commit -m "feat: worker scheduler with cleanup, backup freshness and public health jobs"
```

---

### Task 9: Контейнери, проксі, backup, деплой, runbook

**Files:**
- Create: `Dockerfile`, `.dockerignore`
- Create: `deploy/compose.yml`, `deploy/proxy/compose.yml`, `deploy/proxy/Caddyfile`
- Create: `deploy/backup/Dockerfile`, `deploy/backup/backup.sh`, `deploy/backup/backup-loop.sh`
- Create: `deploy/deploy.sh`, `deploy/restore-test.sh`
- Create: `docs/ops/runbook.md`

**Interfaces:**
- Consumes: entrypoints `python -m pokazun.app`, `python -m pokazun.worker.main`, `alembic upgrade head`; `/healthz`.
- Produces: образ `pokazun:<git-sha>` + тег `pokazun:<env>`; Compose-проєкти `pokazun-prod`, `pokazun-staging`, `pokazun-proxy`; зовнішня мережа `pokazun-edge`; backup-маркер `/backups/last_backup_at`.

Тут немає юніт-тестів; перевірка — локальний прогін контейнерів (Step 8) і чек-лист на VPS (Step 9).

- [ ] **Step 1: Образ застосунку**

`Dockerfile`:

```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY alembic.ini ./
COPY migrations ./migrations
RUN uv sync --frozen --no-dev

RUN useradd --system --uid 10001 pokazun \
    && mkdir -p /var/log/pokazun /var/lib/pokazun \
    && chown pokazun /var/log/pokazun /var/lib/pokazun
USER pokazun

CMD ["python", "-m", "pokazun.app"]
```

`.dockerignore`:

```
.git
.venv
.env
.env.*
**/__pycache__
.pytest_cache
.ruff_cache
docs
tests
```

- [ ] **Step 2: Compose одного середовища**

`deploy/compose.yml`:

```yaml
name: pokazun-${POKAZUN_ENV:?set POKAZUN_ENV}

x-app: &app
  image: pokazun:${POKAZUN_ENV}
  env_file: ${POKAZUN_ENV_FILE:?set POKAZUN_ENV_FILE}
  restart: unless-stopped
  depends_on:
    db:
      condition: service_healthy
  logging:
    driver: local
    options:
      max-size: 20m
      max-file: "5"

services:
  db:
    image: postgres:16
    restart: unless-stopped
    environment:
      POSTGRES_DB: pokazun
      POSTGRES_USER: pokazun
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
    networks: [internal]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U pokazun -d pokazun"]
      interval: 5s
      timeout: 5s
      retries: 20

  migrate:
    <<: *app
    restart: "no"
    command: ["alembic", "upgrade", "head"]
    networks: [internal]
    profiles: ["migrate"]

  bot:
    <<: *app
    command: ["python", "-m", "pokazun.app"]
    volumes:
      - logs:/var/log/pokazun
      - state:/var/lib/pokazun
      - backups:/backups:ro
    networks:
      internal: {}
      edge:
        aliases: ["pokazun-${POKAZUN_ENV}-bot"]
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=5)"]
      interval: 30s
      timeout: 10s
      retries: 3

  worker:
    <<: *app
    command: ["python", "-m", "pokazun.worker.main"]
    volumes:
      - logs:/var/log/pokazun
      - state:/var/lib/pokazun
      - backups:/backups:ro
    networks: [internal, edge]

  backup:
    build: ./backup
    image: pokazun-backup:16
    restart: unless-stopped
    env_file: ${POKAZUN_ENV_FILE}
    volumes:
      - backups:/backups
    networks: [internal, edge]
    depends_on:
      db:
        condition: service_healthy
    profiles: ["backup"]

networks:
  internal: {}
  edge:
    external: true
    name: pokazun-edge

volumes:
  pgdata: {}
  logs: {}
  state: {}
  backups: {}
```

`db` підключений лише до `internal` і не має `ports:` — назовні PostgreSQL недоступний. `worker` у мережі `edge`, бо ходить в інтернет (Airtable, Telegram, перевірка HTTPS).

- [ ] **Step 3: HTTPS-проксі (спільний для середовищ)**

`deploy/proxy/compose.yml`:

```yaml
name: pokazun-proxy

services:
  caddy:
    image: caddy:2
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    networks: [edge]

networks:
  edge:
    external: true
    name: pokazun-edge

volumes:
  caddy_data: {}
  caddy_config: {}
```

`deploy/proxy/Caddyfile`:

```caddyfile
bot.praktik.cn.ua {
	encode gzip
	reverse_proxy pokazun-prod-bot:8080
}

staging-bot.praktik.cn.ua {
	encode gzip
	reverse_proxy pokazun-staging-bot:8080
}
```

Caddy сам отримує й оновлює сертифікати Let’s Encrypt. Потрібні DNS A-записи `bot.praktik.cn.ua` і `staging-bot.praktik.cn.ua` на IP VPS — додати в список «Що ще отримати».

- [ ] **Step 4: Backup-контейнер**

`deploy/backup/Dockerfile`:

```dockerfile
FROM postgres:16-alpine
RUN apk add --no-cache rclone curl
COPY backup.sh backup-loop.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/backup.sh /usr/local/bin/backup-loop.sh
CMD ["/usr/local/bin/backup-loop.sh"]
```

`deploy/backup/backup.sh`:

```sh
#!/bin/sh
# One backup run: dump → local retention → off-VPS copy → marker. Any failure exits non-zero.
set -eu

TS=$(date -u +%Y%m%dT%H%M%SZ)
FILE="/backups/pokazun-${TS}.dump"

PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -h db -U pokazun -d pokazun -Fc -f "${FILE}.partial"
mv "${FILE}.partial" "$FILE"
find /backups -name 'pokazun-*.dump' -mtime +13 -delete

if [ -z "${BACKUP_REMOTE:-}" ]; then
  echo "BACKUP_REMOTE is not set: off-VPS copy is required" >&2
  exit 1
fi
rclone copy "$FILE" "$BACKUP_REMOTE"
rclone delete --min-age 14d "$BACKUP_REMOTE"

date -u +%Y-%m-%dT%H:%M:%SZ > /backups/last_backup_at
echo "backup ok: $FILE"
```

`deploy/backup/backup-loop.sh`:

```sh
#!/bin/sh
# Daily at 00:30 UTC (02:30/03:30 Kyiv). On failure posts to the ops group immediately;
# the worker's backup_freshness job alerts again if no success within 26 hours.
set -u

alert() {
  [ -n "${POKAZUN_ALERT_CHAT_ID:-}" ] || return 0
  curl -fsS -m 20 "https://api.telegram.org/bot${POKAZUN_BOT_TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${POKAZUN_ALERT_CHAT_ID}" \
    --data-urlencode "text=🔴 [${POKAZUN_ENV}] backup
$(date -u '+%Y-%m-%d %H:%M:%S') UTC
$1" > /dev/null || true
}

while true; do
  now=$(date -u +%s)
  target=$(date -u -d "$(date -u +%Y-%m-%d) 00:30:00" +%s)
  [ "$target" -gt "$now" ] || target=$((target + 86400))
  sleep $((target - now))
  if ! /usr/local/bin/backup.sh; then
    alert "backup.sh failed, see: docker compose logs backup"
  fi
done
```

- [ ] **Step 5: Скрипт деплою**

`deploy/deploy.sh`:

```bash
#!/usr/bin/env bash
# Usage: deploy/deploy.sh <staging|prod> [git-ref]
# Order: build → (prod: manual backup) → migrations → restart → smoke check.
set -euo pipefail

ENV_NAME="${1:?usage: deploy.sh <staging|prod> [git-ref]}"
REF="${2:-origin/main}"
case "$ENV_NAME" in staging|prod) ;; *) echo "unknown env: $ENV_NAME" >&2; exit 2 ;; esac

ROOT=/opt/pokazun
SRC="$ROOT/src"
ENV_FILE="$ROOT/$ENV_NAME/.env"
[ -f "$ENV_FILE" ] || { echo "missing $ENV_FILE" >&2; exit 2; }

cd "$SRC"
git fetch --tags origin
git checkout --detach "$REF"
SHA=$(git rev-parse --short HEAD)

docker build -t "pokazun:$SHA" .
docker tag "pokazun:$SHA" "pokazun:$ENV_NAME"

set -a; . "$ENV_FILE"; set +a
export POKAZUN_ENV="$ENV_NAME" POKAZUN_ENV_FILE="$ENV_FILE"
DC=(docker compose -f "$SRC/deploy/compose.yml" --env-file "$ENV_FILE")

"${DC[@]}" up -d db
if [ "$ENV_NAME" = prod ]; then
  "${DC[@]}" --profile backup build backup
  "${DC[@]}" --profile backup run --rm backup /usr/local/bin/backup.sh
fi
"${DC[@]}" --profile migrate run --rm migrate
"${DC[@]}" up -d --remove-orphans

for _ in $(seq 1 30); do
  if curl -fsS -m 5 "${POKAZUN_PUBLIC_BASE_URL%/}/healthz"; then
    echo; echo "deployed $ENV_NAME @ $SHA"
    exit 0
  fi
  sleep 2
done
echo "smoke check failed for $ENV_NAME @ $SHA" >&2
exit 1
```

Для prod у `.env` стоїть `COMPOSE_PROFILES=backup`, тож `up -d` піднімає й backup-сервіс. Відкат: `deploy/deploy.sh prod <попередній-sha>` (міграції пишемо так, щоб попередня версія коду працювала з новою схемою; інакше — `alembic downgrade` за runbook).

- [ ] **Step 6: Тест відновлення з backup**

`deploy/restore-test.sh`:

```bash
#!/usr/bin/env bash
# Restores the latest dump into a scratch database and checks it. Usage: deploy/restore-test.sh prod
set -euo pipefail

ENV_NAME="${1:-prod}"
ENV_FILE="/opt/pokazun/$ENV_NAME/.env"
set -a; . "$ENV_FILE"; set +a
export POKAZUN_ENV="$ENV_NAME" POKAZUN_ENV_FILE="$ENV_FILE"
DC=(docker compose -f /opt/pokazun/src/deploy/compose.yml --env-file "$ENV_FILE")

"${DC[@]}" exec -T db dropdb -U pokazun --if-exists restore_test
"${DC[@]}" exec -T db createdb -U pokazun restore_test
"${DC[@]}" --profile backup run --rm backup sh -c \
  'LATEST=$(ls -1t /backups/pokazun-*.dump | head -1) && echo "restoring $LATEST" &&
   PGPASSWORD="$POSTGRES_PASSWORD" pg_restore -h db -U pokazun -d restore_test --no-owner "$LATEST"'
"${DC[@]}" exec -T db psql -U pokazun -d restore_test -v ON_ERROR_STOP=1 \
  -c "SELECT version_num FROM alembic_version" \
  -c "SELECT count(*) AS users FROM users"
"${DC[@]}" exec -T db dropdb -U pokazun restore_test
echo "restore test OK"
```

- [ ] **Step 7: Runbook**

`docs/ops/runbook.md`:

````markdown
# Показун — runbook

## Первинне налаштування VPS

1. Docker Engine + Compose plugin; `systemctl enable --now docker` (автостарт після перезавантаження).
2. SSH лише за ключами; `PasswordAuthentication no`.
3. `docker network create pokazun-edge`
4. `git clone https://github.com/Vnedrenec/pokazun.git /opt/pokazun/src`
5. `/opt/pokazun/prod/.env` і `/opt/pokazun/staging/.env` за шаблоном `.env.example`; `chmod 600`.
   - prod: `POKAZUN_ENV=prod`, `COMPOSE_PROFILES=backup`, `BACKUP_REMOTE` + `RCLONE_CONFIG_*`, `POKAZUN_ALERT_CHAT_ID`.
   - staging: власний bot token, власний `POSTGRES_PASSWORD`, `POKAZUN_ALLOWED_USER_IDS`.
   - `POKAZUN_WEBHOOK_SECRET`: `openssl rand -hex 32`.
6. `docker compose -f /opt/pokazun/src/deploy/proxy/compose.yml up -d`

## Деплой

```bash
/opt/pokazun/src/deploy/deploy.sh staging origin/main   # 1. staging
# 2. smoke test у staging-боті вручну (сценарії поточного етапу)
/opt/pokazun/src/deploy/deploy.sh prod <той-самий-sha>  # 3. prod
```

## Перевірки після першого розгортання

- [ ] `curl https://bot.praktik.cn.ua/healthz` → 200, `"db": "ok"`.
- [ ] `docker compose ... ps`: db, bot, worker, backup — `running`/`healthy`.
- [ ] Порт 5432 закритий ззовні: `nc -zv <vps-ip> 5432` з іншої машини → відмова.
- [ ] Тестовий алерт доходить у «Парсер + Показун» (зупинити `bot` 3 рази поспіль за 10 хв або дочекатися `backup_freshness`).
- [ ] Ручний запуск backup: `docker compose ... --profile backup run --rm backup /usr/local/bin/backup.sh`; файл є локально і в `BACKUP_REMOTE`.
- [ ] `deploy/restore-test.sh prod` → `restore test OK`. Повторювати щомісяця.
- [ ] `sudo reboot` → через 2 хв усі сервіси знову `running`, `/healthz` 200.
- [ ] staging-бот не відповідає користувачу поза allowlist.

## Логи

- Файли: volume `logs` → `/var/log/pokazun/{bot,worker}.log`, ротація щодоби, 45 днів.
- `docker compose ... logs -f bot` — поточний stdout.

## Відкат

`deploy/deploy.sh prod <попередній-sha>`. Якщо нова міграція несумісна зі старим кодом — перед відкатом `docker compose ... --profile migrate run --rm migrate alembic downgrade <revision>` (лише після ручного backup).
````

- [ ] **Step 8: Локальна перевірка контейнерів**

Створити тимчасовий `/tmp/pokazun-local.env` (не в репозиторій):

```dotenv
POKAZUN_ENV=staging
POKAZUN_ENV_FILE=/tmp/pokazun-local.env
POSTGRES_PASSWORD=localpass
POKAZUN_BOT_TOKEN=42:TEST
POKAZUN_DATABASE_URL=postgresql+asyncpg://pokazun:localpass@db:5432/pokazun
POKAZUN_TELEGRAM_MODE=polling
POKAZUN_ALLOWED_USER_IDS=1
BACKUP_REMOTE=/backups/offsite
```

Run:

```bash
docker network create pokazun-edge || true
docker build -t pokazun:staging .
export POKAZUN_ENV=staging POKAZUN_ENV_FILE=/tmp/pokazun-local.env
DC="docker compose -f deploy/compose.yml --env-file /tmp/pokazun-local.env"
$DC config --quiet
$DC up -d db
$DC --profile migrate run --rm migrate
$DC --profile backup build backup
$DC --profile backup run --rm backup /usr/local/bin/backup.sh
$DC --profile backup run --rm backup sh -c 'ls -l /backups /backups/offsite && cat /backups/last_backup_at'
$DC down -v
```

Expected: `config` без помилок; міграція `Running upgrade  -> 0001`; `backup ok: /backups/pokazun-…dump`; у `/backups/offsite` є копія; маркер містить поточний UTC-час. (`BACKUP_REMOTE` як локальний шлях працює, бо rclone приймає локальні шляхи.)

- [ ] **Step 9: Розгортання на VPS (коли є доступи з етапу 0)**

Пройти runbook «Первинне налаштування VPS», `deploy.sh staging`, потім чек-лист «Перевірки після першого розгортання». Для prod — після того ж на staging.

- [ ] **Step 10: Commit**

```bash
git add Dockerfile .dockerignore deploy docs/ops
git commit -m "feat: docker compose deployment, https proxy, daily off-site backup and runbook"
```

---

## Готово, коли

- `uv run pytest` зелений, `ruff check` і `ruff format --check` чисті, CI зелений.
- Staging на VPS: `https://staging-bot.praktik.cn.ua/healthz` → 200; бот ігнорує користувачів поза allowlist.
- Prod на VPS: `https://bot.praktik.cn.ua/healthz` → 200; backup щодня + копія поза VPS; restore-тест пройдено; перезавантаження VPS перевірене; тестовий алерт дійшов у групу.
- Секретів немає в git (`git grep -nE "pat[A-Za-z0-9]{10,}\.|[0-9]{8,10}:[A-Za-z0-9_-]{35}"` порожній).
