"""Телеграм-бот «Битва сладостей»."""

import logging
import os

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

from db import (
    init_db,
    upsert_user,
    get_recent_games,
    get_game_rounds,
    get_users,
    get_user_count,
    get_game_count,
    get_open_count,
)


# ============================================================
# НАСТРОЙКИ
# ============================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8383819197:AAEN4UXjgGz1CvUXZv0dw_MId8I4XlCuKPU")

WEBAPP_URL = os.environ.get(
    "WEBAPP_URL",
    "https://mlasik.github.io/food_/"
)

ADMIN_USERNAME = "Fastmilk1"


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# ============================================================
# /start
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:

    user = update.effective_user

    if not user:
        return

    # Сохраняем пользователя в базу.
    upsert_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )

    mention = (
        f"@{user.username}"
        if user.username
        else user.first_name or "друг"
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🍬 Открыть игру",
                    web_app=WebAppInfo(
                        url=WEBAPP_URL
                    ),
                )
            ]
        ]
    )

    if update.message:

        await update.message.reply_text(
            f"Привет, {mention}, поиграем?",
            reply_markup=keyboard,
        )


# ============================================================
# /admin
# ============================================================

async def admin_panel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:

    user = update.effective_user

    if not user:
        return

    # Проверяем username администратора.
    if (
        not user.username
        or user.username.lower()
        != ADMIN_USERNAME.lower()
    ):

        if update.message:

            await update.message.reply_text(
                "⛔ У вас нет доступа к админ-панели."
            )

        return


    # --------------------------------------------------------
    # Общая статистика
    # --------------------------------------------------------

    user_count = get_user_count()

    game_count = get_game_count()

    open_count = get_open_count()


    response = (
        "📊 АДМИН-ПАНЕЛЬ\n\n"
        f"👥 Пользователей: {user_count}\n"
        f"🎮 Игр: {game_count}\n"
        f"📱 Открытий Mini App: {open_count}\n\n"
    )


    # --------------------------------------------------------
    # Пользователи
    # --------------------------------------------------------

    users = get_users(20)


    response += "👥 ПОСЛЕДНИЕ ПОЛЬЗОВАТЕЛИ\n\n"


    if not users:

        response += "Пока нет пользователей.\n"

    else:

        for item in users:

            username = (
                f"@{item['username']}"
                if item["username"]
                else "без username"
            )

            name = (
                item["first_name"]
                or "Без имени"
            )

            response += (
                f"👤 {name}\n"
                f"   {username}\n"
                f"   ID: {item['telegram_id']}\n"
                f"   Открытий: {item['mini_app_opens']}\n"
                f"   Последний вход: {item['last_seen_at']}\n\n"
            )


    # Telegram ограничивает размер одного сообщения.
    if len(response) > 3900:

        response = response[:3900] + "\n\n..."

    if update.message:

        await update.message.reply_text(
            response
        )


    # --------------------------------------------------------
    # Последние игры
    # --------------------------------------------------------

    games = get_recent_games(10)


    if not games:

        if update.message:

            await update.message.reply_text(
                "🎮 Игр пока нет."
            )

        return


    games_response = (
        "🎮 ПОСЛЕДНИЕ ИГРЫ\n\n"
    )


    for game in games:

        username = (
            f"@{game['username']}"
            if game["username"]
            else "без username"
        )

        name = (
            game["first_name"]
            or "Без имени"
        )


        status = (
            game["winner"]
            if game["winner"]
            else "Игра не завершена"
        )


        games_response += (
            f"🎮 Игра #{game['id']}\n"
            f"👤 {name} ({username})\n"
            f"🆔 ID: {game['telegram_id']}\n"
            f"🕒 Начало: {game['started_at']}\n"
            f"🏆 Итог: {status}\n"
        )


        rounds = get_game_rounds(
            game["id"]
        )


        if rounds:

            games_response += (
                "📋 Раунды:\n"
            )

            for round_data in rounds:

                games_response += (
                    f"  {round_data['round_number']}. "
                    f"{round_data['option_1']} "
                    f"vs "
                    f"{round_data['option_2']} "
                    f"→ "
                    f"{round_data['choice']}\n"
                )


        games_response += (
            "--------------------\n"
        )


    if len(games_response) > 3900:

        games_response = (
            games_response[:3900]
            + "\n\n..."
        )


    if update.message:

        await update.message.reply_text(
            games_response
        )


# ============================================================
# Web App Data
# ============================================================

async def web_app_data_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:

    """
    Пока оставляем обработчик старого механизма sendData.

    Позже основной сбор аналитики будет идти
    через API напрямую из Mini App.
    """

    if (
        not update.message
        or not update.message.web_app_data
    ):
        return


    if update.message:

        await update.message.reply_text(
            "✨ Данные получены."
        )


# ============================================================
# Кнопка Mini App в меню Telegram
# ============================================================

async def set_menu_button(
    application: Application
) -> None:

    await application.bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(
            text="Играть",
            web_app=WebAppInfo(
                url=WEBAPP_URL
            ),
        )
    )


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    # Создаём базу и таблицы,
    # если их ещё нет.
    init_db()


    if not BOT_TOKEN:

        raise RuntimeError(
            "Переменная окружения BOT_TOKEN не установлена."
        )


    application = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .post_init(set_menu_button)
        .build()
    )


    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )


    application.add_handler(
        CommandHandler(
            "admin",
            admin_panel
        )
    )


    application.add_handler(
        MessageHandler(
            filters.StatusUpdate.WEB_APP_DATA,
            web_app_data_handler,
        )
    )


    logger.info(
        "Бот запускается..."
    )


    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        close_loop=False,
    )


if __name__ == "__main__":
    main()
