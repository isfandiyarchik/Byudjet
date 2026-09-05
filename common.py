import os


def _load_admin_ids():
    """
    Support both:
    - ADMIN_IDS=123456,789012   (recommended, multiple admins)
    - ADMIN_ID=123456           (old single-admin var, still works)
    """
    ids = set()
    raw_multi = os.getenv("ADMIN_IDS")
    if raw_multi:
        for part in raw_multi.split(","):
            part = part.strip()
            if part:
                ids.add(int(part))
    raw_single = os.getenv("ADMIN_ID")
    if raw_single:
        ids.add(int(raw_single))
    return ids


ADMIN_IDS = _load_admin_ids()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


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

