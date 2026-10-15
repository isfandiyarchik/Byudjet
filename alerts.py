"""
Ботта қәте шықса админге автомат хабар жибереди.
- Бирдей қәте 10 минутта бир рет ғана жиберилеме (спам болмаўы ушын).
- Хабар жибериў өзи қәте берсе, бот қулап кетпейди.
"""
import time
import traceback
from common import uz_now

THROTTLE_SECONDS = 600
_last_sent = {}


def _key(exc):
    tb = traceback.extract_tb(exc.__traceback__)
    where = f"{tb[-1].filename}:{tb[-1].lineno}" if tb else ""
    return f"{type(exc).__name__}|{where}|{str(exc)[:80]}"


def notify_admins(bot, admin_ids, title, exc):
    try:
        key = _key(exc)
        now = time.time()
        if now - _last_sent.get(key, 0) < THROTTLE_SECONDS:
            return
        _last_sent[key] = now

        tb_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        text = (f"⚠️ Ботта қәте\n"
                f"📍 {title}\n"
                f"🕒 {uz_now().strftime('%Y-%m-%d %H:%M:%S')} (Тошкент waqtı)\n\n"
                f"{type(exc).__name__}: {str(exc)[:300]}\n\n"
                f"{tb_text[-2500:]}")
        text = text[:4000]
        for admin_id in admin_ids:
            try:
                bot.send_message(admin_id, text)  # parse_mode жоқ — белгилер бузбайды
            except Exception as send_err:
                print(f"❌ Админге қәте хабары жиберилмеди {admin_id}: {send_err}")
    except Exception as e:
        print(f"❌ alerts ишинде қәте: {e}")


class AdminExceptionHandler:
    """telebot ушын: handler ишинде шыққан барлық қәтелер усы жерге келеди."""

    def __init__(self, admin_ids):
        self.admin_ids = admin_ids
        self.bot = None  # bot дүзилгеннен кейин қойылады

    def handle(self, exception):
        print(f"❌ Handler қәтеси: {exception!r}")
        traceback.print_exception(type(exception), exception, exception.__traceback__)
        if self.bot is not None:
            notify_admins(self.bot, self.admin_ids, "Бот handler", exception)
        return True  # қәте дурысланды, бот ислей береди
