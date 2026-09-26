from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, Enum, Identity, String, func
from sqlalchemy.orm import Mapped, mapped_column

from pokazun.db.base import Base


def str_enum(enum_cls: type[StrEnum]) -> Enum:
    """Store a StrEnum as VARCHAR(32) holding its value.

    The CHECK constraint lives in the migration.
    """
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
