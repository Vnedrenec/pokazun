"""searches and search_drafts

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "searches",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("rooms", postgresql.ARRAY(sa.SmallInteger()), nullable=False),
        sa.Column("conditions", postgresql.ARRAY(sa.String(32)), nullable=False),
        sa.Column("price_low", sa.SmallInteger(), nullable=False),
        sa.Column("price_high", sa.SmallInteger(), nullable=False),
        sa.Column("baseline_at", TS, nullable=False),
        sa.Column("confirmed_at", TS, nullable=False),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_searches"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_searches_user_id_users", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("user_id", name="uq_searches_user_id"),
        sa.CheckConstraint("price_low <= price_high", name="ck_searches_price_range"),
        sa.CheckConstraint("cardinality(rooms) > 0", name="ck_searches_rooms_not_empty"),
        sa.CheckConstraint("cardinality(conditions) > 0", name="ck_searches_conditions_not_empty"),
    )
    op.create_table(
        "search_drafts",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("step", sa.String(32), nullable=False),
        sa.Column(
            "rooms",
            postgresql.ARRAY(sa.SmallInteger()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "conditions",
            postgresql.ARRAY(sa.String(32)),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("price_low", sa.SmallInteger(), nullable=True),
        sa.Column("price_high", sa.SmallInteger(), nullable=True),
        sa.Column("reached_summary", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", name="pk_search_drafts"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_search_drafts_user_id_users", ondelete="CASCADE"
        ),
        sa.CheckConstraint("mode IN ('create', 'edit')", name="ck_search_drafts_mode"),
        sa.CheckConstraint(
            "step IN ('rooms', 'condition', 'price', 'summary', 'edit_menu')",
            name="ck_search_drafts_step",
        ),
    )


def downgrade() -> None:
    op.drop_table("search_drafts")
    op.drop_table("searches")
