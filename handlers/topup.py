"""In-bot balance top-up. Creates a payment on the site (same balance as the
website — paying via the bot credits the site account automatically) and polls
until it's paid."""
from __future__ import annotations

import asyncio
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from api import ApiError, api
from config import SITE_URL
from keyboards import back_to_menu_kb
from premoji import eid, pe
from utils import esc, fmt_rub, typing

router = Router(name="topup")
log = logging.getLogger(__name__)

RULE = "━━━━━━━━━━━━━━━━━━━━━━"
PRESETS = [100, 300, 500, 1000, 2000, 5000]
MIN_RUB = 10
_SPIN = ["◐", "◓", "◑", "◒"]


class TopupStates(StatesGroup):
    waiting_amount = State()   # state data: {"method": <id>}


# method id → display metadata (label, premoji icon, commission text, subtitle)
_METHODS = {
    "crypto":   {"label": "CryptoBot",        "icon": "money",    "fee": "без комиссии",  "sub": "USDT · TON · BTC и др."},
    "stars":    {"label": "Telegram Stars ⭐", "icon": "star",     "fee": "1 ⭐ = 1 ₽",     "sub": "оплата звёздами в Telegram"},
    "platega":  {"label": "Карта / СБП",      "icon": "money_in", "fee": "0%",            "sub": "Visa · MIR · СБП"},
}
_ORDER = ("crypto", "stars", "platega")


async def _enabled_methods():
    try:
        cfg = await api.topup_config()
    except ApiError:
        cfg = {}
    enabled = [m for m in _ORDER if (cfg.get(m) or {}).get("enabled")]
    return enabled, cfg


def _fee_text(method: str, cfg: dict) -> str:
    if method == "stars":
        try:
            rate = float((cfg.get("stars") or {}).get("rub_rate") or 1)
        except Exception:
            rate = 1.0
        return f"1 ⭐ = {('%g' % rate)} ₽"
    return _METHODS[method]["fee"]


# ── STEP 1 — choose the payment method (shows min + commission per method) ──
async def _show_methods(target) -> None:
    msg = target if isinstance(target, Message) else target.message
    if isinstance(target, Message):
        await typing(target)
    enabled, cfg = await _enabled_methods()
    if not enabled:
        text = (
            f"{pe('cross')}  <b>Оплата временно недоступна</b>\n\n"
            f"Способы пополнения ещё подключаются. Пока можно на сайте: {SITE_URL}/v2#topup"
        )
        if isinstance(target, CallbackQuery):
            try: await msg.edit_text(text, reply_markup=back_to_menu_kb(), parse_mode="HTML")
            except Exception: await msg.answer(text, reply_markup=back_to_menu_kb(), parse_mode="HTML")
            await target.answer()
        else:
            await msg.answer(text, reply_markup=back_to_menu_kb(), parse_mode="HTML")
        return

    rows = []
    for m in enabled:
        meta = _METHODS[m]
        rows.append([InlineKeyboardButton(
            text=f"{meta['label']} · мин {MIN_RUB} ₽ · {_fee_text(m, cfg)}",
            callback_data=f"topup:m:{m}", icon_custom_emoji_id=eid(meta["icon"]))])
    rows.append([InlineKeyboardButton(text="◁  В меню", callback_data="menu:main",
                                      icon_custom_emoji_id=eid("home"))])
    text = (
        f"{pe('money_in')}  <b>Пополнение баланса</b>\n{RULE}\n\n"
        f"{pe('send')}  Сначала выбери способ оплаты:\n"
        f"{pe('check')}  Баланс общий с сайтом — пополнишь здесь, будет и на сайте.\n\n"
        f"{pe('info')}  <i>Минимум — {MIN_RUB} ₽. Комиссия указана у каждого способа.</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    if isinstance(target, CallbackQuery):
        try: await msg.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception: await msg.answer(text, reply_markup=kb, parse_mode="HTML")
        await target.answer()
    else:
        await msg.answer(text, reply_markup=kb, parse_mode="HTML")


# ── STEP 2 — choose the amount (method already picked) ──
def _amount_kb(method: str) -> InlineKeyboardMarkup:
    rows, line = [], []
    for a in PRESETS:
        line.append(InlineKeyboardButton(text=f"{a} ₽", callback_data=f"topup:amt:{method}:{a}"))
        if len(line) == 3:
            rows.append(line); line = []
    if line:
        rows.append(line)
    rows.append([InlineKeyboardButton(text="Своя сумма", callback_data=f"topup:custom:{method}",
                                      icon_custom_emoji_id=eid("pencil"))])
    rows.append([InlineKeyboardButton(text="◁  Назад к способам", callback_data="topup:start",
                                      icon_custom_emoji_id=eid("home"))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _ask_amount(cb: CallbackQuery, method: str, cfg: dict) -> None:
    meta = _METHODS[method]
    text = (
        f"{meta['label']}  ·  <i>{meta['sub']}</i>\n{RULE}\n\n"
        f"{pe('wallet')}  Комиссия: <b>{_fee_text(method, cfg)}</b>\n"
        f"{pe('info')}  Минимум: <b>{MIN_RUB} ₽</b>\n\n"
        f"{pe('send')}  Теперь выбери или введи сумму:"
    )
    try:
        await cb.message.edit_text(text, reply_markup=_amount_kb(method), parse_mode="HTML")
    except Exception:
        await cb.message.answer(text, reply_markup=_amount_kb(method), parse_mode="HTML")


@router.callback_query(F.data == "topup:start")
async def cb_topup_start(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await _show_methods(cb)


@router.callback_query(F.data.startswith("topup:m:"))
async def cb_topup_method(cb: CallbackQuery, state: FSMContext):
    method = cb.data.split(":")[2]
    if method not in _METHODS:
        await cb.answer("Неизвестный способ", show_alert=True); return
    enabled, cfg = await _enabled_methods()
    if method not in enabled:
        await cb.answer("Этот способ сейчас недоступен", show_alert=True); return
    await state.clear()
    await cb.answer()
    await _ask_amount(cb, method, cfg)


@router.callback_query(F.data.startswith("topup:custom:"))
async def cb_topup_custom(cb: CallbackQuery, state: FSMContext):
    method = cb.data.split(":")[2]
    if method not in _METHODS:
        await cb.answer("Ошибка", show_alert=True); return
    await state.set_state(TopupStates.waiting_amount)
    await state.update_data(method=method)
    await cb.message.edit_text(
        f"{pe('write')}  <b>Введи сумму пополнения в рублях</b>\n{RULE}\n\n"
        f"Например: <code>500</code>.  Минимум — {MIN_RUB} ₽.",
        reply_markup=back_to_menu_kb(), parse_mode="HTML",
    )
    await cb.answer()


@router.message(TopupStates.waiting_amount)
async def msg_topup_amount(msg: Message, state: FSMContext):
    raw = (msg.text or "").strip().replace(" ", "").replace(",", "")
    if not raw.isdigit() or int(raw) < MIN_RUB:
        await msg.answer(f"{pe('cross')}  Введи число от {MIN_RUB}, например <code>500</code>.", parse_mode="HTML")
        return
    data = await state.get_data()
    method = str(data.get("method") or "crypto")
    await state.clear()
    await _go(msg, msg.from_user.id, method, int(raw))


@router.callback_query(F.data.startswith("topup:amt:"))
async def cb_topup_amt(cb: CallbackQuery):
    parts = cb.data.split(":")
    try:
        method, amount = parts[2], int(parts[3])
    except (ValueError, IndexError):
        await cb.answer("Неверная сумма", show_alert=True)
        return
    await cb.answer()
    await _go(cb.message, cb.from_user.id, method, amount)


async def _go(msg: Message, tg_id: int, method: str, amount: int) -> None:
    if method == "stars":
        await _create_stars(msg, tg_id, amount)
    else:
        await _create(msg, tg_id, amount, method)


async def _create_stars(msg: Message, tg_id: int, amount: int) -> None:
    """Stars top-up: create the pending row on the site, then send an XTR invoice
    right here. Crediting happens in handlers/payments.py on successful_payment."""
    await typing(msg)
    try:
        r = await api.topup_create(tg_id, amount, "stars")
    except ApiError as e:
        await msg.answer(f"{pe('cross')}  Не удалось создать счёт: <i>{esc(e)}</i>",
                         reply_markup=back_to_menu_kb(), parse_mode="HTML")
        return
    tid = int(r.get("id") or 0)
    stars = int(r.get("stars") or 0)
    if tid <= 0 or stars <= 0:
        await msg.answer(f"{pe('cross')}  Сервер не вернул счёт. Попробуй ещё раз.",
                         reply_markup=back_to_menu_kb(), parse_mode="HTML")
        return
    from .payments import send_stars_invoice
    await send_stars_invoice(msg.bot, msg.chat.id, tid, stars, amount)


async def _create(msg: Message, tg_id: int, amount: int, method: str) -> None:
    await typing(msg)
    try:
        r = await api.topup_create(tg_id, amount, method)
    except ApiError as e:
        await msg.answer(f"{pe('cross')}  Не удалось создать оплату: <i>{esc(e)}</i>\n\n"
                         f"Можно пополнить на сайте: {SITE_URL}/v2#topup",
                         reply_markup=back_to_menu_kb(), parse_mode="HTML")
        return
    pay_url = r.get("pay_url") or ""
    tid = int(r.get("id") or 0)
    if not pay_url:
        await msg.answer(f"{pe('cross')}  Сервер не вернул ссылку на оплату. Попробуй ещё раз.",
                         reply_markup=back_to_menu_kb(), parse_mode="HTML")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Оплатить {amount} ₽", url=pay_url, icon_custom_emoji_id=eid("money_in"))],
        [InlineKeyboardButton(text="Проверить оплату", callback_data=f"topup:check:{tid}",
                              icon_custom_emoji_id=eid("loading"))],
        [InlineKeyboardButton(text="◁  В меню", callback_data="menu:main", icon_custom_emoji_id=eid("home"))],
    ])
    card = await msg.answer(
        f"{pe('money_in')}  <b>Счёт на {fmt_rub(amount)}</b>\n{RULE}\n\n"
        f"{pe('send')}  Нажми «Оплатить» и заверши оплату.\n"
        f"{pe('loading')}  Как оплатишь — баланс зачислится автоматически.\n\n"
        f"{pe('info')}  <i>Заказ #{tid} · я слежу за оплатой.</i>",
        reply_markup=kb, parse_mode="HTML",
    )
    asyncio.create_task(_poll(card, tg_id, tid, amount, kb))


@router.callback_query(F.data.startswith("topup:check:"))
async def cb_topup_check(cb: CallbackQuery):
    try:
        tid = int(cb.data.split(":")[2])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    try:
        o = await api.topup_status(cb.from_user.id, tid)
    except ApiError as e:
        await cb.answer(f"Ошибка: {e}", show_alert=True); return
    st = str(o.get("status") or "")
    if st == "paid":
        await cb.message.edit_text(_paid_text(tid), reply_markup=back_to_menu_kb(), parse_mode="HTML")
        await cb.answer("Оплачено!")
    elif st in ("failed", "expired", "cancelled"):
        await cb.message.edit_text(f"{pe('cross')}  Оплата не прошла ({esc(st)}). Попробуй заново: «Пополнить».",
                                   reply_markup=back_to_menu_kb(), parse_mode="HTML")
        await cb.answer()
    else:
        await cb.answer("Оплата ещё не поступила — попробуй через минуту", show_alert=True)


def _paid_text(tid: int) -> str:
    return (
        f"{pe('party')}  <b>Баланс пополнен!</b>\n{RULE}\n\n"
        f"{pe('check')}  Платёж #{tid} зачислен.\n"
        f"{pe('money')}  Теперь можно открыть каталог — /shop"
    )


async def _poll(card: Message, tg_id: int, tid: int, amount: int, kb) -> None:
    for _ in range(150):  # ~10 min
        await asyncio.sleep(4)
        try:
            o = await api.topup_status(tg_id, tid)
        except ApiError:
            continue
        st = str(o.get("status") or "")
        if st == "paid":
            try:
                await card.edit_text(_paid_text(tid), reply_markup=back_to_menu_kb(), parse_mode="HTML")
            except Exception:
                pass
            return
        if st in ("failed", "expired", "cancelled"):
            try:
                await card.edit_text(
                    f"{pe('cross')}  Оплата не прошла ({esc(st)}). Попробуй заново: «Пополнить».",
                    reply_markup=back_to_menu_kb(), parse_mode="HTML")
            except Exception:
                pass
            return
