"""
Discord-бот: трекинг голосовой и текстовой активности.

АРХИТЕКТУРА ТРЕКИНГА ГОЛОСА
────────────────────────────
Источник истины во время работы — это словарь:

    active_sessions: dict[user_id -> datetime UTC]

Значение = момент, С КОТОРОГО ЕЩЁ НЕ СОХРАНЕНО ВРЕМЯ для этого пользователя.

Три атомарные операции:

  start_session(user_id, channel_id):
      active_sessions[user_id] = NOW
      БД: voice_sessions ← (user_id, channel_id, NOW)

  end_session(user_id):
      delta = NOW - active_sessions[user_id]
      users.voice_seconds += delta
      del active_sessions[user_id]
      БД: DELETE FROM voice_sessions

  flush_session(user_id):  # периодически, чтобы не потерять при крэше
      delta = NOW - active_sessions[user_id]
      users.voice_seconds += delta
      active_sessions[user_id] = NOW          # сдвигаем "точку отсчёта"
      БД: UPDATE voice_sessions SET joined_at = NOW

События on_voice_state_update:

  JOIN  (None → channel)              : start_session
  LEAVE (channel → None)              : end_session
  MOVE  (channel A → channel B)       : end_session + start_session
  STATE (mute/deafen, тот же канал)   : если не отслеживается — start_session;
                                        иначе — ничего (время продолжает идти)

При старте on_ready:
  1. clear_all_sessions() — стираем старые сессии из БД (теряем максимум 60с,
     это плата за гарантированную консистентность)
  2. Сканируем все голосовые каналы — для каждого пользователя в войсе вызываем
     start_session(user_id, channel_id). Точка отсчёта = NOW.

Точно так же on_guild_join — сканируем войсы нового сервера.

Периодический flush раз в 60 секунд — гарантирует, что при крэше теряется не
больше минуты на пользователя.
"""

from __future__ import annotations

import io
import os
import traceback
from datetime import datetime, time, timedelta, timezone

import discord
from discord.ext import commands, tasks

from database import (
    init_db,
    upsert_user,
    add_voice_seconds,
    add_message,
    save_voice_session,
    update_session_timestamp,
    delete_voice_session,
    clear_all_sessions,
    get_members,
    log_voice_event,
    log_message_event,
    utc_now_iso,
)


# ──────────────────────────────────────────────────────────────────────────────
#  КОНФИГ
# ──────────────────────────────────────────────────────────────────────────────

GUILD_IDS: set[int] = {
    1498790092104401009,   # Neverlove Fam'Q
}

FLUSH_INTERVAL_SECONDS = 60   # как часто сбрасывать накопленное время в БД

# Канал для авто-отчётов и время отправки (в локальной таймзоне)
REPORT_CHANNEL_ID = 1502095669396111482
REPORT_TZ         = timezone(timedelta(hours=3))   # UTC+3 (Москва)
REPORT_TIMES      = [time(0, 0, tzinfo=timezone(timedelta(hours=3))),
                     time(12, 0, tzinfo=timezone(timedelta(hours=3)))]


# ──────────────────────────────────────────────────────────────────────────────
#  ЛОГИРОВАНИЕ
# ──────────────────────────────────────────────────────────────────────────────

_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_log.txt")


def log(msg: str) -> None:
    line = f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    try:
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────────────────────
#  СОСТОЯНИЕ
# ──────────────────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states    = True
intents.members         = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Источник истины: {user_id: datetime UTC — момент, с которого ещё не сохранено}
active_sessions: dict[int, datetime] = {}
# Канал текущей сессии: {user_id: channel_id}
_session_channel: dict[int, int] = {}


# ──────────────────────────────────────────────────────────────────────────────
#  ХЕЛПЕРЫ: метаданные участника
# ──────────────────────────────────────────────────────────────────────────────

def member_meta(member: discord.Member) -> dict:
    """Извлекает метаданные участника для записи в БД."""
    role = member.top_role
    has_role = role is not None and role.name != "@everyone"
    return {
        "username":         member.display_name,
        "avatar_url":       str(member.display_avatar.url) if member.display_avatar else "",
        "top_role_name":    role.name if has_role else "",
        "top_role_color":   role.color.value if has_role else 0,
        "server_joined_at": member.joined_at.isoformat() if member.joined_at else "",
    }


async def upsert_member(member: discord.Member) -> None:
    """Сохраняет/обновляет участника в БД со всеми метаданными."""
    await upsert_user(member.id, **member_meta(member))


# ──────────────────────────────────────────────────────────────────────────────
#  АТОМАРНЫЕ ОПЕРАЦИИ
# ──────────────────────────────────────────────────────────────────────────────

async def start_session(user_id: int, channel_id: int) -> None:
    """Открывает сессию: ставит точку отсчёта = NOW."""
    now = datetime.now(timezone.utc)
    active_sessions[user_id] = now
    # Сохраняем канал чтобы при flush/end знать куда писать в историю
    _session_channel[user_id] = channel_id
    await save_voice_session(user_id, channel_id, now.isoformat())


async def end_session(user_id: int) -> int:
    """
    Закрывает сессию: считает delta, прибавляет в users.voice_seconds,
    пишет в историю, удаляет запись из voice_sessions.
    Возвращает количество добавленных секунд.
    """
    if user_id not in active_sessions:
        await delete_voice_session(user_id)
        return 0

    start_time = active_sessions.pop(user_id)
    channel_id = _session_channel.pop(user_id, 0)
    delta = int((datetime.now(timezone.utc) - start_time).total_seconds())
    if delta < 0:
        delta = 0

    if delta > 0:
        await add_voice_seconds(user_id, delta)
        await log_voice_event(user_id, channel_id, delta)
    await delete_voice_session(user_id)
    return delta


async def flush_session(user_id: int) -> int:
    """
    Сохраняет накопленное время БЕЗ закрытия сессии.
    Сдвигает точку отсчёта на NOW. Пишет отрезок в историю.
    """
    if user_id not in active_sessions:
        return 0

    now = datetime.now(timezone.utc)
    start_time = active_sessions[user_id]
    delta = int((now - start_time).total_seconds())

    if delta < 1:
        return 0

    channel_id = _session_channel.get(user_id, 0)
    await add_voice_seconds(user_id, delta)
    await log_voice_event(user_id, channel_id, delta)
    active_sessions[user_id] = now
    await update_session_timestamp(user_id, now.isoformat())
    return delta


# ──────────────────────────────────────────────────────────────────────────────
#  СКАНИРОВАНИЕ ВОЙСОВ
# ──────────────────────────────────────────────────────────────────────────────

async def scan_guild_voice(guild: discord.Guild) -> int:
    """
    Открывает сессии для всех, кто СЕЙЧАС в войсе на сервере.
    Возвращает число открытых сессий.
    """
    count = 0
    for channel in guild.voice_channels:
        for member in channel.members:
            if member.bot:
                continue
            if member.id in active_sessions:
                continue
            await upsert_member(member)
            await start_session(member.id, channel.id)
            count += 1
    return count


# ──────────────────────────────────────────────────────────────────────────────
#  СОБЫТИЯ ЖИЗНЕННОГО ЦИКЛА БОТА
# ──────────────────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    try:
        log(f"[БОТ] on_ready. Подключён как {bot.user}")
        await init_db()

        # Стираем старые сессии (бот мог быть выключен — мы не знаем сколько).
        # Цена: теряем последние 0–60 секунд активности перед крэшем.
        # Выгода: 100% гарантия что не насчитаем "лишнее" время простоя.
        await clear_all_sessions()
        active_sessions.clear()
        _session_channel.clear()

        total = 0
        for guild_id in GUILD_IDS:
            guild = bot.get_guild(guild_id)
            if guild is None:
                log(f"[БОТ] Сервер {guild_id} не найден (бот не добавлен)")
                continue
            log(f"[БОТ] Подключён к серверу: {guild.name}")
            total += await scan_guild_voice(guild)

        if not flush_loop.is_running():
            flush_loop.start()
        if not refresh_metadata_loop.is_running():
            refresh_metadata_loop.start()
        if not report_loop.is_running():
            report_loop.start()

        log(f"[БОТ] Запущено сессий при старте: {total}")
        log(f"[БОТ] Готов. Flush {FLUSH_INTERVAL_SECONDS}с, мета 5мин, "
            f"отчёты в 00:00 и 12:00 МСК")

    except Exception as exc:
        log(f"[БОТ] ОШИБКА в on_ready: {exc}")
        log(traceback.format_exc())


@bot.event
async def on_guild_join(guild: discord.Guild):
    """Бот добавлен на сервер во время работы."""
    if guild.id not in GUILD_IDS:
        log(f"[БОТ] Добавлен на неотслеживаемый сервер: {guild.name} ({guild.id})")
        return
    log(f"[БОТ] Добавлен на сервер: {guild.name}")
    await init_db()
    count = await scan_guild_voice(guild)
    log(f"[БОТ] Открыто сессий: {count}")


# ──────────────────────────────────────────────────────────────────────────────
#  ОБНОВЛЕНИЕ УЧАСТНИКА (роли, ник, аватар)
# ──────────────────────────────────────────────────────────────────────────────

@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    """Срабатывает при смене ника, ролей, статуса буста и т.д."""
    if after.bot or after.guild.id not in GUILD_IDS:
        return
    # Обновляем метаданные только если что-то реально поменялось
    if (
        before.display_name != after.display_name
        or before.top_role != after.top_role
        or before.display_avatar != after.display_avatar
    ):
        try:
            await upsert_member(after)
            log(f"[МЕТА] Обновлены данные {after.display_name} "
                f"(роль: {after.top_role.name})")
        except Exception as exc:
            log(f"[МЕТА] ОШИБКА при обновлении {after.id}: {exc}")


# ──────────────────────────────────────────────────────────────────────────────
#  ПЕРИОДИЧЕСКИЙ FLUSH
# ──────────────────────────────────────────────────────────────────────────────

@tasks.loop(seconds=FLUSH_INTERVAL_SECONDS)
async def flush_loop():
    """Сбрасывает накопленное время всех активных сессий в БД."""
    try:
        # snapshot ключей чтобы не падать на изменении словаря во время итерации
        for user_id in list(active_sessions.keys()):
            await flush_session(user_id)
    except Exception as exc:
        log(f"[FLUSH] ОШИБКА: {exc}")
        log(traceback.format_exc())


# ──────────────────────────────────────────────────────────────────────────────
#  ПЕРИОДИЧЕСКОЕ ОБНОВЛЕНИЕ МЕТАДАННЫХ (раз в 5 минут)
# ──────────────────────────────────────────────────────────────────────────────

@tasks.loop(minutes=5)
async def refresh_metadata_loop():
    """Подтягивает свежие роли/ники/аватарки всех активных участников."""
    try:
        for guild_id in GUILD_IDS:
            guild = bot.get_guild(guild_id)
            if guild is None:
                continue
            for user_id in list(active_sessions.keys()):
                member = guild.get_member(user_id)
                if member and not member.bot:
                    await upsert_member(member)
    except Exception as exc:
        log(f"[МЕТА-LOOP] ОШИБКА: {exc}")


# ──────────────────────────────────────────────────────────────────────────────
#  АВТО-ОТЧЁТЫ В ТЕКСТОВЫЙ КАНАЛ
# ──────────────────────────────────────────────────────────────────────────────

def _format_voice(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}с"
    if seconds < 3600:
        return f"{seconds // 60}м"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h}ч {m}м" if m else f"{h}ч"


async def build_report() -> tuple[str, str]:
    """
    Формирует отчёт.
    Возвращает:
      header — короткая шапка-эмбед (поместится в одно сообщение),
      body   — полный текст со всеми участниками для file attachment.
    """
    members = await get_members()  # все
    now_local = datetime.now(REPORT_TZ)

    # Сначала flush'им активные сессии чтобы данные были свежие
    for user_id in list(active_sessions.keys()):
        await flush_session(user_id)
    members = await get_members()

    total_voice = sum(m["voice_seconds"] for m in members)
    total_msgs  = sum(m["message_count"] for m in members)

    # ── Шапка для эмбеда ──
    header = (
        f"📊 **ОТЧЁТ ОБ АКТИВНОСТИ — {now_local.strftime('%d.%m.%Y %H:%M')} МСК**\n\n"
        f"👥 Активных участников: **{len(members)}**\n"
        f"🎙️ Общий голосовой опыт: **{_format_voice(total_voice)}**\n"
        f"💬 Всего сообщений: **{total_msgs}**\n"
    )

    # ── Тело: топ для embed (первые 15) ──
    top_lines = ["```", f"{'#':<3} {'Участник':<28} {'Войс':<10} {'Сообщ.':<8}"]
    top_lines.append("─" * 52)
    for i, m in enumerate(members[:15], 1):
        name = m["username"][:27]
        voice = _format_voice(m["voice_seconds"])
        msgs  = str(m["message_count"])
        top_lines.append(f"{i:<3} {name:<28} {voice:<10} {msgs:<8}")
    top_lines.append("```")
    embed_top = "\n".join(top_lines)

    # ── Полный текст для файла ──
    body_lines = [
        f"ОТЧЁТ ОБ АКТИВНОСТИ — Neverlove Fam'Q",
        f"Дата: {now_local.strftime('%d.%m.%Y %H:%M')} МСК",
        "",
        f"Активных участников: {len(members)}",
        f"Общий голосовой опыт: {_format_voice(total_voice)}",
        f"Всего сообщений: {total_msgs}",
        "",
        f"{'#':<4} {'Участник':<32} {'Роль':<20} {'Войс':<12} {'Сообщ.':<8} {'Вступил':<12}",
        "─" * 95,
    ]
    for i, m in enumerate(members, 1):
        joined = ""
        if m["server_joined_at"]:
            try:
                joined = datetime.fromisoformat(m["server_joined_at"]).strftime("%d.%m.%Y")
            except Exception:
                pass
        body_lines.append(
            f"{i:<4} {m['username'][:31]:<32} {(m['top_role_name'] or '—')[:19]:<20} "
            f"{_format_voice(m['voice_seconds']):<12} {m['message_count']:<8} {joined:<12}"
        )
    body = "\n".join(body_lines)

    return header + "\n" + embed_top, body


async def send_report():
    """Отправляет отчёт в канал."""
    try:
        channel = bot.get_channel(REPORT_CHANNEL_ID)
        if channel is None:
            channel = await bot.fetch_channel(REPORT_CHANNEL_ID)
        if channel is None:
            log(f"[ОТЧЁТ] Канал {REPORT_CHANNEL_ID} не найден")
            return

        header_with_top, full_body = await build_report()

        # Если активных <=15 — отправляем только embed-сообщение
        members = await get_members()
        if len(members) <= 15:
            await channel.send(header_with_top)
        else:
            # Иначе — embed + файл со всеми
            file = discord.File(
                io.BytesIO(full_body.encode("utf-8")),
                filename=f"отчёт_{datetime.now(REPORT_TZ).strftime('%Y-%m-%d_%H%M')}.txt"
            )
            await channel.send(header_with_top, file=file)

        log(f"[ОТЧЁТ] Отправлен в канал {channel.name}, участников: {len(members)}")

    except Exception as exc:
        log(f"[ОТЧЁТ] ОШИБКА: {exc}")
        log(traceback.format_exc())


@tasks.loop(time=REPORT_TIMES)
async def report_loop():
    await send_report()


# Ручной триггер отчёта (только в самом канале или для удобства тестирования)
@bot.command(name="отчёт")
async def manual_report(ctx: commands.Context):
    if ctx.guild and ctx.guild.id not in GUILD_IDS:
        return
    await ctx.message.add_reaction("⏳")
    await send_report()
    try:
        await ctx.message.add_reaction("✅")
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────────────────────
#  СОБЫТИЕ ИЗМЕНЕНИЯ ГОЛОСОВОГО СОСТОЯНИЯ
# ──────────────────────────────────────────────────────────────────────────────

@bot.event
async def on_voice_state_update(
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
):
    if member.bot or member.guild.id not in GUILD_IDS:
        return

    try:
        await upsert_member(member)

        before_ch = before.channel
        after_ch  = after.channel

        # ── СОБЫТИЕ: ПОДКЛЮЧЕНИЕ К ГОЛОСОВОМУ КАНАЛУ ────────────────────────
        if before_ch is None and after_ch is not None:
            await start_session(member.id, after_ch.id)
            return

        # ── СОБЫТИЕ: ОТКЛЮЧЕНИЕ ОТ ГОЛОСОВОГО КАНАЛА ────────────────────────
        if before_ch is not None and after_ch is None:
            await end_session(member.id)
            return

        # ── СОБЫТИЕ: ПЕРЕХОД МЕЖДУ КАНАЛАМИ ─────────────────────────────────
        if before_ch is not None and after_ch is not None and before_ch.id != after_ch.id:
            # 1. Закрываем сессию в старом канале (сохраняем время)
            await end_session(member.id)
            # 2. Открываем сессию в новом канале (новый отсчёт)
            await start_session(member.id, after_ch.id)
            return

        # ── СОБЫТИЕ: ИЗМЕНЕНИЕ СОСТОЯНИЯ В ТОМ ЖЕ КАНАЛЕ (mute/deafen/...) ──
        # Время продолжает идти.
        # Но если по какой-то причине участник был в войсе и не отслеживался —
        # начинаем считать с этого момента (recovery).
        if before_ch is not None and after_ch is not None:
            if member.id not in active_sessions:
                log(f"[РЕКАВЕРИ] {member.display_name} был в войсе без сессии — открываю")
                await start_session(member.id, after_ch.id)
            return

    except Exception as exc:
        log(f"[ГОЛОС] ОШИБКА у {member.display_name}: {exc}")
        log(traceback.format_exc())


# ──────────────────────────────────────────────────────────────────────────────
#  СОБЫТИЕ СООБЩЕНИЯ
# ──────────────────────────────────────────────────────────────────────────────

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if not message.guild or message.guild.id not in GUILD_IDS:
        return

    try:
        # message.author в guild-сообщениях это Member со всеми метаданными
        if isinstance(message.author, discord.Member):
            await upsert_member(message.author)
        else:
            await upsert_user(message.author.id, message.author.display_name)
        await add_message(message.author.id)
        await log_message_event(message.author.id, message.channel.id)
    except Exception as exc:
        log(f"[ТЕКСТ] ОШИБКА: {exc}")

    await bot.process_commands(message)
