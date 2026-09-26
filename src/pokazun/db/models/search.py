from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Identity,
    SmallInteger,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from pokazun.db.base import Base
from pokazun.db.models.users import str_enum
from pokazun.search.filters import ConditionGroup, PriceRange, RoomOption, SearchCriteria
from pokazun.search.steps import DraftMode, Step


class Search(Base):
    """The user's single confirmed search. Replaced atomically on edit (Д2 §23)."""

    __tablename__ = "searches"
    __table_args__ = (
        CheckConstraint("price_low <= price_high", name="price_range"),
        CheckConstraint("cardinality(rooms) > 0", name="rooms_not_empty"),
        CheckConstraint("cardinality(conditions) > 0", name="conditions_not_empty"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    rooms: Mapped[list[int]] = mapped_column(ARRAY(SmallInteger))
    conditions: Mapped[list[str]] = mapped_column(ARRAY(String(32)))
    price_low: Mapped[int] = mapped_column(SmallInteger)
    price_high: Mapped[int] = mapped_column(SmallInteger)
    baseline_at: Mapped[datetime]
    confirmed_at: Mapped[datetime]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    @property
    def criteria(self) -> SearchCriteria:
        return SearchCriteria(
            rooms=frozenset(RoomOption(r) for r in self.rooms),
            conditions=frozenset(ConditionGroup(c) for c in self.conditions),
            price=PriceRange(self.price_low, self.price_high),
        )


class SearchDraft(Base):
    """Unfinished setup or edit of a search (Д1 §3.4). Not an active search."""

    __tablename__ = "search_drafts"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    mode: Mapped[DraftMode] = mapped_column(str_enum(DraftMode))
    step: Mapped[Step] = mapped_column(str_enum(Step))
    rooms: Mapped[list[int]] = mapped_column(
        ARRAY(SmallInteger), default=list, server_default=text("'{}'")
    )
    conditions: Mapped[list[str]] = mapped_column(
        ARRAY(String(32)), default=list, server_default=text("'{}'")
    )
    price_low: Mapped[int | None] = mapped_column(SmallInteger)
    price_high: Mapped[int | None] = mapped_column(SmallInteger)
    reached_summary: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
