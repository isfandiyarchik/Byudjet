import telebot
from apscheduler.schedulers.background import BackgroundScheduler
from pytz import timezone
from database import get_conn
from datetime import datetime, timedelta

UZ_TZ = timezone("Asia/Tashkent")

def start_scheduler(bot, admin_id):
    scheduler = BackgroundScheduler(timezone=UZ_TZ)
    scheduler.add_job(check_credit_reminders, 'cron', hour=9, minute=0,
                      args=[bot, admin_id])
    scheduler.add_job(monthly_payment_reminder, 'cron', day=1, hour=9, minute=0,
                      args=[bot, admin_id])
    scheduler.add_job(morning_summary, 'cron', hour=8, minute=0,
                      args=[bot])
    scheduler.start()
    print("✅ Scheduler иске қосылды! (Asia/Tashkent)")

def morning_summary(bot):
    print(f"🌅 Таңертең хабарлама жиберилди... {datetime.now(UZ_TZ)}")
    conn = get_conn()
    c = conn.cursor()

    month = datetime.now(UZ_TZ).strftime("%Y-%m")

    c.execute("SELECT COALESCE(SUM(amount),0) FROM budget")
    month_budget = float(c.fetchone()[0])

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
    planned_total = credit_total + fixed_total
    remaining = month_budget - paid_total - other

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

    text += "🔴 <b>Кредитлер:</b>\n"
    for cid, name, amount, pay_day in credits:
        amount = float(amount)
        if cid in paid_credit_ids:
            text += f"  • {name}: <b>{amount:,.0f} сум</b> ✅\n"
        else:
            text += f"  • {name}: <b>{amount:,.0f} сум</b> ({pay_day}-{get_payment_month(pay_day)})\n"

    text += "\n🟡 <b>Тұрақлы харажатлар:</b>\n"
    for fid, name, amount, pay_day in fixed:
        amount = float(amount)
        if fid in paid_fixed_ids:
            text += f"  • {name}: <b>{amount:,.0f} сум</b> ✅\n"
        else:
            text += f"  • {name}: <b>{amount:,.0f} сум</b> ({pay_day}-{get_payment_month(pay_day)})\n"

    if other_by_cat:
        text += "\n🟢 <b>Басқа харажатлар:</b>\n"
        for cat, amt in other_by_cat:
            text += f"  • {cat}: <b>{float(amt):,.0f} сум</b>\n"

    text += f"\n📊 Ойласылған: <b>-{planned_total:,.0f} сум</b>\n"
    text += f"✅ Төленген: <b>-{paid_total:,.0f} сум</b>\n"
    text += f"\n──────────────────\n"
    text += f"💰 Қолда бар: <b>{remaining:,.0f} сум</b>\n"

    after_planned = month_budget - planned_total - other
    if after_planned >= 0:
        text += f"📉 Барлығын төлесе қалады: <b>{after_planned:,.0f} сум</b>\n"
    else:
        text += f"⚠️ Барлығын төлеуге жетиспейди: <b>{after_planned:,.0f} сум</b>\n"

    text += f"\n💼 Семьяда айланған бюджет: <b>{month_budget:,.0f} сум</b>"

    for (telegram_id,) in users:
        try:
            bot.send_message(telegram_id, text, parse_mode='HTML')
            print(f"✅ Таңертең хабар жиберилди: {telegram_id}")
        except Exception as e:
            print(f"❌ Қате: {e}")

def check_credit_reminders(bot, admin_id):
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
        cur_month = months_kk[today.month]

        text = "🔔 <b>2 күннен соң төлем!</b>\n\n"
        for name, amount, pay_day in reminders:
            text += f"• {name}: <b>{float(amount):,.0f} сум</b>\n"
            text += f"  Төлем күни: {pay_day}-{cur_month}\n\n"

        for (telegram_id,) in users:
            try:
                bot.send_message(telegram_id, text, parse_mode='HTML')
                print(f"✅ Хабар жиберилди: {telegram_id}")
            except Exception as e:
                print(f"❌ Қате: {e}")

def monthly_payment_reminder(bot, admin_id):
    print(f"📅 Ай басы ескертиуи... {datetime.now(UZ_TZ)}")
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, name, amount FROM credits WHERE is_active=1")
    credits = c.fetchall()
    c.execute("SELECT id, name, amount FROM fixed_expenses WHERE is_active=1")
    fixed = c.fetchall()
    c.execute("SELECT telegram_id FROM users")
    users = c.fetchall()
    conn.close()

    markup = telebot.types.InlineKeyboardMarkup()
    text = "📅 <b>Таза ай басланды!</b>\nТөлемлерди раслаң:\n\n"

    for cid, name, amount in credits:
        text += f"💳 {name}: <b>{float(amount):,.0f} сум</b>\n"
        markup.add(telebot.types.InlineKeyboardButton(
            f"✅ {name} төледим",
            callback_data=f"pc_{cid}"
        ))

    for fid, name, amount in fixed:
        text += f"🏠 {name}: <b>{float(amount):,.0f} сум</b>\n"
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
