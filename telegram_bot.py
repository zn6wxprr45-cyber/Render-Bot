# -*- coding: utf-8 -*-
"""Основной файл телеграмм-бота "Онлайн-Поликлиника"

Этот бот использует python-telegram-bot и Firebase Firestore.
"""

import logging
import os
import json
import datetime
import asyncio
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
    CallbackQueryHandler
)
import firebase_admin
from firebase_admin import credentials, firestore, auth

# --- КОНФИГУРАЦИЯ СРЕДЫ (Исправлено) ---
# Читаем критически важные переменные окружения.
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "FAKE_TOKEN")
RENDER_EXTERNAL_HOSTNAME = os.getenv("RENDER_EXTERNAL_HOSTNAME")
WEBHOOK_PORT = int(os.getenv("PORT", 10000))

# Переменные для Firebase
APP_ID = os.getenv('APP_ID', 'default-app-id')
FIREBASE_CONFIG_JSON = os.getenv('FIREBASE_CONFIG_JSON')

# --- Константы для диалогов и кнопок ---
(
    Q1_PAIN,
    Q2_SLEEP,
    Q3_MEDICATION,
    Q4_SIDE_EFFECTS,
    Q5_COMMENTS,
    Q6_SAVE
) = range(6)

SURVEY_BTN = "✅ Заполнить опросник"
ILLNESS_BTN = "ℹ️ Информация о синдроме"
INFO_BTN = "🧑‍⚕️ Режим работы и связь"
EMERGENCY_BTN = "🚨 Срочная помощь"
CANCEL_BTN = "❌ Отмена"

# --- Настройка логирования ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# --- Инициализация Firebase ---
db = None # Глобальная переменная для Firestore
firebase_initialized = False

def initialize_firebase():
    """Инициализирует Firebase Admin SDK и получает клиент Firestore."""
    global db, firebase_initialized
    if FIREBASE_CONFIG_JSON:
        try:
            # Парсим JSON-строку
            config = json.loads(FIREBASE_CONFIG_JSON)
            
            # Используем учетные данные сервисного аккаунта для инициализации
            if 'private_key' in config and 'client_email' in config:
                cred = credentials.Certificate(config)
                firebase_admin.initialize_app(cred, name=APP_ID)
            else:
                # Если это публичный конфиг, используем его (но Admin SDK лучше работает с сервисным ключом)
                firebase_admin.initialize_app(options=config, name=APP_ID)

            db = firestore.client()
            firebase_initialized = True
            logger.info("Клиент Firestore успешно создан и инициализирован.")
            return True
        except json.JSONDecodeError:
            logger.error("Ошибка парсинга JSON в FIREBASE_CONFIG_JSON. Убедитесь, что это валидная JSON строка.")
        except Exception as e:
            logger.error(f"Ошибка инициализации Firebase/Firestore: {e}")
    else:
        logger.warning("Переменная FIREBASE_CONFIG_JSON не найдена. Firebase не инициализирован.")
    return False

initialize_firebase()

# --- Вспомогательные функции (Dummy/Placeholder) ---
def get_main_menu_keyboard():
    """Возвращает основную клавиатуру меню."""
    return ReplyKeyboardMarkup(
        [[SURVEY_BTN], [ILLNESS_BTN, INFO_BTN], [EMERGENCY_BTN]],
        resize_keyboard=True,
        one_time_keyboard=False
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает команду /start."""
    user = update.effective_user
    await update.message.reply_html(
        f"Здравствуйте, {user.first_name}! Добро пожаловать в Онлайн-Поликлинику для пациентов с постинсультным таламическим синдромом. Я — ваш помощник в ежедневном мониторинге состояния.",
        reply_markup=get_main_menu_keyboard(),
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает отмену диалога."""
    await update.message.reply_text(
        "Действие отменено. Вы вернулись в главное меню.",
        reply_markup=get_main_menu_keyboard(),
    )
    return ConversationHandler.END

# --- ФУНКЦИИ ДИАЛОГА (Placeholder) ---
async def start_survey(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало опроса - Вопрос 1: Оценка боли."""
    context.user_data['survey'] = {'user_id': str(update.effective_user.id), 'date': datetime.datetime.now().isoformat()}
    
    await update.message.reply_text(
        "**Начинаем ежедневный опросник.**\n\n**Вопрос 1/5:** Оцените текущий болевой синдром по шкале от 0 (нет боли) до 10 (самая сильная боль).",
        reply_markup=ReplyKeyboardMarkup([['0', '1', '2', '3'], ['4', '5', '6', '7'], ['8', '9', '10'], [CANCEL_BTN]], one_time_keyboard=True, resize_keyboard=True)
    )
    return Q1_PAIN

async def q1_pain(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Вопрос 2: Сон."""
    try:
        pain_score = int(update.message.text)
        if not 0 <= pain_score <= 10:
             await update.message.reply_text("Пожалуйста, введите число от 0 до 10.")
             return Q1_PAIN
        context.user_data['survey']['pain_score'] = pain_score
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите числовое значение боли (0-10).")
        return Q1_PAIN

    await update.message.reply_text(
        "**Вопрос 2/5:** Как Вы спали прошлой ночью? (Выберите вариант)",
        reply_markup=ReplyKeyboardMarkup([['Отлично', 'Хорошо'], ['Удовлетворительно', 'Плохо'], ['Совсем не спал'], [CANCEL_BTN]], one_time_keyboard=True, resize_keyboard=True)
    )
    return Q2_SLEEP

async def q2_sleep(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Вопрос 3: Лекарства."""
    context.user_data['survey']['sleep_quality'] = update.message.text
    
    await update.message.reply_text(
        "**Вопрос 3/5:** Какие лекарственные препараты Вы приняли сегодня? (Перечислите или укажите 'Без изменений')",
        reply_markup=ReplyKeyboardMarkup([['Без изменений'], [CANCEL_BTN]], one_time_keyboard=True, resize_keyboard=True)
    )
    return Q3_MEDICATION

async def q3_medication(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Вопрос 4: Побочные эффекты."""
    context.user_data['survey']['medication'] = update.message.text
    
    await update.message.reply_text(
        "**Вопрос 4/5:** Отметили ли Вы сегодня какие-либо побочные эффекты или новые симптомы? (Опишите или укажите 'Нет')",
        reply_markup=ReplyKeyboardMarkup([['Нет'], [CANCEL_BTN]], one_time_keyboard=True, resize_keyboard=True)
    )
    return Q4_SIDE_EFFECTS

async def q4_side_effects(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Вопрос 5: Комментарии."""
    context.user_data['survey']['side_effects'] = update.message.text
    
    await update.message.reply_text(
        "**Вопрос 5/5:** Ваши общие комментарии или вопросы, которые Вы хотели бы передать врачу.",
        reply_markup=ReplyKeyboardMarkup([[CANCEL_BTN]], one_time_keyboard=True, resize_keyboard=True)
    )
    return Q5_COMMENTS

async def q5_comments_and_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохранение данных и завершение опроса."""
    context.user_data['survey']['comments'] = update.message.text
    survey_data = context.user_data['survey']

    save_status = "Данные не сохранены."
    if firebase_initialized and db:
        try:
            # Путь для сохранения: /artifacts/{APP_ID}/users/{user_id}/daily_surveys
            doc_ref = db.collection(f"artifacts/{APP_ID}/users/{survey_data['user_id']}/daily_surveys").document()
            
            # Сохранение данных
            await asyncio.to_thread(doc_ref.set, survey_data)
            save_status = "Данные успешно сохранены в Firestore."
        except Exception as e:
            save_status = f"Ошибка при сохранении в Firestore: {e}"
            logger.error(save_status)
    else:
        save_status = "Firebase не инициализирован. Данные сохранены только локально."
        logger.warning(save_status)
    
    # Формирование отчета для пользователя
    report = f"**Спасибо! Опрос завершен.**\n\n"
    report += f"**Болевой синдром:** {survey_data.get('pain_score', 'N/A')}/10\n"
    report += f"**Сон:** {survey_data.get('sleep_quality', 'N/A')}\n"
    report += f"**Лекарства:** {survey_data.get('medication', 'N/A')}\n"
    report += f"**Побочные эффекты:** {survey_data.get('side_effects', 'N/A')}\n"
    report += f"**Комментарии:** {survey_data.get('comments', 'N/A')}\n\n"
    report += f"_{save_status}_"
    
    await update.message.reply_text(report, reply_markup=get_main_menu_keyboard())
    
    # Очистка данных диалога
    del context.user_data['survey']
    return ConversationHandler.END

# --- ФУНКЦИИ КНОПОК-КОМАНД (Placeholder) ---
async def show_illness_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает информацию о постинсультном таламическом синдроме."""
    info_text = (
        "**Постинсультный таламический синдром (ПТС)**\n\n"
        "Это хроническое болевое состояние, которое возникает после инсульта, "
        "повредившего таламус. Характеризуется упорной, часто жгучей болью, "
        "которая плохо поддается стандартным обезболивающим.\n\n"
        "**Ключевые симптомы:** аллодиния (боль от не болевых стимулов), гипералгезия, "
        "иногда дизестезия. Течение заболевания может быть волнообразным."
    )
    await update.message.reply_text(info_text, reply_markup=get_main_menu_keyboard())

async def show_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает режим работы и форму обратной связи."""
    info_text = (
        "**Режим работы Онлайн-Поликлиники:**\n"
        "Ежедневный опросник доступен **круглосуточно**.\n"
        "Анализ данных врачом проводится **ежедневно с 8:00 до 17:00 (МСК)**.\n\n"
        "**Форма обратной связи:**\n"
        "Для вопросов, не требующих срочности, пожалуйста, оставьте комментарий в ежедневном опроснике. "
        "Врач свяжется с вами через этот чат в рабочее время.\n"
        "Для немедленной помощи используйте кнопку 🚨 **Срочная помощь**."
    )
    await update.message.reply_text(info_text, reply_markup=get_main_menu_keyboard())

async def show_emergency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает, что делать в случае срочной помощи."""
    emergency_text = (
        "**🚨 СРОЧНАЯ МЕДИЦИНСКАЯ ПОМОЩЬ!**\n\n"
        "Если у вас или вашего близкого:\n"
        "1. Внезапно ухудшилось состояние (новый инсульт, потеря сознания).\n"
        "2. Возникли жизнеугрожающие симптомы (затруднение дыхания, острая боль в груди).\n"
        "3. Вы не можете контролировать боль или принимаете слишком много лекарств.\n\n"
        "**НЕМЕДЛЕННО звоните по номеру скорой помощи:**\n"
        "**103** (Россия) или **112** (Единый номер экстренных служб).\n\n"
        "Онлайн-Поликлиника не заменяет экстренную медицинскую помощь."
    )
    await update.message.reply_text(emergency_text, reply_markup=get_main_menu_keyboard())

# --- НАСТРОЙКА ОБРАБОТЧИКОВ ---
def setup_handlers(application: Application) -> None:
    """Настраивает все обработчики для приложения."""
    
    # Обработчик отмены для кнопок
    async def cancel_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        return await cancel(update, context)

    # 1. Диалог для ежедневного опросника
    survey_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f"^{SURVEY_BTN}$"), start_survey)],
        states={
            Q1_PAIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, q1_pain)],
            Q2_SLEEP: [MessageHandler(filters.TEXT & ~filters.COMMAND, q2_sleep)],
            Q3_MEDICATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, q3_medication)],
            Q4_SIDE_EFFECTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, q4_side_effects)],
            Q5_COMMENTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, q5_comments_and_save)],
        },
        fallbacks=[MessageHandler(filters.Regex(f"^{CANCEL_BTN}$"), cancel_button_handler)],
    )

    # 2. Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(survey_conv_handler)
    
    # Добавляем обработчики для кнопок-команд
    application.add_handler(MessageHandler(filters.Regex(f"^{ILLNESS_BTN}$"), show_illness_info))
    application.add_handler(MessageHandler(filters.Regex(f"^{INFO_BTN}$"), show_info))
    application.add_handler(MessageHandler(filters.Regex(f"^{EMERGENCY_BTN}$"), show_emergency))

    # Обработчик для любого другого текста (на случай, если пользователь просто пишет)
    async def other_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Я не понял ваш запрос. Пожалуйста, используйте кнопки меню.",
            reply_markup=get_main_menu_keyboard()
        )
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(f"^{SURVEY_BTN}|{ILLNESS_BTN}|{INFO_BTN}|{EMERGENCY_BTN}|{CANCEL_BTN}$"), other_text))


# --- ГЛАВНАЯ ТОЧКА ВХОДА ---
def main() -> None:
    """Запускает бота."""
    WEBHOOK_URL_HOST = RENDER_EXTERNAL_HOSTNAME 
    
    # КРИТИЧЕСКАЯ ПРОВЕРКА
    if TELEGRAM_TOKEN == "FAKE_TOKEN" or not WEBHOOK_URL_HOST:
        logger.error("КРИТИЧЕСКАЯ ОШИБКА: TELEGRAM_TOKEN или RENDER_EXTERNAL_HOSTNAME не установлены.")
        logger.error("Пожалуйста, установите переменные среды на Render и перезапустите сервис.")
        # Прерываем выполнение, чтобы не тратить ресурсы на нерабочий токен
        return

    logger.info("Инициализация приложения Telegram Bot...")
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    setup_handlers(application)
    logger.info("Application handlers set up successfully.")

    # Создаем URL для Webhook (например, https://my-bot.onrender.com/TOKEN_SECRET)
    WEBHOOK_URL = f"{WEBHOOK_URL_HOST}/{TELEGRAM_TOKEN}"

    logger.info(f"Запуск Webhook на порту {WEBHOOK_PORT} с URL: https://{WEBHOOK_URL}")
    application.run_webhook(
        listen="0.0.0.0",
        port=WEBHOOK_PORT,
        url_path=TELEGRAM_TOKEN, # Путь в нашем веб-приложении для обработки POST-запросов
        webhook_url=f"https://{WEBHOOK_URL}", # Полный URL, который мы сообщаем Telegram
    )

if __name__ == "__main__":
    main()
