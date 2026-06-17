"""Admin commands — restricted by both ADMIN_TG_IDS env var and is_admin from site profile."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from api import ApiError, api
from config import ADMIN_TG_IDS, SITE_URL
from keyboards import admin_menu_kb, back_to_menu_kb
from premoji import eid, pe
from utils import bar, esc, fmt_relative, fmt_rub, is_premium_active, status_label, typing

router = Router(name="admin")
log = logging.getLogger(__name__)


class AdminStates(StatesGroup):
    finding_user = State()


async def _is_admin(tg_id: int) -> bool:
    if tg_id in ADMIN_TG_IDS:
        return True
    try:
        profile = await api.get_profile(tg_id)
    except ApiError:
        return False
    return bool(profile.get("is_admin"))


async def _deny(target: Message | CallbackQuery) -> None:
    msg = target if isinstance(target, Message) else target.message
    if isinstance(target, CallbackQuery):
        await target.answer("⛔ Нет доступа", show_alert=True)
    else:
        await msg.answer("⛔ Эта команда только для администраторов.")


def _admin_intro() -> str:
    return (
        f"{pe('settings')} <b>Админ-панель</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{pe('stats')} <b>Свежие заказы</b> — последние заказы\n"
        f"{pe('people')} <b>Найти юзера</b> — по нику, email или ID\n"
        f"{pe('money')} <b>Звёзды бота</b> — баланс Telegram Stars\n\n"
        f"{pe('info')} <i>Каталог, склад, баны, выплаты — на сайте.</i>"
    )


def _user_card(u: dict) -> str:
    """Detailed user card (premium-emoji formatted)."""
    uid = int(u.get("id") or 0)
    username = esc(u.get("username") or "—")
    email = esc(u.get("email") or "—")
    balance = int(u.get("balance") or 0)
    is_admin = bool(u.get("is_admin"))
    prem = is_premium_active(u.get("premium_until"))
    badges = []
    if is_admin:
        badges.append(f"{pe('check')} ADMIN")
    if prem:
        badges.append(f"{pe('gift')} PREMIUM")
    badge_line = ("  ".join(badges) + "\n") if badges else ""
    lines = [
        f"{pe('profile')} <b>{username}</b>   <code>#{uid}</code>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        badge_line.rstrip("\n") if badge_line else "",
        f"{pe('clip')} Email: <code>{email}</code>",
        f"{pe('money')} Баланс: <b>{fmt_rub(balance)}</b>",
    ]
    created = u.get("created_at")
    if created:
        lines.append(f"{pe('calendar')} Регистрация: {esc(fmt_relative(created))}")
    tg = u.get("telegram_id") or u.get("tg_id")
    if tg:
        lines.append(f"{pe('bot')} Telegram: <code>{esc(tg)}</code>")
    return "\n".join([l for l in lines if l != ""])


def _user_card_kb(uid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Открыть на сайте", url=f"{SITE_URL}/v2", icon_custom_emoji_id=eid("link"))],
        [
            InlineKeyboardButton(text="Новый поиск", callback_data="admin:find_user", icon_custom_emoji_id=eid("people")),
            InlineKeyboardButton(text="◁ Админка", callback_data="admin:menu", icon_custom_emoji_id=eid("settings")),
        ],
    ])


@router.message(Command("admin"))
async def cmd_admin(msg: Message):
    if not await _is_admin(msg.from_user.id):
        await _deny(msg)
        return
    await msg.answer(_admin_intro(), reply_markup=admin_menu_kb(), parse_mode="HTML")


async def _stars_report(bot) -> str:
    """Build the bot's Telegram Stars (XTR) balance + last transactions report."""
    try:
        bal = await bot.get_my_star_balance()
        amount = int(getattr(bal, "amount", 0) or 0)
    except Exception as e:
        return (f"{pe('cross')}  Не удалось получить баланс звёзд: <i>{esc(str(e))}</i>\n"
                f"<i>Нужен aiogram ≥ 3.16 / Bot API 9.0.</i>")
    lines = [
        f"{pe('money')}  <b>Звёздный баланс бота</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"{pe('check')}  Сейчас на боте:  <b>{amount} ⭐</b>",
    ]
    try:
        tx = await bot.get_star_transactions(limit=10)
        items = list(getattr(tx, "transactions", []) or [])
        if items:
            lines.append("")
            lines.append(f"{pe('stats')}  <b>Последние операции:</b>")
            for t in items[:10]:
                amt = int(getattr(t, "amount", 0) or 0)
                src = getattr(t, "source", None)
                rcv = getattr(t, "receiver", None)
                sign = "+" if src is not None else ("−" if rcv is not None else "•")
                lines.append(f"  {sign}{amt} ⭐  <code>{esc(str(getattr(t,'id','') )[:10])}</code>")
    except Exception:
        pass
    lines.append("")
    lines.append(f"{pe('info')}  <i>Вывод — через Fragment (fragment.com), с удержанием Telegram ~21 день.</i>")
    return "\n".join(lines)


@router.message(Command("stars"))
async def cmd_stars(msg: Message):
    """Show the BOT's Telegram Stars (XTR) balance + last transactions.
    Stars paid for top-ups accumulate here (owned by the bot owner)."""
    if not await _is_admin(msg.from_user.id):
        await _deny(msg)
        return
    await typing(msg)
    await msg.answer(await _stars_report(msg.bot), reply_markup=back_to_menu_kb(), parse_mode="HTML")


@router.callback_query(F.data == "admin:stars")
async def cb_admin_stars(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id):
        await _deny(cb)
        return
    text = await _stars_report(cb.message.bot)
    try:
        await cb.message.edit_text(text, reply_markup=back_to_menu_kb(), parse_mode="HTML")
    except Exception:
        await cb.message.answer(text, reply_markup=back_to_menu_kb(), parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data == "admin:menu")
async def cb_admin_menu(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin(cb.from_user.id):
        await _deny(cb)
        return
    await state.clear()
    try:
        await cb.message.edit_text(_admin_intro(), reply_markup=admin_menu_kb(), parse_mode="HTML")
    except Exception:
        await cb.message.answer(_admin_intro(), reply_markup=admin_menu_kb(), parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data == "admin:orders")
async def cb_admin_orders(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id):
        await _deny(cb)
        return
    try:
        data = await api.admin_orders_recent(cb.from_user.id, limit=15)
    except ApiError as e:
        await cb.answer(f"Ошибка: {e}", show_alert=True)
        return
    items = data.get("orders") or data.get("items") or []
    if not items:
        text = f"{pe('stats')} <b>Последние заказы</b>\n\n<i>Заказов пока нет.</i>"
    else:
        lines = [f"{pe('stats')} <b>Последние Robux-заказы</b>", "━━━━━━━━━━━━━━━━━━━━━━", ""]
        for o in items[:15]:
            oid = int(o.get("id") or 0)
            user = esc(o.get("username") or f"#{o.get('user_id') or '?'}")
            amount = int(o.get("robux_amount") or 0)
            rub = int(o.get("rub_price") or 0)
            st = status_label(str(o.get("status") or ""))
            when = fmt_relative(o.get("created_at"))
            lines.append(
                f"#{oid}  ·  <b>{user}</b>\n"
                f"   {amount:,} R$".replace(",", " ") + f"  ·  {fmt_rub(rub)}  ·  {st}\n"
                f"   <i>{esc(when)}</i>"
            )
            lines.append("")
        text = "\n".join(lines)
    try:
        await cb.message.edit_text(text, reply_markup=admin_menu_kb(), parse_mode="HTML")
    except Exception:
        await cb.message.answer(text, reply_markup=admin_menu_kb(), parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data == "admin:find_user")
async def cb_admin_find_user(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin(cb.from_user.id):
        await _deny(cb)
        return
    await state.set_state(AdminStates.finding_user)
    text = (
        f"{pe('people')} <b>Поиск пользователя</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{pe('write')} Отправь одним сообщением:\n"
        "• ник  •  email  •  ID  (#123 или 123)\n\n"
        f"{pe('info')} <i>Отмена — /menu или кнопка ниже.</i>"
    )
    try:
        await cb.message.edit_text(text, reply_markup=back_to_menu_kb(), parse_mode="HTML")
    except Exception:
        await cb.message.answer(text, reply_markup=back_to_menu_kb(), parse_mode="HTML")
    await cb.answer()


@router.message(AdminStates.finding_user)
async def msg_admin_find_user(msg: Message, state: FSMContext):
    if not await _is_admin(msg.from_user.id):
        await state.clear()
        await _deny(msg)
        return
    query = (msg.text or "").strip().lstrip("#")
    if not query:
        await msg.answer("Пустой запрос, попробуй ещё раз.")
        return
    await state.clear()
    await typing(msg)
    try:
        data = await api.admin_users_find(msg.from_user.id, query)
    except ApiError as e:
        await msg.answer(f"{pe('cross')} Ошибка: <i>{esc(e)}</i>", parse_mode="HTML")
        return
    users = data.get("users") or data.get("items") or []
    if not users:
        await msg.answer(
            f"{pe('people')} По запросу <b>{esc(query)}</b> ничего не найдено.\n"
            f"<i>Проверь написание или попробуй email/ID.</i>",
            reply_markup=back_to_menu_kb(), parse_mode="HTML",
        )
        return

    # Single exact hit → straight to the detailed card.
    if len(users) == 1:
        u = users[0]
        await msg.answer(_user_card(u), reply_markup=_user_card_kb(int(u.get("id") or 0)), parse_mode="HTML")
        return

    # Multiple → compact list + a button per user that opens the full card.
    lines = [f"{pe('people')} <b>Найдено: {len(users)}</b>", "━━━━━━━━━━━━━━━━━━━━━━", ""]
    rows = []
    for u in users[:8]:
        uid = int(u.get("id") or 0)
        username = esc(u.get("username") or "—")
        balance = int(u.get("balance") or 0)
        adm = f"  {pe('check')}" if u.get("is_admin") else ""
        lines.append(f"<code>#{uid}</code>  <b>{username}</b>{adm}  ·  {fmt_rub(balance)}")
        rows.append([InlineKeyboardButton(
            text=f"{u.get('username') or ('#'+str(uid))}", callback_data=f"admin:u:{uid}",
            icon_custom_emoji_id=eid("profile"))])
    if len(users) > 8:
        lines.append("")
        lines.append(f"<i>… ещё {len(users) - 8}. Уточни запрос.</i>")
    rows.append([InlineKeyboardButton(text="◁ Админка", callback_data="admin:menu", icon_custom_emoji_id=eid("settings"))])
    await msg.answer("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")


@router.callback_query(F.data.startswith("admin:u:"))
async def cb_admin_user_detail(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id):
        await _deny(cb)
        return
    try:
        uid = int(cb.data.split(":")[2])
    except (ValueError, IndexError):
        await cb.answer("Неверный ID", show_alert=True)
        return
    await typing(cb)
    try:
        data = await api.admin_users_find(cb.from_user.id, str(uid))
    except ApiError as e:
        await cb.answer(f"Ошибка: {e}", show_alert=True)
        return
    users = data.get("users") or data.get("items") or []
    u = next((x for x in users if int(x.get("id") or 0) == uid), users[0] if users else None)
    if not u:
        await cb.answer("Пользователь не найден", show_alert=True)
        return
    try:
        await cb.message.edit_text(_user_card(u), reply_markup=_user_card_kb(uid), parse_mode="HTML")
    except Exception:
        await cb.message.answer(_user_card(u), reply_markup=_user_card_kb(uid), parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data == "admin:robux_settings")
async def cb_admin_robux_settings(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id):
        await _deny(cb)
        return
    try:
        # Re-use public stock endpoint — admin one has more, but stock is enough for a glance
        stock = await api.robux_stock()
    except ApiError as e:
        await cb.answer(f"Ошибка: {e}", show_alert=True)
        return
    avail = int(stock.get("available") or stock.get("stock") or 0)
    rate = stock.get("rate")
    rate_str = ""
    if rate:
        try:
            rate_str = f"{float(rate):.4f} ₽/R$"
        except (TypeError, ValueError):
            rate_str = str(rate)
    text = (
        f"{pe('money')} <b>Robux — настройки</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{pe('box')} <b>В наличии:</b> {avail:,} R$\n".replace(",", " ")
        + (f"{pe('stats')} <b>Курс:</b> {rate_str}\n" if rate_str else "")
        + f"\n{pe('info')} <i>Изменить — в админ-панели на сайте.</i>"
    )
    try:
        await cb.message.edit_text(text, reply_markup=admin_menu_kb(), parse_mode="HTML")
    except Exception:
        await cb.message.answer(text, reply_markup=admin_menu_kb(), parse_mode="HTML")
    await cb.answer()
