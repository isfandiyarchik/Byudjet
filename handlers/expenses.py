from database import get_conn
from datetime import datetime
import telebot
import os

ADMIN_ID = int(os.getenv("ADMIN_ID"))

def register_expense_handlers(bot):

    @bot.message_handler(func=lambda m: m.text == "➕ Харажат қосыў")
    def expense_type(message):
        markup = telebot.types.InlineKeyboardMarkup()
        if message.from_user.id == ADMIN_ID:
            markup.add(telebot.types.InlineKeyboardButton("🔴 Кредит төлеми", callback_data="exp_credit"))
            markup.add(telebot.types.InlineKeyboardButton("🟡 Тұрақлы харажат", callback_data="exp_fixed"))
        markup.add(telebot.types.InlineKeyboardButton("🟢 Басқа харажат", callback_data="exp_other"))
        bot.send_message(message.chat.id, "Харажат түрин таңла:", reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data == "exp_credit")
    def show_credits(call):
        if call.from_user.id != ADMIN_ID:
            bot.answer_callback_query(call.id, "❌ Бул тек админ ушын!")
            return
        month = datetime.now().strftime("%Y-%m")
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT id, name, amount FROM credits WHERE is_active=1")
        credits = c.fetchall()
        # ТҮЗЕТИЛДИ: осы айда әллекашан төленген кредитлерди тексереміз
        c.execute("SELECT ref_id FROM payments WHERE month=%s AND status='paid' AND type='credit'", (month,))
        paid_ids = {row[0] for row in c.fetchall()}
        conn.close()
        markup = telebot.types.InlineKeyboardMarkup()
        for cid, name, amount in credits:
            if cid in paid_ids:
                continue
            markup.add(telebot.types.InlineKeyboardButton(
                f"{name}: {amount:,.0f} сум",
                callback_data=f"pc_{cid}"
            ))
        if not markup.keyboard:
            bot.send_message(call.message.chat.id, "✅ Бул айдағы барлық кредитлер төленген!")
            return
        bot.send_message(call.message.chat.id, "Қайси кредит?", reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data == "exp_fixed")
    def show_fixed(call):
        if call.from_user.id != ADMIN_ID:
            bot.answer_callback_query(call.id, "❌ Бул тек админ ушын!")
            return
        month = datetime.now().strftime("%Y-%m")
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT id, name, amount FROM fixed_expenses WHERE is_active=1")
        fixed = c.fetchall()
        # ТҮЗЕТИЛДИ: осы айда әллекашан төленген харажатларды тексереміз
        c.execute("SELECT ref_id FROM payments WHERE month=%s AND status='paid' AND type='fixed'", (month,))
        paid_ids = {row[0] for row in c.fetchall()}
        conn.close()
        markup = telebot.types.InlineKeyboardMarkup()
        for fid, name, amount in fixed:
            if fid in paid_ids:
                continue
            markup.add(telebot.types.InlineKeyboardButton(
                f"{name}: {amount:,.0f} сум",
                callback_data=f"pf_{fid}"
            ))
        if not markup.keyboard:
            bot.send_message(call.message.chat.id, "✅ Бул айдағы барлық тұрақлы харажатлар төленген!")
            return
        bot.send_message(call.message.chat.id, "Қайси харажат?", reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data == "exp_other")
    def other_category(call):
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT DISTINCT category FROM other_expenses ORDER BY category")
        saved_cats = [row[0] for row in c.fetchall()]
        conn.close()

        markup = telebot.types.InlineKeyboardMarkup()
        default_cats = ["🛒 Азық-аўқат", "🚗 Такси", "📦 Басқа"]
        for cat in default_cats:
            markup.add(telebot.types.InlineKeyboardButton(
                cat, callback_data=f"ocat_{cat}"))
        for cat in saved_cats:
            if cat not in default_cats:
                markup.add(telebot.types.InlineKeyboardButton(
                    f"⭐ {cat}", callback_data=f"ocat_{cat}"))
        markup.add(telebot.types.InlineKeyboardButton(
            "➕ Таза категория қос", callback_data="ocat_NEW"))
        bot.send_message(call.message.chat.id, "Категория таңла:", reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data == "ocat_NEW")
    def new_category(call):
        msg = bot.send_message(call.message.chat.id,
                               "Таза категория атын жаз:\nМысалы: Кийим, Дәри, Китап, Саяхат")
        bot.register_next_step_handler(msg, ask_new_cat_amount, call.from_user.id)

    def ask_new_cat_amount(message, telegram_id):
        category = message.text.strip()
        if not category:
            bot.send_message(message.chat.id, "❌ Категория аты бос болмасын!")
            return
        msg = bot.send_message(message.chat.id, f"💸 {category} суммасын жаз (сум):")
        bot.register_next_step_handler(msg, save_other_expense, category, telegram_id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("ocat_") and call.data != "ocat_NEW")
    def other_amount(call):
        category = call.data[5:]
        msg = bot.send_message(call.message.chat.id, f"💸 {category} суммасын жаз (сум):")
        bot.register_next_step_handler(msg, save_other_expense, category, call.from_user.id)

    def save_other_expense(message, category, telegram_id):
        try:
            amount = float(message.text.replace(",", "").replace(" ", ""))
            conn = get_conn()
            c = conn.cursor()
            c.execute(
                "INSERT INTO other_expenses (telegram_id, category, amount, created_at) VALUES (%s,%s,%s,%s)",
                (telegram_id, category, amount, str(datetime.now())))
            conn.commit()
            conn.close()
            bot.send_message(message.chat.id, f"✅ {category}: -{amount:,.0f} сум қосылды!")
        except ValueError:
            bot.send_message(message.chat.id, "❌ Қате! Тек сан жазың. Мысалы: 150000")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("pc_"))
    def pay_credit(call):
        if call.from_user.id != ADMIN_ID:
            bot.answer_callback_query(call.id, "❌ Бул тек админ ушын!")
            return
        cid = int(call.data.split("_")[1])
        month = datetime.now().strftime("%Y-%m")

        conn = get_conn()
        c = conn.cursor()

        # ТҮЗЕТИЛДИ: бул кредит осы айда әллекашан төленген бе — тексеремиз
        c.execute("SELECT id FROM payments WHERE month=%s AND status='paid' AND type='credit' AND ref_id=%s",
                  (month, cid))
        already_paid = c.fetchone()
        if already_paid:
            conn.close()
            bot.answer_callback_query(call.id, "⚠️ Бул кредит бул айда әллекашан төленген!")
            return

        c.execute("SELECT name, amount FROM credits WHERE id=%s", (cid,))
        credit = c.fetchone()

        # Осы айда қосылған бюджет
        c.execute("SELECT COALESCE(SUM(amount),0) FROM budget WHERE created_at LIKE %s",
                  (f"{month}%",))
        month_budget = c.fetchone()[0]

        # Осы айда төленген
        c.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE month=%s AND status='paid'",
                  (month,))
        paid_total = c.fetchone()[0]

        # Осы айдағы басқа харажатлар
        c.execute("SELECT COALESCE(SUM(amount),0) FROM other_expenses WHERE created_at LIKE %s",
                  (f"{month}%",))
        other = c.fetchone()[0]

        conn.close()

        name, amount = credit

        # Қолда бар = осы айдың бюджеті - төленгендер - басқа харажатлар
        remaining = month_budget - paid_total - other

        if remaining >= amount:
            conn = get_conn()
            c = conn.cursor()
            c.execute(
                "INSERT INTO payments (type, ref_id, amount, status, month, created_at) VALUES (%s,%s,%s,%s,%s,%s)",
                ("credit", cid, amount, "paid", month, str(datetime.now())))
            conn.commit()
            conn.close()
            bot.answer_callback_query(call.id, f"✅ {name} төленди!")
            bot.send_message(call.message.chat.id,
                             f"✅ {name}: -{amount:,.0f} сум төленди!\n"
                             f"💰 Қалған: {remaining - amount:,.0f} сум")
        else:
            bot.answer_callback_query(call.id, "❌ Бюджет жетиспейди!")
            bot.send_message(call.message.chat.id,
                             f"⚠️ Бюджет жетиспейди!\n"
                             f"• {name}: {amount:,.0f} сум керек\n"
                             f"• Қолда бар: {remaining:,.0f} сум\n"
                             f"• Айырма: -{amount - remaining:,.0f} сум\n\n"
                             f"Бюджетти толтырың!")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("pf_"))
    def pay_fixed(call):
        if call.from_user.id != ADMIN_ID:
            bot.answer_callback_query(call.id, "❌ Бул тек админ ушын!")
            return
        fid = int(call.data.split("_")[1])
        month = datetime.now().strftime("%Y-%m")

        conn = get_conn()
        c = conn.cursor()

        # ТҮЗЕТИЛДИ: бул харажат осы айда әллекашан төленген бе — тексеремиз
        c.execute("SELECT id FROM payments WHERE month=%s AND status='paid' AND type='fixed' AND ref_id=%s",
                  (month, fid))
        already_paid = c.fetchone()
        if already_paid:
            conn.close()
            bot.answer_callback_query(call.id, "⚠️ Бул харажат бул айда әллекашан төленген!")
            return

        c.execute("SELECT name, amount FROM fixed_expenses WHERE id=%s", (fid,))
        fixed = c.fetchone()

        # Осы айда қосылған бюджет
        c.execute("SELECT COALESCE(SUM(amount),0) FROM budget WHERE created_at LIKE %s",
                  (f"{month}%",))
        month_budget = c.fetchone()[0]

        # Осы айда төленген
        c.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE month=%s AND status='paid'",
                  (month,))
        paid_total = c.fetchone()[0]

        # Осы айдағы басқа харажатлар
        c.execute("SELECT COALESCE(SUM(amount),0) FROM other_expenses WHERE created_at LIKE %s",
                  (f"{month}%",))
        other = c.fetchone()[0]

        conn.close()

        name, amount = fixed

        # Қолда бар = осы айдың бюджеті - төленгендер - басқа харажатлар
        remaining = month_budget - paid_total - other

        if remaining >= amount:
            conn = get_conn()
            c = conn.cursor()
            c.execute(
                "INSERT INTO payments (type, ref_id, amount, status, month, created_at) VALUES (%s,%s,%s,%s,%s,%s)",
                ("fixed", fid, amount, "paid", month, str(datetime.now())))
            conn.commit()
            conn.close()
            bot.answer_callback_query(call.id, f"✅ {name} төленди!")
            bot.send_message(call.message.chat.id,
                             f"✅ {name}: -{amount:,.0f} сум төленди!\n"
                             f"💰 Қалған: {remaining - amount:,.0f} сум")
        else:
            bot.answer_callback_query(call.id, "❌ Бюджет жетиспейди!")
            bot.send_message(call.message.chat.id,
                             f"⚠️ Бюджет жетиспейди!\n"
                             f"• {name}: {amount:,.0f} сум керек\n"
                             f"• Қолда бар: {remaining:,.0f} сум\n"
                             f"• Айырма: -{amount - remaining:,.0f} сум\n\n"
                             f"Бюджетти толтырың!")
