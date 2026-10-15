"""
Кириў бақлаўы: тек ADMIN_IDS ҳәм ALLOWED_IDS дағы адамлар ботты қоллана алады.
Бөтен адам /start басса — оған «рухсат жоқ» ҳәм өз ID си көрсетиледи,
админге «бейтаныс адам кирмекши» деп хабар барады (ҳәр адам ушын 24 саатта бир рет).
"""
import time
from common import is_allowed, ADMIN_IDS, extract_sender

_denied_reply_at = {}
_admin_notified_at = {}

REPLY_EVERY = 3600       # бөтен адамға 1 саатта бир рет жуўап
NOTIFY_EVERY = 86400     # админге 24 саатта бир рет


def gate(bot, update_dict):
    """True — update ти ислеўге болады. False — тоқтатылады."""
    sender = extract_sender(update_dict)
    if sender is None:
        return False
    uid = sender["id"]
    if is_allowed(uid):
        return True

    now = time.time()
    try:
        cq = update_dict.get("callback_query")
        if isinstance(cq, dict) and cq.get("id"):
            try:
                bot.answer_callback_query(cq["id"], "⛔ Рухсат жоқ")
            except Exception:
                pass

        if now - _denied_reply_at.get(uid, 0) > REPLY_EVERY:
            _denied_reply_at[uid] = now
            bot.send_message(
                uid,
                "⛔ Бул бот жеке пайдаланыў ушын, сизге рухсат жоқ.\n\n"
                f"Сизиң Telegram ID ңиз: {uid}\n"
                "Рухсат алыў ушын усы ID ни бот ийесине жибериң.")

        if now - _admin_notified_at.get(uid, 0) > NOTIFY_EVERY:
            _admin_notified_at[uid] = now
            uname = f"@{sender['username']}" if sender["username"] else "—"
            for admin_id in ADMIN_IDS:
                try:
                    bot.send_message(
                        admin_id,
                        "🔔 Бейтаныс адам ботқа кирмекши болды (кириўге рухсат берилмеди)\n"
                        f"Аты: {sender['name'] or '—'}\n"
                        f"Username: {uname}\n"
                        f"ID: {uid}\n\n"
                        "Рухсат бериў керек болса, Render → Environment де ALLOWED_IDS ке "
                        "усы ID ни қосың (бир неше адам болса, үтир менен бөлиң).")
                except Exception as e:
                    print(f"❌ Админге хабар жиберилмеди {admin_id}: {e}")
    except Exception as e:
        print(f"❌ access.gate қәтеси: {e}")
    return False
