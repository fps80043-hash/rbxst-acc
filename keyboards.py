"""Inline keyboards for the Robux-bot.

Buttons use premium/custom-emoji ICONS via `icon_custom_emoji_id` (Bot API 9.4+,
aiogram ≥ 3.28). The button text stays clean — the custom emoji renders as the
button's leading icon.
"""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import ROBUX_PRESETS, SITE_URL
from premoji import eid


def _btn(text: str, *, cb: str = "", url: str = "", icon: str = "") -> InlineKeyboardButton:
    """InlineKeyboardButton with a premium-emoji icon (by premoji name)."""
    kw = {"text": text}
    if cb:
        kw["callback_data"] = cb
    if url:
        kw["url"] = url
    ico = eid(icon) if icon else None
    if ico:
        kw["icon_custom_emoji_id"] = ico
    return InlineKeyboardButton(**kw)


def main_menu_kb(is_admin: bool = False, balance: int | None = None) -> InlineKeyboardMarkup:
    rows = [
        [_btn("Каталог товаров", cb="shop:start", icon="box")],
        [
            _btn("Баланс", cb="profile:balance", icon="wallet"),
            _btn("Пополнить", cb="topup:start", icon="money_in"),
        ],
        [
            _btn("Профиль", cb="profile:show", icon="profile"),
            _btn("Мои покупки", cb="orders:list", icon="box"),
        ],
        [
            _btn("Помощь", cb="help:show", icon="info"),
            _btn("На сайт", url=SITE_URL, icon="link"),
        ],
    ]
    if is_admin:
        rows.append([_btn("Админ-панель", cb="admin:menu", icon="settings")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def link_prompt_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("Получить код на сайте", url=f"{SITE_URL}/v2", icon="link")],
        [_btn("Как привязать?", cb="link:help", icon="info")],
    ])


def back_to_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("◁  В главное меню", cb="menu:main", icon="home")]
    ])


def robux_amount_kb() -> InlineKeyboardMarkup:
    rows, line = [], []
    for amount in ROBUX_PRESETS:
        line.append(InlineKeyboardButton(text=f"{amount}", callback_data=f"robux:amt:{amount}"))
        if len(line) == 3:
            rows.append(line); line = []
    if line:
        rows.append(line)
    rows.append([
        _btn("Своя сумма", cb="robux:custom", icon="pencil"),
        _btn("Обновить", cb="robux:refresh", icon="loading"),
    ])
    rows.append([_btn("◁  В меню", cb="menu:main", icon="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def robux_confirm_kb(amount: int, can_pay: bool) -> InlineKeyboardMarkup:
    rows = []
    if can_pay:
        rows.append([_btn(f"Купить {amount} R$", cb=f"robux:buy:{amount}", icon="lock")])
    else:
        rows.append([_btn("Пополнить баланс", cb="topup:start", icon="money_in")])
    rows.append([
        _btn("◁ Другая сумма", cb="robux:start", icon="money"),
        _btn("Пересчитать", cb=f"robux:amt:{amount}", icon="loading"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def profile_kb(is_linked: bool) -> InlineKeyboardMarkup:
    if is_linked:
        rows = [
            [
                _btn("Обновить", cb="profile:show", icon="loading"),
                _btn("Пополнить", cb="topup:start", icon="money_in"),
            ],
            [
                _btn("Мои заказы", cb="orders:list", icon="box"),
                _btn("Сайт", url=SITE_URL, icon="link"),
            ],
            [_btn("Отвязать аккаунт", cb="profile:unlink", icon="unlock")],
            [_btn("◁  В меню", cb="menu:main", icon="home")],
        ]
    else:
        rows = [
            [_btn("Привязать аккаунт", cb="link:start", icon="link")],
            [_btn("Сайт", url=SITE_URL, icon="link")],
        ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_unlink_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        _btn("Да, отвязать", cb="profile:unlink:yes", icon="check"),
        _btn("Отмена", cb="profile:show", icon="cross"),
    ]])


def orders_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            _btn("Обновить", cb="orders:list", icon="loading"),
            _btn("На сайте", url=f"{SITE_URL}/v2", icon="link"),
        ],
        [_btn("◁  В меню", cb="menu:main", icon="home")],
    ])


def admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            _btn("Свежие заказы", cb="admin:orders", icon="stats"),
            _btn("Найти юзера", cb="admin:find_user", icon="people"),
        ],
        [
            _btn("Звёзды бота", cb="admin:stars", icon="money"),
            _btn("Сайт", url=f"{SITE_URL}/v2", icon="link"),
        ],
        [_btn("◁  В меню", cb="menu:main", icon="home")],
    ])
