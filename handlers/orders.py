"""Show the user's recent shop purchases (accounts / digital goods)."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from api import ApiError, api
from keyboards import link_prompt_kb, orders_kb
from premoji import pe
from utils import esc, fmt_relative, fmt_rub, status_label

router = Router(name="orders")
log = logging.getLogger(__name__)

RULE = "━━━━━━━━━━━━━━━━━━━━━━"


async def _ensure_linked(target: Message | CallbackQuery) -> bool:
    tg_id = target.from_user.id
    try:
        link = await api.get_link(tg_id)
    except ApiError:
        link = None
    if not link:
        msg = target if isinstance(target, Message) else target.message
        await msg.answer(
            "🔗  Привяжи аккаунт сайта чтобы видеть свои покупки.\n\n"
            "Получи код на сайте → Профиль → Безопасность, затем пришли <code>/link 123456</code>.",
            reply_markup=link_prompt_kb(), parse_mode="HTML",
        )
        if isinstance(target, CallbackQuery):
            await target.answer()
        return False
    return True


def _format_orders(items: list) -> str:
    if not items:
        return (
            f"{pe('box')}  <b>Мои покупки</b>\n"
            f"{RULE}\n\n"
            f"{pe('info')}  Пока нет покупок.\n\n"
            "Открой каталог в меню — купишь прямо здесь."
        )
    total = len(items)
    spent = sum(int(float(o.get("price_rub") or 0)) for o in items)
    lines = [
        f"{pe('box')}  <b>Мои покупки</b>",
        RULE, "",
        f"{pe('stats')}  Всего: <b>{total}</b>  ·  Потрачено: <b>{fmt_rub(spent)}</b>",
        "", RULE, "",
    ]
    for o in items[:10]:
        oid = int(o.get("id") or 0)
        title = esc(str(o.get("product_title") or o.get("product_id") or "Товар"))
        rub = int(float(o.get("price_rub") or 0))
        st = status_label(str(o.get("status") or "done"))
        when = fmt_relative(o.get("created_at"))
        lines.append(f"<b>#{oid}</b>  ·  {title}")
        lines.append(f"   {fmt_rub(rub)}  ·  {st}  ·  <i>{esc(when)}</i>")
        dt = (o.get("delivery_text") or "").strip()
        if dt:
            short = dt if len(dt) <= 80 else dt[:80] + "…"
            lines.append(f"   <tg-spoiler><code>{esc(short)}</code></tg-spoiler>")
        lines.append("")
    if len(items) > 10:
        lines.append(f"<i>… и ещё {len(items) - 10}. Полный список — на сайте.</i>")
    return "\n".join(lines)


async def _render(target: Message | CallbackQuery) -> None:
    msg = target if isinstance(target, Message) else target.message
    tg_id = target.from_user.id
    try:
        data = await api.shop_orders(tg_id, limit=20)
        items = data.get("orders") or data.get("items") or []
        text = _format_orders(items)
    except ApiError as e:
        text = f"⚠️ Не удалось загрузить покупки: <i>{esc(e)}</i>"
    kb = orders_kb()
    if isinstance(target, CallbackQuery):
        try:
            await msg.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await msg.answer(text, reply_markup=kb, parse_mode="HTML")
        await target.answer()
    else:
        await msg.answer(text, reply_markup=kb, parse_mode="HTML")


@router.message(Command("orders"))
async def cmd_orders(msg: Message):
    if not await _ensure_linked(msg):
        return
    await _render(msg)


@router.callback_query(F.data == "orders:list")
async def cb_orders_list(cb: CallbackQuery):
    if not await _ensure_linked(cb):
        return
    await _render(cb)
