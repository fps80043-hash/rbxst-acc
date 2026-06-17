"""Mandatory site-link gate.

Nobody can use the bot until they've linked a site account. Linking itself is
done on the website (register/login → get a code) and confirmed here via
/link <code>. Everything else is blocked behind this gate.

Implemented as an aiogram middleware registered on the message + callback_query
observers. Positive link results are cached briefly so we don't hit the site
on every update; cache is invalidated on link/unlink.
"""
from __future__ import annotations

import time
from typing import Any, Awaitable, Callable, Dict, Optional

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from api import ApiError, api
from keyboards import link_prompt_kb
from premoji import pe

# tg_id -> (linked, expiry).  Only POSITIVE results are cached (so a freshly
# linked user is recognised within TTL; unlinked users are re-checked each time
# but that's cheap and rare).
_LINK_CACHE: Dict[int, tuple] = {}
_TTL = 45.0

# Commands anyone may use unlinked (entry points + linking + help).
# /stars is admin-gated inside its handler, so it's safe to let through the gate.
_EXEMPT_CMDS = {"/start", "/link", "/unlink", "/help", "/menu", "/stars"}
# Callback prefixes anyone may use unlinked.
_EXEMPT_CB = ("link:", "help:")
_EXEMPT_CB_EXACT = {"menu:main"}


def invalidate_link(tg_id: int) -> None:
    _LINK_CACHE.pop(int(tg_id), None)


def mark_linked(tg_id: int) -> None:
    _LINK_CACHE[int(tg_id)] = (True, time.time() + _TTL)


async def _is_linked(tg_id: int) -> bool:
    now = time.time()
    c = _LINK_CACHE.get(tg_id)
    if c and c[1] > now:
        return c[0]
    try:
        link = await api.get_link(tg_id)
    except ApiError:
        link = None
    ok = bool(link)
    if ok:
        _LINK_CACHE[tg_id] = (True, now + _TTL)
    return ok


def _gate_text() -> str:
    return (
        f"{pe('lock')} <b>Доступ только после регистрации</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{pe('info')} Чтобы пользоваться ботом, нужно <b>привязать аккаунт сайта</b> — "
        "это обязательно (баланс, заказы и история живут на сайте).\n\n"
        f"{pe('bot')} <b>Как привязать за 30 секунд:</b>\n"
        f"<b>1.</b> Открой сайт и войди / зарегистрируйся\n"
        f"<b>2.</b> Профиль → <b>Безопасность</b> → блок Telegram-бот\n"
        f"<b>3.</b> Нажми «Получить код привязки»\n"
        f"<b>4.</b> Пришли мне: <code>/link 123456</code>"
    )


class LinkGate(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        tg_id: Optional[int] = None

        if isinstance(event, Message):
            tg_id = event.from_user.id if event.from_user else None
            # Stars payment confirmations carry no text and must never be gated —
            # the money already moved; we must credit it.
            if getattr(event, "successful_payment", None):
                return await handler(event, data)
            txt = (event.text or "").strip()
            cmd = txt.split()[0].split("@")[0].lower() if txt else ""
            if cmd in _EXEMPT_CMDS:
                return await handler(event, data)
        elif isinstance(event, CallbackQuery):
            tg_id = event.from_user.id if event.from_user else None
            d = event.data or ""
            if d in _EXEMPT_CB_EXACT or d.startswith(_EXEMPT_CB):
                return await handler(event, data)
        else:
            return await handler(event, data)

        if tg_id is None or await _is_linked(tg_id):
            return await handler(event, data)

        # Blocked — show the registration/linking gate.
        if isinstance(event, Message):
            await event.answer(_gate_text(), reply_markup=link_prompt_kb(), parse_mode="HTML")
        else:
            await event.answer("Сначала привяжи аккаунт сайта", show_alert=True)
            try:
                await event.message.answer(_gate_text(), reply_markup=link_prompt_kb(), parse_mode="HTML")
            except Exception:
                pass
        return None
