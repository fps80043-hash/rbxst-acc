"""Shop catalog → product → buy → instant delivery.

Synced with the site: purchase deducts the shared balance and the site returns
the delivery payload (login/password/code/…), which we show right away.
"""
from __future__ import annotations

import logging
from collections import OrderedDict

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from api import ApiError, api
from config import SITE_URL
from keyboards import back_to_menu_kb
from premoji import eid, pe
from utils import esc, fmt_rub, typing

router = Router(name="shop")
log = logging.getLogger(__name__)

RULE = "━━━━━━━━━━━━━━━━━━━━━━"


# ─────────────────────────── catalog helpers ───────────────────────────
def _group_items_by_category(items: list, categories: list) -> "OrderedDict[str, dict]":
    cat_titles = {str(c.get("id")): str(c.get("title") or c.get("id") or "") for c in (categories or [])}
    cat_order = [str(c.get("id")) for c in (categories or []) if c.get("visible") is not False]
    grouped: "OrderedDict[str, dict]" = OrderedDict()
    for cid in cat_order:
        grouped[cid] = {"title": cat_titles.get(cid, cid), "items": []}
    for item in items or []:
        if item.get("visible") is False:
            continue
        raw = item.get("raw") or {}
        cid = str(raw.get("category_id") or item.get("category") or "other")
        if cid not in grouped:
            grouped[cid] = {"title": cat_titles.get(cid, cid or "Прочее"), "items": []}
        grouped[cid]["items"].append(item)
    return OrderedDict((k, v) for k, v in grouped.items() if v["items"])


def _find_item(items: list, product_id: str) -> dict | None:
    for it in items or []:
        if str(it.get("id")) == str(product_id):
            return it
    return None


def _item_oos(item: dict) -> bool:
    raw = item.get("raw") or {}
    if raw.get("out_of_stock"):
        return True
    stock = item.get("stock")
    return stock is not None and int(stock) <= 0 and not raw.get("unlimited")


# ─────────────────────────── keyboards ───────────────────────────
def _categories_kb(grouped: "OrderedDict[str, dict]") -> InlineKeyboardMarkup:
    rows, line = [], []
    for cid, data in grouped.items():
        line.append(InlineKeyboardButton(text=f"{data['title'][:24]} · {len(data['items'])}",
                                         callback_data=f"shop:cat:{cid}"))
        if len(line) == 2:
            rows.append(line); line = []
    if line:
        rows.append(line)
    rows.append([InlineKeyboardButton(text="На сайт", url=f"{SITE_URL}/v2", icon_custom_emoji_id=eid("link"))])
    rows.append([InlineKeyboardButton(text="◁  В меню", callback_data="menu:main", icon_custom_emoji_id=eid("home"))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _category_kb(cid: str, items: list) -> InlineKeyboardMarkup:
    rows = []
    for it in items[:30]:
        title = str(it.get("title") or "Товар")[:30]
        price = int(float(it.get("price") or 0))
        mark = "  ⚠️" if _item_oos(it) else ""
        rows.append([InlineKeyboardButton(text=f"{title} · {price} ₽{mark}",
                                          callback_data=f"shop:item:{it.get('id')}")])
    rows.append([InlineKeyboardButton(text="◁  К категориям", callback_data="shop:list",
                                      icon_custom_emoji_id=eid("home"))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _product_kb(item: dict) -> InlineKeyboardMarkup:
    pid = item.get("id")
    raw = item.get("raw") or {}
    cid = str(raw.get("category_id") or item.get("category") or "")
    price = int(float(item.get("price") or 0))
    rows = []
    if _item_oos(item):
        rows.append([InlineKeyboardButton(text="Нет в наличии", callback_data="shop:oos")])
    else:
        rows.append([InlineKeyboardButton(text=f"Купить за {price} ₽", callback_data=f"shop:buy:{pid}",
                                          icon_custom_emoji_id=eid("lock"))])
    back = f"shop:cat:{cid}" if cid else "shop:list"
    rows.append([InlineKeyboardButton(text="◁  Назад", callback_data=back, icon_custom_emoji_id=eid("home"))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ─────────────────────────── handlers ───────────────────────────
@router.message(Command("shop"))
async def cmd_shop(msg: Message):
    await _show_categories(msg)


@router.callback_query(F.data == "shop:start")
@router.callback_query(F.data == "shop:list")
async def cb_shop_list(cb: CallbackQuery):
    await _show_categories(cb)


@router.callback_query(F.data == "shop:oos")
async def cb_shop_oos(cb: CallbackQuery):
    await cb.answer("Этого товара сейчас нет в наличии", show_alert=True)


async def _show_categories(target) -> None:
    msg = target if isinstance(target, Message) else target.message
    if isinstance(target, Message):
        await typing(target)
    try:
        data = await api.shop_catalog()
    except ApiError as e:
        await msg.answer(f"{pe('cross')}  Не удалось загрузить каталог: <i>{esc(e)}</i>", parse_mode="HTML")
        if isinstance(target, CallbackQuery):
            await target.answer()
        return
    items = data.get("items") or []
    cfg = data.get("config") or {}
    grouped = _group_items_by_category(items, cfg.get("categories") or [])
    if not grouped:
        text = (f"{pe('box')}  <b>Каталог</b>\n{RULE}\n\n"
                "Сейчас нет доступных товаров. Загляни позже или открой сайт.")
        kb = back_to_menu_kb()
    else:
        total = sum(len(v["items"]) for v in grouped.values())
        text = (f"{pe('box')}  <b>Магазин аккаунтов и товаров</b>\n{RULE}\n\n"
                f"{pe('stats')}  Категорий: <b>{len(grouped)}</b>  ·  Товаров: <b>{total}</b>\n\n"
                f"{pe('send')}  Выбери категорию:")
        kb = _categories_kb(grouped)
    await _render(target, text, kb)


@router.callback_query(F.data.startswith("shop:cat:"))
async def cb_shop_category(cb: CallbackQuery):
    cid = cb.data.split(":", 2)[2] if cb.data.count(":") >= 2 else ""
    try:
        data = await api.shop_catalog()
    except ApiError as e:
        await cb.answer(f"Ошибка: {e}", show_alert=True); return
    items = data.get("items") or []
    cfg = data.get("config") or {}
    grouped = _group_items_by_category(items, cfg.get("categories") or [])
    cat = grouped.get(cid)
    if not cat:
        await cb.answer("Категория не найдена", show_alert=True); return
    text = (f"{pe('box')}  <b>{esc(cat['title'])}</b>\n{RULE}\n\n"
            f"{pe('send')}  Выбери товар:")
    await _render(cb, text, _category_kb(cid, cat["items"]))


@router.callback_query(F.data.startswith("shop:item:"))
async def cb_shop_item(cb: CallbackQuery):
    pid = cb.data.split(":", 2)[2] if cb.data.count(":") >= 2 else ""
    try:
        data = await api.shop_catalog()
    except ApiError as e:
        await cb.answer(f"Ошибка: {e}", show_alert=True); return
    item = _find_item(data.get("items") or [], pid)
    if not item:
        await cb.answer("Товар не найден", show_alert=True); return
    title = esc(str(item.get("title") or "Товар"))
    price = int(float(item.get("price") or 0))
    desc = str(item.get("description") or "").strip()
    stock = item.get("stock")
    lines = [f"{pe('box')}  <b>{title}</b>", RULE, "", f"{pe('money')}  Цена:  <b>{fmt_rub(price)}</b>"]
    if stock is not None and not (item.get('raw') or {}).get("unlimited"):
        lines.append(f"{pe('stats')}  В наличии:  <b>{int(stock)}</b>")
    if desc:
        lines += ["", f"<i>{esc(desc[:600])}</i>"]
    if _item_oos(item):
        lines += ["", f"{pe('cross')}  <i>Сейчас нет в наличии.</i>"]
    else:
        lines += ["", f"{pe('info')}  <i>Оплата с баланса — выдача мгновенная.</i>"]
    await _render(cb, "\n".join(lines), _product_kb(item))


@router.callback_query(F.data.startswith("shop:buy:"))
async def cb_shop_buy(cb: CallbackQuery):
    pid = cb.data.split(":", 2)[2] if cb.data.count(":") >= 2 else ""
    await cb.answer()
    await typing(cb.message)
    try:
        r = await api.shop_buy(cb.from_user.id, pid)
    except ApiError as e:
        st = getattr(e, "status", 0)
        if st == 402:  # insufficient balance
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Пополнить баланс", callback_data="topup:start",
                                      icon_custom_emoji_id=eid("money_in"))],
                [InlineKeyboardButton(text="◁  Назад", callback_data=f"shop:item:{pid}",
                                      icon_custom_emoji_id=eid("home"))],
            ])
            await cb.message.edit_text(
                f"{pe('cross')}  <b>Недостаточно средств</b>\n{RULE}\n\n"
                f"<i>{esc(e)}</i>\n\nПополни баланс и попробуй снова.",
                reply_markup=kb, parse_mode="HTML")
            return
        if st == 409:  # out of stock
            await cb.message.edit_text(
                f"{pe('cross')}  <b>Товар закончился</b>\n{RULE}\n\n<i>{esc(e)}</i>",
                reply_markup=back_to_menu_kb(), parse_mode="HTML")
            return
        await cb.message.edit_text(
            f"{pe('cross')}  Не удалось купить: <i>{esc(e)}</i>",
            reply_markup=back_to_menu_kb(), parse_mode="HTML")
        return

    title = esc(str(r.get("product_title") or "Товар"))
    delivery = str(r.get("delivery_text") or "").strip()
    new_bal = r.get("new_balance")
    body = [
        f"{pe('party')}  <b>Покупка успешна!</b>\n{RULE}",
        "",
        f"{pe('box')}  Товар:  <b>{title}</b>",
    ]
    if new_bal is not None:
        body.append(f"{pe('wallet')}  Остаток на балансе:  <b>{fmt_rub(int(new_bal))}</b>")
    if delivery:
        body += ["", f"{pe('lock')}  <b>Твои данные</b> (нажми, чтобы скопировать):",
                 f"<tg-spoiler><code>{esc(delivery)}</code></tg-spoiler>"]
    else:
        body += ["", f"{pe('info')}  <i>Данные придут отдельно / уже на сайте в «Покупках».</i>"]
    body += ["", f"{pe('smile')}  Спасибо за покупку!"]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Мои покупки", callback_data="orders:list", icon_custom_emoji_id=eid("box"))],
        [InlineKeyboardButton(text="◁  В меню", callback_data="menu:main", icon_custom_emoji_id=eid("home"))],
    ])
    try:
        await cb.message.edit_text("\n".join(body), reply_markup=kb, parse_mode="HTML")
    except Exception:
        await cb.message.answer("\n".join(body), reply_markup=kb, parse_mode="HTML")


async def _render(target, text: str, kb) -> None:
    msg = target if isinstance(target, Message) else target.message
    if isinstance(target, CallbackQuery):
        try:
            await msg.edit_text(text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)
        except Exception:
            await msg.answer(text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)
        await target.answer()
    else:
        await msg.answer(text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)
