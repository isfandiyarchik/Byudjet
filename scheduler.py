import telebot
from apscheduler.schedulers.background import BackgroundScheduler
from pytz import timezone
from database import get_conn
from datetime import datetime, timedelta
from backup import generate_backup

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
            buf = generate_backup()  # regenerate per-recipient (BytesIO cursor safety)
            bot.send_document(admin_id, buf, caption="📦 Автоматлық күнделикли backup")
            print(f"✅ Backup жиберилди: {admin_id}")
        except Exception as e:
            print(f"❌ Backup жиберилмеди {admin_id}: {e}")

def morning_summary(bot):
    print(f"🌅 Таңертең хабарлама жиберилди... {datetime.now(UZ_TZ)}")
    conn = get_conn()
    c = conn.cursor()

    month = datetime.now(UZ_TZ).strftime("%Y-%m")

    c.execute("SELECT COALESCE(SUM(amount),0) FROM budget WHERE created_at LIKE %s",
              (f"{month}%",))
    total_income = float(c.fetchone()[0])

    c.execute("SELECT id, name, amount, pay_day FROM credits WHERE is_active=1")
    credits = c.fetchall()

    c.execute("SELECT id, name, amount, pay_day FROM fixed_expenses WHERE is_active=1")
    fixed = c.fetchall()

    c.execute("SELECT COALESCE(SUM(amount),0) FROM other_expenses WHERE created_at LIKE %s",
              (f"{month}%",))
    other = float(c.fetchone()[0])

    c.execute("SELECT category, COALESCE(SUM(amount),0) FROM other_expenses WHERE created_at LIKE %s GROUP BY category",
              (f"{month}%",))
    other_by_cat = c.fetchall()

    c.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE month=%s AND status='paid'",
              (month,))
    paid_total = float(c.fetchone()[0])

    c.execute("SELECT ref_id FROM payments WHERE month=%s AND status='paid' AND type='credit'",
              (month,))
    paid_credit_ids = [row[0] for row in c.fetchall()]

    c.execute("SELECT ref_id FROM payments WHERE month=%s AND status='paid' AND type='fixed'",
              (month,))
    paid_fixed_ids = [row[0] for row in c.fetchall()]

    c.execute("SELECT telegram_id FROM users")
    users = c.fetchall()
    conn.close()

    credit_total = sum(float(a) for _, _, a, _ in credits)
    fixed_total = sum(float(a) for _, _, a, _ in fixed)
    family_budget = credit_total + fixed_total + other
    remaining = total_income - paid_total - other

    months_kk = {
        1: "январь", 2: "февраль", 3: "март", 4: "апрель",
        5: "май", 6: "июнь", 7: "июль", 8: "август",
        9: "сентябрь", 10: "октябрь", 11: "ноябрь", 12: "декабрь"
    }
    today = datetime.now(UZ_TZ)

    def get_payment_month(pay_day):
        if pay_day >= today.day:
            return months_kk[today.month]
        else:
            next_month = today.month + 1 if today.month < 12 else 1
            return months_kk[next_month]

    text = "🌅 <b>Қайырлы таң!</b>\n\n"
    text += f"💼 Семьяда айланған бюджет: <b>{family_budget:,.0f} сум</b>\n\n"

    text += "🔴 <b>Кредитлер:</b>\n"
    for cid, name, amount, pay_day in credits:
        amount = float(amount)
        if cid in paid_credit_ids:
            text += f"  • {name}: <b>{amount:,.0f} сум</b> ✅\n"
        else:
            text += f"  • {name}: <b>{amount:,.0f} сум</b> ({pay_day}-{get_payment_month(pay_day)})\n"
    text += f"  Итого: <b>-{credit_total:,.0f} сум</b>\n"

    text += "\n🟡 <b>Тұрақлы харажатлар:</b>\n"
    for fid, name, amount, pay_day in fixed:
        amount = float(amount)
        if fid in paid_fixed_ids:
            text += f"  • {name}: <b>{amount:,.0f} сум</b> ✅\n"
        else:
            text += f"  • {name}: <b>{amount:,.0f} сум</b> ({pay_day}-{get_payment_month(pay_day)})\n"
    text += f"  Итого: <b>-{fixed_total:,.0f} сум</b>\n"

    if other_by_cat:
        text += "\n🟢 <b>Басқа харажатлар:</b>\n"
        for cat, amt in other_by_cat:
            text += f"  • {cat}: <b>{float(amt):,.0f} сум</b>\n"
        text += f"  Итого: <b>-{other:,.0f} сум</b>\n"

    text += f"\n──────────────────\n"
    text += f"💰 Қолда бар: <b>{remaining:,.0f} сум</b>"

    for (telegram_id,) in users:
        try:
            bot.send_message(telegram_id, text, parse_mode='HTML')
            print(f"✅ Таңертең хабар жиберилди: {telegram_id}")
        except Exception as e:
            print(f"❌ Қате: {e}")

def check_credit_reminders(bot, admin_ids):
    print(f"🔍 Кредит тексерилип атыр... {datetime.now(UZ_TZ)}")
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT name, amount, pay_day FROM credits WHERE is_active=1")
    credits = c.fetchall()
    conn.close()

    today = datetime.now(UZ_TZ)
    remind_date = (today + timedelta(days=2)).day
    reminders = [(n, a, p) for n, a, p in credits if p == remind_date]

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
    c.execute("SELECT id, name, amount FROM credits WHERE is_active=1")
    credits = c.fetchall()
    c.execute("SELECT id, name, amount FROM fixed_expenses WHERE is_active=1")
    fixed = c.fetchall()
    c.execute("SELECT telegram_id FROM users")
    users = c.fetchall()

    month = datetime.now(UZ_TZ).strftime("%Y-%m")
    c.execute("SELECT ref_id FROM payments WHERE month=%s AND status='paid' AND type='credit'", (month,))
    paid_credit_ids = {row[0] for row in c.fetchall()}
    c.execute("SELECT ref_id FROM payments WHERE month=%s AND status='paid' AND type='fixed'", (month,))
    paid_fixed_ids = {row[0] for row in c.fetchall()}
    conn.close()

    markup = telebot.types.InlineKeyboardMarkup()
    text = "📅 <b>Таза ай басланды!</b>\nТөлемлерди раслаң:\n\n"

    for cid, name, amount in credits:
        text += f"💳 {name}: <b>{float(amount):,.0f} сум</b>\n"
        if cid not in paid_credit_ids:
            markup.add(telebot.types.InlineKeyboardButton(
                f"✅ {name} төледим",
                callback_data=f"pc_{cid}"
            ))

    for fid, name, amount in fixed:
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
