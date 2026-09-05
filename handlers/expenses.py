from database import get_conn, get_category_limit
from datetime import datetime
import telebot
from common import is_admin, with_cancel

def register_expense_handlers(bot):

    @bot.message_handler(func=lambda m: m.text == "➕ Харажат қосыў")
    def expense_type(message):
        markup = telebot.types.InlineKeyboardMarkup()
        if is_admin(message.from_user.id):
            markup.add(telebot.types.InlineKeyboardButton("🔴 Кредит төлеми", callback_data="exp_credit"))
            markup.add(telebot.types.InlineKeyboardButton("🟡 Тұрақлы харажат", callback_data="exp_fixed"))
        markup.add(telebot.types.InlineKeyboardButton("🟢 Басқа харажат", callback_data="exp_other"))
        bot.send_message(message.chat.id, "Харажат түрин таңла:", reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data == "exp_credit")
    def show_credits(call):
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Бул тек админ ушын!")
            return
        month = datetime.now().strftime("%Y-%m")
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT id, name, amount FROM credits WHERE is_active=1")
        credits = c.fetchall()
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
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Бул тек админ ушын!")
            return
        month = datetime.now().strftime("%Y-%m")
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT id, name, amount FROM fixed_expenses WHERE is_active=1")
        fixed = c.fetchall()
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
        bot.register_next_step_handler(msg, with_cancel(bot, ask_new_cat_amount), call.from_user.id)

    def ask_new_cat_amount(message, telegram_id):
        category = message.text.strip()
        if not category:
            bot.send_message(message.chat.id, "❌ Категория аты бос болмасын!")
            return
        msg = bot.send_message(message.chat.id, f"💸 {category} суммасын жаз (сум):")
        bot.register_next_step_handler(msg, with_cancel(bot, save_other_expense), category, telegram_id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("ocat_") and call.data != "ocat_NEW")
    def other_amount(call):
        category = call.data[5:]
        msg = bot.send_message(call.message.chat.id, f"💸 {category} суммасын жаз (сум):")
        bot.register_next_step_handler(msg, with_cancel(bot, save_other_expense), category, call.from_user.id)

    def save_other_expense(message, category, telegram_id):
        try:
            amount = float(message.text.replace(",", "").replace(" ", ""))
            conn = get_conn()
            c = conn.cursor()
            c.execute(
                "INSERT INTO other_expenses (telegram_id, category, amount, created_at) VALUES (%s,%s,%s,%s)",
                (telegram_id, category, amount, str(datetime.now())))
            conn.commit()

            # ЖАҢА: категория лимитин тексериў
            month = datetime.now().strftime("%Y-%m")
            c.execute("SELECT COALESCE(SUM(amount),0) FROM other_expenses WHERE category=%s AND created_at LIKE %s",
                      (category, f"{month}%"))
            category_month_total = float(c.fetchone()[0])
            conn.close()

            bot.send_message(message.chat.id, f"✅ {category}: -{amount:,.0f} сум қосылды!")

            limit = get_category_limit(category)
            if limit is not None and category_month_total > limit:
                bot.send_message(message.chat.id,
                                 f"⚠️ <b>Лимиттен асты!</b>\n"
                                 f"• {category}: <b>{category_month_total:,.0f} сум</b>\n"
                                 f"• Лимит: <b>{limit:,.0f} сум</b>\n"
                                 f"• Асыў: <b>+{category_month_total - limit:,.0f} сум</b>",
                                 parse_mode='HTML')
        except ValueError:
            bot.send_message(message.chat.id, "❌ Қате! Тек сан жазың. Мысалы: 150000")

    # ------------------- Соңғы харажатларды көриу / өшириу -------------------

    @bot.callback_query_handler(func=lambda call: call.data == "view_recent_other")
    def view_recent_other(call):
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Бул тек админ ушын!")
            return
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT id, category, amount, created_at FROM other_expenses ORDER BY id DESC LIMIT 10")
        rows = c.fetchall()
        conn.close()
        if not rows:
            bot.send_message(call.message.chat.id, "Харажат жазбалары жоқ.")
            return
        markup = telebot.types.InlineKeyboardMarkup()
        for oid, cat, amt, created in rows:
            date_part = str(created)[:10]
            markup.add(telebot.types.InlineKeyboardButton(
                f"🗑 {cat}: {float(amt):,.0f} сум ({date_part})",
                callback_data=f"delo_{oid}"
            ))
        bot.send_message(call.message.chat.id, "Соңғы харажатлар (өшириў ушын бас):", reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("delo_"))
    def delete_other_expense(call):
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Бул тек админ ушын!")
            return
        oid = int(call.data.split("_")[1])
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT category, amount FROM other_expenses WHERE id=%s", (oid,))
        row = c.fetchone()
        if not row:
            conn.close()
            bot.answer_callback_query(call.id, "❌ Табылмады (әллекашан өширилген болыўы мүмкин)")
            return
        cat, amt = row
        c.execute("DELETE FROM other_expenses WHERE id=%s", (oid,))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, "✅ Өширилди!")
        bot.send_message(call.message.chat.id, f"🗑 <b>{cat}</b>: {float(amt):,.0f} сум өширилди!", parse_mode='HTML')

    # ------------------- Кредит/тұрақлы төлеў -------------------

    @bot.callback_query_handler(func=lambda call: call.data.startswith("pc_"))
    def pay_credit(call):
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Бул тек админ ушын!")
            return
        cid = int(call.data.split("_")[1])
        month = datetime.now().strftime("%Y-%m")

        conn = get_conn()
        c = conn.cursor()

        c.execute("SELECT id FROM payments WHERE month=%s AND status='paid' AND type='credit' AND ref_id=%s",
                  (month, cid))
        already_paid = c.fetchone()
        if already_paid:
            conn.close()
            bot.answer_callback_query(call.id, "⚠️ Бул кредит бул айда әллекашан төленген!")
            return

        c.execute("SELECT name, amount FROM credits WHERE id=%s", (cid,))
        credit = c.fetchone()

        c.execute("SELECT COALESCE(SUM(amount),0) FROM budget WHERE created_at LIKE %s",
                  (f"{month}%",))
        month_budget = c.fetchone()[0]

        c.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE month=%s AND status='paid'",
                  (month,))
        paid_total = c.fetchone()[0]

        c.execute("SELECT COALESCE(SUM(amount),0) FROM other_expenses WHERE created_at LIKE %s",
                  (f"{month}%",))
        other = c.fetchone()[0]

        conn.close()

        name, amount = credit
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
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Бул тек админ ушын!")
            return
        fid = int(call.data.split("_")[1])
        month = datetime.now().strftime("%Y-%m")

        conn = get_conn()
        c = conn.cursor()

        c.execute("SELECT id FROM payments WHERE month=%s AND status='paid' AND type='fixed' AND ref_id=%s",
                  (month, fid))
        already_paid = c.fetchone()
        if already_paid:
            conn.close()
            bot.answer_callback_query(call.id, "⚠️ Бул харажат бул айда әллекашан төленген!")
            return

        c.execute("SELECT name, amount FROM fixed_expenses WHERE id=%s", (fid,))
        fixed = c.fetchone()

        c.execute("SELECT COALESCE(SUM(amount),0) FROM budget WHERE created_at LIKE %s",
                  (f"{month}%",))
        month_budget = c.fetchone()[0]

        c.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE month=%s AND status='paid'",
                  (month,))
        paid_total = c.fetchone()[0]

        c.execute("SELECT COALESCE(SUM(amount),0) FROM other_expenses WHERE created_at LIKE %s",
                  (f"{month}%",))
        other = c.fetchone()[0]

        conn.close()

        name, amount = fixed
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
