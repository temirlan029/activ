"""
SQLite-слой для трекера активности.

Схема:
  users:
    user_id        TEXT PRIMARY KEY  – ID участника Discord
    username       TEXT              – отображаемое имя (может меняться)
    voice_seconds  INTEGER           – накопленное время в войсе (в секундах)
    message_count  INTEGER           – накопленное число сообщений
    last_active    TEXT              – ISO 8601 UTC таймстемп последней активности

  voice_sessions:
    user_id    TEXT PRIMARY KEY  – ID участника, сейчас в войсе
    channel_id TEXT              – ID голосового канала
    joined_at  TEXT              – ISO 8601 UTC таймстемп начала текущего отрезка

Все таймстемпы — ISO 8601 UTC с явной таймзоной, чтобы избежать
неоднозначностей с SQLite CURRENT_TIMESTAMP на разных платформах.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import aiosqlite

DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "data",
    "activity.db",
)


# ──────────────────────────────────────────────────────────────────────────────
#  ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ──────────────────────────────────────────────────────────────────────────────

def utc_now_iso() -> str:
    """Текущее время UTC в формате ISO 8601 с таймзоной."""
    return datetime.now(timezone.utc).isoformat()


def parse_iso(ts: str) -> datetime:
    """Парсит ISO 8601 строку в timezone-aware UTC datetime."""
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ──────────────────────────────────────────────────────────────────────────────
#  ИНИЦИАЛИЗАЦИЯ
# ──────────────────────────────────────────────────────────────────────────────

async def init_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id          TEXT PRIMARY KEY,
                username         TEXT NOT NULL,
                avatar_url       TEXT NOT NULL DEFAULT '',
                top_role_name    TEXT NOT NULL DEFAULT '',
                top_role_color   INTEGER NOT NULL DEFAULT 0,
                server_joined_at TEXT NOT NULL DEFAULT '',
                voice_seconds    INTEGER NOT NULL DEFAULT 0,
                message_count    INTEGER NOT NULL DEFAULT 0,
                last_active      TEXT NOT NULL DEFAULT ''
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS voice_sessions (
                user_id    TEXT PRIMARY KEY,
                channel_id TEXT NOT NULL,
                joined_at  TEXT NOT NULL
            )
        """)

        # ── ИСТОРИЯ СОБЫТИЙ (time-series) ──
        # Каждая запись = либо отрезок голоса (с длительностью),
        # либо одно сообщение (duration=0).
        await db.execute("""
            CREATE TABLE IF NOT EXISTS activity_events (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id          TEXT NOT NULL,
                event_type       TEXT NOT NULL,           -- 'voice' | 'message'
                timestamp        TEXT NOT NULL,           -- ISO 8601 UTC
                channel_id       TEXT NOT NULL DEFAULT '',
                duration_seconds INTEGER NOT NULL DEFAULT 0
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_user_time ON activity_events(user_id, timestamp)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_time ON activity_events(timestamp)"
        )

        # ── Миграции для существующих БД ──
        for col_def in (
            ("avatar_url",       "TEXT NOT NULL DEFAULT ''"),
            ("top_role_name",    "TEXT NOT NULL DEFAULT ''"),
            ("top_role_color",   "INTEGER NOT NULL DEFAULT 0"),
            ("server_joined_at", "TEXT NOT NULL DEFAULT ''"),
        ):
            try:
                await db.execute(f"ALTER TABLE users ADD COLUMN {col_def[0]} {col_def[1]}")
            except Exception:
                pass

        await db.commit()


# ──────────────────────────────────────────────────────────────────────────────
#  ПОЛЬЗОВАТЕЛИ
# ──────────────────────────────────────────────────────────────────────────────

async def upsert_user(
    user_id: int,
    username: str,
    avatar_url: str = "",
    top_role_name: str = "",
    top_role_color: int = 0,
    server_joined_at: str = "",
) -> None:
    """Создаёт или обновляет данные пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO users
                (user_id, username, avatar_url, top_role_name, top_role_color,
                 server_joined_at, last_active)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username         = excluded.username,
                avatar_url       = excluded.avatar_url,
                top_role_name    = excluded.top_role_name,
                top_role_color   = excluded.top_role_color,
                server_joined_at = excluded.server_joined_at
            """,
            (
                str(user_id), username, avatar_url, top_role_name,
                int(top_role_color), server_joined_at, utc_now_iso(),
            ),
        )
        await db.commit()


async def add_voice_seconds(user_id: int, seconds: int) -> None:
    """Накапливает голосовое время."""
    if seconds <= 0:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE users
            SET voice_seconds = voice_seconds + ?,
                last_active   = ?
            WHERE user_id = ?
            """,
            (seconds, utc_now_iso(), str(user_id)),
        )
        await db.commit()


async def add_message(user_id: int) -> None:
    """Инкремент счётчика сообщений."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE users
            SET message_count = message_count + 1,
                last_active   = ?
            WHERE user_id = ?
            """,
            (utc_now_iso(), str(user_id)),
        )
        await db.commit()


# ──────────────────────────────────────────────────────────────────────────────
#  АКТИВНЫЕ ГОЛОСОВЫЕ СЕССИИ (для восстановления после крэша)
# ──────────────────────────────────────────────────────────────────────────────

async def save_voice_session(user_id: int, channel_id: int, joined_at_iso: str) -> None:
    """Записывает / обновляет активную голосовую сессию в БД."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO voice_sessions (user_id, channel_id, joined_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE
                SET channel_id = excluded.channel_id,
                    joined_at  = excluded.joined_at
            """,
            (str(user_id), str(channel_id), joined_at_iso),
        )
        await db.commit()


async def update_session_timestamp(user_id: int, joined_at_iso: str) -> None:
    """Обновляет только joined_at (вызывается из периодического flush)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE voice_sessions SET joined_at = ? WHERE user_id = ?",
            (joined_at_iso, str(user_id)),
        )
        await db.commit()


async def delete_voice_session(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM voice_sessions WHERE user_id = ?",
            (str(user_id),),
        )
        await db.commit()


async def clear_all_sessions() -> None:
    """Очищает все активные сессии (вызывается при старте бота)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM voice_sessions")
        await db.commit()


# ──────────────────────────────────────────────────────────────────────────────
#  API: ТОП-15
# ──────────────────────────────────────────────────────────────────────────────

# ──────────────────────────────────────────────────────────────────────────────
#  ИСТОРИЯ СОБЫТИЙ (time-series)
# ──────────────────────────────────────────────────────────────────────────────

async def log_voice_event(user_id: int, channel_id: int, duration_seconds: int) -> None:
    """Записать отрезок войса в историю."""
    if duration_seconds <= 0:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO activity_events
               (user_id, event_type, timestamp, channel_id, duration_seconds)
               VALUES (?, 'voice', ?, ?, ?)""",
            (str(user_id), utc_now_iso(), str(channel_id), duration_seconds),
        )
        await db.commit()


async def log_message_event(user_id: int, channel_id: int) -> None:
    """Записать факт сообщения в историю."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO activity_events
               (user_id, event_type, timestamp, channel_id, duration_seconds)
               VALUES (?, 'message', ?, ?, 0)""",
            (str(user_id), utc_now_iso(), str(channel_id)),
        )
        await db.commit()


async def get_user(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE user_id = ?", (str(user_id),)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


# ──────────────────────────────────────────────────────────────────────────────
#  АНАЛИТИКА
# ──────────────────────────────────────────────────────────────────────────────

async def get_user_stats_period(user_id: int, since_iso: str) -> dict:
    """Сумма голоса и сообщений за период [since, now]."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT
                 COALESCE(SUM(CASE WHEN event_type='voice'   THEN duration_seconds END), 0) AS voice,
                 COALESCE(SUM(CASE WHEN event_type='message' THEN 1 END), 0)                 AS msgs
               FROM activity_events
               WHERE user_id = ? AND timestamp >= ?""",
            (str(user_id), since_iso),
        ) as cur:
            row = await cur.fetchone()
            return {"voice_seconds": row[0] or 0, "message_count": row[1] or 0}


async def get_top_period(since_iso: str, limit: int = 50) -> list[dict]:
    """Топ участников за период."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT
                 e.user_id,
                 u.username, u.avatar_url, u.top_role_name, u.top_role_color, u.server_joined_at,
                 COALESCE(SUM(CASE WHEN e.event_type='voice'   THEN e.duration_seconds END), 0) AS voice_seconds,
                 COALESCE(SUM(CASE WHEN e.event_type='message' THEN 1 END), 0)                  AS message_count,
                 MAX(e.timestamp) AS last_active
               FROM activity_events e
               LEFT JOIN users u ON u.user_id = e.user_id
               WHERE e.timestamp >= ?
               GROUP BY e.user_id
               HAVING voice_seconds > 0 OR message_count > 0
               ORDER BY voice_seconds DESC, message_count DESC
               LIMIT ?""",
            (since_iso, limit),
        ) as cur:
            return [dict(row) for row in await cur.fetchall()]


async def get_user_timeline(user_id: int, since_iso: str, bucket: str = "day") -> list[dict]:
    """
    Агрегация активности по дням / часам.
    bucket: 'hour' | 'day'
    Возвращает [{bucket: '2026-05-08', voice_seconds: 1200, message_count: 5}, ...]
    """
    if bucket == "hour":
        # YYYY-MM-DDTHH:00:00
        bucket_expr = "substr(timestamp, 1, 13) || ':00:00'"
    else:
        # YYYY-MM-DD
        bucket_expr = "substr(timestamp, 1, 10)"

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            f"""SELECT
                  {bucket_expr} AS bucket,
                  COALESCE(SUM(CASE WHEN event_type='voice'   THEN duration_seconds END), 0) AS voice_seconds,
                  COALESCE(SUM(CASE WHEN event_type='message' THEN 1 END), 0)                AS message_count
                FROM activity_events
                WHERE user_id = ? AND timestamp >= ?
                GROUP BY bucket
                ORDER BY bucket""",
            (str(user_id), since_iso),
        ) as cur:
            return [
                {"bucket": r[0], "voice_seconds": r[1] or 0, "message_count": r[2] or 0}
                for r in await cur.fetchall()
            ]


async def get_user_heatmap(user_id: int, since_iso: str, tz_offset_hours: int = 3) -> list[list[int]]:
    """
    Возвращает матрицу 7×24 (день недели × час) с суммой voice_seconds.
    Все таймстемпы в БД — UTC, конвертим в локальную таймзону для группировки.
    Понедельник = 0, воскресенье = 6.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT timestamp, duration_seconds
               FROM activity_events
               WHERE user_id = ? AND timestamp >= ? AND event_type = 'voice'""",
            (str(user_id), since_iso),
        ) as cur:
            rows = await cur.fetchall()

    # Матрица 7 (дни) × 24 (часы) секунд
    matrix = [[0] * 24 for _ in range(7)]
    offset = timedelta(hours=tz_offset_hours)
    for ts, dur in rows:
        try:
            dt = datetime.fromisoformat(ts) + offset
            dow = dt.weekday()  # понедельник = 0
            hour = dt.hour
            matrix[dow][hour] += dur or 0
        except Exception:
            continue
    return matrix


async def get_user_active_hours(user_id: int, since_iso: str, tz_offset_hours: int = 3) -> list[int]:
    """Возвращает массив 24 значений (секунды войса по часу суток)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT timestamp, duration_seconds
               FROM activity_events
               WHERE user_id = ? AND timestamp >= ? AND event_type = 'voice'""",
            (str(user_id), since_iso),
        ) as cur:
            rows = await cur.fetchall()

    hours = [0] * 24
    offset = timedelta(hours=tz_offset_hours)
    for ts, dur in rows:
        try:
            dt = datetime.fromisoformat(ts) + offset
            hours[dt.hour] += dur or 0
        except Exception:
            continue
    return hours


async def get_user_active_days(user_id: int, tz_offset_hours: int = 3) -> list[str]:
    """Возвращает отсортированный список дат (YYYY-MM-DD) когда была активность."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT DISTINCT timestamp
               FROM activity_events
               WHERE user_id = ?
               ORDER BY timestamp""",
            (str(user_id),),
        ) as cur:
            rows = await cur.fetchall()

    days: set[str] = set()
    offset = timedelta(hours=tz_offset_hours)
    for (ts,) in rows:
        try:
            dt = datetime.fromisoformat(ts) + offset
            days.add(dt.strftime("%Y-%m-%d"))
        except Exception:
            continue
    return sorted(days)


async def search_members(query: str, role: str = "", limit: int = 50) -> list[dict]:
    """Поиск + фильтр по роли."""
    sql = """
        SELECT user_id, username, avatar_url, top_role_name, top_role_color,
               server_joined_at, voice_seconds, message_count, last_active
        FROM users
        WHERE 1=1
    """
    params: list = []
    if query:
        sql += " AND LOWER(username) LIKE ?"
        params.append(f"%{query.lower()}%")
    if role:
        sql += " AND top_role_name = ?"
        params.append(role)
    sql += " ORDER BY voice_seconds DESC, message_count DESC LIMIT ?"
    params.append(limit)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(sql, params) as cur:
            return [dict(row) for row in await cur.fetchall()]


async def get_all_roles() -> list[dict]:
    """Список всех уникальных ролей с их цветами (для фильтра)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT top_role_name, top_role_color, COUNT(*) AS cnt
               FROM users
               WHERE top_role_name <> ''
               GROUP BY top_role_name, top_role_color
               ORDER BY cnt DESC"""
        ) as cur:
            return [
                {"name": r[0], "color": r[1], "count": r[2]}
                for r in await cur.fetchall()
            ]


async def get_members(limit: int | None = None) -> list[dict]:
    """Общий список участников, отсортированный по активности (войс → сообщения).
    Показывает ВСЕХ зарегистрированных, включая с нулевой активностью."""
    sql = """
        SELECT user_id, username, avatar_url,
               top_role_name, top_role_color, server_joined_at,
               voice_seconds, message_count, last_active
        FROM users
        ORDER BY voice_seconds DESC, message_count DESC, username ASC
    """
    params: tuple = ()
    if limit and limit > 0:
        sql += " LIMIT ?"
        params = (limit,)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(sql, params) as cur:
            return [dict(row) for row in await cur.fetchall()]
