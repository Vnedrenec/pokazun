import os
import re
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

import pokazun.db.models  # noqa: F401
from pokazun.db.base import Base
from pokazun.db.session import create_sessionmaker

ROOT = Path(__file__).resolve().parents[1]

_TEST_DB_RE = re.compile(r"^pokazun_test_[a-z0-9_]+_[a-z0-9_]+$")

# Snapshot of the operator's database URL taken before any test mutates the env.
# alembic_config() overwrites POKAZUN_DATABASE_URL with the test URL, so later
# comparisons must use this snapshot, not the live variable.
_ORIGINAL_DATABASE_URL = os.environ.get("POKAZUN_DATABASE_URL")


def _guard_database_url(url: str) -> str:
    """Refuse destructive DB work on a missing, shared, or production database URL."""
    try:
        parsed = make_url(url)
    except Exception as exc:
        pytest.fail(f"TEST_DATABASE_URL is not a valid database URL: {exc}", pytrace=False)
    if not _TEST_DB_RE.match(parsed.database or ""):
        pytest.fail(
            "Refusing destructive DB tests: database name must be "
            "pokazun_test_<agent>_<workspace> with non-empty ASCII [a-z0-9_]+ parts, "
            f"got {parsed.database!r}. Create your own database and export "
            "TEST_DATABASE_URL=postgresql+asyncpg://pokazun:pokazun@localhost:5432/"
            "pokazun_test_<agent>_<workspace>",
            pytrace=False,
        )
    if _ORIGINAL_DATABASE_URL:
        try:
            ref = make_url(_ORIGINAL_DATABASE_URL)
        except Exception:
            ref = None
        if ref is not None and (ref.host, ref.port or 5432, ref.database) == (
            parsed.host,
            parsed.port or 5432,
            parsed.database,
        ):
            pytest.fail(
                "Refusing destructive DB tests: TEST_DATABASE_URL points at the same "
                "host/port/database as the original POKAZUN_DATABASE_URL. "
                "Unset POKAZUN_DATABASE_URL (or point it elsewhere) and use your own "
                "pokazun_test_<agent>_<workspace> database for tests.",
                pytrace=False,
            )
    return url


def _test_database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.fail(
            "TEST_DATABASE_URL is not set. Start Postgres with "
            "`docker compose -f compose.dev.yml up -d`, create your own database, and export "
            "TEST_DATABASE_URL=postgresql+asyncpg://pokazun:pokazun@localhost:5432/"
            "pokazun_test_<agent>_<workspace>",
            pytrace=False,
        )
    return _guard_database_url(url)


def alembic_config(url: str) -> Config:
    _guard_database_url(url)
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
