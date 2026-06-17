"""Profile, balance & unlink-confirm flow."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from api import ApiError, api
from keyboards import confirm_unlink_kb, link_prompt_kb, profile_kb
from premoji import pe
from utils import esc, fmt_rub, is_premium_active, parse_iso

router = Router(name="profile")
log = logging.getLogger(__name__)

RULE = "━━━━━━━━━━━━━━━━━━━━━━"


def _profile_text(profile: dict, link: dict | None) -> str:
    username = profile.get("username") or "—"
    balance = int(profile.get("balance") or 0)
    email = profile.get("email") or ""
    prem = is_premium_active(profile.get("premium_until"))

    lines = [
        f"{pe('profile')}  <b>{esc(username)}</b>",
        RULE,
        "",
        f"{pe('wallet')}  <b>Баланс</b>",
        f"        {fmt_rub(balance)}",
        "",
        f"{pe('tag')}  <b>ID на сайте</b>",
        f"        <code>#{int(profile.get('id') or 0)}</code>",
    ]

    if email:
        lines += ["", f"{pe('clip')}  <b>Email</b>", f"        <code>{esc(email)}</code>"]

    if prem:
        until = parse_iso(profile.get("premium_until"))
        if until:
            lines += ["", f"{pe('gift')}  <b>Premium до</b>", f"        {until.strftime('%d.%m.%Y')}"]

    if link:
        tg_un = link.get("telegram_username")
        linked_at = link.get("created_at")
        lines += ["", f"{pe('bot')}  <b>Telegram</b>"]
        if tg_un:
            lines.append(f"        @{esc(tg_un)}")
        if linked_at:
            from utils import fmt_relative
            lines.append(f"        привязан {fmt_relative(linked_at)}")

    return "\n".join(lines)


async def _show_profile(target: Message | CallbackQuery) -> None:
    msg = target if isinstance(target, Message) else target.message
    tg_id = target.from_user.id

    try:
        link = await api.get_link(tg_id)
    except ApiError as e:
        await msg.answer(f"⚠️ Ошибка: <i>{esc(e)}</i>", parse_mode="HTML")
        return

    if not link:
        text = (
            f"{pe('profile')}  <b>Профиль</b>\n"
            f"{RULE}\n\n"
            "У тебя ещё нет привязанного аккаунта сайта.\n\n"
            "Нажми «Привязать аккаунт» чтобы видеть здесь баланс, "
            "историю покупок и покупать товары."
        )
        if isinstance(target, CallbackQuery):
            try:
                await msg.edit_text(text, reply_markup=profile_kb(False), parse_mode="HTML")
            except Exception:
                await msg.answer(text, reply_markup=profile_kb(False), parse_mode="HTML")
        else:
            await msg.answer(text, reply_markup=profile_kb(False), parse_mode="HTML")
        return

    try:
        profile = await api.get_profile(tg_id)
    except ApiError as e:
        await msg.answer(f"⚠️ Не удалось загрузить профиль: <i>{esc(e)}</i>", parse_mode="HTML")
        return

    text = _profile_text(profile, link)
    if isinstance(target, CallbackQuery):
        try:
            await msg.edit_text(text, reply_markup=profile_kb(True), parse_mode="HTML")
        except Exception:
            await msg.answer(text, reply_markup=profile_kb(True), parse_mode="HTML")
    else:
        await msg.answer(text, reply_markup=profile_kb(True), parse_mode="HTML")


@router.message(Command("profile"))
async def cmd_profile(msg: Message):
    await _show_profile(msg)


@router.message(Command("balance"))
async def cmd_balance(msg: Message):
    tg_id = msg.from_user.id
    try:
        link = await api.get_link(tg_id)
    except ApiError as e:
        await msg.answer(f"⚠️ Ошибка: {esc(e)}", parse_mode="HTML")
        return
    if not link:
        await msg.answer(
            "Сначала привяжи аккаунт сайта: <code>/link &lt;код&gt;</code>",
            parse_mode="HTML", reply_markup=link_prompt_kb(),
        )
        return
    try:
        balance = await api.get_balance(tg_id)
    except ApiError as e:
        await msg.answer(f"⚠️ Ошибка: {esc(e)}", parse_mode="HTML")
        return
    await msg.answer(
        f"{pe('wallet')}  <b>Твой баланс</b>\n"
        f"{RULE}\n\n"
        f"        <b>{fmt_rub(balance)}</b>",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "profile:show")
async def cb_profile(cb: CallbackQuery):
    await _show_profile(cb)
    await cb.answer()


@router.callback_query(F.data == "profile:balance")
async def cb_balance(cb: CallbackQuery):
    tg_id = cb.from_user.id
    try:
        balance = await api.get_balance(tg_id)
    except ApiError as e:
        await cb.answer(f"Ошибка: {e}", show_alert=True)
        return
    # NOTE: callback alerts are PLAIN TEXT — no HTML/tg-emoji here, or the raw
    # <tg-emoji…> tag shows up literally. Use a plain unicode emoji.
    await cb.answer(f"💰  Баланс: {fmt_rub(balance)}", show_alert=True)


@router.callback_query(F.data == "profile:unlink")
async def cb_unlink_ask(cb: CallbackQuery):
    text = (
        f"{pe('unlock')}  <b>Отвязать аккаунт?</b>\n"
        f"{RULE}\n\n"
        "После отвязки бот перестанет показывать твой баланс и заказы.\n\n"
        "Данные на сайте сохранятся — это просто разрыв связи Telegram ↔ сайт.\n\n"
        "Чтобы привязать снова — получи новый код на сайте."
    )
    try:
        await cb.message.edit_text(text, reply_markup=confirm_unlink_kb(), parse_mode="HTML")
    except Exception:
        await cb.message.answer(text, reply_markup=confirm_unlink_kb(), parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data == "profile:unlink:yes")
async def cb_unlink_yes(cb: CallbackQuery):
    tg_id = cb.from_user.id
    try:
        await api.unlink(tg_id)
    except ApiError as e:
        await cb.answer(f"Ошибка: {e}", show_alert=True)
        return
    await cb.message.edit_text(
        f"{pe('check')}  <b>Аккаунт отвязан</b>\n\n"
        "Если захочешь привязать снова — получи код на сайте и пришли <code>/link 123456</code>.",
        reply_markup=link_prompt_kb(), parse_mode="HTML",
    )
    await cb.answer("Отвязано")
