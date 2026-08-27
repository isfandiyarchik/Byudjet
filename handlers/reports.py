from database import get_conn
from datetime import datetime
import calendar
import telebot

MONTHS_RU = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
    5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
    9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
}

MONTHS_KK = {
    1: "январь", 2: "февраль", 3: "март", 4: "апрель",
    5: "май", 6: "июнь", 7: "июль", 8: "август",
    9: "сентябрь", 10: "октябрь", 11: "ноябрь", 12: "декабрь"
}

def register_report_handlers(bot):

    @bot.message_handler(func=lambda m: m.text == "📊 Есап")
    def report_period(message):
        now = datetime.now()
        markup = telebot.types.InlineKeyboardMarkup()

        for month_num in range(1, 13):
            year = now.year
            month_str = f"{year}-{month_num:02d}"
            label = f"📅 {MONTHS_RU[month_num]} {year}"

            if month_num == now.month:
                label = f"📅 {MONTHS_RU[month_num]} {year} ← бул ай"
            elif month_num > now.month:
                label = f"✏️ {MONTHS_RU[month_num]} {year}"

            markup.add(telebot.types.InlineKeyboardButton(
                label,
                callback_data=f"rep_{month_str}"
            ))

        bot.send_message(message.chat.id, "Есап дәўирин таңла:", reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("rep_"))
    def show_report(call):
        date_filter = call.data[4:]  # "2026-08"
        year = int(date_filter.split("-")[0])
        month_num = int(date_filter.split("-")[1])
        now = datetime.now()

        conn = get_conn()
        c = conn.cursor()

        # Кіріс
        c.execute("SELECT COALESCE(SUM(amount),0) FROM budget WHERE created_at LIKE %s",
                  (f"{date_filter}%",))
        total_budget = float(c.fetchone()[0])

        c.execute("SELECT source, COALESCE(SUM(amount),0) FROM budget WHERE created_at LIKE %s GROUP BY source",
                  (f"{date_filter}%",))
        income_by_source = c.fetchall()

        # Кредитлер
        c.execute("SELECT name, amount FROM credits WHERE is_active=1")
        credits = c.fetchall()
        credit_total = sum(float(a) for _, a in credits)

        # Тұрақлы
        c.execute("SELECT name, amount FROM fixed_expenses WHERE is_active=1")
        fixed = c.fetchall()
        fixed_total = sum(float(a) for _, a in fixed)

        # Басқа харажатлар
        c.execute("SELECT category, COALESCE(SUM(amount),0) FROM other_expenses WHERE created_at LIKE %s GROUP BY category",
                  (f"{date_filter}%",))
        other_by_cat = c.fetchall()
        other_total = sum(float(a) for _, a in other_by_cat)

        # Төленген
        c.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE month=%s AND status='paid'",
                  (date_filter,))
        paid_total = float(c.fetchone()[0])

        conn.close()

        family_budget = credit_total + fixed_total + other_total
        remaining = total_budget - paid_total - other_total

        title = f"📊 {MONTHS_RU[month_num]} {year} есабы"
        if month_num > now.month or year > now.year:
            title = f"✏️ {MONTHS_RU[month_num]} {year} — жоспар"

        text = f"{title}\n\n"

        # Кіріс
        if income_by_source:
            text += "📥 <b>Кириc:</b>\n"
            for source, amount in income_by_source:
                text += f"  • {source}: <b>+{float(amount):,.0f} сум</b>\n"
            text += f"  Итого: <b>+{total_budget:,.0f} сум</b>\n\n"

        # Кредитлер
        text += "🔴 <b>Кредитлер:</b>\n"
        for name, amount in credits:
            text += f"  • {name}: <b>{float(amount):,.0f} сум</b>\n"
        text += f"  Итого: <b>-{credit_total:,.0f} сум</b>\n"

        # Тұрақлы
        text += "\n🟡 <b>Тұрақлы харажатлар:</b>\n"
        for name, amount in fixed:
            text += f"  • {name}: <b>{float(amount):,.0f} сум</b>\n"
        text += f"  Итого: <b>-{fixed_total:,.0f} сум</b>\n"

        # Басқа
        if other_by_cat:
            text += "\n🟢 <b>Басқа харажатлар:</b>\n"
            for cat, amt in other_by_cat:
                text += f"  • {cat}: <b>-{float(amt):,.0f} сум</b>\n"
            text += f"  Итого: <b>-{other_total:,.0f} сум</b>\n"

        text += f"\n💼 Семьяда айланған бюджет: <b>{family_budget:,.0f} сум</b>\n"
        text += f"✅ Төленген: <b>-{paid_total:,.0f} сум</b>\n"
        text += f"\n──────────────────\n"
        text += f"💰 Қолда бар: <b>{remaining:,.0f} сум</b>"

        bot.send_message(call.message.chat.id, text, parse_mode='HTML')
