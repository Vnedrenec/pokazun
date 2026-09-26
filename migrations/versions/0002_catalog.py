"""object_state and sync_state

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "object_state",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("airtable_record_id", sa.String(32), nullable=False),
        sa.Column("object_code", sa.Integer(), nullable=False),
        sa.Column("eligible", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("rooms", sa.SmallInteger(), nullable=True),
        sa.Column("condition", sa.String(64), nullable=True),
        sa.Column("price_segment", sa.SmallInteger(), nullable=True),
        sa.Column("price_usd", sa.Numeric(12, 2), nullable=True),
        sa.Column("registered_at", TS, nullable=True),
        sa.Column("airtable_modified_at", TS, nullable=True),
        sa.Column(
            "public",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("catalog_entered_at", TS, nullable=True),
        sa.Column("eligible_since", TS, nullable=True),
        sa.Column("inactive_since", TS, nullable=True),
        sa.Column("synced_at", TS, nullable=False),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_object_state"),
        sa.UniqueConstraint("airtable_record_id", name="uq_object_state_airtable_record_id"),
    )
    op.create_index("ix_object_state_object_code", "object_state", ["object_code"])
    op.create_index(
        "ix_object_state_catalog_order",
        "object_state",
        ["registered_at", "object_code"],
        postgresql_where=sa.text("eligible"),
    )
    op.create_table(
        "sync_state",
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("watermark", TS, nullable=True),
        sa.Column("last_successful_sync_at", TS, nullable=True),
        sa.Column("last_full_sync_at", TS, nullable=True),
        sa.Column("bootstrapped_at", TS, nullable=True),
        sa.Column(
            "consecutive_failures", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("source", name="pk_sync_state"),
    )


def downgrade() -> None:
    op.drop_table("sync_state")
    op.drop_index("ix_object_state_catalog_order", table_name="object_state")
    op.drop_index("ix_object_state_object_code", table_name="object_state")
    op.drop_table("object_state")
