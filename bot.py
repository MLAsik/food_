import hashlib
import hmac
import json
import logging
import os
import threading
import time
from urllib.parse import parse_qsl

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    Update,
    WebAppInfo,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from db import (
    add_round,
    create_game,
    finish_game,
    get_game,
    get_games,
    get_stats,
    get_users,
    init_db,
    upsert_user,
)


# ============================================================
# НАСТРОЙКИ
# ============================================================

BOT_TOKEN = os.environ["BOT_TOKEN"]

WEBAPP_URL = os.environ.get(
    "WEBAPP_URL",
    "https://mlasik.github.io/food_/",
)

API_HOST = os.environ.get("API_HOST", "0.0.0.0")
API_PORT = int(os.environ.get("API_PORT", "8000"))

ADMIN_USERNAME = os.environ.get(
    "ADMIN_USERNAME",
    "Fastmilk1",
).lstrip("@").lower()


# ============================================================
# ЛОГИ
# ============================================================

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# ============================================================
# DATABASE
# ============================================================

init_db()


# ============================================================
# TELEGRAM INIT DATA
# ============================================================

def validate_init_data(init_data: str):
    if not init_data:
        raise ValueError("Empty Telegram initData")

    try:
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    except Exception as exc:
        raise ValueError("Invalid initData") from exc

    received_hash = parsed.pop("hash", None)

    if not received_hash:
        raise ValueError("Missing hash")

    secret_key = hmac.new(
        b"WebAppData",
        BOT_TOKEN.encode(),
        hashlib.sha256,
    ).digest()

    data_check_string = "\n".join(
        f"{key}={value}"
        for key, value in sorted(parsed.items())
    )

    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(
        calculated_hash,
        received_hash,
    ):
        raise ValueError("Invalid Telegram initData signature")

    auth_date = int(parsed.get("auth_date", "0"))

    if auth_date and time.time() - auth_date > 86400:
        raise ValueError("Telegram initData expired")

    user_raw = parsed.get("user")

    if not user_raw:
        raise ValueError("Telegram user not found")

    user = json.loads(user_raw)

    if not user.get("id"):
        raise ValueError("Telegram user ID not found")

    return user


# ============================================================
# FASTAPI
# ============================================================

api = FastAPI(
    title="Food Battle API",
)


def get_user_from_request(request: Request):
    init_data = request.headers.get("X-Telegram-Init-Data")

    if not init_data:
        raise HTTPException(
            status_code=401,
            detail="Telegram initData required",
        )

    try:
        user = validate_init_data(init_data)
    except Exception as exc:
        logger.warning("Invalid initData: %s", exc)

        raise HTTPException(
            status_code=401,
            detail="Invalid Telegram authorization",
        )

    upsert_user(
        telegram_id=user["id"],
        username=user.get("username"),
        first_name=user.get("first_name"),
        last_name=user.get("last_name"),
        language_code=user.get("language_code"),
        count_start=False,
    )

    return user


@api.get("/api/health")
async def health():
    return {
        "status": "ok",
        "service": "food-battle",
    }


@api.post("/api/session")
async def create_session(request: Request):
    user = get_user_from_request(request)

    return {
        "ok": True,
        "user_id": user["id"],
    }


@api.post("/api/game/start")
async def api_game_start(request: Request):
    user = get_user_from_request(request)

    game_id = create_game(user["id"])

    logger.info(
        "Game started: game_id=%s user_id=%s",
        game_id,
        user["id"],
    )

    return {
        "ok": True,
        "game_id": game_id,
    }


@api.post("/api/game/round")
async def api_game_round(request: Request):
    user = get_user_from_request(request)

    try:
        data = await request.json()
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid JSON",
        )

    required = [
        "game_id",
        "round_number",
        "stage",
        "option_1",
        "option_2",
        "choice",
    ]

    for field in required:
        if field not in data:
            raise HTTPException(
                status_code=400,
                detail=f"Missing field: {field}",
            )

    try:
        add_round(
            game_id=data["game_id"],
            telegram_id=user["id"],
            round_number=int(data["round_number"]),
            stage=int(data["stage"]),
            option_1=str(data["option_1"]),
            option_2=str(data["option_2"]),
            choice=str(data["choice"]),
        )
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail="Game not found",
        )

    return {
        "ok": True,
    }


@api.post("/api/game/finish")
async def api_game_finish(request: Request):
    user = get_user_from_request(request)

    try:
        data = await request.json()
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid JSON",
        )

    game_id = data.get("game_id")
    winner = data.get("winner")

    if not game_id or not winner:
        raise HTTPException(
            status_code=400,
            detail="game_id and winner are required",
        )

    try:
        finish_game(
            game_id=game_id,
            telegram_id=user["id"],
            winner=str(winner),
        )
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail="Game not found",
        )

    logger.info(
        "Game finished: game_id=%s user_id=%s winner=%s",
        game_id,
        user["id"],
        winner,
    )

    return {
        "ok": True,
    }


# ============================================================
# ADMIN
# ============================================================

def is_admin(user) -> bool:
    if not user:
        return False

    username = (user.username or "").lower()

    return username == ADMIN_USERNAME


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not is_admin(user):
        await update.message.reply_text(
            "⛔ У тебя нет доступа к этой команде."
        )
        return

    stats = get_stats()

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "👥 Пользователи",
                    callback_data="admin:users",
                )
            ],
            [
                InlineKeyboardButton(
                    "🎮 Последние игры",
                    callback_data="admin:games",
                )
            ],
            [
                InlineKeyboardButton(
                    "🔄 Обновить",
                    callback_data="admin:home",
                )
            ],
        ]
    )

    await update.message.reply_text(
        (
            "🔐 <b>Админ-панель</b>\n\n"
            f"👥 Пользователей: <b>{stats['users']}</b>\n"
            f"🎮 Игр: <b>{stats['games']}</b>\n"
            f"🏆 Завершённых: <b>{stats['finished_games']}</b>\n"
            f"🎯 Раундов: <b>{stats['rounds']}</b>"
        ),
        reply_markup=keyboard,
        parse_mode="HTML",
    )


async def admin_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    await query.answer()

    user = query.from_user

    if not is_admin(user):
        await query.edit_message_text(
            "⛔ Доступ запрещён."
        )
        return

    data = query.data

    if data == "admin:home":
        stats = get_stats()

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "👥 Пользователи",
                        callback_data="admin:users",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🎮 Последние игры",
                        callback_data="admin:games",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🔄 Обновить",
                        callback_data="admin:home",
                    )
                ],
            ]
        )

        await query.edit_message_text(
            (
                "🔐 <b>Админ-панель</b>\n\n"
                f"👥 Пользователей: <b>{stats['users']}</b>\n"
                f"🎮 Игр: <b>{stats['games']}</b>\n"
                f"🏆 Завершённых: <b>{stats['finished_games']}</b>\n"
                f"🎯 Раундов: <b>{stats['rounds']}</b>"
            ),
            reply_markup=keyboard,
            parse_mode="HTML",
        )

    elif data == "admin:users":
        users = get_users(20)

        if not users:
            text = "👥 Пользователей пока нет."
        else:
            lines = ["👥 <b>Последние пользователи</b>"]

            for index, item in enumerate(users, 1):
                username = (
                    f"@{item['username']}"
                    if item["username"]
                    else "без username"
                )

                name = " ".join(
                    x for x in [
                        item["first_name"],
                        item["last_name"],
                    ]
                    if x
                ) or "Без имени"

                lines.append(
                    f"{index}. <b>{name}</b> "
                    f"({username})\n"
                    f"   ID: <code>{item['telegram_id']}</code>\n"
                    f"   Запусков: {item['start_count']}\n"
                    f"   Последний: {item['last_seen_at']}"
                )

            text = "\n\n".join(lines)

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "⬅️ Назад",
                        callback_data="admin:home",
                    )
                ]
            ]
        )

        await query.edit_message_text(
            text,
            reply_markup=keyboard,
            parse_mode="HTML",
        )

    elif data == "admin:games":
        games = get_games(20)

        if not games:
            text = "🎮 Игр пока нет."

            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "⬅️ Назад",
                            callback_data="admin:home",
                        )
                    ]
                ]
            )

            await query.edit_message_text(
                text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
            return

        lines = ["🎮 <b>Последние игры</b>"]
        buttons = []

        for index, game in enumerate(games, 1):
            name = " ".join(
                x for x in [
                    game["first_name"],
                    game["last_name"],
                ]
                if x
            ) or "Без имени"

            username = (
                f"@{game['username']}"
                if game["username"]
                else "без username"
            )

            status = (
                f"🏆 {game['winner']}"
                if game["winner"]
                else "⏳ не завершена"
            )

            lines.append(
                f"{index}. {name} ({username})\n"
                f"   {status}\n"
                f"   {game['started_at']}"
            )

            buttons.append(
                [
                    InlineKeyboardButton(
                        f"🎮 Игра {index}",
                        callback_data=f"admin:game:{game['id']}",
                    )
                ]
            )

        buttons.append(
            [
                InlineKeyboardButton(
                    "⬅️ Назад",
                    callback_data="admin:home",
                )
            ]
        )

        await query.edit_message_text(
            "\n\n".join(lines),
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="HTML",
        )

    elif data.startswith("admin:game:"):
        game_id = data.split("admin:game:", 1)[1]

        game, rounds = get_game(game_id)

        if not game:
            await query.edit_message_text(
                "❌ Игра не найдена."
            )
            return

        name = " ".join(
            x for x in [
                game["first_name"],
                game["last_name"],
            ]
            if x
        ) or "Без имени"

        username = (
            f"@{game['username']}"
            if game["username"]
            else "без username"
        )

        lines = [
            "🎮 <b>Игра</b>",
            "",
            f"👤 {name}",
            f"🔹 {username}",
            f"🆔 <code>{game['telegram_id']}</code>",
            "",
            f"🕐 Начало: {game['started_at']}",
            f"🕐 Конец: {game['finished_at'] or 'ещё идёт'}",
            f"🏆 Итог: <b>{game['winner'] or '—'}</b>",
            "",
            "📋 <b>Раунды:</b>",
        ]

        if not rounds:
            lines.append("Раундов пока нет.")
        else:
            for item in rounds:
                lines.append(
                    (
                        f"\n<b>Раунд {item['round_number']}</b> "
                        f"(этап {item['stage']})\n"
                        f"🍬 {item['option_1']}\n"
                        f"🍫 {item['option_2']}\n"
                        f"👉 Выбор: <b>{item['choice']}</b>"
                    )
                )

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "⬅️ К играм",
                        callback_data="admin:games",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🏠 В админку",
                        callback_data="admin:home",
                    )
                ],
            ]
        )

        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=keyboard,
            parse_mode="HTML",
        )


# ============================================================
# /START
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user = update.effective_user

    if user:
        upsert_user(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            language_code=user.language_code,
            count_start=True,
        )

    mention = (
        f"@{user.username}"
        if user and user.username
        else (
            user.first_name
            if user
            else "друг"
        )
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🍬 Открыть игру",
                    web_app=WebAppInfo(url=WEBAPP_URL),
                )
            ]
        ]
    )

    await update.message.reply_text(
        f"Привет {mention}, поиграем?",
        reply_markup=keyboard,
    )


# ============================================================
# MENU BUTTON
# ============================================================

async def set_menu_button(
    application: Application,
):
    await application.bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(
            text="Играть",
            web_app=WebAppInfo(url=WEBAPP_URL),
        )
    )


# ============================================================
# API SERVER
# ============================================================

def run_api():
    uvicorn.run(
        api,
        host=API_HOST,
        port=API_PORT,
        log_level="info",
    )


# ============================================================
# MAIN
# ============================================================

def main():
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(set_menu_button)
        .build()
    )

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("admin", admin)
    )

    application.add_handler(
        CallbackQueryHandler(
            admin_callback,
            pattern=r"^admin:",
        )
    )

    api_thread = threading.Thread(
        target=run_api,
        daemon=True,
    )

    api_thread.start()

    logger.info(
        "API started on %s:%s",
        API_HOST,
        API_PORT,
    )

    application.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
