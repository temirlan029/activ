# NEVERLOVE Activity Tracker — Документация для агента

Проект: Discord-бот + FastAPI + React дашборд для трекинга активности
сервера **Neverlove Fam'Q** (`1498790092104401009`).

---

## Текущее состояние

**Полностью рабочая система. Тестируется локально.**

Всё что работает:
- Бот подключается к Discord как `Neverlove_Activ#1552`
- Точный трекинг голоса с погрешностью **<1 секунды** (flush раз в 60с)
- Подсчёт сообщений в реальном времени
- Сохранение метаданных: имя, аватарка, топ-роль с цветом, дата вступления
- Real-time обновление ролей через `on_member_update` + periodic refresh раз в 5 мин
- Восстановление сессий после рестарта (clear → rescan)
- **Авто-отчёты в Discord-канал в 00:00 и 12:00 МСК** (UTC+3)
- Команда `!отчёт` для ручного запуска
- Веб-дашборд с цветовой индикацией активности (показывает ВСЕХ активных, не лимитировано)

**Чего ещё нет:**
- Деплой на DigitalOcean (юзер уже зарегался, но не настраивали)
- Push на GitHub
- HTTPS / домен

---

## Стек

| Слой | Технология |
|---|---|
| Бот | Python 3.12, `discord.py 2.3.2` |
| БД | SQLite через `aiosqlite` |
| API | FastAPI + Uvicorn |
| Фронт | React 18 + Vite + Tailwind CSS 3 |
| Лаунчер | `asyncio.gather(bot.start(), uvicorn.serve())` в одном процессе |

**ВАЖНО:** на Windows НЕ устанавливать `WindowsSelectorEventLoopPolicy` — это
ломает discord.py. Дефолтный ProactorEventLoop работает с обоими.

---

## Структура проекта

```
neverloveactiv/
├── main.py              ← Точка входа: бот + API в одном asyncio loop
├── bot.py               ← Discord бот, трекинг, события
├── api.py               ← FastAPI: /members, /top15, статика
├── database.py          ← SQLite слой, ISO 8601 UTC таймстемпы
├── requirements.txt
├── .env                 ← DISCORD_TOKEN=... PORT=8000
├── .env.example
├── .gitignore           ← .env, data/, __pycache__, frontend/dist
├── README.md
├── AGENTS.md            ← (этот файл)
├── bot_log.txt          ← Лог работы бота (UTF-8)
├── data/
│   └── activity.db      ← SQLite база
└── frontend/
    ├── src/
    │   ├── App.jsx      ← Главный компонент дашборда
    │   ├── main.jsx
    │   └── index.css
    ├── package.json
    ├── tailwind.config.js
    ├── vite.config.js
    └── dist/            ← Собранный фронт (раздаётся через FastAPI)
```

---

## Запуск локально

```bash
# 1. Зависимости Python
pip install -r requirements.txt

# 2. .env
cp .env.example .env
# Положить туда DISCORD_TOKEN

# 3. Собрать фронт
cd frontend && npm install && npm run build && cd ..

# 4. Запуск
python main.py
# Дашборд: http://localhost:8000
```

### Перезапуск во время разработки (Windows PowerShell)

```bash
# Убить процесс на порту 8000
powershell -Command "Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id \$_.OwningProcess -Force -ErrorAction SilentlyContinue }"
sleep 2
python -u main.py
```

### Чтение логов на Windows

Лог в UTF-8, терминал может не отображать кириллицу. Безопасный способ:

```bash
python -u -c "
import sys
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
sys.stdout.write(open(r'C:\Users\tima\Desktop\neverloveactiv\bot_log.txt','rb').read().decode('utf-8','replace'))
" 2>&1 | cat
```

---

## Архитектура трекинга голоса

**Источник истины** — словарь в памяти:
```python
active_sessions: dict[user_id -> datetime UTC]
```
Значение = момент с которого ещё не сохранено время для этого юзера.

Три атомарные операции:

```
start_session(user_id, channel_id):
    active_sessions[user_id] = NOW
    DB voice_sessions ← (user_id, channel_id, NOW.isoformat())

end_session(user_id):
    delta = NOW - active_sessions[user_id]
    users.voice_seconds += delta
    del active_sessions[user_id]
    DB DELETE FROM voice_sessions

flush_session(user_id):  # каждые 60с
    delta = NOW - active_sessions[user_id]
    users.voice_seconds += delta
    active_sessions[user_id] = NOW          # сдвиг точки отсчёта
    DB UPDATE voice_sessions SET joined_at = NOW
```

### Маппинг событий `on_voice_state_update`

| Что | Действие |
|---|---|
| JOIN (None → channel) | `start_session` |
| LEAVE (channel → None) | `end_session` |
| MOVE (channel A → B) | `end_session` + `start_session` |
| STATE (mute/deafen, тот же канал) | если не отслеживается — `start_session`, иначе ничего |

### При `on_ready` / `on_guild_join`

1. `clear_all_sessions()` — стираем старые сессии из БД
2. Сканируем все voice channels, открываем сессии для всех в войсе с `now`
3. Стартуем `flush_loop` (60с) и `refresh_metadata_loop` (5мин)

**Гарантия:** теряем максимум 60 секунд при крэше, никогда не считаем время простоя бота.

---

## Схема БД

```sql
CREATE TABLE users (
    user_id          TEXT PRIMARY KEY,
    username         TEXT NOT NULL,
    avatar_url       TEXT NOT NULL DEFAULT '',
    top_role_name    TEXT NOT NULL DEFAULT '',
    top_role_color   INTEGER NOT NULL DEFAULT 0,  -- Discord int color
    server_joined_at TEXT NOT NULL DEFAULT '',    -- ISO 8601 UTC
    voice_seconds    INTEGER NOT NULL DEFAULT 0,
    message_count    INTEGER NOT NULL DEFAULT 0,
    last_active      TEXT NOT NULL DEFAULT ''     -- ISO 8601 UTC
);

CREATE TABLE voice_sessions (
    user_id    TEXT PRIMARY KEY,
    channel_id TEXT NOT NULL,
    joined_at  TEXT NOT NULL                      -- ISO 8601 UTC
);
```

`init_db()` делает `ALTER TABLE ADD COLUMN` для миграции старых БД (try/except — игнор если колонка уже есть).

**Все таймстемпы — ISO 8601 UTC с явной таймзоной**, чтобы не было неоднозначностей с SQLite `CURRENT_TIMESTAMP` на разных платформах.

---

## API

| Endpoint | Описание |
|---|---|
| `GET /members` | **Все** активные участники (без лимита), сортировка по войсу → сообщениям |
| `GET /members?limit=N` | Только N первых |
| `GET /top15` | Legacy совместимость, возвращает `{voice: [...], text: [...]}` (обе одинаковые, 15 шт) |
| `GET /` | Раздача React фронтенда |
| `GET /assets/*` | Статика фронтенда |

Структура одного юзера в ответе:
```json
{
  "user_id": "846507833599983647",
  "username": "Adolf | Тима |94507",
  "avatar_url": "https://cdn.discordapp.com/avatars/.../...",
  "top_role_name": "Owner",
  "top_role_color": 15844367,
  "server_joined_at": "2026-04-28T...+00:00",
  "voice_seconds": 1665,
  "message_count": 0,
  "last_active": "2026-05-07T23:39:10..."
}
```

---

## Фронтенд

**Дизайн:** тёмный кибerpunk + акцент на полосе слева у строки.

**Файлы:**
- `frontend/src/App.jsx` — основной компонент
- `frontend/src/index.css` — стили (Tailwind + custom)

**Цветовая схема активности (по войсу):**
- `> 10ч` → зелёная полоса/строка (`#00ff7f`)
- `3–10ч` → жёлтая (`#ffd600`)
- `< 3ч` → красная (`#ff1744`)

**Колонки таблицы:**
1. # (ранг)
2. Игрок (аватар + ник)
3. Роль (бейдж с настоящим Discord-цветом)
4. Сообщения
5. Войс (отформатировано в часы/минуты)
6. Вступил (дата вступления на сервер)

**Авто-рефреш:** каждые 30 секунд + кнопка "↻ Обновить".

**Сборка:**
```bash
cd frontend && npm run build
# артефакты в frontend/dist/, FastAPI их раздаёт
```

---

## Авто-отчёты в Discord

Бот отправляет отчёт об активности в указанный текстовый канал **2 раза в день**:
**00:00 и 12:00 по Москве (UTC+3)**.

**Канал назначения:** `1502095669396111482`

**Формат сообщения:**
```
📊 ОТЧЁТ ОБ АКТИВНОСТИ — 12.05.2026 12:00 МСК

👥 Активных участников: 23
🎙️ Общий голосовой опыт: 156ч 30м
💬 Всего сообщений: 1234

[таблица топ-15]
```

Если активных >15 — к сообщению прикрепляется файл `.txt`
со ВСЕМИ участниками (с ролями, войсом, сообщениями, датой вступления).

**Реализация:** `tasks.loop(time=REPORT_TIMES)` в `bot.py`. discord.py
v2 поддерживает список объектов `time` с tzinfo как расписание.

**Перед формированием отчёта** делается `flush_session` всех активных
участников, чтобы данные были максимально свежими (с погрешностью <1с).

**Ручной запуск:** команда `!отчёт` в любом канале сервера. Бот ставит
⏳, отправляет отчёт в `REPORT_CHANNEL_ID`, затем ✅.

**Конфигурация в `bot.py`:**
```python
REPORT_CHANNEL_ID = 1502095669396111482
REPORT_TZ         = timezone(timedelta(hours=3))   # UTC+3
REPORT_TIMES      = [time(0, 0, tzinfo=...), time(12, 0, tzinfo=...)]
```

---

## Конфигурация (bot.py)

```python
GUILD_IDS: set[int] = {
    1498790092104401009,   # Neverlove Fam'Q
}
FLUSH_INTERVAL_SECONDS = 60
```

**Discord Intents:**
- `message_content` — для on_message (требует включения в Dev Portal)
- `voice_states` — для on_voice_state_update
- `members` — для on_member_update + видимости участников

**Минимальные права бота на сервере** (permissions=66560):
- View Channels
- Read Message History

Никаких прав на модерацию/кик/бан — бот только наблюдает.

---

## Деплой на DigitalOcean (план, не сделано)

1. Droplet Ubuntu 22.04 LTS, $6/мес (1 vCPU, 1GB RAM), регион Amsterdam/Frankfurt
2. SSH → `apt install python3-pip nodejs npm git`
3. `git clone` репозитория
4. `pip3 install -r requirements.txt`
5. `cd frontend && npm install && npm run build`
6. `.env` с токеном
7. systemd unit `/etc/systemd/system/neverlove.service`:
   ```ini
   [Service]
   WorkingDirectory=/root/neverloveactiv
   ExecStart=/usr/bin/python3 main.py
   Restart=always
   EnvironmentFile=/root/neverloveactiv/.env
   ```
8. `systemctl enable --now neverlove`

Frontend можно либо раздавать через FastAPI (как сейчас), либо отдельно на Vercel.

---

## Как сбросить счётчики (если нужно тестить с нуля)

```python
import sqlite3
conn = sqlite3.connect(r'C:\Users\tima\Desktop\neverloveactiv\data\activity.db')
conn.execute('UPDATE users SET voice_seconds = 0, message_count = 0')
conn.execute('DELETE FROM voice_sessions')
conn.commit()
```

После — обязательно перезапустить бот, чтобы in-memory `active_sessions`
тоже обнулился.

---

## Известные особенности / TODO

**TODO:**
- [ ] Деплой на DigitalOcean
- [ ] GitHub репозиторий + CI

**Особенности (как сейчас работает):**
- Ник на дашборде показывается из `display_name` (учитывает серверный никнейм)
- При смене роли через Discord — обновление в дашборде в течение 30с (`on_member_update` + 30с авто-рефреш фронта)
- При оффлайне бота — теряется до 60с активности (последний несохранённый flush)
- Аватарки берутся напрямую с CDN Discord — если юзер сменит аватар, на дашборде обновится через периодический мета-рефреш (5 мин)
- Авто-отчёты привязаны к Москве (UTC+3) — если переезд в другой часовой пояс, поменять `REPORT_TZ` в `bot.py`
- Отчёты пропускаются если бот был выключен в момент срабатывания (расписание не догоняется задним числом)

---

## Контакты конфига

| Что | Значение |
|---|---|
| Discord Application ID | `1502072942622802082` |
| Bot Username | `Neverlove_Activ#1552` |
| Main Guild ID | `1498790092104401009` (Neverlove Fam'Q) |
| Канал авто-отчётов | `1502095669396111482` |
| Расписание отчётов | 00:00 и 12:00 МСК |
| Таймзона отчётов | UTC+3 (Москва) |
| Локальный путь | `C:\Users\tima\Desktop\neverloveactiv` |
| Хостинг (план) | DigitalOcean ($6/мес, аккаунт уже создан) |

---

## Новые функции (обновление 2026-05-08)

### Time-series аналитика

Добавлена таблица `activity_events` для хранения истории всех событий:
- Голосовые отрезки (с длительностью в секундах)
- Сообщения (duration=0)
- Таймстемпы в ISO 8601 UTC
- Индексы по user_id+timestamp и timestamp для быстрых запросов

### Новые API эндпоинты

| Endpoint | Описание |
|---|---|
| `GET /top?period=week|month|all&limit=N` | Топ участников за период |
| `GET /search?q=имя&role=Роль&limit=N` | Поиск по имени + фильтр по роли |
| `GET /roles` | Список уникальных ролей |
| `GET /profile/{user_id}?period=week|month|all` | Полный профиль с аналитикой |

### Новый фронтенд

**Технологии:**
- `react-router-dom` — навигация между страницами
- `chart.js` + `react-chartjs-2` — графики активности
- Tailwind CSS — адаптивный дизайн

**Структура:**
- `src/components/Common.jsx` — общие компоненты (Avatar, RoleBadge, утилиты)
- `src/pages/Home.jsx` — главная страница
- `src/pages/Profile.jsx` — профиль участника

**Главная страница:**
- Переключатель периодов (неделя/месяц/всё)
- Поиск по имени участника
- Фильтр по роли (выпадающий список)
- Клик на строку → переход на профиль
- Автообновление каждые 30 сек

**Профиль участника:**
- Информация: аватар, имя, роль, дата вступления
- Переключатель периодов
- Статистика за период с сравнением с прошлым периодом
- **Стрики:** текущий, рекорд, всего дней
- **График активности:** линейный Chart.js (войс + сообщения по дням)
- **Heatmap:** 7×24 матрица (день недели × час) как на GitHub
- **Активные часы:** бар по 24 часам суток

### Бэкенд изменения

**database.py:**
- `log_voice_event()` — запись голосового отрезка в историю
- `log_message_event()` — запись сообщения в историю
- `get_user_stats_period()` — статистика за период
- `get_top_period()` — топ за период
- `get_user_timeline()` — агрегация по дням/часам
- `get_user_heatmap()` — 7×24 матрица активности
- `get_user_active_hours()` — активность по часам суток
- `get_user_active_days()` — список дней с активностью
- `search_members()` — поиск + фильтр
- `get_all_roles()` — список уникальных ролей

**bot.py:**
- `_session_channel` — отслеживание канала для каждой сессии
- `start_session()` — сохраняет канал
- `end_session()` — пишет в историю при выходе
- `flush_session()` — пишет отрезок в историю при flush
- `on_message()` — пишет каждое сообщение в историю
- Очистка `_session_channel` при `on_ready`

**api.py:**
- Полностью переписан с новыми эндпоинтами
- `_compute_streaks()` — расчёт стриков из списка дней
- `_since()` — утилита для расчёта начала периода
- Поддержка периодов: week (7дн), month (30дн), all (всё время)

---

## Обновлённое текущее состояние (2026-05-08)

**Полностью рабочая система с расширенной аналитикой. Тестируется локально.**

Всё что работает:
- Бот подключается к Discord как `Neverlove_Activ#1552`
- Точный трекинг голоса с погрешностью **<1 секунды** (flush раз в 60с)
- Подсчёт сообщений в реальном времени
- Сохранение метаданных: имя, аватарка, топ-роль с цветом, дата вступления
- Real-time обновление ролей через `on_member_update` + periodic refresh раз в 5 мин
- Восстановление сессий после рестарта (clear → rescan)
- **Авто-отчёты в Discord-канал в 00:00 и 12:00 МСК** (UTC+3)
- Команда `!отчёт` для ручного запуска
- Веб-дашборд с цветовой индикацией активности (показывает ВСЕХ активных, не лимитировано)
- **Time-series аналитика:** история всех событий для графиков и статистики
- **Стрики:** текущий стрик, рекорд, всего дней активности
- **Графики активности:** по дням/неделям/месяцам (Chart.js)
- **Heatmap:** 7×24 матрица (день недели × час) как на GitHub
- **Активные часы:** распределение активности по часам суток
- **Поиск и фильтры:** по имени участника, по роли
- **Профили участников:** детальная страница с полной аналитикой

---

## Обновлённый стек технологий

| Слой | Технология |
|---|---|
| Бот | Python 3.12, `discord.py 2.3.2` |
| БД | SQLite через `aiosqlite` |
| API | FastAPI + Uvicorn |
| Фронт | React 19 + Vite + Tailwind CSS 3 + React Router + Chart.js + react-chartjs-2 |
| Лаунчер | `asyncio.gather(bot.start(), uvicorn.serve())` в одном процессе |
