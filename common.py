import os
from datetime import datetime
from pytz import timezone

# ---------------------------------------------------------------------------
# Уакыт: сервер (Render) UTC де ислейди, ал сиз Тошкент уакты (UTC+5) бойынша
# жасайсыз. Барлық жерде datetime.now() дың орнына uz_now() қолланылады,
# сонда ай алмасыўы 1-числода 00:00 де дәл болады.
# ---------------------------------------------------------------------------
UZ_TZ = timezone("Asia/Tashkent")


def uz_now():
    """Тошкент уакты (tzinfo сыз). Дерекқорға жазылатуғын created_at усыдан алынады."""
    return datetime.now(UZ_TZ).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Рухсат: ADMIN_IDS (админлер) + ALLOWED_IDS (қосымша рухсат берилген адамлар)
#   ADMIN_IDS=123456,789012     — админлер
#   ALLOWED_IDS=555555,666666   — ботты қолланатуғын, бирақ админ емес адамлар
#   ADMIN_ID=123456             — ески жалғыз админ өзгериўшиси (еле ислейди)
# ---------------------------------------------------------------------------
def _parse_ids(*raws):
    ids = set()
    for raw in raws:
        if not raw:
            continue
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                ids.add(int(part))
            except ValueError:
                print(f"⚠️ ID дурыс емес, өткизип жиберилди: {part!r}")
    return ids


ADMIN_IDS = _parse_ids(os.getenv("ADMIN_IDS"), os.getenv("ADMIN_ID"))
ALLOWED_IDS = _parse_ids(os.getenv("ALLOWED_IDS"))


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def is_allowed(user_id: int) -> bool:
    """Ботты қолланыўға рухсаты бар ма (админ ямаса ALLOWED_IDS)."""
    return user_id in ADMIN_IDS or user_id in ALLOWED_IDS


def allowed_ids():
    return ADMIN_IDS | ALLOWED_IDS


_SENDER_KEYS = ("message", "edited_message", "callback_query", "inline_query",
                "chosen_inline_result", "shipping_query", "pre_checkout_query")


def extract_sender(update_dict):
    """
    Telegram update (dict) ишинен жибериўшини табады: {"id", "name", "username"}.
    Табылмаса None (бундай update лар өзгермейди).
    """
    if not isinstance(update_dict, dict):
        return None
    for key in _SENDER_KEYS:
        obj = update_dict.get(key)
        if isinstance(obj, dict) and isinstance(obj.get("from"), dict):
            u = obj["from"]
            if isinstance(u.get("id"), int):
                return {"id": u["id"],
                        "name": u.get("first_name", ""),
                        "username": u.get("username", "")}
    return None


# Menu buttons / commands that should ALWAYS cancel whatever multi-step
# input flow (register_next_step_handler) is currently in progress,
# instead of being swallowed and misread as an amount/name/etc.
CANCEL_TRIGGERS = {
    "🏠 Баслапқы бет",
    "➕ Бюджет қосыў",
    "➕ Харажат қосыў",
    "📊 Есап",
    "⚙️ Өзгертиў",
    "/cancel",
    "/start",
    "❌ Бийкар етиў",
}


def is_cancel(text) -> bool:
    if not text:
        return False
    return text.strip() in CANCEL_TRIGGERS


def with_cancel(bot, func):
    """
    Wrap a register_next_step_handler callback so that if the user taps
    a main-menu button (or /cancel) instead of answering, the flow stops
    cleanly instead of throwing a parsing error.

    Usage:
        bot.register_next_step_handler(msg, with_cancel(bot, my_next_step), arg1, arg2)
    """
    def wrapper(message, *args, **kwargs):
        if is_cancel(message.text):
            bot.send_message(message.chat.id, "❌ Бийкар етилди.")
            # Re-dispatch the menu button the user actually pressed
            bot.process_new_messages([message])
            return
        return func(message, *args, **kwargs)
    return wrapper
