from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Identity,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pokazun.db.base import Base


class ObjectState(Base):
    """Technical snapshot of an Airtable object for search and events."""

    __tablename__ = "object_state"
    __table_args__ = (
        Index(
            "ix_object_state_catalog_order",
            "registered_at",
            "object_code",
            postgresql_where=text("eligible"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    airtable_record_id: Mapped[str] = mapped_column(String(32), unique=True)
    object_code: Mapped[int] = mapped_column(Integer, index=True)
    eligible: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    rooms: Mapped[int | None] = mapped_column(SmallInteger)
    condition: Mapped[str | None] = mapped_column(String(64))
    price_segment: Mapped[int | None] = mapped_column(SmallInteger)
    price_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    registered_at: Mapped[datetime | None]
    airtable_modified_at: Mapped[datetime | None]
    public: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    catalog_entered_at: Mapped[datetime | None]
    eligible_since: Mapped[datetime | None]
    inactive_since: Mapped[datetime | None]
    synced_at: Mapped[datetime]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class SyncState(Base):
    __tablename__ = "sync_state"

    source: Mapped[str] = mapped_column(String(32), primary_key=True)
    watermark: Mapped[datetime | None]
    last_successful_sync_at: Mapped[datetime | None]
    last_full_sync_at: Mapped[datetime | None]
    bootstrapped_at: Mapped[datetime | None]
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    last_error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
