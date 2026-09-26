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
