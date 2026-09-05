from database import get_conn, get_credits_for_month, get_fixed_for_month
from datetime import datetime
from io import StringIO, BytesIO
import csv
import telebot
from common import with_cancel

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

        c.execute("SELECT category, COALESCE(SUM(amount),0) FROM other_expenses WHERE created_at LIKE %s GROUP BY category",
                  (f"{date_filter}%",))
        other_by_cat = c.fetchall()
        other_total = sum(float(a) for _, a in other_by_cat)

        c.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE month=%s AND status='paid'",
                  (date_filter,))
        paid_total = float(c.fetchone()[0])
        conn.close()

        credits = get_credits_for_month(date_filter)
        fixed = get_fixed_for_month(date_filter)
        credit_total = sum(float(a) for _, _, a, _ in credits)
        fixed_total = sum(float(a) for _, _, a, _ in fixed)

        family_budget = credit_total + fixed_total + other_total
        remaining = total_budget - paid_total - other_total

        title = f"✏️ {MONTHS_RU[month_num]} {year} — жоспар" if is_future else f"📊 {MONTHS_RU[month_num]} {year} есабы"
        text = f"{title}\n\n"

        if income_by_source:
            text += "📥 <b>Кириc:</b>\n"
            for source, amount in income_by_source:
                text += f"  • {source}: <b>+{float(amount):,.0f} сум</b>\n"
            text += f"  Итого: <b>+{total_budget:,.0f} сум</b>\n\n"

        text += "🔴 <b>Кредитлер:</b>\n"
        for cid, name, amount, pay_day in credits:
            text += f"  • {name}: <b>{float(amount):,.0f} сум</b>\n"
        text += f"  Итого: <b>-{credit_total:,.0f} сум</b>\n"

        text += "\n🟡 <b>Тұрақлы харажатлар:</b>\n"
        for fid, name, amount, pay_day in fixed:
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

        markup = telebot.types.InlineKeyboardMarkup()

        if is_future:
            for cid, name, amount, pay_day in credits:
                markup.row(
                    telebot.types.InlineKeyboardButton(
                        f"✏️ {name}: {float(amount):,.0f}",
                        callback_data=f"fec_{cid}_{date_filter}"
                    ),
                    telebot.types.InlineKeyboardButton(
                        "🗑", callback_data=f"fdc_{cid}_{date_filter}"
                    )
                )
            markup.add(telebot.types.InlineKeyboardButton(
                "➕ Таза кредит қосыў", callback_data=f"fac_{date_filter}"
            ))
            for fid, name, amount, pay_day in fixed:
                markup.row(
                    telebot.types.InlineKeyboardButton(
                        f"✏️ {name}: {float(amount):,.0f}",
                        callback_data=f"fef_{fid}_{date_filter}"
                    ),
                    telebot.types.InlineKeyboardButton(
                        "🗑", callback_data=f"fdf_{fid}_{date_filter}"
                    )
                )
            markup.add(telebot.types.InlineKeyboardButton(
                "➕ Таза тұрақлы қосыў", callback_data=f"faf_{date_filter}"
            ))
            markup.add(telebot.types.InlineKeyboardButton(
                "➕ Басқа харажат қосыў", callback_data=f"fao_{date_filter}"
            ))

        markup.add(telebot.types.InlineKeyboardButton(
            "📄 CSV жүклеп алыў", callback_data=f"csvrep_{date_filter}"
        ))

        bot.send_message(call.message.chat.id, text, reply_markup=markup, parse_mode='HTML')

    # ЖАҢА: CSV экспорт
    @bot.callback_query_handler(func=lambda call: call.data.startswith("csvrep_"))
    def export_csv(call):
        date_filter = call.data[7:]

        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT source, amount, created_at FROM budget WHERE created_at LIKE %s",
                  (f"{date_filter}%",))
        income_rows = c.fetchall()
        c.execute("SELECT category, amount, created_at FROM other_expenses WHERE created_at LIKE %s",
                  (f"{date_filter}%",))
        other_rows = c.fetchall()
        conn.close()

        credits = get_credits_for_month(date_filter)
        fixed = get_fixed_for_month(date_filter)

        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["Түри", "Аты/Дереги", "Сумма", "Сана/Күн"])

        for source, amount, created_at in income_rows:
            writer.writerow(["Кирис", source, amount, created_at])
        for cid, name, amount, pay_day in credits:
            writer.writerow(["Кредит", name, amount, f"{pay_day}-күн"])
        for fid, name, amount, pay_day in fixed:
            writer.writerow(["Тұрақлы харажат", name, amount, f"{pay_day}-күн"])
        for cat, amount, created_at in other_rows:
            writer.writerow(["Басқа харажат", cat, amount, created_at])

        buf = BytesIO(output.getvalue().encode("utf-8-sig"))
        buf.name = f"esap_{date_filter}.csv"

        bot.answer_callback_query(call.id, "📄 Таярланды!")
        bot.send_document(call.message.chat.id, buf, caption=f"📄 {date_filter} есабы (CSV)")

    # ✏️ Кредит өзгертиў (тек сол айға)
    @bot.callback_query_handler(func=lambda call: call.data.startswith("fec_"))
    def future_edit_credit(call):
        parts = call.data.split("_")
        cid = int(parts[1])
        date_filter = f"{parts[2]}-{parts[3]}"
        msg = bot.send_message(call.message.chat.id, "Таза сумма жаз (сум):\nМысалы: 450000")
        bot.register_next_step_handler(msg, with_cancel(bot, fec_amount), cid, date_filter)

    def fec_amount(message, cid, date_filter):
        try:
            amount = float(message.text.replace(",", "").replace(" ", ""))
            msg = bot.send_message(message.chat.id, "Төлем күнин жаз (1-31):")
            bot.register_next_step_handler(msg, with_cancel(bot, fec_day), cid, amount, date_filter)
        except ValueError:
            bot.send_message(message.chat.id, "❌ Қате! Тек сан жазың.")

    def fec_day(message, cid, amount, date_filter):
        try:
            day = int(message.text.strip())
            if not 1 <= day <= 31:
                raise ValueError
            conn = get_conn()
            c = conn.cursor()
            c.execute("SELECT id FROM credit_overrides WHERE credit_id=%s AND month=%s", (cid, date_filter))
            existing = c.fetchone()
            if existing:
                c.execute("UPDATE credit_overrides SET amount=%s, pay_day=%s, is_active=1 WHERE credit_id=%s AND month=%s",
                          (amount, day, cid, date_filter))
            else:
                c.execute("INSERT INTO credit_overrides (credit_id, month, amount, pay_day, is_active) VALUES (%s,%s,%s,%s,1)",
                          (cid, date_filter, amount, day))
            conn.commit()
            conn.close()
            bot.send_message(message.chat.id,
                             f"✅ Тек <b>{date_filter}</b> айына тазаланды!\n"
                             f"• Сумма: <b>{amount:,.0f} сум</b>\n"
                             f"• Төлем күни: {day}-күн",
                             parse_mode='HTML')
        except ValueError:
            bot.send_message(message.chat.id, "❌ Қате! 1-31 арасында жазың.")

    # 🗑 Кредит жою (тек сол айға)
    @bot.callback_query_handler(func=lambda call: call.data.startswith("fdc_"))
    def future_del_credit(call):
        parts = call.data.split("_")
        cid = int(parts[1])
        date_filter = f"{parts[2]}-{parts[3]}"
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT name FROM credits WHERE id=%s", (cid,))
        name = c.fetchone()[0]
        c.execute("SELECT id FROM credit_overrides WHERE credit_id=%s AND month=%s", (cid, date_filter))
        existing = c.fetchone()
        if existing:
            c.execute("UPDATE credit_overrides SET is_active=0 WHERE credit_id=%s AND month=%s",
                      (cid, date_filter))
        else:
            c.execute("INSERT INTO credit_overrides (credit_id, month, amount, pay_day, is_active) VALUES (%s,%s,0,1,0)",
                      (cid, date_filter))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, f"✅ {name} тек {date_filter} айынан оширилди!")
        bot.send_message(call.message.chat.id,
                         f"✅ <b>{name}</b> тек <b>{date_filter}</b> айынан оширилди!",
                         parse_mode='HTML')

    # ✏️ Тұрақлы өзгертиў (тек сол айға)
    @bot.callback_query_handler(func=lambda call: call.data.startswith("fef_"))
    def future_edit_fixed(call):
        parts = call.data.split("_")
        fid = int(parts[1])
        date_filter = f"{parts[2]}-{parts[3]}"
        msg = bot.send_message(call.message.chat.id, "Таза сумма жаз (сум):\nМысалы: 300000")
        bot.register_next_step_handler(msg, with_cancel(bot, fef_amount), fid, date_filter)

    def fef_amount(message, fid, date_filter):
        try:
            amount = float(message.text.replace(",", "").replace(" ", ""))
            msg = bot.send_message(message.chat.id, "Төлем күнин жаз (1-31):")
            bot.register_next_step_handler(msg, with_cancel(bot, fef_day), fid, amount, date_filter)
        except ValueError:
            bot.send_message(message.chat.id, "❌ Қате! Тек сан жазың.")

    def fef_day(message, fid, amount, date_filter):
        try:
            day = int(message.text.strip())
            if not 1 <= day <= 31:
                raise ValueError
            conn = get_conn()
            c = conn.cursor()
            c.execute("SELECT id FROM fixed_overrides WHERE fixed_id=%s AND month=%s", (fid, date_filter))
            existing = c.fetchone()
            if existing:
                c.execute("UPDATE fixed_overrides SET amount=%s, pay_day=%s, is_active=1 WHERE fixed_id=%s AND month=%s",
                          (amount, day, fid, date_filter))
            else:
                c.execute("INSERT INTO fixed_overrides (fixed_id, month, amount, pay_day, is_active) VALUES (%s,%s,%s,%s,1)",
                          (fid, date_filter, amount, day))
            conn.commit()
            conn.close()
            bot.send_message(message.chat.id,
                             f"✅ Тек <b>{date_filter}</b> айына тазаланды!\n"
                             f"• Сумма: <b>{amount:,.0f} сум</b>\n"
                             f"• Төлем күни: {day}-күн",
                             parse_mode='HTML')
        except ValueError:
            bot.send_message(message.chat.id, "❌ Қате! 1-31 арасында жазың.")

    # 🗑 Тұрақлы жою (тек сол айға)
    @bot.callback_query_handler(func=lambda call: call.data.startswith("fdf_"))
    def future_del_fixed(call):
        parts = call.data.split("_")
        fid = int(parts[1])
        date_filter = f"{parts[2]}-{parts[3]}"
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT name FROM fixed_expenses WHERE id=%s", (fid,))
        name = c.fetchone()[0]
        c.execute("SELECT id FROM fixed_overrides WHERE fixed_id=%s AND month=%s", (fid, date_filter))
        existing = c.fetchone()
        if existing:
            c.execute("UPDATE fixed_overrides SET is_active=0 WHERE fixed_id=%s AND month=%s",
                      (fid, date_filter))
        else:
            c.execute("INSERT INTO fixed_overrides (fixed_id, month, amount, pay_day, is_active) VALUES (%s,%s,0,1,0)",
                      (fid, date_filter))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, f"✅ {name} тек {date_filter} айынан оширилди!")
        bot.send_message(call.message.chat.id,
                         f"✅ <b>{name}</b> тек <b>{date_filter}</b> айынан оширилди!",
                         parse_mode='HTML')

    # ➕ Таза кредит қосыў (тек сол айға)
    @bot.callback_query_handler(func=lambda call: call.data.startswith("fac_"))
    def future_add_credit(call):
        date_filter = call.data[4:]
        msg = bot.send_message(call.message.chat.id, "Таза кредит атын жаз:\nМысалы: Kaspi кредит")
        bot.register_next_step_handler(msg, with_cancel(bot, fac_name), date_filter)

    def fac_name(message, date_filter):
        name = message.text.strip()
        if not name:
            bot.send_message(message.chat.id, "❌ Аты бос болмасын!")
            return
        msg = bot.send_message(message.chat.id, f"💳 {name} суммасын жаз (сум):")
        bot.register_next_step_handler(msg, with_cancel(bot, fac_amount), name, date_filter)

    def fac_amount(message, name, date_filter):
        try:
            amount = float(message.text.replace(",", "").replace(" ", ""))
            msg = bot.send_message(message.chat.id, "Төлем күнин жаз (1-31):")
            bot.register_next_step_handler(msg, with_cancel(bot, fac_day), name, amount, date_filter)
        except ValueError:
            bot.send_message(message.chat.id, "❌ Қате! Тек сан жазың.")

    def fac_day(message, name, amount, date_filter):
        try:
            day = int(message.text.strip())
            if not 1 <= day <= 31:
                raise ValueError
            conn = get_conn()
            c = conn.cursor()
            c.execute("INSERT INTO credits (name, amount, pay_day, is_active) VALUES (%s,%s,%s,0)",
                      (name, amount, day))
            c.execute("SELECT lastval()")
            new_id = c.fetchone()[0]
            c.execute("INSERT INTO credit_overrides (credit_id, month, amount, pay_day, is_active) VALUES (%s,%s,%s,%s,1)",
                      (new_id, date_filter, amount, day))
            conn.commit()
            conn.close()
            bot.send_message(message.chat.id,
                             f"✅ <b>{name}</b> тек <b>{date_filter}</b> айына қосылды!\n"
                             f"• Сумма: <b>{amount:,.0f} сум</b>\n"
                             f"• Төлем күни: {day}-күн",
                             parse_mode='HTML')
        except ValueError:
            bot.send_message(message.chat.id, "❌ Қате! 1-31 арасында жазың.")

    # ➕ Таза тұрақлы қосыў (тек сол айға)
    @bot.callback_query_handler(func=lambda call: call.data.startswith("faf_"))
    def future_add_fixed(call):
        date_filter = call.data[4:]
        msg = bot.send_message(call.message.chat.id, "Таза тұрақлы харажат атын жаз:\nМысалы: Интернет")
        bot.register_next_step_handler(msg, with_cancel(bot, faf_name), date_filter)

    def faf_name(message, date_filter):
        name = message.text.strip()
        if not name:
            bot.send_message(message.chat.id, "❌ Аты бос болмасын!")
            return
        msg = bot.send_message(message.chat.id, f"🏠 {name} суммасын жаз (сум):")
        bot.register_next_step_handler(msg, with_cancel(bot, faf_amount), name, date_filter)

    def faf_amount(message, name, date_filter):
        try:
            amount = float(message.text.replace(",", "").replace(" ", ""))
            msg = bot.send_message(message.chat.id, "Төлем күнин жаз (1-31):")
            bot.register_next_step_handler(msg, with_cancel(bot, faf_day), name, amount, date_filter)
        except ValueError:
            bot.send_message(message.chat.id, "❌ Қате! Тек сан жазың.")

    def faf_day(message, name, amount, date_filter):
        try:
            day = int(message.text.strip())
            if not 1 <= day <= 31:
                raise ValueError
            conn = get_conn()
            c = conn.cursor()
            c.execute("INSERT INTO fixed_expenses (name, amount, pay_day, is_active) VALUES (%s,%s,%s,0)",
                      (name, amount, day))
            c.execute("SELECT lastval()")
            new_id = c.fetchone()[0]
            c.execute("INSERT INTO fixed_overrides (fixed_id, month, amount, pay_day, is_active) VALUES (%s,%s,%s,%s,1)",
                      (new_id, date_filter, amount, day))
            conn.commit()
            conn.close()
            bot.send_message(message.chat.id,
                             f"✅ <b>{name}</b> тек <b>{date_filter}</b> айына қосылды!\n"
                             f"• Сумма: <b>{amount:,.0f} сум</b>\n"
                             f"• Төлем күни: {day}-күн",
                             parse_mode='HTML')
        except ValueError:
            bot.send_message(message.chat.id, "❌ Қате! 1-31 арасында жазың.")

    # ➕ Басқа харажат қосыў
    @bot.callback_query_handler(func=lambda call: call.data.startswith("fao_"))
    def future_add_other(call):
        date_filter = call.data[4:]
        msg = bot.send_message(call.message.chat.id, "Харажат атын жаз:\nМысалы: Коммунал")
        bot.register_next_step_handler(msg, with_cancel(bot, fao_name), date_filter)

    def fao_name(message, date_filter):
        category = message.text.strip()
        if not category:
            bot.send_message(message.chat.id, "❌ Аты бос болмасын!")
            return
        msg = bot.send_message(message.chat.id, f"💸 {category} суммасын жаз (сум):")
        bot.register_next_step_handler(msg, with_cancel(bot, fao_amount), category, date_filter)

    def fao_amount(message, category, date_filter):
        try:
            amount = float(message.text.replace(",", "").replace(" ", ""))
            conn = get_conn()
            c = conn.cursor()
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
