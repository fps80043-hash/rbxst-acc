"""/start, /help, /menu and main-menu inline routing."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from api import ApiError, api
from config import ADMIN_TG_IDS, BOT_NAME, BOT_TAGLINE
from keyboards import link_prompt_kb, main_menu_kb
from utils import esc, fmt_relative, fmt_rub, is_premium_active, typing
from premoji import pe

router = Router(name="start")
log = logging.getLogger(__name__)

_RULE = "━━━━━━━━━━━━━━━━━━━━━━"

WELCOME_LINKED_TEMPLATE = (
    pe("money") + "  <b>{bot}</b>\n"
    "<i>{tagline}</i>\n"
    "{rule}\n\n"
    + pe("smile") + "  Привет, <b>{username}</b>!\n\n"
    + pe("wallet") + "  Баланс:  <b>{balance}</b>\n"
    + pe("tag") + "  ID:  <code>#{uid}</code>"
    "{premium_line}"
    "\n\n"
    "{rule}\n"
    "Выбери, что делать " + pe("down")
)

WELCOME_NEW = (
    pe("box") + "  <b>{bot}</b>\n"
    "<i>{tagline}</i>\n"
    + _RULE + "\n\n"
    + pe("party") + "  <b>Добро пожаловать!</b>\n\n"
    "Чтобы покупать через бота, нужно <b>привязать аккаунт сайта</b> — "
    "это обязательно и занимает 30 секунд:\n\n"
    "<b>1.</b>  Зайди на сайт и войди / зарегистрируйся\n"
    "<b>2.</b>  Профиль → <b>Безопасность</b> → блок Telegram-бот\n"
    "<b>3.</b>  Нажми «Получить код привязки»\n"
    "<b>4.</b>  Пришли мне:  <code>/link 123456</code>\n\n"
    + pe("info") + "  <i>Аккаунта нет? Регистрация на сайте бесплатная.</i>"
)

HELP_TEXT = (
    pe("info") + "  <b>Команды бота</b>\n"
    + _RULE + "\n\n"
    + pe("box") + "  <b>Магазин</b>\n"
    "/shop — каталог товаров\n"
    "/orders — мои покупки\n\n"
    + pe("wallet") + "  <b>Баланс</b>\n"
    "/balance — баланс\n"
    "Пополнение — кнопка «Пополнить» в меню\n\n"
    + pe("profile") + "  <b>Аккаунт</b>\n"
    "/profile — профиль\n\n"
    + pe("link") + "  <b>Привязка</b>\n"
    "/link &lt;код&gt; — привязать аккаунт\n"
    "/unlink — отвязать\n\n"
    + pe("home") + "  <b>Прочее</b>\n"
    "/menu — главное меню\n"
    "/help — эта справка\n\n"
    "<i>Вопросы — поддержка на сайте.</i>"
)


def _badges(profile: dict) -> str:
    out = []
    if profile.get("is_admin"):
        out.append(f"{pe('check')} ADMIN")
    if is_premium_active(profile.get("premium_until")):
        out.append(f"{pe('gift')} PREMIUM")
    return "  ".join(out)


@router.message(CommandStart(deep_link=True))
async def start_with_deeplink(msg: Message, command):
    """Handle /start <payload> — used for deep-link account binding via ?start=link_<code>."""
    payload = (command.args or "").strip() if command and command.args else ""
    if payload.startswith("link_"):
        code = payload[5:].strip()
        if code:
            from .link import perform_link
            await perform_link(msg, code)
            return
    if payload.startswith("stars_"):
        # Came from the site "Pay with Telegram Stars" button — send the XTR invoice.
        try:
            tid = int(payload[len("stars_"):])
        except ValueError:
            tid = 0
        if tid > 0:
            from .payments import send_stars_invoice
            try:
                info = await api.stars_info(tid)
            except ApiError as e:
                await msg.answer(f"⚠️ Не удалось открыть оплату звёздами: <i>{esc(e)}</i>", parse_mode="HTML")
                return
            if str(info.get("status") or "") == "paid":
                await msg.answer(f"{pe('check')} Этот счёт уже оплачен — баланс пополнен.", parse_mode="HTML")
                return
            await send_stars_invoice(msg.bot, msg.chat.id, tid,
                                     int(info.get("stars") or 0), int(info.get("rub") or 0))
            return
    await cmd_start(msg)


@router.message(CommandStart())
@router.message(Command("menu"))
async def cmd_start(msg: Message):
    tg_id = msg.from_user.id
    await typing(msg)
    try:
        link = await api.get_link(tg_id)
    except ApiError as e:
        log.warning("get_link failed: %s", e)
        link = None

    if not link:
        await msg.answer(
            WELCOME_NEW.format(bot=BOT_NAME, tagline=BOT_TAGLINE),
            reply_markup=link_prompt_kb(),
            parse_mode="HTML",
        )
        return

    try:
        profile = await api.get_profile(tg_id)
    except ApiError as e:
        await msg.answer(
            f"⚠️ Не удалось загрузить твой профиль: <i>{esc(e)}</i>\n"
            f"Попробуй ещё раз через минуту или открой сайт.",
            parse_mode="HTML",
        )
        return

    text = _format_main_menu(profile)
    is_admin = bool(profile.get("is_admin")) or tg_id in ADMIN_TG_IDS
    await msg.answer(
        text,
        reply_markup=main_menu_kb(is_admin=is_admin, balance=profile.get("balance")),
        parse_mode="HTML",
    )


def _format_main_menu(profile: dict) -> str:
    badges = _badges(profile)
    is_prem = is_premium_active(profile.get("premium_until"))
    premium_line = ""
    if is_prem:
        from utils import parse_iso
        until = parse_iso(profile.get("premium_until"))
        if until:
            premium_line = f"\n{pe('gift')}  Premium до:  <b>{until.strftime('%d.%m.%Y')}</b>"
    rule = "━━━━━━━━━━━━━━━━━━━━━━"
    return WELCOME_LINKED_TEMPLATE.format(
        bot=BOT_NAME,
        tagline=BOT_TAGLINE,
        rule=rule,
        username=esc(profile.get("username") or "друг"),
        badges=badges or "",
        balance=fmt_rub(profile.get("balance") or 0),
        uid=int(profile.get("id") or 0),
        premium_line=premium_line,
    )


@router.message(Command("help"))
async def cmd_help(msg: Message):
    await msg.answer(HELP_TEXT, parse_mode="HTML")


@router.callback_query(F.data == "menu:main")
async def cb_main_menu(cb: CallbackQuery):
    """Re-render main menu in place."""
    tg_id = cb.from_user.id
    try:
        link = await api.get_link(tg_id)
    except ApiError:
        link = None

    if not link:
        try:
            await cb.message.edit_text(
                WELCOME_NEW.format(bot=BOT_NAME, tagline=BOT_TAGLINE),
                reply_markup=link_prompt_kb(),
                parse_mode="HTML",
            )
        except Exception:
            await cb.message.answer(
                WELCOME_NEW.format(bot=BOT_NAME, tagline=BOT_TAGLINE),
                reply_markup=link_prompt_kb(),
                parse_mode="HTML",
            )
        await cb.answer()
        return

    try:
        profile = await api.get_profile(tg_id)
    except ApiError as e:
        await cb.answer(f"Ошибка: {e}", show_alert=True)
        return

    is_admin = bool(profile.get("is_admin")) or tg_id in ADMIN_TG_IDS
    text = _format_main_menu(profile)
    try:
        await cb.message.edit_text(
            text,
            reply_markup=main_menu_kb(is_admin=is_admin, balance=profile.get("balance")),
            parse_mode="HTML",
        )
    except Exception:
        await cb.message.answer(
            text,
            reply_markup=main_menu_kb(is_admin=is_admin, balance=profile.get("balance")),
            parse_mode="HTML",
        )
    await cb.answer()


@router.callback_query(F.data == "help:show")
async def cb_help(cb: CallbackQuery):
    from keyboards import back_to_menu_kb
    try:
        await cb.message.edit_text(HELP_TEXT, reply_markup=back_to_menu_kb(), parse_mode="HTML")
    except Exception:
        await cb.message.answer(HELP_TEXT, reply_markup=back_to_menu_kb(), parse_mode="HTML")
    await cb.answer()
