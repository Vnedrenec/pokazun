from aiogram import Router

from pokazun.bot.handlers import fallback, search_setup


def build_routers() -> list[Router]:
    """Production routers in priority order. New feature routers go before the fallback router."""
    return [search_setup.build_router(), fallback.build_router()]
