from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from pokazun.config import WEBHOOK_PATH, Settings
from pokazun.health import HealthRegistry

HEALTH_KEY = web.AppKey("health", HealthRegistry)


async def _healthz(request: web.Request) -> web.Response:
    ok, data = await request.app[HEALTH_KEY].collect()
    return web.json_response(data, status=200 if ok else 503)


async def _set_webhook(bot: Bot, dispatcher: Dispatcher, settings: Settings) -> None:
    secret = settings.webhook_secret.get_secret_value() if settings.webhook_secret else None
    await bot.set_webhook(
        url=settings.webhook_url,
        secret_token=secret,
        allowed_updates=dispatcher.resolve_used_update_types(),
        drop_pending_updates=False,
    )


def build_web_app(
    *,
    health: HealthRegistry,
    bot: Bot | None = None,
    dispatcher: Dispatcher | None = None,
    webhook_secret: str | None = None,
    handle_in_background: bool = True,
) -> web.Application:
    app = web.Application()
    app[HEALTH_KEY] = health
    app.router.add_get("/healthz", _healthz)
    if bot is not None and dispatcher is not None:
        dispatcher.startup.register(_set_webhook)
        SimpleRequestHandler(
            dispatcher=dispatcher,
            bot=bot,
            secret_token=webhook_secret,
            handle_in_background=handle_in_background,
        ).register(app, path=WEBHOOK_PATH)
        setup_application(app, dispatcher, bot=bot)
    return app
