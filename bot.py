"""Телеграм-бот «Битва сладостей»: /start приветствует и открывает мини-приложение."""

import logging
import os

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    Update,
    WebAppInfo,
)
from telegram.ext import Application, CommandHandler, ContextTypes

WEBAPP_URL = os.environ.get("WEBAPP_URL", "https://mlasik.github.io/food_/")

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s", level=logging.INFO
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    mention = f"@{user.username}" if user and user.username else (user.first_name if user else "друг")
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🍬 Открыть игру", web_app=WebAppInfo(url=WEBAPP_URL))]]
    )
    await update.message.reply_text(
        f"Привет {mention}, поиграем?", reply_markup=keyboard
    )


async def set_menu_button(application: Application) -> None:
    await application.bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(text="Играть", web_app=WebAppInfo(url=WEBAPP_URL))
    )


def main() -> None:
    token = os.environ["BOT_TOKEN"]
    application = Application.builder().token(token).post_init(set_menu_button).build()
    application.add_handler(CommandHandler("start", start))
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
