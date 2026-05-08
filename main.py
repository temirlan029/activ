"""
Точка входа — запускает Discord-бот и FastAPI-сервер в одном asyncio-процессе.
"""
import asyncio
import os
import sys
import traceback

import uvicorn
from dotenv import load_dotenv

load_dotenv()

from bot import bot
from api import app

TOKEN = os.getenv("DISCORD_TOKEN")
PORT  = int(os.getenv("PORT", 8000))

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_log.txt")


def log(msg: str):
    line = msg + "\n"
    sys.stdout.write(line)
    sys.stdout.flush()
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)


async def run_bot():
    try:
        await bot.start(TOKEN)
    except Exception as e:
        log(f"[БОТ] ОШИБКА: {e}")
        log(traceback.format_exc())


async def main():
    if not TOKEN:
        log("DISCORD_TOKEN не задан в .env!")
        return

    log(f"[СТАРТ] Запуск сервера на порту {PORT}...")

    uvicorn_config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=PORT,
        log_level="info",
    )
    server = uvicorn.Server(uvicorn_config)

    # Запускаем бот и веб-сервер параллельно в одном event loop
    try:
        await asyncio.gather(
            run_bot(),
            server.serve(),
        )
    except Exception as e:
        log(f"[MAIN] ОШИБКА: {e}")
        log(traceback.format_exc())


if __name__ == "__main__":
    asyncio.run(main())
