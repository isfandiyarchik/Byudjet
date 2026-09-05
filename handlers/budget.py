from database import get_conn
from datetime import datetime
import telebot

def register_budget_handlers(bot):

    @bot.message_handler(func=lambda m: m.text == "➕ Бюджет қосыў")
    def budget_source(message):
        markup = telebot.types.InlineKeyboardMarkup()
        markup.add(telebot.types.InlineKeyboardButton("💵 Айлық", callback_data="bdg_aylik"))
        markup.add(telebot.types.InlineKeyboardButton("☀️ Солнечный панель", callback_data="bdg_solar"))
        markup.add(telebot.types.InlineKeyboardButton("🤝 Жәрдем пул", callback_data="bdg_jardem"))
        markup.add(telebot.types.InlineKeyboardButton("📥 Басқа", callback_data="bdg_baska"))
        bot.send_message(message.chat.id, "Кай Бюджет таңласыз:", reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("bdg_"))
    def budget_amount(call):
        sources = {
            "bdg_aylik": "Айлық",
            "bdg_solar": "Солнечный панель",
            "bdg_jardem": "Жәрдем пул",
            "bdg_baska": "Басқа"
        }
        source = sources.get(call.data, "Басқа")
        msg = bot.send_message(call.message.chat.id, f"💵 {source} суммасын жаз (сум):")
        bot.register_next_step_handler(msg, save_budget, source, call.from_user.id)

    def save_budget(message, source, telegram_id):
        try:
            amount = float(message.text.replace(",", "").replace(" ", ""))
            conn = get_conn()
            c = conn.cursor()
            c.execute(
                "INSERT INTO budget (telegram_id, source, amount, created_at) VALUES (%s,%s,%s,%s)",
                (telegram_id, source, amount, str(datetime.now())))
            conn.commit()
            conn.close()
            bot.send_message(message.chat.id, f"✅ {source}: +{amount:,.0f} сум қосылды!")
        except ValueError:
            bot.send_message(message.chat.id, "❌ Қате! Тек сан жазың. Мысалы: 500000")
