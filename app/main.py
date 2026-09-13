import asyncio
import os
import sqlite3
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


APP_VERSION = os.getenv("APP_VERSION", "0.1.0")
AUTO_BETTING = os.getenv("AUTO_BETTING", "false").lower() == "true"

DB_FILE = "crash_history.db"
MAX_HISTORY = 500


class CrashResult(BaseModel):
    multiplier: float


def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crash_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            multiplier REAL NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def save_result(multiplier: float):
    conn = sqlite3.connect(DB_FILE)

    conn.execute(
        "INSERT INTO crash_results (multiplier) VALUES (?)",
        (multiplier,)
    )

    conn.execute("""
        DELETE FROM crash_results
        WHERE id NOT IN (
            SELECT id
            FROM crash_results
            ORDER BY id DESC
            LIMIT ?
        )
    """, (MAX_HISTORY,))

    conn.commit()
    conn.close()


def history_count():
    conn = sqlite3.connect(DB_FILE)
    count = conn.execute(
        "SELECT COUNT(*) FROM crash_results"
    ).fetchone()[0]
    conn.close()
    return count


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🟢 CrashSignalAI\n\n"
        f"Version: {APP_VERSION}\n"
        "Mode: RESEARCH / DEMO\n"
        f"Auto Betting: {'ON' if AUTO_BETTING else 'OFF'}"
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    count = history_count()

    await update.message.reply_text(
        "🟢 CrashSignalAI Status\n"
        "Bot: ONLINE\n"
        "Engine: COLLECTING_DATA\n"
        f"Version: {APP_VERSION}\n"
        "Mode: RESEARCH / DEMO\n"
        f"Auto Betting: {'ON' if AUTO_BETTING else 'OFF'}\n"
        f"History: {count}/{MAX_HISTORY}\n"
        "Minimum data: 20"
    )


async def telegram_bot():
    token = os.getenv("TELEGRAM_BOT_TOKEN")

    if not token:
        print("Telegram token is not configured")
        return

    bot = Application.builder().token(token).build()

    bot.add_handler(CommandHandler("start", start))
    bot.add_handler(CommandHandler("status", status))

    try:
        await bot.initialize()
        await bot.start()
        await bot.updater.start_polling()

        print("Telegram bot started")

        while True:
            await asyncio.sleep(60)

    except Exception as error:
        print(f"Telegram bot error: {error}")

    finally:
        try:
            await bot.updater.stop()
            await bot.stop()
            await bot.shutdown()
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    print("Crash history database ready")

    bot_task = asyncio.create_task(telegram_bot())

    yield

    bot_task.cancel()

    try:
        await bot_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="CrashSignalAI",
    lifespan=lifespan,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {
        "app": "CrashSignalAI",
        "version": APP_VERSION,
        "status": "ONLINE",
        "auto_betting": AUTO_BETTING,
        "history": history_count(),
    }


@app.post("/ingest")
async def ingest(result: CrashResult):

    multiplier = float(result.multiplier)

    if not multiplier > 0:
        return {
            "status": "REJECTED",
            "reason": "invalid_multiplier"
        }

    save_result(multiplier)

    count = history_count()

    print(
        f"Saved crash result: {multiplier}x "
        f"| History: {count}/{MAX_HISTORY}"
    )

    return {
        "status": "SAVED",
        "multiplier": multiplier,
        "history": count,
    }


@app.get("/history")
async def get_history():

    conn = sqlite3.connect(DB_FILE)

    rows = conn.execute("""
        SELECT multiplier, created_at
        FROM crash_results
        ORDER BY id DESC
        LIMIT ?
    """, (MAX_HISTORY,)).fetchall()

    conn.close()

    return {
        "count": len(rows),
        "results": [
            {
                "multiplier": row[0],
                "created_at": row[1],
            }
            for row in rows
        ],
    }


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
    )
