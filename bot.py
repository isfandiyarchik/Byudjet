import telebot
import os
from flask import Flask, request
from dotenv import load_dotenv
from datetime import datetime
from database import init_db, get_conn, get_credits_for_month, get_fixed_for_month
from scheduler import start_scheduler
from backup import generate_backup
from common import ADMIN_IDS, is_admin, with_cancel
from handlers.budget import register_budget_handlers
from handlers.expenses import register_expense_handlers
from handlers.reports import register_report_handlers

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://byudjet.onrender.com")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

init_db()

@app.route('/')
def home():
    return "Бот жумыс ислеп тур! ✅"

@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def webhook():
    json_str = request.get_data().decode('UTF-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return 'OK', 200

def main_menu():
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🏠 Баслапқы бет")
    markup.row("➕ Бюджет қосыў", "➕ Харажат қосыў")
    markup.row("📊 Есап", "⚙️ Өзгертиў")
    return markup

@bot.message_handler(commands=["start"])
def start(message):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE telegram_id=%s", (message.from_user.id,))
    user = c.fetchone()
    if not user:
        is_admin_flag = 1 if is_admin(message.from_user.id) else 0
        c.execute("INSERT INTO users (telegram_id, name, is_admin, created_at) VALUES (%s,%s,%s,%s)",
                  (message.from_user.id, message.from_user.first_name, is_admin_flag, str(datetime.now())))
        conn.commit()
    conn.close()
    bot.send_message(message.chat.id,
                     f"Ассалаума алейкум, {message.from_user.first_name}! 👋\nБюджет ботына хош келдиңиз!",
                     reply_markup=main_menu())

@bot.message_handler(commands=["cancel"])
def cancel_command(message):
    bot.clear_step_handler_by_chat_id(message.chat.id)
    bot.send_message(message.chat.id, "❌ Бийкар етилди.", reply_markup=main_menu())

@bot.message_handler(commands=["backup"])
def manual_backup(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "❌ Бул тек админ ушын!")
        return
    bot.send_message(message.chat.id, "📦 Backup таярланып атыр...")
    buf = generate_backup()
    bot.send_document(message.chat.id, buf, caption="📦 Дерекқордың толық резерв көширмеси (JSON)")

@bot.message_handler(func=lambda m: m.text == "🏠 Баслапқы бет")
def dashboard(message):
    conn = get_conn()
    c = conn.cursor()

    month = datetime.now().strftime("%Y-%m")

    c.execute("SELECT COALESCE(SUM(amount),0) FROM budget WHERE created_at LIKE %s",
              (f"{month}%",))
    total_income = float(c.fetchone()[0])

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

    conn.close()

    credits = get_credits_for_month(month)
    fixed = get_fixed_for_month(month)

    credit_total = sum(float(a) for _, _, a, _ in credits)
    fixed_total = sum(float(a) for _, _, a, _ in fixed)
    family_budget = credit_total + fixed_total + other
    remaining = total_income - paid_total - other

    months_kk = {
        1: "январь", 2: "февраль", 3: "март", 4: "апрель",
        5: "май", 6: "июнь", 7: "июль", 8: "август",
        9: "сентябрь", 10: "октябрь", 11: "ноябрь", 12: "декабрь"
    }
    today = datetime.now()

    def get_payment_month(pay_day):
        if pay_day >= today.day:
            return months_kk[today.month]
        else:
            next_month = today.month + 1 if today.month < 12 else 1
            return months_kk[next_month]

    text = f"💼 Семьяда айланған бюджет: <b>{family_budget:,.0f} сум</b>\n\n"

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

    bot.send_message(message.chat.id, text, reply_markup=main_menu(), parse_mode='HTML')

@bot.message_handler(func=lambda m: m.text == "⚙️ Өзгертиў")
def settings(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "❌ Бул бөлим тек админ ушын!")
        return
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("💳 Кредит өзгертиў", callback_data="set_credit"))
    markup.add(telebot.types.InlineKeyboardButton("🗑 Кредит ошириу", callback_data="del_credit"))
    markup.add(telebot.types.InlineKeyboardButton("🏠 Тұрақлы харажат өзгертиў", callback_data="set_fixed"))
    markup.add(telebot.types.InlineKeyboardButton("🗑 Тұрақлы харажат ошириу", callback_data="del_fixed"))
    markup.add(telebot.types.InlineKeyboardButton("➕ Таза кредит қосыў", callback_data="add_credit"))
    markup.add(telebot.types.InlineKeyboardButton("➕ Таза тұрақлы қосыў", callback_data="add_fixed"))
    markup.add(telebot.types.InlineKeyboardButton("🗑 Соңғы харажатларды көриу/өшириу", callback_data="view_recent_other"))
    markup.add(telebot.types.InlineKeyboardButton("📊 Категория лимити қою", callback_data="set_cat_limit"))
    markup.add(telebot.types.InlineKeyboardButton("📦 Backup жүклеп алыў", callback_data="do_backup"))
    bot.send_message(message.chat.id, "⚙️ Не өзгертесиз?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "do_backup")
def backup_button(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Бул тек админ ушын!")
        return
    bot.answer_callback_query(call.id, "📦 Таярланып атыр...")
    buf = generate_backup()
    bot.send_document(call.message.chat.id, buf, caption="📦 Дерекқордың толық резерв көширмеси (JSON)")

# ------------------- Категория лимити -------------------

@bot.callback_query_handler(func=lambda call: call.data == "set_cat_limit")
def set_cat_limit_menu(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Бул тек админ ушын!")
        return
    from database import get_all_category_limits
    limits = get_all_category_limits()
    text = "📊 <b>Хәзирги категория лимитлери:</b>\n\n"
    if limits:
        for cat, amt in limits:
            text += f"  • {cat}: <b>{float(amt):,.0f} сум</b>/ай\n"
    else:
        text += "  Ҳеш қандай лимит қойылмаған.\n"
    bot.send_message(call.message.chat.id, text, parse_mode='HTML')
    msg = bot.send_message(call.message.chat.id,
                          "Қайси категорияға лимит қоямыз?\nАтын жазың (мысалы: 🛒 Азық-аўқат):")
    bot.register_next_step_handler(msg, with_cancel(bot, cat_limit_name))

def cat_limit_name(message):
    category = message.text.strip()
    if not category:
        bot.send_message(message.chat.id, "❌ Категория аты бос болмасын!")
        return
    msg = bot.send_message(message.chat.id, f"💰 {category} ушын айлық лимит сумасын жаз (сум):\nМысалы: 2000000\n(лимитти өшириў ушын: 0)")
    bot.register_next_step_handler(msg, with_cancel(bot, cat_limit_amount), category)

def cat_limit_amount(message, category):
    from database import set_category_limit, delete_category_limit
    try:
        amount = float(message.text.replace(",", "").replace(" ", ""))
        if amount <= 0:
            delete_category_limit(category)
            bot.send_message(message.chat.id, f"✅ {category} ушын лимит өширилди.")
        else:
            set_category_limit(category, amount)
            bot.send_message(message.chat.id,
                             f"✅ Лимит қойылды!\n• {category}: <b>{amount:,.0f} сум</b>/ай",
                             parse_mode='HTML')
    except ValueError:
        bot.send_message(message.chat.id, "❌ Қате! Тек сан жазың.")

# ------------------- Кредит/Тұрақлы басқарыў -------------------

@bot.callback_query_handler(func=lambda call: call.data == "set_credit")
def set_credit_menu(call):
    month = datetime.now().strftime("%Y-%m")
    credits = get_credits_for_month(month)
    markup = telebot.types.InlineKeyboardMarkup()
    for cid, name, amount, pay_day in credits:
        markup.add(telebot.types.InlineKeyboardButton(
            f"{name}: {float(amount):,.0f} сум ({pay_day}-күн)",
            callback_data=f"ec_{cid}"
        ))
    bot.send_message(call.message.chat.id, "Қайси кредитти өзгертесиз?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "del_credit")
def del_credit_menu(call):
    month = datetime.now().strftime("%Y-%m")
    credits = get_credits_for_month(month)
    markup = telebot.types.InlineKeyboardMarkup()
    for cid, name, amount, _ in credits:
        markup.add(telebot.types.InlineKeyboardButton(
            f"🗑 {name}: {float(amount):,.0f} сум",
            callback_data=f"dc_{cid}"
        ))
    bot.send_message(call.message.chat.id, "Қайси кредитти оширесиз?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("dc_"))
def delete_credit(call):
    cid = int(call.data.split("_")[1])
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT name FROM credits WHERE id=%s", (cid,))
    name = c.fetchone()[0]
    c.execute("UPDATE credits SET is_active=0 WHERE id=%s", (cid,))
    conn.commit()
    conn.close()
    bot.answer_callback_query(call.id, f"✅ {name} оширилди!")
    bot.send_message(call.message.chat.id, f"✅ <b>{name}</b> оширилди!", parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: call.data == "del_fixed")
def del_fixed_menu(call):
    month = datetime.now().strftime("%Y-%m")
    fixed = get_fixed_for_month(month)
    markup = telebot.types.InlineKeyboardMarkup()
    for fid, name, amount, _ in fixed:
        markup.add(telebot.types.InlineKeyboardButton(
            f"🗑 {name}: {float(amount):,.0f} сум",
            callback_data=f"df_{fid}"
        ))
    bot.send_message(call.message.chat.id, "Қайси харажатты оширесиз?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("df_"))
def delete_fixed(call):
    fid = int(call.data.split("_")[1])
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT name FROM fixed_expenses WHERE id=%s", (fid,))
    name = c.fetchone()[0]
    c.execute("UPDATE fixed_expenses SET is_active=0 WHERE id=%s", (fid,))
    conn.commit()
    conn.close()
    bot.answer_callback_query(call.id, f"✅ {name} оширилди!")
    bot.send_message(call.message.chat.id, f"✅ <b>{name}</b> оширилди!", parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: call.data.startswith("ec_"))
def edit_credit(call):
    cid = int(call.data.split("_")[1])
    msg = bot.send_message(call.message.chat.id, "Таза сумма жаз (сум):\nМысалы: 450000")
    bot.register_next_step_handler(msg, with_cancel(bot, save_credit_amount), cid)

def save_credit_amount(message, cid):
    try:
        amount = float(message.text.replace(",", "").replace(" ", ""))
        msg = bot.send_message(message.chat.id, "Төлем число күнин жаз (1-31):\nМысалы: 15")
        bot.register_next_step_handler(msg, with_cancel(bot, save_credit_day), cid, amount)
    except ValueError:
        bot.send_message(message.chat.id, "❌ Қате! Тек сан жазың.")

def save_credit_day(message, cid, amount):
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
                         f"✅ Тазаланды!\n"
                         f"• Сумма: <b>{amount:,.0f} сум</b>\n"
                         f"• Төлем күни: {day}-күн",
                         parse_mode='HTML')
    except ValueError:
        bot.send_message(message.chat.id, "❌ Қате! 1-31 арасында жазың.")

@bot.callback_query_handler(func=lambda call: call.data == "set_fixed")
def set_fixed_menu(call):
    month = datetime.now().strftime("%Y-%m")
    fixed = get_fixed_for_month(month)
    markup = telebot.types.InlineKeyboardMarkup()
    for fid, name, amount, pay_day in fixed:
        markup.add(telebot.types.InlineKeyboardButton(
            f"{name}: {float(amount):,.0f} сум ({pay_day}-күн)",
            callback_data=f"ef_{fid}"
        ))
    bot.send_message(call.message.chat.id, "Қайси харажатты өзгертесиз?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("ef_"))
def edit_fixed(call):
    fid = int(call.data.split("_")[1])
    msg = bot.send_message(call.message.chat.id, "Таза сумма жаз (сум):\nМысалы: 600000")
    bot.register_next_step_handler(msg, with_cancel(bot, save_fixed_amount), fid)

def save_fixed_amount(message, fid):
    try:
        amount = float(message.text.replace(",", "").replace(" ", ""))
        msg = bot.send_message(message.chat.id, "Төлем число күнин жаз (1-31):\nМысалы: 5")
        bot.register_next_step_handler(msg, with_cancel(bot, save_fixed_day), fid, amount)
    except ValueError:
        bot.send_message(message.chat.id, "❌ Қате! Тек сан жазың.")

def save_fixed_day(message, fid, amount):
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
                         f"✅ Тазаланды!\n"
                         f"• Сумма: <b>{amount:,.0f} сум</b>\n"
                         f"• Төлем күни: {day}-күн",
                         parse_mode='HTML')
    except ValueError:
        bot.send_message(message.chat.id, "❌ Қате! 1-31 арасында жазың.")

@bot.callback_query_handler(func=lambda call: call.data == "add_credit")
def add_credit_start(call):
    msg = bot.send_message(call.message.chat.id, "Таза кредит атын жаз:\nМысалы: Kaspi кредит")
    bot.register_next_step_handler(msg, with_cancel(bot, add_credit_name))

def add_credit_name(message):
    name = message.text.strip()
    if not name:
        bot.send_message(message.chat.id, "❌ Аты бос болмасын!")
        return
    msg = bot.send_message(message.chat.id, f"💳 {name} суммасын жаз (сум):\nМысалы: 500000")
    bot.register_next_step_handler(msg, with_cancel(bot, add_credit_amount), name)

def add_credit_amount(message, name):
    try:
        amount = float(message.text.replace(",", "").replace(" ", ""))
        msg = bot.send_message(message.chat.id, "Төлем число күнин жаз (1-31):\nМысалы: 10")
        bot.register_next_step_handler(msg, with_cancel(bot, add_credit_day), name, amount)
    except ValueError:
        bot.send_message(message.chat.id, "❌ Қате! Тек сан жазың.")

def add_credit_day(message, name, amount):
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

@bot.callback_query_handler(func=lambda call: call.data == "add_fixed")
def add_fixed_start(call):
    msg = bot.send_message(call.message.chat.id, "Таза тұрақлы харажат атын жаз:\nМысалы: Интернет")
    bot.register_next_step_handler(msg, with_cancel(bot, add_fixed_name))

def add_fixed_name(message):
    name = message.text.strip()
    if not name:
        bot.send_message(message.chat.id, "❌ Аты бос болмасын!")
        return
    msg = bot.send_message(message.chat.id, f"🏠 {name} суммасын жаз (сум):\nМысалы: 200000")
    bot.register_next_step_handler(msg, with_cancel(bot, add_fixed_amount), name)

def add_fixed_amount(message, name):
    try:
        amount = float(message.text.replace(",", "").replace(" ", ""))
        msg = bot.send_message(message.chat.id, "Төлем число күнин жаз (1-31):\nМысалы: 5")
        bot.register_next_step_handler(msg, with_cancel(bot, add_fixed_day), name, amount)
    except ValueError:
        bot.send_message(message.chat.id, "❌ Қате! Тек сан жазың.")

def add_fixed_day(message, name, amount):
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

register_budget_handlers(bot)
register_expense_handlers(bot)
register_report_handlers(bot)
start_scheduler(bot, ADMIN_IDS)

if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    print(f"✅ Webhook орнатылды: {WEBHOOK_URL}/{BOT_TOKEN}")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
