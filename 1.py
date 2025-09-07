import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import g4f
import html
import logging
import time
import threading
import json
import os
from datetime import datetime, timedelta

# Настройка логирования
logger = logging.getLogger()
logger.setLevel(logging.INFO)

formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

file_handler = logging.FileHandler('bot.log', encoding='utf-8')
file_handler.setFormatter(formatter)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(stream_handler)

# Конфигурация
BOT_TOKEN = "7767598119:AAG5DWxTCCVPyyPO0MUMXV7EC8c-zbzQQ8I"
SPONSOR_CHANNELS = ['@DedlyxCoder']
ADMIN_ID = 7955714952
GPT_TIMEOUT = 25

# Информация о создателях
CREATORS_INFO = """👥 <b>Создатели бота:</b>

• @DedlyAI - разработчик
• @DedlySupport - поддержка
• @DedlyxCoder - канал проекта"""

# Информация о боте
PROJECT_INFO = """🚀 <b>DedlyAI Bot</b>

🤖 Умный ассистент на основе GPT-4
💬 Общайтесь с искусственным интеллектом
⚡ Быстрые и качественные ответы
🎯 Простой и удобный интерфейс

<b>Тарифы:</b>
• 🆓 Бесплатный - 5 запросов в день
• 💎 Премиум - неограниченно (100 руб)"""

# Лимиты запросов
FREE_REQUEST_LIMIT = 5
PREMIUM_REQUEST_LIMIT = 10000  # Практически неограниченно

bot = telebot.TeleBot(BOT_TOKEN)
user_states = {}
processing_messages = {}

# Загрузка данных пользователей
def load_users_data():
    if os.path.exists('users_data.json'):
        with open('users_data.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Конвертируем строковые ключи обратно в целые числа
            return {int(k): v for k, v in data.items()}
    return {}

# Сохранение данных пользователей
def save_users_data():
    with open('users_data.json', 'w', encoding='utf-8') as f:
        json.dump(users_data, f, ensure_ascii=False, indent=4)

users_data = load_users_data()

# Загрузка настроек оплаты
def load_payment_settings():
    if os.path.exists('payment_settings.json'):
        with open('payment_settings.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"payment_url": "", "price": 100, "currency": "USDT"}

# Сохранение настроек оплаты
def save_payment_settings(settings):
    with open('payment_settings.json', 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)

payment_settings = load_payment_settings()

# Загрузка ожидающих оплат
def load_pending_payments():
    if os.path.exists('pending_payments.json'):
        with open('pending_payments.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

# Сохранение ожидающих оплат
def save_pending_payments(payments):
    with open('pending_payments.json', 'w', encoding='utf-8') as f:
        json.dump(payments, f, ensure_ascii=False, indent=4)

pending_payments = load_pending_payments()

# Вспомогательные функции
def log_user_event(user, action: str):
    username = user.username or "без юзернейма"
    logger.info(f"User {user.id} (@{username}) {action}")

def check_subscription(user_id: int) -> bool:
    try:
        for channel in SPONSOR_CHANNELS:
            member = bot.get_chat_member(channel, user_id)
            if member.status not in ["member", "administrator", "creator"]:
                return False
        return True
    except Exception as e:
        logger.error(f"Ошибка проверки подпики: {str(e)}")
        return False

def update_user_stats(user):
    now = time.time()
    user_id = user.id
    username = user.username or "без юзернейма"
    
    if user_id in users_data:
        users_data[user_id].update({
            'last_active': now,
            'request_count': users_data[user_id].get('request_count', 0) + 1,
            'username': username
        })
    else:
        users_data[user_id] = {
            'first_seen': now,
            'last_active': now,
            'request_count': 1,
            'username': username,
            'premium': False,
            'premium_until': None,
            'daily_requests': 0,
            'last_request_date': datetime.now().strftime('%Y-%m-%d')
        }
    
    # Сброс счетчика daily_requests если день сменился
    current_date = datetime.now().strftime('%Y-%m-%d')
    if users_data[user_id].get('last_request_date') != current_date:
        users_data[user_id]['daily_requests'] = 0
        users_data[user_id]['last_request_date'] = current_date
    
    users_data[user_id]['daily_requests'] = users_data[user_id].get('daily_requests', 0) + 1
    save_users_data()

def can_make_request(user_id):
    if user_id not in users_data:
        return True, ""
    
    user_data = users_data[user_id]
    
    # Проверка Premium статуса
    if user_data.get('premium', False):
        premium_until = user_data.get('premium_until')
        if premium_until and datetime.now().timestamp() < premium_until:
            return True, ""
        else:
            # Срок Premium истек
            users_data[user_id]['premium'] = False
            save_users_data()
    
    # Проверка дневного лимита для бесплатных пользователей
    if user_data.get('daily_requests', 0) >= FREE_REQUEST_LIMIT:
        return False, f"⚠️ <b>Лимит запросов исчерпан</b>\n\nВы использовали все {FREE_REQUEST_LIMIT} бесплатных запросов сегодня.\n\nПриобретите Premium-подписку для неограниченного общения!"
    
    return True, ""

# Клавиатуры
def subscription_keyboard():
    try:
        chat = bot.get_chat(SPONSOR_CHANNELS[0])
        return InlineKeyboardMarkup().row(
            InlineKeyboardButton("📢 Подписаться", url=f"t.me/{chat.username}"),
            InlineKeyboardButton("✅ Проверить", callback_data="check_sub")
        )
    except Exception as e:
        logger.error(f"Ошибка клавиатуры: {str(e)}")
        return None

def main_menu_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        KeyboardButton("💬 Задать вопрос"),
        KeyboardButton("🔄 Сбросить диалог"),
        KeyboardButton("⭐ Лидеры"),
        KeyboardButton("👨‍💻 Создатель"),
        KeyboardButton("📢 Канал проекта"),
        KeyboardButton("ℹ️ О боте"),
        KeyboardButton("💎 Premium")
    ]
    keyboard.add(*buttons)
    return keyboard

def premium_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton(f"💰 Купить Premium ({payment_settings['price']} {payment_settings['currency']})", callback_data="buy_premium"),
        InlineKeyboardButton("📊 Моя статистика", callback_data="my_stats"),
        InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")
    )
    return keyboard

def admin_menu():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"),
        InlineKeyboardButton("👤 Юзернеймы", callback_data="admin_users"),
        InlineKeyboardButton("💎 Премиум", callback_data="admin_premium"),
        InlineKeyboardButton("💰 Оплата", callback_data="admin_payment"),
        InlineKeyboardButton("📤 Экспорт", callback_data="admin_export"),
        InlineKeyboardButton("⚙️ Создатели", callback_data="admin_creators")
    )
    return keyboard

def payment_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    
    if payment_settings['payment_url']:
        keyboard.add(
            InlineKeyboardButton("💳 Оплатить", url=payment_settings['payment_url']),
            InlineKeyboardButton("✅ Я оплатил", callback_data="confirm_payment"),
            InlineKeyboardButton("🔙 Назад", callback_data="back_to_premium")
        )
    else:
        keyboard.add(
            InlineKeyboardButton("❌ Ссылка оплаты не настроена", callback_data="no_payment"),
            InlineKeyboardButton("🔙 Назад", callback_data="back_to_premium")
        )
    
    return keyboard

def admin_premium_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("👥 Список Premium", callback_data="premium_list"),
        InlineKeyboardButton("➕ Добавить Premium", callback_data="premium_add"),
        InlineKeyboardButton("📋 Ожидающие оплаты", callback_data="pending_payments"),
        InlineKeyboardButton("🔙 Назад", callback_data="admin_back")
    )
    return keyboard

def admin_payment_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("🔗 Изменить ссылку оплаты", callback_data="change_payment_url"),
        InlineKeyboardButton("💰 Изменить цену", callback_data="change_payment_price"),
        InlineKeyboardButton("🔙 Назад", callback_data="admin_back")
    )
    return keyboard

def pending_payments_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    if not pending_payments:
        keyboard.add(InlineKeyboardButton("📭 Нет ожидающих оплат", callback_data="no_action"))
    else:
        for i, payment in enumerate(pending_payments[:5]):  # Показываем первые 5
            user_id = payment['user_id']
            username = payment.get('username', 'Unknown')
            keyboard.add(InlineKeyboardButton(f"👤 {username}", callback_data=f"review_payment_{i}"))
    
    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="admin_premium"))
    return keyboard

# Функции, которые отсутствовали в предыдущей версии
def show_leaders(chat_id):
    if not users_data:
        bot.send_message(chat_id, "📊 <b>Пока нет данных о лидерах</b>", parse_mode='HTML')
        return
        
    # Сортируем пользователей по количеству запросов
    sorted_users = sorted(users_data.items(), key=lambda x: x[1].get('request_count', 0), reverse=True)
    
    leaders_text = "🏆 <b>Топ-5 пользователей по запросам:</b>\n\n"
    for i, (user_id, data) in enumerate(sorted_users[:5], 1):
        username = data.get('username', 'без юзернейма')
        if username == "без юзернейма":
            username = f"Пользователь {user_id}"
        
        premium_status = " 💎" if data.get('premium', False) and data.get('premium_until', 0) > time.time() else ""
        leaders_text += f"{i}. {username}{premium_status} - {data.get('request_count', 0)} запросов\n"
    
    bot.send_message(chat_id, leaders_text, parse_mode='HTML')

def show_premium_info(message):
    bot.send_message(
        message.chat.id,
        "💎 <b>Premium подписка</b>\n\n"
        "Приобретите Premium-подписку для неограниченного общения с ботом!\n\n"
        "• Неограниченное количество запросов\n"
        "• Приоритетная обработка\n"
        "• Поддержка развития проекта\n\n"
        f"Стоимость: <b>{payment_settings['price']} {payment_settings['currency']}</b>",
        parse_mode='HTML',
        reply_markup=premium_keyboard()
    )

def show_admin_premium(call):
    premium_users = [uid for uid, data in users_data.items() if data.get('premium', False) and data.get('premium_until', 0) > time.time()]
    
    text = (
        f"💎 <b>Панель управления Premium</b>\n\n"
        f"Активных Premium-пользователей: {len(premium_users)}\n"
        f"Ожидающих оплат: {len(pending_payments)}\n\n"
        "Выберите действие:"
    )
    
    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        parse_mode='HTML',
        reply_markup=admin_premium_keyboard()
    )

def export_data(call):
    with open("users_data.json", "rb") as f:
        bot.send_document(call.message.chat.id, f)
    bot.answer_callback_query(call.id, "Данные экспортированы")

def show_admin_users(call):
    recent_users = list(users_data.values())[-10:]
    user_list = "\n".join([f"├ @{u['username']} ({u['request_count']} запросов)" for u in recent_users])
    
    response = f"👤 <b>Последние 10 пользователей:</b>\n\n{user_list}"
    
    bot.edit_message_text(
        response,
        call.message.chat.id,
        call.message.message_id,
        parse_mode='HTML',
        reply_markup=admin_menu()
    )

def show_admin_payment(call):
    text = (
        f"💰 <b>Настройки оплаты</b>\n\n"
        f"Ссылка: {payment_settings['payment_url'] or 'Не установлена'}\n"
        f"Цена: {payment_settings['price']} {payment_settings['currency']}\n\n"
        "Выберите действие:"
    )
    
    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        parse_mode='HTML',
        reply_markup=admin_payment_keyboard()
    )

def show_admin_settings(call):
    bot.edit_message_text(
        "⚙️ <b>Настройки бота</b>\n\n"
        "Здесь можно настроить различные параметры бота",
        call.message.chat.id,
        call.message.message_id,
        parse_mode='HTML',
        reply_markup=admin_menu()
    )

def get_admin_data(action):
    if action == "stats":
        active_users = len([u for u in users_data.values() if time.time() - u['last_active'] < 86400])
        total_requests = sum(u['request_count'] for u in users_data.values())
        premium_users = len([u for u in users_data.values() if u.get('premium', False) and u.get('premium_until', 0) > time.time()])
        
        return f"""📊 <b>Статистика бота</b>

├ Пользователей: <b>{len(users_data)}</b>
├ Активных (за 24ч): <b>{active_users}</b>
├ Premium-пользователей: <b>{premium_users}</b>
└ Всего запросов: <b>{total_requests}</b>"""
    
    elif action == "users":
        recent_users = list(users_data.values())[-10:]
        user_list = "\n".join([f"├ @{u['username']} ({u['request_count']} запросов)" for u in recent_users])
        
        return f"👤 <b>Последние 10 пользователей:</b>\n\n{user_list}"

# Основные функции
def send_main_menu(chat_id):
    bot.send_message(
        chat_id, 
        "🤖 <b>Добро пожаловать в главное меню!</b>\n\n"
        "Выберите действие на клавиатуре ниже или просто задайте вопрос нейросети.",
        parse_mode='HTML', 
        reply_markup=main_menu_keyboard()
    )

def handle_unsubscribed(chat_id, user_id):
    try:
        msg = bot.send_message(
            chat_id, 
            "📢 <b>Для использования бота необходимо подписаться на наш канал!</b>\n\n"
            "После подписки нажмите кнопку '✅ Проверить'",
            parse_mode='HTML',
            reply_markup=subscription_keyboard()
        )
        user_states[user_id] = {'state': 'awaiting_sub', 'message_id': msg.message_id}
    except Exception as e:
        logger.error(f"Unsubscribed error: {str(e)}")

def process_gpt(user, message):
    try:
        # Показываем что бот "печатает"
        bot.send_chat_action(message.chat.id, 'typing')
        
        response = g4f.ChatCompletion.create(
            model=g4f.models.gpt_4,
            messages=[{"role": "user", "content": message.text}],
            timeout=GPT_TIMEOUT
        )
        
        # Отправляем ответ с форматированием
        bot.send_message(message.chat.id, html.unescape(response), parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"GPT error: {str(e)}")
        bot.send_message(
            message.chat.id, 
            "⚠️ <b>Произошла ошибка при обработке запроса</b>\n\n"
            "Попробуйте повторить запрос позже.",
            parse_mode='HTML'
        )
    finally:
        processing_messages.pop(message.chat.id, None)

# Обработчики
@bot.message_handler(commands=['start'])
def handle_start(message):
    try:
        user = message.from_user
        log_user_event(user, "старт")
        update_user_stats(user)
        
        if user.id in user_states:
            try: 
                bot.delete_message(message.chat.id, user_states[user.id]['message_id'])
            except: 
                pass
            
        if check_subscription(user.id):
            send_main_menu(message.chat.id)
        else:
            msg = bot.send_message(
                message.chat.id, 
                "📢 <b>Для использования бота необходимо подписаться на наш канал!</b>\n\n"
                "После подписки нажмите кнопку '✅ Проверить'",
                parse_mode='HTML',
                reply_markup=subscription_keyboard()
            )
            user_states[user.id] = {'state': 'awaiting_sub', 'message_id': msg.message_id}
            
    except Exception as e:
        logger.error(f"Ошибка старта: {str(e)}")

@bot.message_handler(commands=['admin'])
def handle_admin_command(message):
    if message.from_user.id != ADMIN_ID:
        return
        
    bot.send_message(
        message.chat.id,
        "👨‍💻 <b>Панель администратора</b>",
        parse_mode='HTML',
        reply_markup=admin_menu()
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    try:
        logger.info(f"Received callback: {call.data}")
        
        if call.data == "check_sub":
            handle_subscription(call)
        elif call.data == "buy_premium":
            show_payment_info(call)
        elif call.data == "my_stats":
            show_user_stats(call)
        elif call.data == "back_to_main":
            bot.delete_message(call.message.chat.id, call.message.message_id)
            send_main_menu(call.message.chat.id)
        elif call.data == "back_to_premium":
            bot.edit_message_text(
                "💎 <b>Premium подписка</b>\n\n"
                "Приобретите Premium-подписку для неограниченного общения с ботом!\n\n"
                "• Неограниченное количество запросов\n"
                "• Приоритетная обработка\n"
                "• Поддержка развития проекта\n\n"
                f"Стоимость: <b>{payment_settings['price']} {payment_settings['currency']}</b>",
                call.message.chat.id,
                call.message.message_id,
                parse_mode='HTML',
                reply_markup=premium_keyboard()
            )
        elif call.data == "confirm_payment":
            confirm_payment(call)
        elif call.data == "no_payment":
            bot.answer_callback_query(call.id, "Администратор еще не настроил оплату", show_alert=True)
        elif call.data.startswith("admin_"):
            handle_admin_action(call)
        elif call.data.startswith("premium_"):
            handle_premium_admin_action(call)
        elif call.data.startswith("review_payment_"):
            review_payment(call)
        elif call.data == "pending_payments":
            show_pending_payments(call)
        elif call.data == "change_payment_url":
            handle_change_payment_url(call)
        elif call.data == "change_payment_price":
            handle_change_payment_price(call)
        elif call.data == "admin_back":
            bot.edit_message_text(
                "👨‍💻 <b>Панель администратора</b>",
                call.message.chat.id,
                call.message.message_id,
                parse_mode='HTML',
                reply_markup=admin_menu()
            )
        elif call.data == "admin_premium":
            show_admin_premium(call)
        elif call.data == "admin_payment":
            show_admin_payment(call)
        elif call.data.startswith("approve_") or call.data.startswith("reject_"):
            handle_payment_review_action(call)
            
        bot.answer_callback_query(call.id)
    except Exception as e:
        logger.error(f"Callback error: {str(e)}")
        try:
            bot.answer_callback_query(call.id, "Произошла ошибка при обработке запроса")
        except:
            pass

def handle_change_payment_url(call):
    if call.from_user.id != ADMIN_ID:
        return
        
    user_states[call.from_user.id] = {'state': 'change_payment_url'}
    bot.send_message(
        call.message.chat.id,
        "Введите новую ссылку для оплаты:",
        reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 Назад", callback_data="admin_payment"))
    )

def handle_change_payment_price(call):
    if call.from_user.id != ADMIN_ID:
        return
        
    user_states[call.from_user.id] = {'state': 'change_payment_price'}
    bot.send_message(
        call.message.chat.id,
        "Введите новую цену и валюту через пробел:\n\nПример: <code>100 USDT</code>",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 Назад", callback_data="admin_payment"))
    )

def handle_subscription(call):
    user = call.from_user
    try:
        time.sleep(1)
        if check_subscription(user.id):
            try: 
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except: 
                bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
            send_main_menu(call.message.chat.id)
            bot.answer_callback_query(call.id, "✅ Подписка подтверждена! Теперь вы можете использовать бота.", show_alert=True)
        else:
            bot.answer_callback_query(call.id, "❌ Вы еще не подписались на канал! Подпитесь и нажмите снова.", show_alert=True)
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=subscription_keyboard())
    except Exception as e:
        logger.error(f"Subscription error: {str(e)}")

def show_payment_info(call):
    if not payment_settings['payment_url']:
        bot.answer_callback_query(call.id, "Оплата временно недоступна", show_alert=True)
        return
        
    bot.edit_message_text(
        f"💳 <b>Оплата Premium подписки</b>\n\n"
        f"Для получения Premium-доступа оплатите <b>{payment_settings['price']} {payment_settings['currency']}</b>\n\n"
        "1. Нажмите кнопку '💳 Оплатить' для перехода к оплате\n"
        "2. После оплаты нажмите '✅ Я оплатил'\n"
        "3. Администратор проверит оплату и активирует ваш статус\n\n"
        "Обычно активация занимает не более 24 часов.",
        call.message.chat.id,
        call.message.message_id,
        parse_mode='HTML',
        reply_markup=payment_keyboard()
    )

def confirm_payment(call):
    user_id = call.from_user.id
    username = call.from_user.username or "без username"
    
    # Проверяем, нет ли уже ожидающей оплаты от этого пользователя
    for payment in pending_payments:
        if payment['user_id'] == user_id:
            bot.answer_callback_query(call.id, "Вы уже отправили запрос на проверку оплаты", show_alert=True)
            return
    
    # Добавляем в список ожидающих оплат
    pending_payments.append({
        'user_id': user_id,
        'username': username,
        'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'status': 'pending'
    })
    save_pending_payments(pending_payments)
    
    # Уведомление администратору
    try:
        bot.send_message(
            ADMIN_ID,
            f"💎 Новый запрос на проверку оплаты\n\n"
            f"Пользователь: @{username}\n"
            f"ID: {user_id}\n"
            f"Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("📋 К ожидающим оплатам", callback_data="pending_payments")
            )
        )
    except Exception as e:
        logger.error(f"Error sending admin notification: {str(e)}")
    
    bot.edit_message_text(
        "✅ <b>Запрос на проверку оплаты отправлен администратору</b>\n\n"
        "Обычно проверка занимает не более 24 часов. Вы получите уведомление, как только ваш Premium-статус будет активирован.",
        call.message.chat.id,
        call.message.message_id,
        parse_mode='HTML'
    )

def show_user_stats(call):
    user_id = call.from_user.id
    if user_id in users_data:
        user_data = users_data[user_id]
        premium_status = "✅ Активна" if user_data.get('premium', False) and user_data.get('premium_until', 0) > time.time() else "❌ Не активна"
        
        if user_data.get('premium_until'):
            premium_until = datetime.fromtimestamp(user_data['premium_until']).strftime('%d.%m.%Y %H:%M')
        else:
            premium_until = "Не установлено"
        
        stats_text = (
            f"📊 <b>Ваша статистика</b>\n\n"
            f"👤 Имя: @{call.from_user.username or 'Не установлено'}\n"
            f"🆔 ID: {call.from_user.id}\n"
            f"💎 Premium: {premium_status}\n"
            f"📅 До: {premium_until}\n"
            f"📞 Всего запросов: {user_data.get('request_count', 0)}\n"
            f"📅 Запросов сегодня: {user_data.get('daily_requests', 0)}/{FREE_REQUEST_LIMIT if not user_data.get('premium', False) else '∞'}"
        )
    else:
        stats_text = "📊 <b>Ваша статистика</b>\n\nДанные не найдены."
    
    bot.edit_message_text(
        stats_text,
        call.message.chat.id,
        call.message.message_id,
        parse_mode='HTML',
        reply_markup=premium_keyboard()
    )

def handle_admin_action(call):
    if call.from_user.id != ADMIN_ID:
        return
    
    action = call.data.split('_')[1]
    
    if action == "creators":
        response = CREATORS_INFO
        bot.edit_message_text(
            response,
            call.message.chat.id,
            call.message.message_id,
            parse_mode='HTML',
            reply_markup=admin_menu()
        )
    elif action == "export":
        export_data(call)
    elif action == "premium":
        show_admin_premium(call)
    elif action == "payment":
        show_admin_payment(call)
    elif action == "back":
        bot.edit_message_text(
            "👨‍💻 <b>Панель администратора</b>",
            call.message.chat.id,
            call.message.message_id,
            parse_mode='HTML',
            reply_markup=admin_menu()
        )
    else:
        response = get_admin_data(action)
        bot.edit_message_text(
            response,
            call.message.chat.id,
            call.message.message_id,
            parse_mode='HTML',
            reply_markup=admin_menu()
        )

def show_premium_admin_panel(call):
    premium_users = [uid for uid, data in users_data.items() if data.get('premium', False) and data.get('premium_until', 0) > time.time()]
    
    text = (
        f"💎 <b>Панель управления Premium</b>\n\n"
        f"Активных Premium-пользователей: {len(premium_users)}\n"
        f"Ожидающих оплат: {len(pending_payments)}\n\n"
        "Выберите действие:"
    )
    
    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        parse_mode='HTML',
        reply_markup=admin_premium_keyboard()
    )

def show_payment_admin_panel(call):
    text = (
        f"💰 <b>Настройки оплаты</b>\n\n"
        f"Ссылка: {payment_settings['payment_url'] or 'Не установлена'}\n"
        f"Цена: {payment_settings['price']} {payment_settings['currency']}\n\n"
        "Выберите действие:"
    )
    
    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        parse_mode='HTML',
        reply_markup=admin_payment_keyboard()
    )

def show_pending_payments(call):
    text = f"📋 <b>Ожидающие оплаты</b>\n\nВсего: {len(pending_payments)}\n\n"
    
    if not pending_payments:
        text += "Нет ожидающих оплат"
    else:
        for i, payment in enumerate(pending_payments[:5]):  # Показываем первые 5
            text += f"{i+1}. @{payment['username']} (ID: {payment['user_id']})\n   Дата: {payment['date']}\n\n"
    
    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        parse_mode='HTML',
        reply_markup=pending_payments_keyboard()
    )

def review_payment(call):
    payment_index = int(call.data.split('_')[-1])
    
    if payment_index >= len(pending_payments):
        bot.answer_callback_query(call.id, "Оплата не найдена", show_alert=True)
        return
    
    payment = pending_payments[payment_index]
    user_id = payment['user_id']
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("✅ Подтвердить (30 дней)", callback_data=f"approve_30_{payment_index}"),
        InlineKeyboardButton("✅ Подтвердить (90 дней)", callback_data=f"approve_90_{payment_index}"),
        InlineKeyboardButton("✅ Подтвердить (бессрочно)", callback_data=f"approve_forever_{payment_index}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{payment_index}"),
        InlineKeyboardButton("🔙 Назад", callback_data="pending_payments")
    )
    
    bot.edit_message_text(
        f"👤 <b>Запрос на проверку оплаты</b>\n\n"
        f"Пользователь: @{payment['username']}\n"
        f"ID: {user_id}\n"
        f"Дата: {payment['date']}\n\n"
        f"Выберите действие:",
        call.message.chat.id,
        call.message.message_id,
        parse_mode='HTML',
        reply_markup=keyboard
    )

def handle_premium_admin_action(call):
    if call.from_user.id != ADMIN_ID:
        return
    
    if call.data == "premium_list":
        premium_users = []
        for uid, data in users_data.items():
            if data.get('premium', False) and data.get('premium_until', 0) > time.time():
                premium_until = datetime.fromtimestamp(data['premium_until']).strftime('%d.%m.%Y')
                premium_users.append(f"@{data['username']} до {premium_until}")
        
        text = "💎 <b>Активные Premium-пользователи:</b>\n\n" + "\n".join(premium_users) if premium_users else "Нет активных Premium-пользователей"
        
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 Назад", callback_data="admin_premium"))
        )
    
    elif call.data == "premium_add":
        user_states[call.from_user.id] = {'state': 'admin_add_premium'}
        bot.edit_message_text(
            "Введите ID пользователя и срок подписки в днях через пробел:\n\nПример: <code>123456789 30</code>\nДля бессрочной подписки введите 0",
            call.message.chat.id,
            call.message.message_id,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 Назад", callback_data="admin_premium"))
        )
    
    elif call.data.startswith("approve_") or call.data.startswith("reject_"):
        handle_payment_review_action(call)
    
    elif call.data == "admin_back":
        bot.edit_message_text(
            "👨‍💻 <b>Панель администратора</b>",
            call.message.chat.id,
            call.message.message_id,
            parse_mode='HTML',
            reply_markup=admin_menu()
        )

def handle_payment_review_action(call):
    try:
        action_parts = call.data.split('_')
        action = action_parts[0]
        payment_index = int(action_parts[-1])
        
        logger.info(f"Processing payment review: {action}, index: {payment_index}")
        
        if payment_index >= len(pending_payments):
            bot.answer_callback_query(call.id, "Оплата не найдена", show_alert=True)
            return
        
        payment = pending_payments[payment_index]
        user_id = payment['user_id']
        
        if action == "approve":
            # Определяем срок подписки
            if action_parts[1] == "30":
                days = 30
            elif action_parts[1] == "90":
                days = 90
            else:  # forever
                days = 36500  # ~100 лет (практически бессрочно)
            
            # Активируем Premium
            if user_id not in users_data:
                users_data[user_id] = {
                    'username': payment['username'],
                    'request_count': 0,
                    'premium': True,
                    'premium_until': (datetime.now() + timedelta(days=days)).timestamp(),
                    'first_seen': time.time(),
                    'last_active': time.time()
                }
            else:
                users_data[user_id]['premium'] = True
                users_data[user_id]['premium_until'] = (datetime.now() + timedelta(days=days)).timestamp()
            
            save_users_data()
            
            # Уведомляем пользователя
            try:
                if days == 36500:
                    duration_text = "бессрочный"
                else:
                    duration_text = f"{days} дней"
                
                bot.send_message(
                    user_id,
                    f"🎉 <b>Вам активирована Premium-подписка!</b>\n\n"
                    f"Срок действия: {duration_text}\n"
                    f"До: {(datetime.now() + timedelta(days=days)).strftime('%d.%m.%Y')}\n\n"
                    f"Теперь вам доступно неограниченное количество запросов!",
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.error(f"Error sending notification to user: {e}")
            
            # Удаляем из ожидающих
            pending_payments.pop(payment_index)
            save_pending_payments(pending_payments)
            
            # Отвечаем на callback
            bot.answer_callback_query(call.id, f"✅ Premium активирован на {days} дней")
            
            # Редактируем сообщение
            bot.edit_message_text(
                f"✅ Premium-подписка активирована для пользователя @{payment['username']} на {days} дней",
                call.message.chat.id,
                call.message.message_id,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 К ожидающим", callback_data="pending_payments"))
            )
        
        elif action == "reject":
            # Уведомляем пользователя
            try:
                bot.send_message(
                    user_id,
                    "❌ <b>Ваш запрос на Premium-подписку отклонен</b>\n\n"
                    "Возможно, оплата не была обнаружена. Если вы уверены, что оплатили, свяжитесь с администратором.",
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.error(f"Error sending rejection notification: {e}")
            
            # Удаляем из ожидающих
            pending_payments.pop(payment_index)
            save_pending_payments(pending_payments)
            
            # Отвечаем на callback
            bot.answer_callback_query(call.id, "❌ Запрос отклонен")
            
            # Редактируем сообщение
            bot.edit_message_text(
                f"❌ Запрос на Premium от @{payment['username']} отклонен",
                call.message.chat.id,
                call.message.message_id,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 К ожидающим", callback_data="pending_payments"))
            )
    
    except Exception as e:
        logger.error(f"Error in handle_payment_review_action: {str(e)}")
        bot.answer_callback_query(call.id, "⚠️ Произошла ошибка при обработке")

@bot.message_handler(func=lambda m: True)
def handle_message(message):
    try:
        user = message.from_user
        user_id = user.id
        
        # Обработка состояний администратора
        if user_id == ADMIN_ID and user_id in user_states:
            state = user_states[user_id]['state']
            
            if state == 'admin_add_premium':
                # Админ добавляет Premium
                try:
                    parts = message.text.split()
                    target_user_id = int(parts[0])
                    days = int(parts[1])
                    
                    if target_user_id not in users_data:
                        users_data[target_user_id] = {
                            'username': 'админ-добавлен',
                            'request_count': 0,
                            'premium': True,
                            'premium_until': (datetime.now() + timedelta(days=days)).timestamp() if days > 0 else (datetime.now() + timedelta(days=36500)).timestamp(),
                            'first_seen': time.time(),
                            'last_active': time.time()
                        }
                    else:
                        users_data[target_user_id]['premium'] = True
                        if days > 0:
                            users_data[target_user_id]['premium_until'] = (datetime.now() + timedelta(days=days)).timestamp()
                        else:
                            users_data[target_user_id]['premium_until'] = (datetime.now() + timedelta(days=36500)).timestamp()
                    
                    save_users_data()
                    
                    # Уведомление пользователю, если возможно
                    try:
                        duration_text = "бессрочный" if days == 0 else f"{days} дней"
                        bot.send_message(
                            target_user_id,
                            f"🎉 <b>Вам активирована Premium-подписка!</b>\n\n"
                            f"Срок действия: {duration_text}\n"
                            f"До: {(datetime.now() + timedelta(days=days if days > 0 else 36500)).strftime('%d.%m.%Y')}\n\n"
                            f"Теперь вам доступно неограниченное количество запросов!",
                            parse_mode='HTML'
                        )
                    except:
                        pass
                    
                    bot.send_message(
                        message.chat.id,
                        f"✅ Premium-подписка активирована для пользователя {target_user_id} на {'бессрочно' if days == 0 else f'{days} дней'}"
                    )
                    
                except Exception as e:
                    bot.send_message(message.chat.id, f"Ошибка: {str(e)}")
                
                del user_states[user_id]
                return
                
            elif state == 'change_payment_url':
                payment_settings['payment_url'] = message.text
                save_payment_settings(payment_settings)
                bot.send_message(message.chat.id, f"✅ Ссылка оплаты обновлена: {message.text}")
                del user_states[user_id]
                return
                
            elif state == 'change_payment_price':
                try:
                    parts = message.text.split()
                    price = int(parts[0])
                    currency = parts[1] if len(parts) > 1 else "USDT"
                    
                    payment_settings['price'] = price
                    payment_settings['currency'] = currency
                    save_payment_settings(payment_settings)
                    bot.send_message(message.chat.id, f"✅ Цена обновлена: {price} {currency}")
                except Exception as e:
                    bot.send_message(message.chat.id, f"Ошибка: {str(e)}")
                
                del user_states[user_id]
                return
        
        # Обычная обработка сообщений
        update_user_stats(user)
        
        if message.text == "🔄 Сбросить диалог":
            bot.send_message(message.chat.id, "♻️ <b>Диалог сброшен!</b>", parse_mode='HTML')
            return
            
        elif message.text == "⭐ Лидеры":
            show_leaders(message.chat.id)
            return
            
        elif message.text == "👨‍💻 Создатель":
            bot.send_message(
                message.chat.id,
                "👨‍💻 <b>Создатель бота:</b>\n@DedlyAI\n\n"
                "📧 <b>Поддержка:</b>\n@DedlySupport\n\n"
                "📢 <b>Канал проекта:</b>\n@DedlyxCoder",
                parse_mode='HTML'
            )
            return
            
        elif message.text == "📢 Канал проекта":
            bot.send_message(
                message.chat.id,
                "📢 <b>Наш канал:</b>\n@DedlyxCoder\n\n"
                "Подпишитесь чтобы быть в курсе обновлений!",
                parse_mode='HTML'
            )
            return
            
        elif message.text == "ℹ️ О боте":
            bot.send_message(
                message.chat.id,
                PROJECT_INFO,
                parse_mode='HTML'
            )
            return
            
        elif message.text == "💎 Premium":
            show_premium_info(message)
            return
            
        elif message.text == "💬 Задать вопрос":
            bot.send_message(
                message.chat.id,
                "💬 <b>Просто напишите ваш вопрос</b>\n\n"
                "Я постараюсь дать максимально полезный и точный ответ!",
                parse_mode='HTML'
            )
            return
            
        if not check_subscription(user.id):
            handle_unsubscribed(message.chat.id, user.id)
            return
        
        # Проверка лимита запросов
        can_request, error_msg = can_make_request(user.id)
        if not can_request:
            bot.send_message(message.chat.id, error_msg, parse_mode='HTML')
            return
            
        processing_messages[message.chat.id] = True
        threading.Thread(target=process_gpt, args=(user, message)).start()
        
    except Exception as e:
        logger.error(f"Message error: {str(e)}")

if __name__ == "__main__":
    # Убедимся, что нет активных вебхуков
    bot.remove_webhook()
    # Добавим небольшую задержку перед запуском polling
    time.sleep(1)
    logger.info("Бот запущен")
    bot.infinity_polling()