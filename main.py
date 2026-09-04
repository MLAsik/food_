"""Телеграм-бот «Битва сладостей» с функциональной админ-панелью."""

import asyncio
import json
import logging
import os
from datetime import datetime

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    Update,
    WebAppInfo,
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8383819197:AAEN4UXjgGz1CvUXZv0dw_MId8I4XlCuKPU")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "https://mlasik.github.io/food_/")

# Разрешенный администратор
ADMIN_USERNAME = "Fastmilk1"

# Хранилище логов игр в памяти
GAME_LOGS = []

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    mention = f"@{user.username}" if user and user.username else (user.first_name if user else "друг")
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🍬 Открыть игру", web_app=WebAppInfo(url=WEBAPP_URL))]]
    )
    if update.message:
        await update.message.reply_text(
            f"Привет, {mention}, поиграем?", reply_markup=keyboard
        )


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or (user.username or "").lower() != ADMIN_USERNAME.lower():
        if update.message:
            await update.message.reply_text("⛔ У вас нет доступа к админ-панели.")
        return

    if not GAME_LOGS:
        if update.message:
            await update.message.reply_text("📊 Админ-панель\n\nЗаписей об играх пока нет.")
        return

    response = "📊 Логи игр:\n\n"
    for idx, log in enumerate(GAME_LOGS[-10:], 1):  # Показываем последние 10 игр
        rounds_fmt = "\n".join([f"  • {r}" for r in log.get("rounds", [])])
        if not rounds_fmt:
            rounds_fmt = "  • Нет данных"

        response += (
            f"Запись #{idx}\n"
            f"🕒 Время старта: {log['start_time']} (завершение: {log['end_time']})\n"
            f"🆔 Telegram ID: {log['user_id']}\n"
            f"👤 Юзернейм: @{log['username']}\n"
            f"📝 Имя: {log['first_name']}\n"
            f"🏆 Победитель: {log['winner']}\n"
            f"📋 Выборы по раундам:\n{rounds_fmt}\n"
            f"-----------------------------------\n"
        )

    if update.message:
        await update.message.reply_text(response, parse_mode="Markdown")


async def web_app_data_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик данных, приходящих из мини-приложения."""
    if not update.message or not update.message.web_app_data:
        return

    user = update.effective_user
    raw_data = update.message.web_app_data.data

    try:
        data = json.loads(raw_data)
    except json.JSONDecodeError:
        data = {}

    log_entry = {
        "start_time": data.get("startTime", "Не указано"),
        "end_time": datetime.now().strftime("%H:%M:%S (%Y-%m-%d)"),
        "user_id": user.id if user else "Н/Д",
        "username": user.username if user and user.username else "нет_юзернейма",
        "first_name": user.first_name if user else "Неизвестно",
        "winner": data.get("winner", "Неизвестно"),
        "rounds": data.get("rounds", []),
    }

    GAME_LOGS.append(log_entry)
    await update.message.reply_text("✨ Игра завершена! Результаты отправлены администратору.")


async def set_menu_button(application: Application) -> None:
    await application.bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(text="Играть", web_app=WebAppInfo(url=WEBAPP_URL))
    )


def main() -> None:
    application = Application.builder().token(BOT_TOKEN).post_init(set_menu_button).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data_handler))

    # Запуск бота в режиме непрерывного ожидания событий
    application.run_polling(allowed_updates=Update.ALL_TYPES, close_loop=False)


if __name__ == "__main__":
    main()