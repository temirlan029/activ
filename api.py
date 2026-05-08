import os
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from database import (
    get_members,
    get_user,
    get_user_stats_period,
    get_top_period,
    get_user_timeline,
    get_user_heatmap,
    get_user_active_hours,
    get_user_active_days,
    search_members,
    get_all_roles,
)


# ──────────────────────────────────────────────
#  ПРИЛОЖЕНИЕ
# ──────────────────────────────────────────────

app = FastAPI(title="Discord Activity Tracker")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

LOCAL_TZ_OFFSET = 3   # МСК
PERIOD_DAYS = {"week": 7, "month": 30, "all": None}


def _since(period: str) -> str:
    """Возвращает ISO 8601 UTC начала периода."""
    days = PERIOD_DAYS.get(period)
    if days is None:
        return "1970-01-01T00:00:00+00:00"
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _compute_streaks(active_days: list[str]) -> dict:
    """
    Из отсортированного списка дат YYYY-MM-DD считает текущий и рекордный стрик.
    Текущий = серия дней подряд заканчивающаяся сегодня или вчера.
    """
    if not active_days:
        return {"current": 0, "longest": 0, "active_days_total": 0}

    # Уникальные отсортированные даты
    days = [datetime.strptime(d, "%Y-%m-%d").date() for d in active_days]
    days_set = set(days)

    # Считаем longest streak
    longest = 1
    current_streak_in_history = 1
    for i in range(1, len(days)):
        if (days[i] - days[i - 1]).days == 1:
            current_streak_in_history += 1
            longest = max(longest, current_streak_in_history)
        elif (days[i] - days[i - 1]).days > 1:
            current_streak_in_history = 1

    # Текущий стрик (от сегодня назад)
    today = (datetime.now(timezone.utc) + timedelta(hours=LOCAL_TZ_OFFSET)).date()
    yesterday = today - timedelta(days=1)

    if today in days_set:
        anchor = today
    elif yesterday in days_set:
        anchor = yesterday
    else:
        return {"current": 0, "longest": longest, "active_days_total": len(days_set)}

    current = 1
    cursor = anchor
    while True:
        prev = cursor - timedelta(days=1)
        if prev in days_set:
            current += 1
            cursor = prev
        else:
            break

    return {
        "current": current,
        "longest": longest,
        "active_days_total": len(days_set),
    }


# ──────────────────────────────────────────────
#  ОСНОВНЫЕ ЭНДПОИНТЫ
# ──────────────────────────────────────────────

@app.get("/members")
async def members(limit: int | None = None):
    """Все участники, отсортированы по cumulative активности."""
    return {"members": await get_members(limit=limit)}


@app.get("/top")
async def top(
    period: Literal["week", "month", "all"] = "week",
    limit: int = 100,
):
    """Топ участников за период."""
    if period == "all":
        return {"period": "all", "members": await get_members(limit=limit)}
    since = _since(period)
    return {
        "period": period,
        "since": since,
        "members": await get_top_period(since, limit=limit),
    }


@app.get("/search")
async def search(
    q: str = "",
    role: str = "",
    limit: int = 50,
):
    """Поиск + фильтр по роли."""
    return {"members": await search_members(q.strip(), role.strip(), limit=limit)}


@app.get("/roles")
async def roles():
    """Список уникальных ролей с цветами и количеством участников."""
    return {"roles": await get_all_roles()}


@app.get("/profile/{user_id}")
async def profile(user_id: int, period: Literal["week", "month", "all"] = "month"):
    """Полный профиль участника со всей аналитикой."""
    user = await get_user(user_id)
    if user is None:
        raise HTTPException(404, "Участник не найден")

    since_period = _since(period)

    # Все данные параллельно были бы быстрее, но aiosqlite использует общий файл
    # — нет смысла, sequential read fast enough
    period_stats = await get_user_stats_period(user_id, since_period)
    timeline_day = await get_user_timeline(user_id, since_period, bucket="day")
    heatmap = await get_user_heatmap(user_id, since_period, LOCAL_TZ_OFFSET)
    hours = await get_user_active_hours(user_id, since_period, LOCAL_TZ_OFFSET)
    active_days = await get_user_active_days(user_id, LOCAL_TZ_OFFSET)
    streaks = _compute_streaks(active_days)

    # Сравнение с предыдущим аналогичным периодом
    prev_compare = None
    days = PERIOD_DAYS.get(period)
    if days:
        prev_since = (datetime.now(timezone.utc) - timedelta(days=days * 2)).isoformat()
        prev_until_dt = datetime.now(timezone.utc) - timedelta(days=days)
        prev_until = prev_until_dt.isoformat()
        # Считаем прошлый период вычитанием
        prev_total = await get_user_stats_period(user_id, prev_since)
        # prev_total включает текущий период тоже — вычтем его
        prev_compare = {
            "voice_seconds": max(0, prev_total["voice_seconds"] - period_stats["voice_seconds"]),
            "message_count": max(0, prev_total["message_count"] - period_stats["message_count"]),
        }
        # Уточним: нужны события >= prev_since И < prev_until
        # SQLite не любит между двумя — упрощено: за prev_since..now минус period_stats
        # Это правильно потому что prev_since включает period_stats

    return {
        "user": user,
        "period": period,
        "period_stats": period_stats,
        "prev_period_stats": prev_compare,
        "timeline": timeline_day,
        "heatmap": heatmap,        # 7×24 матрица секунд
        "hours": hours,            # 24 значения секунд по часам суток
        "streaks": streaks,
    }


# ──────────────────────────────────────────────
#  LEGACY (старый клиент)
# ──────────────────────────────────────────────

@app.get("/top15")
async def top15_legacy():
    data = await get_members(limit=15)
    return {"voice": data, "text": data}


# ──────────────────────────────────────────────
#  Раздача React-фронтенда
# ──────────────────────────────────────────────

FRONTEND_DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend", "dist")

if os.path.exists(FRONTEND_DIST):
    app.mount(
        "/assets",
        StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")),
        name="static-assets",
    )

    @app.get("/")
    async def serve_index():
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # SPA fallback (для React Router)
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))
