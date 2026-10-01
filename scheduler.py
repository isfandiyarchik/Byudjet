import telebot
from apscheduler.schedulers.background import BackgroundScheduler
from pytz import timezone
from database import get_conn, get_credits_for_month, get_fixed_for_month
from datetime import datetime, timedelta
from backup import generate_backup
from summary import get_month_stats, format_month_text

UZ_TZ = timezone("Asia/Tashkent")

def start_scheduler(bot, admin_ids):
    scheduler = BackgroundScheduler(timezone=UZ_TZ)
    scheduler.add_job(check_credit_reminders, 'cron', hour=9, minute=0,
                      args=[bot, admin_ids])
    scheduler.add_job(monthly_payment_reminder, 'cron', day=1, hour=9, minute=0,
                      args=[bot, admin_ids])
    scheduler.add_job(morning_summary, 'cron', hour=8, minute=30,
                      args=[bot])
    scheduler.add_job(daily_backup, 'cron', hour=3, minute=0,
                      args=[bot, admin_ids])
    scheduler.start()
    print("✅ Scheduler иске қосылды! (Asia/Tashkent)")

def daily_backup(bot, admin_ids):
    print(f"📦 Күнделикли backup таярланып атыр... {datetime.now(UZ_TZ)}")
    for admin_id in admin_ids:
        try:
            buf = generate_backup()
            bot.send_document(admin_id, buf, caption="📦 Автоматлық күнделикли backup")
            print(f"✅ Backup жиберилди: {admin_id}")
        except Exception as e:
            print(f"❌ Backup жиберилмеди {admin_id}: {e}")

def morning_summary(bot):
    print(f"🌅 Азанда хабарлама жиберилди... {datetime.now(UZ_TZ)}")
    today = datetime.now(UZ_TZ).replace(tzinfo=None)
    month = today.strftime("%Y-%m")

    conn = get_conn()
    c = conn.cursor()
    stats = get_month_stats(month, conn, today)
    c.execute("SELECT telegram_id FROM users")
    users = c.fetchall()
    conn.close()

    text = "🌅 <b>Қайырлы таң!</b>\n\n" + format_month_text(stats, today)

    for (telegram_id,) in users:
        try:
            bot.send_message(telegram_id, text, parse_mode='HTML')
            print(f"✅ Азанда хабар жиберилди: {telegram_id}")
        except Exception as e:
            print(f"❌ Қате: {e}")

def check_credit_reminders(bot, admin_ids):
    print(f"🔍 Кредит тексерилип атыр... {datetime.now(UZ_TZ)}")
    conn = get_conn()
    c = conn.cursor()
    today = datetime.now(UZ_TZ)
    remind_dt = today + timedelta(days=2)
    remind_date = remind_dt.day
    remind_month = remind_dt.strftime("%Y-%m")

    credits = get_credits_for_month(remind_month, conn=conn)
    c.execute("SELECT ref_id FROM payments WHERE month=%s AND status='paid' AND type='credit'", (remind_month,))
    paid_ids = {row[0] for row in c.fetchall()}
    conn.close()

    reminders = [(n, a, p) for cid, n, a, p in credits if p == remind_date and cid not in paid_ids]

    print(f"📅 Бүгин: {today.day}, 2 күннен соң: {remind_date}")
    print(f"📋 Ескертиулер: {reminders}")

    if reminders:
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT telegram_id FROM users")
        users = c.fetchall()
        conn.close()

        months_kk = {
            1: "январь", 2: "февраль", 3: "март", 4: "апрель",
            5: "май", 6: "июнь", 7: "июль", 8: "август",
            9: "сентябрь", 10: "октябрь", 11: "ноябрь", 12: "декабрь"
        }

        def get_remind_month(pay_day):
            if pay_day >= today.day:
                return months_kk[today.month]
            else:
                next_month = today.month + 1 if today.month < 12 else 1
                return months_kk[next_month]

        text = "🔔 <b>2 күннен кейин төлем!</b>\n\n"
        for name, amount, pay_day in reminders:
            text += f"• {name}: <b>{float(amount):,.0f} сум</b>\n"
            text += f"  Төлем күни: {pay_day}-{get_remind_month(pay_day)}\n\n"

        for (telegram_id,) in users:
            try:
                bot.send_message(telegram_id, text, parse_mode='HTML')
                print(f"✅ Хабар жиберилди: {telegram_id}")
            except Exception as e:
                print(f"❌ Қате: {e}")

def monthly_payment_reminder(bot, admin_ids):
    print(f"📅 Ай басы ескертиуи... {datetime.now(UZ_TZ)}")
    conn = get_conn()
    c = conn.cursor()

    month = datetime.now(UZ_TZ).strftime("%Y-%m")

    # Override ескеретін функциялар
    credits = get_credits_for_month(month)
    fixed = get_fixed_for_month(month)

    c.execute("SELECT telegram_id FROM users")
    users = c.fetchall()

    c.execute("SELECT ref_id FROM payments WHERE month=%s AND status='paid' AND type='credit'", (month,))
    paid_credit_ids = {row[0] for row in c.fetchall()}
    c.execute("SELECT ref_id FROM payments WHERE month=%s AND status='paid' AND type='fixed'", (month,))
    paid_fixed_ids = {row[0] for row in c.fetchall()}
    conn.close()

    markup = telebot.types.InlineKeyboardMarkup()
    text = "📅 <b>Таза ай басланды!</b>\nТөлемлерди раслаң:\n\n"

    for cid, name, amount, pay_day in credits:
        text += f"💳 {name}: <b>{float(amount):,.0f} сум</b>\n"
        if cid not in paid_credit_ids:
            markup.add(telebot.types.InlineKeyboardButton(
                f"✅ {name} төледим",
                callback_data=f"pc_{cid}"
            ))

    for fid, name, amount, pay_day in fixed:
        text += f"🏠 {name}: <b>{float(amount):,.0f} сум</b>\n"
        if fid not in paid_fixed_ids:
            markup.add(telebot.types.InlineKeyboardButton(
                f"✅ {name} төледим",
                callback_data=f"pf_{fid}"
            ))

    for (telegram_id,) in users:
        try:
            bot.send_message(telegram_id, text, reply_markup=markup, parse_mode='HTML')
            print(f"✅ Ай басы хабары жиберилди: {telegram_id}")
        except Exception as e:
            print(f"❌ Қате: {e}")
