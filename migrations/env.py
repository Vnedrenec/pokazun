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
