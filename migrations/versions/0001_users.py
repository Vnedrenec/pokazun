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
        sa.Column(
            "telegram_delivery_state", sa.String(32), server_default="active", nullable=False
        ),
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
    op.create_index("ix_processed_updates_processed_at", "processed_updates", ["processed_at"])


def downgrade() -> None:
    op.drop_index("ix_processed_updates_processed_at", table_name="processed_updates")
    op.drop_table("processed_updates")
    op.drop_table("users")
