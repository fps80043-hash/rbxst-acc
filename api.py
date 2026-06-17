"""HTTP client for talking to the RBX Store backend.

All requests go to the /api/bot/* family of endpoints which require the
shared SITE_API_SECRET. Per-user actions also require either ?telegram_id=...
or ?site_user_id=... — we always pass telegram_id since the bot only knows
that.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import aiohttp

from config import HTTP_TIMEOUT_SEC, SITE_API_SECRET, SITE_URL

log = logging.getLogger(__name__)


class ApiError(RuntimeError):
    """Raised when the site returns a non-2xx response or unexpected payload."""

    def __init__(self, message: str, status: int = 0, *, payload: Any = None):
        super().__init__(message)
        self.status = status
        self.payload = payload


class SiteApi:
    """Thin async wrapper. One instance per bot process."""

    def __init__(self) -> None:
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SEC)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers={
                    "X-API-SECRET": SITE_API_SECRET,
                    "User-Agent": "rbx-store-bot/1.0",
                    "Accept": "application/json",
                },
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        url = f"{SITE_URL}{path}"
        session = await self._get_session()
        req_timeout = aiohttp.ClientTimeout(total=timeout) if timeout else None
        try:
            async with session.request(method, url, params=params, json=json_body, timeout=req_timeout) as resp:
                # Try parsing JSON regardless of status (errors usually have detail)
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    text = await resp.text()
                    raise ApiError(
                        f"Bad response from server: {text[:200]}",
                        status=resp.status,
                    )
                if resp.status >= 400:
                    detail = ""
                    if isinstance(data, dict):
                        detail = data.get("detail") or data.get("message") or ""
                    raise ApiError(detail or f"HTTP {resp.status}", status=resp.status, payload=data)
                if not isinstance(data, dict):
                    raise ApiError("Unexpected response shape", status=resp.status, payload=data)
                return data
        except aiohttp.ClientError as e:
            log.warning("Network error talking to %s %s: %s", method, path, e)
            raise ApiError(f"Сервер недоступен: {e}", status=0) from e

    # ────────── Public helpers ──────────

    async def health(self) -> Dict[str, Any]:
        return await self._request("GET", "/api/bot/health")

    async def diag(self) -> Dict[str, Any]:
        """Public diagnostic — works even if secret is wrong, used at startup."""
        return await self._request("GET", "/api/bot/diag")

    async def get_link(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        try:
            data = await self._request("GET", "/api/bot/telegram/link", params={"telegram_id": telegram_id})
        except ApiError as e:
            if e.status == 404:
                return None
            raise
        link = data.get("link")
        if not link:
            return None
        return link

    async def link_by_code(self, code: str, telegram_id: int, telegram_username: str = "") -> Dict[str, Any]:
        """Bind site account to telegram via 6-digit code obtained on the site."""
        body = {
            "code": code.strip(),
            "telegram_id": telegram_id,
            "telegram_username": telegram_username or "",
        }
        return await self._request("POST", "/api/bot/link_by_code", json_body=body)

    async def unlink(self, telegram_id: int) -> Dict[str, Any]:
        return await self._request(
            "POST", "/api/bot/telegram/unlink", json_body={"telegram_id": telegram_id}
        )

    async def get_profile(self, telegram_id: int) -> Dict[str, Any]:
        data = await self._request("GET", "/api/bot/profile", params={"telegram_id": telegram_id})
        return data.get("user") or {}

    async def get_balance(self, telegram_id: int) -> int:
        data = await self._request("GET", "/api/bot/balance", params={"telegram_id": telegram_id})
        return int(data.get("balance") or 0)

    async def robux_stock(self) -> Dict[str, Any]:
        return await self._request("GET", "/api/bot/robux/stock")

    async def robux_quote(self, robux_amount: int) -> Dict[str, Any]:
        return await self._request(
            "GET", "/api/bot/robux/quote", params={"robux_amount": robux_amount}
        )

    async def robux_orders(self, telegram_id: int, limit: int = 10) -> Dict[str, Any]:
        return await self._request(
            "GET", "/api/bot/robux/orders",
            params={"telegram_id": telegram_id, "limit": limit},
        )

    async def robux_order(self, telegram_id: int, robux_amount: int, *,
                          nick: str = "", url: str = "") -> Dict[str, Any]:
        """Reserve + pay a Robux order in one call (in-bot purchase)."""
        body = {"robux_amount": int(robux_amount)}
        if url:
            body["gamepass_url"] = url
        if nick:
            body["nick"] = nick
        # By-nick gamepass scan on the site can take a while → generous timeout.
        return await self._request(
            "POST", "/api/bot/robux/order",
            params={"telegram_id": telegram_id}, json_body=body, timeout=120,
        )

    async def robux_order_status(self, telegram_id: int, order_id: int) -> Dict[str, Any]:
        data = await self._request(
            "GET", "/api/bot/robux/order_status",
            params={"telegram_id": telegram_id, "id": order_id},
        )
        return data.get("order") or {}

    async def topup_config(self) -> Dict[str, Any]:
        data = await self._request("GET", "/api/bot/topup/config")
        return data.get("topup") or {}

    async def topup_create(self, telegram_id: int, amount: int, method: str) -> Dict[str, Any]:
        return await self._request(
            "POST", "/api/bot/topup/create",
            params={"telegram_id": telegram_id},
            json_body={"amount": int(amount), "method": method},
        )

    async def topup_status(self, telegram_id: int, topup_id: int) -> Dict[str, Any]:
        return await self._request(
            "GET", "/api/bot/topup/status",
            params={"telegram_id": telegram_id, "id": topup_id},
        )

    async def stars_info(self, topup_id: int) -> Dict[str, Any]:
        """How many Stars (XTR) to charge for a pending stars top-up (used for the
        site deep-link flow). No per-user param — the topup row already knows its user."""
        return await self._request("GET", "/api/bot/topup/stars_info", params={"id": topup_id})

    async def stars_confirm(self, topup_id: int, charge_id: str = "") -> Dict[str, Any]:
        """Credit a stars top-up after a successful XTR payment. Idempotent."""
        return await self._request(
            "POST", "/api/bot/topup/stars_confirm",
            json_body={"id": int(topup_id), "charge_id": charge_id},
        )

    async def shop_catalog(self) -> Dict[str, Any]:
        return await self._request("GET", "/api/bot/shop/catalog")

    async def shop_orders(self, telegram_id: int, limit: int = 10) -> Dict[str, Any]:
        return await self._request(
            "GET", "/api/bot/shop/orders",
            params={"telegram_id": telegram_id, "limit": limit},
        )

    async def shop_buy(self, telegram_id: int, product_id: str, discount_code: str = "") -> Dict[str, Any]:
        """Buy a shop item for the linked user — deducts balance, returns delivery."""
        from urllib.parse import quote
        body: Dict[str, Any] = {}
        if discount_code:
            body["discount_code"] = discount_code
        return await self._request(
            "POST", f"/api/bot/shop/buy/{quote(str(product_id), safe='')}",
            params={"telegram_id": telegram_id}, json_body=body, timeout=60,
        )

    # ────────── Admin endpoints (require admin user link + bot secret) ──────────

    async def admin_orders_recent(self, telegram_id: int, limit: int = 10) -> Dict[str, Any]:
        return await self._request(
            "GET", "/api/bot/admin/orders/recent",
            params={"telegram_id": telegram_id, "limit": limit},
        )

    async def admin_users_find(self, telegram_id: int, query: str) -> Dict[str, Any]:
        return await self._request(
            "GET", "/api/bot/admin/users/find",
            params={"telegram_id": telegram_id, "q": query},
        )

    async def admin_balance_adjust(
        self, admin_tg_id: int, target_user_id: int, delta: int, reason: str
    ) -> Dict[str, Any]:
        return await self._request(
            "POST", "/api/bot/admin/balance_adjust",
            params={"telegram_id": admin_tg_id},
            json_body={"user_id": target_user_id, "delta": int(delta), "reason": reason[:140]},
        )


# Singleton
api = SiteApi()
