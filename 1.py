# Правильные импорты
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackContext,
    CallbackQueryHandler
)
import logging
import openai
import sqlite3
# Настройки
TOKEN = "8155546438:AAGywyaZrtarVNHnlpVd6VD5LMJPiLYcKpU"
OPENAI_API_KEY = "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"
ADMIN_PASSWORD = "admin123"  # Пароль для админ-панели

# Инициализация OpenAI
openai.api_key = OPENAI_API_KEY

# Инициализация базы данных
conn = sqlite3.connect('bot_stats.db', check_same_thread=False)
cursor = conn.cursor()

# Создание таблиц
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        visits INTEGER DEFAULT 0,
        has_subscription INTEGER DEFAULT 0
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS purchases (
        purchase_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        date TEXT
    )
''')
conn.commit()

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def add_user(user_id, username):
    cursor.execute('INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)', (user_id, username))
    cursor.execute('UPDATE users SET visits = visits + 1 WHERE user_id = ?', (user_id,))
    conn.commit()

def add_purchase(user_id):
    cursor.execute('UPDATE users SET has_subscription = 1 WHERE user_id = ?', (user_id,))
    cursor.execute('INSERT INTO purchases (user_id, date) VALUES (?, datetime("now"))', (user_id,))
    conn.commit()

def get_stats():
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM purchases')
    total_purchases = cursor.fetchone()[0]
    
    return f"👥 Всего пользователей: {total_users}\n💰 Подписок куплено: {total_purchases}"

# Обработчики для бота
def start(update: Update, context: CallbackContext):
    user = update.effective_user
    add_user(user.id, user.username)
    update.message.reply_text(
        "Привет! Я бот с нейросетью. Задай мне любой вопрос!\n"
        "Для доступа к админ-панели введи /admin"
    )

def admin_panel(update: Update, context: CallbackContext):
    update.message.reply_text("Введите пароль для доступа к админ-панели:")

def handle_admin_password(update: Update, context: CallbackContext):
    if update.message.text == ADMIN_PASSWORD:
        keyboard = [
            [InlineKeyboardButton("📊 Статистика", callback_data='stats')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text("Админ-панель:", reply_markup=reply_markup)
    else:
        update.message.reply_text("Неверный пароль!")

def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    
    if query.data == 'stats':
        stats = get_stats()
        query.edit_message_text(text=stats)

def handle_message(update: Update, context: CallbackContext):
    user = update.effective_user
    add_user(user.id, user.username)
    
    # Генерация ответа через OpenAI
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": update.message.text}]
        )
        answer = response.choices[0].message['content']
    except Exception as e:
        answer = f"Ошибка: {str(e)}"
    
    update.message.reply_text(answer)

def handle_purchase(update: Update, context: CallbackContext):
    user = update.effective_user
    add_purchase(user.id)
    update.message.reply_text("✅ Спасибо за покупку подписки!")

def main():
    updater = Updater(TOKEN)

    dp = updater.dispatcher

    dp.add_handler(CommandHandler('start', start))
    dp.add_handler(CommandHandler('admin', admin_panel))
    dp.add_handler(CommandHandler('buy', handle_purchase))
    dp.add_handler(MessageHandler(filters.text & ~filters.command, handle_message))
    dp.add_handler(MessageHandler(filters.regex(r'^/admin'), handle_admin_password))
    dp.add_handler(CallbackQueryHandler(button_handler))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()