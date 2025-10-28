# -*- coding: utf-8 -*-
"""Телеграмм-бот "Онлайн-Поликлиника"

Основной файл телеграмм-бота "Онлайн-Поликлиника"
для пациентов с постинсультными таламическим синдромом.

Этот бот использует python-telegram-bot и Firebase Firestore.
"""

import logging
import os
import json
import datetime
import asyncio
import firebase_admin
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from firebase_admin import credentials, firestore, auth

# --- Глобальные переменные для Firebase и Токена ---
# Используем os.getenv для получения переменных окружения в Render.

# Глобальная переменная для ID приложения
# Используем часть hostname Render как ID, если APP_ID не задан
appId = os.getenv('RENDER_EXTERNAL_HOSTNAME', 'default-app-id').split('.')[0]

# Глобальная переменная для конфигурации Firebase (JSON строка)
firebase_config_str = os.getenv('FIREBASE_CONFIG_JSON')

# Токен бота и URL Webhook
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("RENDER_EXTERNAL_HOSTNAME")

# --- Конфигурация Логирования ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("telegram_bot")

# Проверка наличия обязательных переменных
if not TELEGRAM_TOKEN or not WEBHOOK_URL:
    logger.error("TELEGRAM_TOKEN или RENDER_EXTERNAL_HOSTNAME не установлены.")
    # Присваиваем фиктивные значения для предотвращения сбоя, но бот не будет работать
    TELEGRAM_TOKEN = TELEGRAM_TOKEN or "FAKE_TOKEN"
    WEBHOOK_URL = WEBHOOK_URL or "FAKE_URL"


# --- Firebase Initialization (ОБЯЗАТЕЛЬНО для Admin SDK) ---
try:
    if firebase_config_str:
        # Создаем учетные данные на основе JSON-объекта
        firebase_config = json.loads(firebase_config_str)
        cred = credentials.Certificate(firebase_config)
        firebase_admin.initialize_app(cred, {
            'projectId': firebase_config['project_id']
        })
        logger.info("Firebase Admin SDK инициализирован.")
        logger.info(f"Firebase App ID: {appId}")
    else:
        logger.warning("Переменная FIREBASE_CONFIG_JSON не найдена. Firebase не инициализирован.")

except Exception as e:
    logger.error(f"Ошибка инициализации Firebase: {e}")

# Инициализация клиента Firestore (для работы с БД)
db = None
try:
    # Проверяем, был ли инициализирован Firebase Admin SDK
    if firebase_admin._DEFAULT_APP:
        db = firestore.client()
        logger.info("Клиент Firestore успешно создан.")
    else:
        logger.warning("Firebase Admin SDK не инициализирован. Клиент Firestore не создан.")
except Exception as e:
    logger.error(f"Ошибка создания клиента Firestore: {e}")


# --- Константы для интерфейса и логики ---
# Кнопки главного меню
SURVEY_BTN = "📊 Заполнить анкету"
ILLNESS_BTN = "🧠 О болезни (таламический синдром)"
INFO_BTN = "🏥 Режим работы и контакты"
EMERGENCY_BTN = "🆘 Срочная помощь"

# Кнопки в диалоге
CANCEL_BTN = "❌ Отмена"

# Состояния для ConversationHandler
Q1_PAIN = 1
Q2_SLEEP = 2
Q3_MEDICATION = 3
Q4_SIDE_EFFECTS = 4
Q5_COMMENTS = 5
FEEDBACK_TEXT = 6


# --- Вспомогательные функции для Firestore ---

def get_patient_doc_ref(user_id: int):
    """Возвращает ссылку на документ пациента в базе данных Firestore."""
    if db:
        # /artifacts/{appId}/users/{userId}/patient_data/{docId}
        return db.collection("artifacts").document(appId).collection("users").document(str(user_id)).collection("patient_data").document("profile")
    return None

def get_survey_collection_ref(user_id: int):
    """Возвращает ссылку на коллекцию анкет пациента."""
    if db:
        # /artifacts/{appId}/users/{userId}/survey_entries
        return db.collection("artifacts").document(appId).collection("users").document(str(user_id)).collection("survey_entries")
    return None

async def save_survey_data(user_id: int, survey_data: dict):
    """Сохраняет данные анкеты в Firestore."""
    if not db:
        logger.error("База данных Firestore недоступна. Невозможно сохранить анкету.")
        return False
    
    try:
        # Добавляем временную метку
        survey_data['timestamp'] = firestore.SERVER_TIMESTAMP
        survey_data['date'] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

        collection_ref = get_survey_collection_ref(user_id)
        if collection_ref:
            # Firestore автоматически присвоит ID документу
            await collection_ref.add(survey_data)
            logger.info(f"Анкета сохранена для пользователя {user_id}.")
            return True
        return False

    except Exception as e:
        logger.error(f"Ошибка сохранения анкеты для {user_id}: {e}")
        return False


# --- Обработчики команд и меню ---

def get_main_menu_keyboard():
    """Возвращает клавиатуру главного меню."""
    keyboard = [
        [KeyboardButton(SURVEY_BTN)],
        [KeyboardButton(ILLNESS_BTN), KeyboardButton(INFO_BTN)],
        [KeyboardButton(EMERGENCY_BTN)]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start."""
    user = update.effective_user
    logger.info(f"Пользователь {user.id} начал чат.")
    
    welcome_message = (
        f"Здравствуйте, {user.full_name}!\n\n"
        "Я ваш помощник в онлайн-поликлинике для пациентов с постинсультным таламическим синдромом.\n\n"
        "**Мои функции:**\n"
        "1. **Ежедневная анкета:** Сбор информации о вашем состоянии и лечении.\n"
        "2. **Информационная поддержка:** Предоставление информации о заболевании, режиме работы и контактах.\n\n"
        "Пожалуйста, используйте кнопки меню ниже для работы."
    )
    
    await update.message.reply_text(
        welcome_message,
        reply_markup=get_main_menu_keyboard(),
        parse_mode='Markdown'
    )

# --- Обработчики информационных кнопок ---

async def show_illness_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает информацию о постинсультном таламическом синдроме."""
    info_text = (
        "🧠 **О постинсультном таламическом синдроме**\n\n"
        "Это неврологическое осложнение, возникающее после инсульта, поразившего таламус. "
        "Главный симптом — это **таламическая боль**, которая часто описывается как жгучая, "
        "пронизывающая или давящая, и плохо поддается обычным анальгетикам.\n\n"
        "**Ключевые моменты:**\n"
        "- **Симптомы:** Хроническая боль, изменения чувствительности, иногда непроизвольные движения.\n"
        "- **Лечение:** Требует комплексного подхода, часто включает антидепрессанты и противосудорожные препараты "
        "(например, Габапентин, Прегабалин) для контроля боли. Важен регулярный анализ эффективности лечения.\n\n"
        "Для получения более подробной информации обратитесь к вашему лечащему врачу."
    )
    await update.message.reply_text(info_text, parse_mode='Markdown')

async def show_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает режим работы, форму обратной связи и контакты."""
    info_text = (
        "🏥 **Режим работы и контакты онлайн-поликлиники**\n\n"
        "**Режим работы:** Ежедневно, с **8:00 до 20:00 (МСК)**.\n\n"
        "**Форма обратной связи:**\n"
        "Для неэкстренных вопросов, пожалуйста, используйте команду /feedback или напишите на почту: `support@example.com`.\n\n"
        "**Контактный телефон:** +7 (495) 123-45-67 (администратор)\n\n"
        "**ВНИМАНИЕ:** Этот бот не предназначен для немедленной медицинской консультации. "
        "Всегда следуйте инструкциям вашего лечащего врача."
    )
    await update.message.reply_text(info_text, parse_mode='Markdown')

async def show_emergency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает, что делать при срочной медицинской помощи."""
    info_text = (
        "🆘 **Срочная медицинская помощь**\n\n"
        "**Если вы испытываете:**\n"
        "1. Внезапное ухудшение состояния.\n"
        "2. Острое нарастание боли, не купируемое обычными средствами.\n"
        "3. Симптомы нового инсульта (внезапная слабость, онемение, нарушение речи).\n\n"
        "**НЕМЕДЛЕННО звоните по телефонам экстренных служб:**\n"
        "- **103** (Скорая помощь)\n"
        "- **112** (Единый номер экстренных служб)\n\n"
        "Сотрудники онлайн-поликлиники не оказывают экстренную помощь. Ваше здоровье — ваш приоритет!"
    )
    await update.message.reply_text(info_text, parse_mode='Markdown')


# --- Диалог обратной связи ---

async def start_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало диалога обратной связи."""
    await update.message.reply_text(
        "Напишите ваше сообщение или вопрос. Мы свяжемся с вами в рабочее время. \nДля отмены введите /cancel или нажмите кнопку '❌ Отмена'.",
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton(CANCEL_BTN)]], resize_keyboard=True, one_time_keyboard=True)
    )
    return FEEDBACK_TEXT

async def receive_feedback_and_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Принимает текст обратной связи и завершает диалог."""
    user_id = update.effective_user.id
    feedback_text = update.message.text
    
    # В реальном приложении здесь было бы сохранение в специальную коллекцию
    # или отправка уведомления администратору.
    
    logger.info(f"Получена обратная связь от {user_id}: {feedback_text[:50]}...")
    
    await update.message.reply_text(
        "Спасибо! Ваше сообщение принято. Мы обязательно рассмотрим его.",
        reply_markup=get_main_menu_keyboard()
    )
    return ConversationHandler.END

# --- Диалог заполнения анкеты (Survey) ---

async def start_survey(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало диалога анкеты."""
    # Инициализация словаря для сбора данных анкеты
    context.user_data['survey'] = {}
    
    keyboard = [[KeyboardButton("1"), KeyboardButton("5"), KeyboardButton("10")], [KeyboardButton(CANCEL_BTN)]]
    await update.message.reply_text(
        "**ШАГ 1/5: Оценка боли**\n\nОцените ваш уровень таламической боли сейчас по шкале от **0 (нет боли)** до **10 (самая сильная боль)**. Введите число.",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True),
        parse_mode='Markdown'
    )
    return Q1_PAIN

async def q1_pain(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Принимает оценку боли."""
    try:
        pain_score = int(update.message.text.strip())
        if not 0 <= pain_score <= 10:
            raise ValueError
        
        context.user_data['survey']['pain_score'] = pain_score
        
        keyboard = [[KeyboardButton("Отлично"), KeyboardButton("Плохо"), KeyboardButton("Как обычно")], [KeyboardButton(CANCEL_BTN)]]
        await update.message.reply_text(
            f"Принято, оценка боли: **{pain_score}**.\n\n**ШАГ 2/5: Сон**\n\nОцените качество вашего сна за последнюю ночь (количество часов, прерывания, общая бодрость). Опишите кратко.",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True),
            parse_mode='Markdown'
        )
        return Q2_SLEEP
    except ValueError:
        await update.message.reply_text(
            "Некорректный ввод. Пожалуйста, введите число от 0 до 10 или /cancel."
        )
        return Q1_PAIN

async def q2_sleep(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Принимает описание сна."""
    context.user_data['survey']['sleep_description'] = update.message.text.strip()
    
    keyboard = [[KeyboardButton("Да"), KeyboardButton("Нет"), KeyboardButton("Изменил дозу")], [KeyboardButton(CANCEL_BTN)]]
    await update.message.reply_text(
        "Принято.\n\n**ШАГ 3/5: Лечение**\n\nПринимали ли вы сегодня предписанные препараты (например, антидепрессанты, противосудорожные) согласно назначению врача?",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True),
        parse_mode='Markdown'
    )
    return Q3_MEDICATION

async def q3_medication(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Принимает информацию о приеме препаратов."""
    context.user_data['survey']['medication_compliance'] = update.message.text.strip()
    
    keyboard = [[KeyboardButton("Нет"), KeyboardButton("Да, слабые"), KeyboardButton("Да, сильные")], [KeyboardButton(CANCEL_BTN)]]
    await update.message.reply_text(
        "Принято.\n\n**ШАГ 4/5: Побочные эффекты**\n\nОщущали ли вы сегодня какие-либо побочные эффекты от принимаемого лечения (сонливость, тошнота, головокружение)? Опишите кратко.",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True),
        parse_mode='Markdown'
    )
    return Q4_SIDE_EFFECTS

async def q4_side_effects(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Принимает информацию о побочных эффектах."""
    context.user_data['survey']['side_effects'] = update.message.text.strip()
    
    keyboard = [[KeyboardButton("Нет комментариев"), KeyboardButton(CANCEL_BTN)]]
    await update.message.reply_text(
        "Принято.\n\n**ШАГ 5/5: Комментарии**\n\nЕсть ли у вас общие комментарии, вопросы или дополнительная информация, которую вы хотели бы сообщить врачу?",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True),
        parse_mode='Markdown'
    )
    return Q5_COMMENTS

async def q5_comments_and_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Принимает комментарии и сохраняет всю анкету."""
    context.user_data['survey']['comments'] = update.message.text.strip()
    user_id = update.effective_user.id
    
    # Получаем полную анкету
    final_survey_data = context.user_data['survey']
    
    # Сохраняем в базу данных
    success = await save_survey_data(user_id, final_survey_data)
    
    if success:
        message = (
            "✅ **Анкета успешно заполнена!**\n\n"
            "Ваши данные переданы на анализ. Ваш врач увидит:\n"
            f"- Оценка боли: **{final_survey_data.get('pain_score', 'N/A')} / 10**\n"
            "- Прием лекарств: {final_survey_data.get('medication_compliance', 'N/A')}\n\n"
            "Спасибо за вашу оперативность. Мы с вами на связи."
        )
    else:
        message = (
            "❌ **Ошибка сохранения!**\n\n"
            "К сожалению, не удалось сохранить вашу анкету в базу данных. "
            "Пожалуйста, попробуйте позже или свяжитесь с технической поддержкой."
        )

    await update.message.reply_text(
        message,
        reply_markup=get_main_menu_keyboard(),
        parse_mode='Markdown'
    )
    
    # Очистка данных пользователя
    context.user_data.clear()
    return ConversationHandler.END


# --- Обработчики отмены ---

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает команду /cancel."""
    if 'survey' in context.user_data:
        context.user_data.pop('survey')
    
    await update.message.reply_text(
        "Действие отменено. Вы вернулись в главное меню.",
        reply_markup=get_main_menu_keyboard()
    )
    # Обязательно возвращаем ConversationHandler.END для завершения диалога
    return ConversationHandler.END

async def cancel_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает нажатие кнопки '❌ Отмена'."""
    # Эта функция используется в MessageHandler для обработки текста кнопки
    # В ConversationHandler.fallbacks нужно передавать MessageHandler, но
    # поскольку текст кнопки уже обрабатывается здесь, просто вызываем cancel
    return await cancel(update, context)


# --- Главная функция бота ---

def main() -> None:
    """Запускает бота в режиме Webhook."""
    logger.info("Инициализация приложения Telegram Bot...")
    
    # 1. Создание приложения
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Определение обработчиков для fallbacks (отмена по команде или по кнопке)
    # Это исправляет NameError
    cancel_command_handler = CommandHandler("cancel", cancel)
    # Обработчик кнопки "❌ Отмена" (используется для fallbacks)
    cancel_message_handler = MessageHandler(filters.Regex(f"^{CANCEL_BTN}$"), cancel_button_handler)
    
    # 2. Обработчик диалога анкеты
    survey_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f"^{SURVEY_BTN}$"), start_survey)],
        states={
            Q1_PAIN: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(f"^{CANCEL_BTN}$"), q1_pain)],
            Q2_SLEEP: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(f"^{CANCEL_BTN}$"), q2_sleep)],
            Q3_MEDICATION: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(f"^{CANCEL_BTN}$"), q3_medication)],
            Q4_SIDE_EFFECTS: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(f"^{CANCEL_BTN}$"), q4_side_effects)],
            Q5_COMMENTS: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(f"^{CANCEL_BTN}$"), q5_comments_and_save)],
        },
        fallbacks=[cancel_command_handler, cancel_message_handler],
    )
    
    # 3. Обработчик диалога обратной связи
    feedback_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("feedback", start_feedback)],
        states={
            FEEDBACK_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(f"^{CANCEL_BTN}$"), receive_feedback_and_save)],
        },
        fallbacks=[cancel_command_handler, cancel_message_handler],
    )
    
    # 4. Обработчики команд и кнопок
    application.add_handler(CommandHandler("start", start))
    application.add_handler(survey_conv_handler)
    application.add_handler(feedback_conv_handler)
    application.add_handler(MessageHandler(filters.Regex(f"^{ILLNESS_BTN}$"), show_illness_info))
    application.add_handler(MessageHandler(filters.Regex(f"^{INFO_BTN}$"), show_info))
    application.add_handler(MessageHandler(filters.Regex(f"^{EMERGENCY_BTN}$"), show_emergency))
    
    # Обработчик для любого другого текста (на случай, если пользователь просто пишет)
    async def other_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Я не понял ваш запрос. Пожалуйста, используйте кнопки меню.",
            reply_markup=get_main_menu_keyboard()
        )
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(f"^{SURVEY_BTN}|{ILLNESS_BTN}|{INFO_BTN}|{EMERGENCY_BTN}$"), other_text))
    
    logger.info("Application handlers set up successfully.")

    # 5. Запуск бота в режиме Webhook (для Render)
    port = int(os.environ.get("PORT", "8080")) # Стандартный порт для Render
    
    logger.info(f"Запуск Webhook на порту {port} с URL: https://{WEBHOOK_URL}")

    # Устанавливаем Webhook URL (для Telegram)
    application.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path="",
        webhook_url=f"https://{WEBHOOK_URL}",
    )

if __name__ == '__main__':
    main()
