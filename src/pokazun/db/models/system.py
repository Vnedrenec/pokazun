from datetime import datetime

from sqlalchemy import BigInteger, func
from sqlalchemy.orm import Mapped, mapped_column

from pokazun.db.base import Base


class ProcessedUpdate(Base):
    """Telegram update_id already handled; protects against re-delivery after restarts."""

    __tablename__ = "processed_updates"

    update_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    processed_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)
