from collections.abc import Callable, Sequence
from datetime import datetime

from aiogram import Dispatcher, Router
from aiogram.types import ErrorEvent
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pokazun.alerts import Alert, AlertService
from pokazun.bot.middlewares import (
    AccessMiddleware,
    ActivityMiddleware,
    DbSessionMiddleware,
    IdempotencyMiddleware,
    LogContextMiddleware,
)
from pokazun.clock import utcnow
from pokazun.config import Settings
from pokazun.log import get_logger

log = get_logger(__name__)


def build_dispatcher(
    *,
    settings: Settings,
    sessionmaker: async_sessionmaker[AsyncSession],
    alerts: AlertService,
    routers: Sequence[Router],
    clock: Callable[[], datetime] = utcnow,
) -> Dispatcher:
    dp = Dispatcher(settings=settings, alerts=alerts, clock=clock)
    dp.update.outer_middleware(LogContextMiddleware())
    dp.update.outer_middleware(DbSessionMiddleware(sessionmaker))
    dp.update.outer_middleware(AccessMiddleware(settings.allowlist))
    dp.update.outer_middleware(IdempotencyMiddleware())
    dp.update.outer_middleware(ActivityMiddleware(clock))
    dp.errors.register(_on_error)
    for router in routers:
        dp.include_router(router)
    return dp


async def _on_error(event: ErrorEvent, alerts: AlertService) -> bool:
    exc = event.exception
    job = "postgres" if isinstance(exc, DBAPIError) else "bot_handler"
    log.error("update_failed", exc_info=exc)
    await alerts.send(
        Alert(
            job=job,
            message=f"{type(exc).__name__}: {exc}",
            ids={"update_id": event.update.update_id},
            dedupe_key=f"{job}:{type(exc).__name__}",
        )
    )
    return True
