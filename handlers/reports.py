from database import get_conn
from datetime import datetime
import calendar
import telebot

MONTHS_RU = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
    5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
    9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
}

def register_report_handlers(bot):

    @bot.message_handler(func=lambda m: m.text == "📊 Есап")
    def report_period(message):
        now = datetime.now()
        markup = telebot.types.InlineKeyboardMarkup()

        for month_num in range(1, 13):
            year = now.year
            month_str = f"{year}-{month_num:02d}"

            if month_num < now.month:
                label = f"📅 {MONTHS_RU[month_num]} {year}"
            elif month_num == now.month:
                label = f"📅 {MONTHS_RU[month_num]} {year} ← бул ай"
            else:
                label = f"✏️ {MONTHS_RU[month_num]} {year} — план"

            markup.add(telebot.types.InlineKeyboardButton(
                label, callback_data=f"rep_{month_str}"
            ))

        bot.send_message(message.chat.id, "Есап дәўирин таңла:", reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("rep_") and len(call.data) == 11)
    def show_report(call):
        date_filter = call.data[4:]
        year = int(date_filter.split("-")[0])
        month_num = int(date_filter.split("-")[1])
        now = datetime.now()
        is_future = (year > now.year) or (year == now.year and month_num > now.month)

        conn = get_conn()
        c = conn.cursor()

        c.execute("SELECT COALESCE(SUM(amount),0) FROM budget WHERE created_at LIKE %s",
                  (f"{date_filter}%",))
        total_budget = float(c.fetchone()[0])

        c.execute("SELECT source, COALESCE(SUM(amount),0) FROM budget WHERE created_at LIKE %s GROUP BY source",
                  (f"{date_filter}%",))
        income_by_source = c.fetchall()

        c.execute("SELECT id, name, amount FROM credits WHERE is_active=1")
        credits = c.fetchall()
        credit_total = sum(float(a) for _, _, a in credits)

        c.execute("SELECT id, name, amount FROM fixed_expenses WHERE is_active=1")
        fixed = c.fetchall()
        fixed_total = sum(float(a) for _, _, a in fixed)

        c.execute("SELECT category, COALESCE(SUM(amount),0) FROM other_expenses WHERE created_at LIKE %s GROUP BY category",
                  (f"{date_filter}%",))
        other_by_cat = c.fetchall()
        other_total = sum(float(a) for _, a in other_by_cat)

        c.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE month=%s AND status='paid'",
                  (date_filter,))
        paid_total = float(c.fetchone()[0])

        conn.close()

        family_budget = credit_total + fixed_total + other_total
        remaining = total_budget - paid_total - other_total

        if is_future:
            title = f"✏️ {MONTHS_RU[month_num]} {year} — план"
        else:
            title = f"📊 {MONTHS_RU[month_num]} {year} итого"

        text = f"{title}\n\n"

        if income_by_source:
            text += "📥 <b>Кириc:</b>\n"
            for source, amount in income_by_source:
                text += f"  • {source}: <b>+{float(amount):,.0f} сум</b>\n"
            text += f"  Итого: <b>+{total_budget:,.0f} сум</b>\n\n"

        text += "🔴 <b>Кредитлер:</b>\n"
        for cid, name, amount in credits:
            text += f"  • {name}: <b>{float(amount):,.0f} сум</b>\n"
        text += f"  Итого: <b>-{credit_total:,.0f} сум</b>\n"

        text += "\n🟡 <b>Тұрақлы харажатлар:</b>\n"
        for fid, name, amount in fixed:
            text += f"  • {name}: <b>{float(amount):,.0f} сум</b>\n"
        text += f"  Итого: <b>-{fixed_total:,.0f} сум</b>\n"

        if other_by_cat:
            text += "\n🟢 <b>Басқа харажатлар:</b>\n"
            for cat, amt in other_by_cat:
                text += f"  • {cat}: <b>-{float(amt):,.0f} сум</b>\n"
            text += f"  Итого: <b>-{other_total:,.0f} сум</b>\n"

        text += f"\n💼 Семьяда айланған бюджет: <b>{family_budget:,.0f} сум</b>\n"
        text += f"✅ Төленген: <b>-{paid_total:,.0f} сум</b>\n"
        text += f"\n──────────────────\n"
        text += f"💰 Қолда бар: <b>{remaining:,.0f} сум</b>"

        # Келесі ай болса өзгертиў батырмалары
        if is_future:
            markup = telebot.types.InlineKeyboardMarkup()
            for cid, name, amount in credits:
                markup.add(telebot.types.InlineKeyboardButton(
                    f"✏️ {name}: {float(amount):,.0f} сум",
                    callback_data=f"fec_{cid}_{date_filter}"
                ))
            markup.add(telebot.types.InlineKeyboardButton(
                "➕ Таза кредит қосыў",
                callback_data=f"fac_{date_filter}"
            ))
            for fid, name, amount in fixed:
                markup.add(telebot.types.InlineKeyboardButton(
                    f"✏️ {name}: {float(amount):,.0f} сум",
                    callback_data=f"fef_{fid}_{date_filter}"
                ))
            markup.add(telebot.types.InlineKeyboardButton(
                "➕ Таза тұрақлы қосыў",
                callback_data=f"faf_{date_filter}"
            ))
            markup.add(telebot.types.InlineKeyboardButton(
                "➕ Басқа харажат қосыў",
                callback_data=f"fao_{date_filter}"
            ))
            bot.send_message(call.message.chat.id, text, reply_markup=markup, parse_mode='HTML')
        else:
            bot.send_message(call.message.chat.id, text, parse_mode='HTML')

    # ✏️ Кредит өзгертиў (келесі ай)
    @bot.callback_query_handler(func=lambda call: call.data.startswith("fec_"))
    def future_edit_credit(call):
        parts = call.data.split("_")
        cid = int(parts[1])
        date_filter = f"{parts[2]}_{parts[3]}" if len(parts) == 4 else parts[2]
        msg = bot.send_message(call.message.chat.id, "Жаңа сумма жаз (сум):\nМысалы: 450000")
        bot.register_next_step_handler(msg, future_save_credit_amount, cid, date_filter)

    def future_save_credit_amount(message, cid, date_filter):
        try:
            amount = float(message.text.replace(",", "").replace(" ", ""))
            msg = bot.send_message(message.chat.id, "Төлем күнин жаз (1-31):\nМысалы: 15")
            bot.register_next_step_handler(msg, future_save_credit_day, cid, amount, date_filter)
        except ValueError:
            bot.send_message(message.chat.id, "❌ Қате! Тек сан жазың.")

    def future_save_credit_day(message, cid, amount, date_filter):
        try:
            day = int(message.text.strip())
            if not 1 <= day <= 31:
                raise ValueError
            conn = get_conn()
            c = conn.cursor()
            c.execute("UPDATE credits SET amount=%s, pay_day=%s WHERE id=%s",
                      (amount, day, cid))
            conn.commit()
            conn.close()
            bot.send_message(message.chat.id,
                             f"✅ Жаңартылды!\n"
                             f"• Сумма: <b>{amount:,.0f} сум</b>\n"
                             f"• Төлем күни: {day}-күн",
                             parse_mode='HTML')
        except ValueError:
            bot.send_message(message.chat.id, "❌ Қате! 1-31 арасында жазың.")

    # ✏️ Тұрақлы өзгертиў (келесі ай)
    @bot.callback_query_handler(func=lambda call: call.data.startswith("fef_"))
    def future_edit_fixed(call):
        parts = call.data.split("_")
        fid = int(parts[1])
        date_filter = f"{parts[2]}_{parts[3]}" if len(parts) == 4 else parts[2]
        msg = bot.send_message(call.message.chat.id, "Жаңа сумма жаз (сум):\nМысалы: 300000")
        bot.register_next_step_handler(msg, future_save_fixed_amount, fid, date_filter)

    def future_save_fixed_amount(message, fid, date_filter):
        try:
            amount = float(message.text.replace(",", "").replace(" ", ""))
            msg = bot.send_message(message.chat.id, "Төлем күнин жаз (1-31):\nМысалы: 23")
            bot.register_next_step_handler(msg, future_save_fixed_day, fid, amount, date_filter)
        except ValueError:
            bot.send_message(message.chat.id, "❌ Қате! Тек сан жазың.")

    def future_save_fixed_day(message, fid, amount, date_filter):
        try:
            day = int(message.text.strip())
            if not 1 <= day <= 31:
                raise ValueError
            conn = get_conn()
            c = conn.cursor()
            c.execute("UPDATE fixed_expenses SET amount=%s, pay_day=%s WHERE id=%s",
                      (amount, day, fid))
            conn.commit()
            conn.close()
            bot.send_message(message.chat.id,
                             f"✅ Жаңартылды!\n"
                             f"• Сумма: <b>{amount:,.0f} сум</b>\n"
                             f"• Төлем күни: {day}-күн",
                             parse_mode='HTML')
        except ValueError:
            bot.send_message(message.chat.id, "❌ Қате! 1-31 арасында жазың.")

    # ➕ Таза кредит қосыў (келесі ай)
    @bot.callback_query_handler(func=lambda call: call.data.startswith("fac_"))
    def future_add_credit(call):
        date_filter = call.data[4:]
        msg = bot.send_message(call.message.chat.id, "Таза кредит атын жаз:\nМысалы: Kaspi кредит")
        bot.register_next_step_handler(msg, future_add_credit_name, date_filter)

    def future_add_credit_name(message, date_filter):
        name = message.text.strip()
        if not name:
            bot.send_message(message.chat.id, "❌ Аты бос болмасын!")
            return
        msg = bot.send_message(message.chat.id, f"💳 {name} суммасын жаз (сум):\nМысалы: 500000")
        bot.register_next_step_handler(msg, future_add_credit_amount, name, date_filter)

    def future_add_credit_amount(message, name, date_filter):
        try:
            amount = float(message.text.replace(",", "").replace(" ", ""))
            msg = bot.send_message(message.chat.id, "Төлем күнин жаз (1-31):\nМысалы: 10")
            bot.register_next_step_handler(msg, future_add_credit_day, name, amount, date_filter)
        except ValueError:
            bot.send_message(message.chat.id, "❌ Қате! Тек сан жазың.")

    def future_add_credit_day(message, name, amount, date_filter):
        try:
            day = int(message.text.strip())
            if not 1 <= day <= 31:
                raise ValueError
            conn = get_conn()
            c = conn.cursor()
            c.execute("INSERT INTO credits (name, amount, pay_day, is_active) VALUES (%s,%s,%s,1)",
                      (name, amount, day))
            conn.commit()
            conn.close()
            bot.send_message(message.chat.id,
                             f"✅ Таза кредит қосылды!\n"
                             f"• Аты: {name}\n"
                             f"• Сумма: <b>{amount:,.0f} сум</b>\n"
                             f"• Төлем күни: {day}-күн",
                             parse_mode='HTML')
        except ValueError:
            bot.send_message(message.chat.id, "❌ Қате! 1-31 арасында жазың.")

    # ➕ Таза тұрақлы қосыў (келесі ай)
    @bot.callback_query_handler(func=lambda call: call.data.startswith("faf_"))
    def future_add_fixed(call):
        date_filter = call.data[4:]
        msg = bot.send_message(call.message.chat.id, "Таза тұрақлы харажат атын жаз:\nМысалы: Интернет")
        bot.register_next_step_handler(msg, future_add_fixed_name, date_filter)

    def future_add_fixed_name(message, date_filter):
        name = message.text.strip()
        if not name:
            bot.send_message(message.chat.id, "❌ Аты бос болмасын!")
            return
        msg = bot.send_message(message.chat.id, f"🏠 {name} суммасын жаз (сум):\nМысалы: 200000")
        bot.register_next_step_handler(msg, future_add_fixed_amount, name, date_filter)

    def future_add_fixed_amount(message, name, date_filter):
        try:
            amount = float(message.text.replace(",", "").replace(" ", ""))
            msg = bot.send_message(message.chat.id, "Төлем күнин жаз (1-31):\nМысалы: 5")
            bot.register_next_step_handler(msg, future_add_fixed_day, name, amount, date_filter)
        except ValueError:
            bot.send_message(message.chat.id, "❌ Қате! Тек сан жазың.")

    def future_add_fixed_day(message, name, amount, date_filter):
        try:
            day = int(message.text.strip())
            if not 1 <= day <= 31:
                raise ValueError
            conn = get_conn()
            c = conn.cursor()
            c.execute("INSERT INTO fixed_expenses (name, amount, pay_day, is_active) VALUES (%s,%s,%s,1)",
                      (name, amount, day))
            conn.commit()
            conn.close()
            bot.send_message(message.chat.id,
                             f"✅ Таза тұрақлы харажат қосылды!\n"
                             f"• Аты: {name}\n"
                             f"• Сумма: <b>{amount:,.0f} сум</b>\n"
                             f"• Төлем күни: {day}-күн",
                             parse_mode='HTML')
        except ValueError:
            bot.send_message(message.chat.id, "❌ Қате! 1-31 арасында жазың.")

    # ➕ Басқа харажат қосыў (келесі ай)
    @bot.callback_query_handler(func=lambda call: call.data.startswith("fao_"))
    def future_add_other(call):
        date_filter = call.data[4:]
        msg = bot.send_message(call.message.chat.id, "Харажат атын жаз:\nМысалы: Коммунал")
        bot.register_next_step_handler(msg, future_add_other_name, date_filter)

    def future_add_other_name(message, date_filter):
        category = message.text.strip()
        if not category:
            bot.send_message(message.chat.id, "❌ Аты бос болмасын!")
            return
        msg = bot.send_message(message.chat.id, f"💸 {category} суммасын жаз (сум):\nМысалы: 50000")
        bot.register_next_step_handler(msg, future_add_other_amount, category, date_filter)

    def future_add_other_amount(message, category, date_filter):
        try:
            amount = float(message.text.replace(",", "").replace(" ", ""))
            conn = get_conn()
            c = conn.cursor()
            # date_filter = "2026-09" → created_at = "2026-09-01 00:00:00"
            created_at = f"{date_filter}-01 00:00:00"
            c.execute(
                "INSERT INTO other_expenses (telegram_id, category, amount, created_at) VALUES (%s,%s,%s,%s)",
                (message.from_user.id, category, amount, created_at))
            conn.commit()
            conn.close()
            bot.send_message(message.chat.id,
                             f"✅ {category}: <b>-{amount:,.0f} сум</b> қосылды!",
                             parse_mode='HTML')
        except ValueError:
            bot.send_message(message.chat.id, "❌ Қате! Тек сан жазың.")
