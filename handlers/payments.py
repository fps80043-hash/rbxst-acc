"""Telegram Stars (XTR) payments.

Flow:
  • Site: user picks "Stars" → site creates a pending topup → returns a deep-link
    t.me/<bot>?start=stars_<id>. Opening it lands in start.py, which calls
    send_stars_invoice() below.
  • Bot: user picks "Stars" in the topup menu → topup.py creates the topup via the
    site API and calls send_stars_invoice() directly.

Both end here: pre_checkout is approved, and on successful_payment we ask the
site to credit the balance (idempotent). Stars can only be charged inside
Telegram, so all XTR logic lives in the bot.
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    LabeledPrice, Message, PreCheckoutQuery,
)

from api import ApiError, api
from config import ADMIN_TG_IDS
from keyboards import back_to_menu_kb
from premoji import pe
from utils import esc

router = Router(name="payments")
log = logging.getLogger(__name__)

RULE = "━━━━━━━━━━━━━━━━━━━━━━"


async def send_stars_invoice(bot, chat_id: int, tid: int, stars: int, rub: int) -> None:
    """Send a Telegram Stars (XTR) invoice for a pending top-up."""
    stars = max(1, int(stars))
    await bot.send_invoice(
        chat_id=chat_id,
        title=f"Пополнение баланса на {rub} ₽",
        description=f"После оплaты {stars} ⭐ на твой баланс RBX ST зачислится {rub} ₽.",
        payload=f"stars_{tid}",
        currency="XTR",
        prices=[LabeledPrice(label=f"{rub} ₽ на баланс", amount=stars)],
        # No provider_token for Stars.
    )


@router.pre_checkout_query()
async def on_pre_checkout(pcq: PreCheckoutQuery):
    """Approve every Stars pre-checkout — the amount was fixed when we created it."""
    try:
        await pcq.answer(ok=True)
    except Exception as e:
        log.warning("pre_checkout answer failed: %s", e)


@router.message(F.successful_payment)
async def on_successful_payment(msg: Message):
    sp = msg.successful_payment
    payload = (sp.invoice_payload or "").strip()
    log.info("[STARS] successful_payment: payload=%r amount=%s charge=%s",
             payload, sp.total_amount, sp.telegram_payment_charge_id)
    if not payload.startswith("stars_"):
        return
    try:
        tid = int(payload[len("stars_"):])
    except ValueError:
        return
    charge = sp.telegram_payment_charge_id or ""
    try:
        r = await api.stars_confirm(tid, charge)
        log.info("[STARS] stars_confirm topup=%s -> %s", tid, r)
    except ApiError as e:
        log.warning("[STARS] stars_confirm FAILED topup=%s: %s", tid, e)
        # Payment went through but crediting failed — tell the user, keep the
        # charge id so support can credit/refund manually.
        await msg.answer(
            f"{pe('warn', '⚠️')}  Оплата прошла ({sp.total_amount} ⭐), но зачисление не удалось: <i>{esc(e)}</i>\n"
            f"Напиши в поддержку, код платежа: <code>{esc(charge)}</code>",
            reply_markup=back_to_menu_kb(), parse_mode="HTML",
        )
        return
    rub = 0
    try:
        info = await api.stars_info(tid)
        rub = int(info.get("rub") or 0)
    except ApiError:
        pass
    await msg.answer(
        f"{pe('party')}  <b>Баланс пополнен!</b>\n{RULE}\n\n"
        f"{pe('check')}  Платёж #{tid} · {sp.total_amount} ⭐\n"
        + (f"{pe('money')}  Зачислено: <b>{rub} ₽</b>\n" if rub else "")
        + f"\n{pe('smile')}  Спасибо! Теперь можно открыть каталог — /shop",
        reply_markup=back_to_menu_kb(), parse_mode="HTML",
    )


@router.message(Command("recover_stars"))
async def cmd_recover_stars(msg: Message):
    """Reconcile paid-but-uncredited Stars top-ups. If a successful_payment was
    missed (bot redeploy/downtime), Telegram doesn't resend it — so we read the
    bot's star transactions and re-credit each `stars_<id>` payload via the site
    (idempotent). Admin-gated; falls back to open if ADMIN_TG_IDS is unset."""
    if ADMIN_TG_IDS and msg.from_user.id not in ADMIN_TG_IDS:
        return
    try:
        tx = await msg.bot.get_star_transactions(limit=100)
    except Exception as e:
        await msg.answer(f"{pe('cross')}  Не удалось прочитать транзакции: <i>{esc(str(e))}</i>",
                         parse_mode="HTML")
        return
    seen, credited, already = 0, [], 0
    for t in (getattr(tx, "transactions", []) or []):
        src = getattr(t, "source", None)  # incoming payment partner
        payload = getattr(src, "invoice_payload", None) if src else None
        if not payload or not str(payload).startswith("stars_"):
            continue
        seen += 1
        try:
            tid = int(str(payload)[len("stars_"):])
        except ValueError:
            continue
        try:
            r = await api.stars_confirm(tid, getattr(t, "id", "") or "")
            if r.get("credited"):
                credited.append(tid)
            else:
                already += 1
        except ApiError as e:
            log.warning("[STARS] recover topup=%s failed: %s", tid, e)
    lines = [
        f"{pe('money')}  <b>Восстановление звёздных пополнений</b>",
        RULE, "",
        f"Найдено платежей: <b>{seen}</b>",
        f"{pe('check')}  Зачислено сейчас: <b>{len(credited)}</b>" + (f"  (#{', #'.join(map(str, credited))})" if credited else ""),
        f"{pe('info')}  Уже было зачислено: <b>{already}</b>",
    ]
    await msg.answer("\n".join(lines), reply_markup=back_to_menu_kb(), parse_mode="HTML")
