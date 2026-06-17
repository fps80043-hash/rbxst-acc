"""Configuration loaded from environment variables."""
from __future__ import annotations

import logging
import os
from typing import Set

from dotenv import load_dotenv

load_dotenv()


def _get_required(key: str) -> str:
    val = os.environ.get(key, "").strip()
    if not val:
        raise RuntimeError(
            f"Missing required environment variable: {key}\n"
            f"Copy .env.example to .env and fill in the values."
        )
    return val


def _get_optional(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _parse_admin_ids(raw: str) -> Set[int]:
    out: Set[int] = set()
    for chunk in (raw or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            out.add(int(chunk))
        except ValueError:
            continue
    return out


def _normalize_site_url(raw: str) -> str:
    """Force https + strip trailing slash. The site serves https-only and
    redirects http→https with a 301 that turns POST into GET (→ 405 Method Not
    Allowed on linking/buying). So we never let an http:// or trailing-slash
    URL through, regardless of how SITE_URL is typed in the env."""
    u = (raw or "").strip().rstrip("/")
    low = u.lower()
    is_local = ("localhost" in low) or ("127.0.0.1" in low)
    if low.startswith("http://") and not is_local:
        u = "https://" + u[len("http://"):]
    elif not low.startswith(("http://", "https://")):
        u = ("http://" if is_local else "https://") + u
    return u


BOT_TOKEN: str = _get_required("BOT_TOKEN")
SITE_URL: str = _normalize_site_url(_get_required("SITE_URL"))
SITE_API_SECRET: str = _get_required("SITE_API_SECRET")

ADMIN_TG_IDS: Set[int] = _parse_admin_ids(_get_optional("ADMIN_TG_IDS"))
LOG_LEVEL: str = _get_optional("LOG_LEVEL", "INFO").upper()


# Bot-level constants
BOT_NAME = "RBX ST | Аккаунты и товары"
BOT_TAGLINE = "Магазин аккаунтов и цифровых товаров"
ROBUX_PRESETS = (100, 400, 800, 1700, 4500, 10000)  # kept for keyboards import compat
HTTP_TIMEOUT_SEC = 15
PROFILE_CACHE_SEC = 30  # cache /api/bot/profile responses for this many seconds


def setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    # Quiet down chatty libraries
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)
