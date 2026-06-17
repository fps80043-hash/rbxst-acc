"""Main entry point for the RBX Store Telegram bot.

Run:    python bot.py

Env vars required (see .env.example):
    BOT_TOKEN          — from @BotFather
    SITE_URL           — public URL of the rbx-site backend
    SITE_API_SECRET    — same value as BOT_API_SECRET on the site
"""
from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeDefault

from api import ApiError, api
from config import BOT_TOKEN, BOT_NAME, setup_logging
from handlers import admin, link, orders, payments, profile, shop, start, topup
from middlewares import LinkGate

log = logging.getLogger("bot")


BOT_COMMANDS = [
    BotCommand(command="start", description="🏠 Главное меню"),
    BotCommand(command="menu", description="🏠 Главное меню"),
    BotCommand(command="shop", description="🛒 Каталог товаров"),
    BotCommand(command="balance", description="💰 Баланс"),
    BotCommand(command="profile", description="👤 Профиль"),
    BotCommand(command="orders", description="📋 Мои покупки"),
    BotCommand(command="link", description="🔗 Привязать аккаунт"),
    BotCommand(command="unlink", description="🔓 Отвязать"),
    BotCommand(command="help", description="❓ Помощь"),
]


async def _on_startup(bot: Bot) -> None:
    me = await bot.get_me()
    log.info("Bot started as @%s (id=%s, %s)", me.username, me.id, BOT_NAME)
    # Register slash-command list shown in Telegram clients
    try:
        await bot.set_my_commands(BOT_COMMANDS, scope=BotCommandScopeDefault())
        log.info("Bot commands registered (%d)", len(BOT_COMMANDS))
    except Exception as e:
        log.warning("Failed to register commands: %s", e)
    # Quick health-check against the site + secret diagnostics
    try:
        diag = await api.diag()
        if not diag.get("secret_configured"):
            log.error(
                "❌ Site has BOT_API_SECRET NOT SET. "
                "Set it on Railway → Variables and redeploy the site."
            )
        elif not diag.get("provided_matches"):
            log.error(
                "❌ Secret MISMATCH: site has %d chars, bot sent %d chars, but values differ.\n"
                "   Bot's SITE_API_SECRET must EXACTLY equal site's BOT_API_SECRET.\n"
                "   Check for trailing spaces, missing chars, or quotes around the value.",
                int(diag.get("secret_length") or 0),
                int(diag.get("provided_length") or 0),
            )
        else:
            h = await api.health()
            log.info("✅ Site reachable AND secrets match. build=%s", h.get("build"))
    except ApiError as e:
        log.error(
            "Cannot reach site at startup: %s.\n"
            "Bot will still run but commands will fail until the site is up.",
            e,
        )


async def _on_shutdown(bot: Bot) -> None:
    log.info("Shutting down...")
    await api.close()


async def main() -> None:
    setup_logging()
    log.info("Starting %s", BOT_NAME)

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Mandatory site-link gate — blocks everything except /start, /link, /help,
    # /menu and link/help callbacks until the user links a site account.
    dp.message.middleware(LinkGate())
    dp.callback_query.middleware(LinkGate())

    # Order matters a bit — register routers in a logical sequence.
    # Aiogram dispatches on first match, so put more specific (e.g. start with deeplink) first.
    dp.include_router(start.router)
    dp.include_router(link.router)
    dp.include_router(profile.router)
    dp.include_router(payments.router)   # pre_checkout + successful_payment (Stars)
    dp.include_router(topup.router)
    dp.include_router(shop.router)
    dp.include_router(orders.router)
    dp.include_router(admin.router)

    dp.startup.register(_on_startup)
    dp.shutdown.register(_on_shutdown)

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)
