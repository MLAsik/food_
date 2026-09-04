import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "food_bot.sqlite3"


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_connection()

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL UNIQUE,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            language_code TEXT,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            start_count INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS games (
            id TEXT PRIMARY KEY,
            telegram_id INTEGER NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            winner TEXT,
            FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
        );

        CREATE TABLE IF NOT EXISTS rounds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id TEXT NOT NULL,
            round_number INTEGER NOT NULL,
            stage INTEGER NOT NULL,
            option_1 TEXT NOT NULL,
            option_2 TEXT NOT NULL,
            choice TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_games_user
            ON games(telegram_id);

        CREATE INDEX IF NOT EXISTS idx_rounds_game
            ON rounds(game_id);

        CREATE INDEX IF NOT EXISTS idx_users_last_seen
            ON users(last_seen_at);
        """
    )

    conn.commit()
    conn.close()


def upsert_user(
    telegram_id,
    username=None,
    first_name=None,
    last_name=None,
    language_code=None,
    count_start=False,
):
    conn = get_connection()

    now = now_iso()

    existing = conn.execute(
        "SELECT telegram_id FROM users WHERE telegram_id = ?",
        (telegram_id,),
    ).fetchone()

    if existing:
        if count_start:
            conn.execute(
                """
                UPDATE users
                SET username = ?,
                    first_name = ?,
                    last_name = ?,
                    language_code = ?,
                    last_seen_at = ?,
                    start_count = start_count + 1
                WHERE telegram_id = ?
                """,
                (
                    username,
                    first_name,
                    last_name,
                    language_code,
                    now,
                    telegram_id,
                ),
            )
        else:
            conn.execute(
                """
                UPDATE users
                SET username = ?,
                    first_name = ?,
                    last_name = ?,
                    language_code = ?,
                    last_seen_at = ?
                WHERE telegram_id = ?
                """,
                (
                    username,
                    first_name,
                    last_name,
                    language_code,
                    now,
                    telegram_id,
                ),
            )
    else:
        conn.execute(
            """
            INSERT INTO users (
                telegram_id,
                username,
                first_name,
                last_name,
                language_code,
                first_seen_at,
                last_seen_at,
                start_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                telegram_id,
                username,
                first_name,
                last_name,
                language_code,
                now,
                now,
                1 if count_start else 0,
            ),
        )

    conn.commit()
    conn.close()


def create_game(telegram_id):
    game_id = str(uuid.uuid4())
    conn = get_connection()

    conn.execute(
        """
        INSERT INTO games (
            id,
            telegram_id,
            started_at
        )
        VALUES (?, ?, ?)
        """,
        (
            game_id,
            telegram_id,
            now_iso(),
        ),
    )

    conn.commit()
    conn.close()

    return game_id


def add_round(
    game_id,
    telegram_id,
    round_number,
    stage,
    option_1,
    option_2,
    choice,
):
    conn = get_connection()

    game = conn.execute(
        """
        SELECT id
        FROM games
        WHERE id = ? AND telegram_id = ?
        """,
        (game_id, telegram_id),
    ).fetchone()

    if not game:
        conn.close()
        raise ValueError("Game not found")

    conn.execute(
        """
        INSERT INTO rounds (
            game_id,
            round_number,
            stage,
            option_1,
            option_2,
            choice,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            game_id,
            round_number,
            stage,
            option_1,
            option_2,
            choice,
            now_iso(),
        ),
    )

    conn.commit()
    conn.close()


def finish_game(game_id, telegram_id, winner):
    conn = get_connection()

    result = conn.execute(
        """
        UPDATE games
        SET finished_at = ?,
            winner = ?
        WHERE id = ? AND telegram_id = ?
        """,
        (
            now_iso(),
            winner,
            game_id,
            telegram_id,
        ),
    )

    conn.commit()
    conn.close()

    if result.rowcount == 0:
        raise ValueError("Game not found")


def get_stats():
    conn = get_connection()

    users = conn.execute(
        "SELECT COUNT(*) AS count FROM users"
    ).fetchone()["count"]

    games = conn.execute(
        "SELECT COUNT(*) AS count FROM games"
    ).fetchone()["count"]

    finished_games = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM games
        WHERE finished_at IS NOT NULL
        """
    ).fetchone()["count"]

    rounds = conn.execute(
        "SELECT COUNT(*) AS count FROM rounds"
    ).fetchone()["count"]

    conn.close()

    return {
        "users": users,
        "games": games,
        "finished_games": finished_games,
        "rounds": rounds,
    }


def get_users(limit=20):
    conn = get_connection()

    rows = conn.execute(
        """
        SELECT *
        FROM users
        ORDER BY last_seen_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    conn.close()
    return rows


def get_games(limit=20):
    conn = get_connection()

    rows = conn.execute(
        """
        SELECT
            g.*,
            u.username,
            u.first_name,
            u.last_name
        FROM games g
        LEFT JOIN users u
            ON u.telegram_id = g.telegram_id
        ORDER BY g.started_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    conn.close()
    return rows


def get_game(game_id):
    conn = get_connection()

    game = conn.execute(
        """
        SELECT
            g.*,
            u.username,
            u.first_name,
            u.last_name
        FROM games g
        LEFT JOIN users u
            ON u.telegram_id = g.telegram_id
        WHERE g.id = ?
        """,
        (game_id,),
    ).fetchone()

    rounds = conn.execute(
        """
        SELECT *
        FROM rounds
        WHERE game_id = ?
        ORDER BY round_number ASC
        """,
        (game_id,),
    ).fetchall()

    conn.close()

    return game, rounds
