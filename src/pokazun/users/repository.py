from datetime import datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from pokazun.db.models import DeliveryState, User


async def touch_user(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    username: str | None,
    first_name: str | None,
    now: datetime,
) -> User:
    """Create or refresh the user on any user action; any action also restores Telegram delivery."""
    stmt = (
        insert(User)
        .values(
            telegram_user_id=telegram_user_id,
            username=username,
            first_name=first_name,
            last_activity_at=now,
            telegram_delivery_state=DeliveryState.ACTIVE,
        )
        .on_conflict_do_update(
            index_elements=[User.telegram_user_id],
            set_={
                "username": username,
                "first_name": first_name,
                "last_activity_at": now,
                "telegram_delivery_state": DeliveryState.ACTIVE.value,
                "updated_at": now,
            },
        )
        .returning(User)
    )
    result = await session.scalars(stmt, execution_options={"populate_existing": True})
    return result.one()
