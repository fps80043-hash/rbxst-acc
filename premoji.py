"""Premium (custom) Telegram emoji helpers.

Bots can render custom/premium emoji inside MESSAGE TEXT via the HTML tag
    <tg-emoji emoji-id="ID">🙂</tg-emoji>
(parse_mode=HTML). The inner unicode emoji is the graceful fallback shown to
clients that can't display the custom one.

NOTE: Telegram's Bot API does NOT support custom-emoji icons on inline / reply
keyboard buttons (no `icon_custom_emoji_id` field), so buttons keep plain
unicode emoji — that's a platform limitation, not a styling choice.
"""
from __future__ import annotations

# id → (fallback_unicode)
_PE = {
    "settings":   ("5870982283724328568", "⚙️"),
    "profile":    ("5870994129244131212", "👤"),
    "people":     ("5870772616305839506", "👥"),
    "user_ok":    ("5891207662678317861", "👤"),
    "user_no":    ("5893192487324880883", "👤"),
    "file":       ("5870528606328852614", "📁"),
    "smile":      ("5870764288364252592", "🙂"),
    "growth":     ("5870930636742595124", "📈"),
    "stats":      ("5870921681735781843", "📊"),
    "home":       ("5873147866364514353", "🏠"),
    "lock":       ("6037249452824072506", "🔒"),
    "unlock":     ("6037496202990194718", "🔓"),
    "megaphone":  ("6039422865189638057", "📣"),
    "check":      ("5870633910337015697", "✅"),
    "cross":      ("5870657884844462243", "❌"),
    "pencil":     ("5870676941614354370", "🖋"),
    "trash":      ("5870875489362513438", "🗑"),
    "down":       ("5893057118545646106", "🔽"),
    "clip":       ("6039451237743595514", "📎"),
    "link":       ("5769289093221454192", "🔗"),
    "info":       ("6028435952299413210", "ℹ️"),
    "bot":        ("6030400221232501136", "🤖"),
    "eye":        ("6037397706505195857", "👁"),
    "hidden":     ("6037243349675544634", "👁"),
    "send":       ("5963103826075456248", "⬆️"),
    "download":   ("6039802767931871481", "⬇️"),
    "bell":       ("6039486778597970865", "🔔"),
    "gift":       ("6032644646587338669", "🎁"),
    "clock":      ("5983150113483134607", "⏰"),
    "party":      ("6041731551845159060", "🎉"),
    "font":       ("5870801517140775623", "🔤"),
    "write":      ("5870753782874246579", "✍️"),
    "media":      ("6035128606563241721", "🖼"),
    "pin":        ("6042011682497106307", "📍"),
    "wallet":     ("5769126056262898415", "👛"),
    "box":        ("5884479287171485878", "📦"),
    "cryptobot":  ("5260752406890711732", "👾"),
    "calendar":   ("5890937706803894250", "📅"),
    "tag":        ("5886285355279193209", "🏷"),
    "timeover":   ("5775896410780079073", "🕓"),
    "apps":       ("5778672437122045013", "📦"),
    "brush":      ("6050679691004612757", "🖌"),
    "addtext":    ("5771851822897566479", "🔡"),
    "resize":     ("5778479949572738874", "↔️"),
    "money":      ("5904462880941545555", "🪙"),
    "money_out":  ("5890848474563352982", "🪙"),
    "money_in":   ("5879814368572478751", "🏧"),
    "code":       ("5940433880585605708", "🔨"),
    "loading":    ("5345906554510012647", "🔄"),
}


def pe(name: str, fallback: str = "") -> str:
    """Return a <tg-emoji> tag for use inside HTML message text.
    Unknown name → the given fallback (or empty)."""
    item = _PE.get(name)
    if not item:
        return fallback
    emoji_id, uni = item
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback or uni}</tg-emoji>'


def eid(name: str) -> str | None:
    """Return the bare custom-emoji id for use as a keyboard button icon
    (InlineKeyboardButton/KeyboardButton.icon_custom_emoji_id, Bot API 9.4+)."""
    item = _PE.get(name)
    return item[0] if item else None
