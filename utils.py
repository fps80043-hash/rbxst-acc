"""Utility helpers used across handlers."""
from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Any, Optional


def esc(text: Any) -> str:
    """Escape HTML for use in aiogram.HTML parse_mode messages."""
    return html.escape(str(text or ""), quote=False)


def fmt_rub(amount: Any) -> str:
    """Format integer rubles like 1 234 ₽."""
    try:
        n = int(amount)
    except (TypeError, ValueError):
        n = 0
    return f"{n:,}".replace(",", " ") + " ₽"


def fmt_robux(amount: Any) -> str:
    """Format Robux amount like 1 700 R$."""
    try:
        n = int(amount)
    except (TypeError, ValueError):
        n = 0
    return f"{n:,}".replace(",", " ") + " R$"


def fmt_num(n: Any) -> str:
    try:
        return f"{int(n):,}".replace(",", " ")
    except (TypeError, ValueError):
        return str(n or 0)


def parse_iso(s: Any) -> Optional[datetime]:
    if not s:
        return None
    try:
        text = str(s).strip()
        # Handle Z suffix and missing tz
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def fmt_relative(s: Any) -> str:
    """Render a timestamp as relative ("3 мин назад") or short date."""
    dt = parse_iso(s)
    if not dt:
        return str(s or "")
    now = datetime.now(timezone.utc)
    diff = (now - dt).total_seconds()
    if diff < 0:
        diff = 0
    if diff < 60:
        return "только что"
    if diff < 3600:
        return f"{int(diff // 60)} мин назад"
    if diff < 86400:
        return f"{int(diff // 3600)} ч назад"
    if diff < 30 * 86400:
        return f"{int(diff // 86400)} д назад"
    return dt.strftime("%d.%m.%Y")


_STATUS_LABELS = {
    "new": "🆕 Новый",
    "pending": "⏳ Ожидание",
    "reserved": "🔒 Забронирован",
    "paid": "💰 Оплачен",
    "processing": "⚙️ Выполняется",
    "in_progress": "⚙️ Выполняется",
    "done": "✅ Доставлен",
    "completed": "✅ Доставлен",
    "cancelled": "❌ Отменён",
    "expired": "⌛ Истёк",
    "refunded": "↩️ Возвращён",
    "failed": "⚠️ Ошибка",
    "error": "⚠️ Ошибка",
}


def status_label(status: str) -> str:
    s = (status or "").strip().lower()
    return _STATUS_LABELS.get(s, f"❔ {status or '?'}")


def is_premium_active(premium_until: Any) -> bool:
    dt = parse_iso(premium_until)
    if not dt:
        return False
    return dt > datetime.now(timezone.utc)


def bar(value: Any, maximum: Any, width: int = 10) -> str:
    """Render a compact progress bar like ▰▰▰▰▰▱▱▱▱▱ (filled/empty blocks)."""
    try:
        v = max(0.0, float(value))
        m = float(maximum)
        if m <= 0:
            return "▱" * width
    except (TypeError, ValueError):
        return "▱" * width
    filled = int(round(width * min(v / m, 1.0)))
    filled = max(0, min(width, filled))
    return "▰" * filled + "▱" * (width - filled)


async def typing(target: Any) -> None:
    """Show the 'typing…' chat action — makes the bot feel responsive/alive.
    Accepts a Message or CallbackQuery; never raises."""
    try:
        msg = getattr(target, "message", None) or target
        bot = getattr(target, "bot", None) or getattr(msg, "bot", None)
        chat = getattr(msg, "chat", None)
        if bot and chat:
            await bot.send_chat_action(chat.id, "typing")
    except Exception:
        pass
