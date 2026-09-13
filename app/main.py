import os
import sqlite3
import asyncio
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from telegram import Bot


APP_VERSION = os.getenv("APP_VERSION", "0.3.0")
DB_FILE = "crash_history.db"

MAX_HISTORY = 500
MIN_DATA = 20

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Auto betting is permanently disabled.
AUTO_BETTING = False

last_alert_level = None


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


def save_result(multiplier):
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


def get_results():
    conn = sqlite3.connect(DB_FILE)

    rows = conn.execute("""
        SELECT multiplier
        FROM crash_results
        ORDER BY id DESC
        LIMIT ?
    """, (MAX_HISTORY,)).fetchall()

    conn.close()

    return [float(x[0]) for x in rows]


def history_count():
    conn = sqlite3.connect(DB_FILE)

    count = conn.execute(
        "SELECT COUNT(*) FROM crash_results"
    ).fetchone()[0]

    conn.close()

    return count


def analyze():
    global last_alert_level

    data = get_results()

    if len(data) < MIN_DATA:
        return None

    sample = data[:MIN_DATA]

    average = sum(sample) / len(sample)

    below_2 = sum(x < 2 for x in sample)
    above_2 = sum(x >= 2 for x in sample)
    above_5 = sum(x >= 5 for x in sample)

    below_2_pct = below_2 / len(sample)
    above_5_pct = above_5 / len(sample)

    if below_2_pct >= 0.70:
        level = "HIGH"

        reason = (
            "70% or more of the recent observations "
            "were below 2x."
        )

    elif above_5_pct >= 0.20:
        level = "WATCH"

        reason = (
            "At least 20% of the recent observations "
            "were at or above 5x."
        )

    else:
        level = "NORMAL"
        reason = "No strong statistical condition detected."

    # Only alert when the condition changes.
    if level == last_alert_level:
        return None

    last_alert_level = level

    if level == "NORMAL":
        return None

    return {
        "level": level,
        "sample": len(sample),
        "average": average,
        "below_2": below_2,
        "above_2": above_2,
        "above_5": above_5,
        "reason": reason,
    }


async def send_telegram_alert(analysis):
    if not TELEGRAM_TOKEN:
        print("Telegram token missing")
        return

    if not TELEGRAM_CHAT_ID:
        print("Telegram chat ID missing")
        return

    message = (
        "📊 CrashSignalAI\n"
        "Research Alert\n\n"
        f"Level: {analysis['level']}\n"
        f"Sample: {analysis['sample']}\n"
        f"Average: {analysis['average']:.2f}x\n\n"
        f"Below 2x: {analysis['below_2']}\n"
        f"2x+: {analysis['above_2']}\n"
        f"5x+: {analysis['above_5']}\n\n"
        f"Reason:\n{analysis['reason']}\n\n"
        "⚠️ Statistical information only.\n"
        "Auto Betting: OFF"
    )

    try:
        bot = Bot(token=TELEGRAM_TOKEN)

        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message
        )

        print("Research alert sent to Telegram")

    except Exception as error:
        print(f"Telegram alert error: {error}")


async def start(update, context):
    await update.message.reply_text(
        "🟢 CrashSignalAI\n\n"
        f"Version: {APP_VERSION}\n"
        "Mode: RESEARCH / DEMO\n"
        "Auto Betting: OFF"
    )


app = FastAPI(
    title="CrashSignalAI",
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
        "auto_betting": False,
        "history": history_count(),
    }


@app.get("/status")
async def status():
    count = history_count()

    return {
        "bot": "ONLINE",
        "engine": (
            "ANALYZING"
            if count >= MIN_DATA
            else "COLLECTING_DATA"
        ),
        "version": APP_VERSION,
        "auto_betting": False,
        "history": count,
        "minimum_data": MIN_DATA,
    }


@app.get("/history")
async def history():
    data = get_results()

    return {
        "count": len(data),
        "results": data,
    }


@app.post("/ingest")
async def ingest(result: CrashResult):

    multiplier = float(result.multiplier)

    if multiplier <= 0:
        return {
            "status": "REJECTED",
            "reason": "invalid_multiplier"
        }

    save_result(multiplier)

    count = history_count()

    print(
        f"Received crash result: {multiplier}x "
        f"| History: {count}/{MAX_HISTORY}"
    )

    if count >= MIN_DATA:
        analysis = analyze()

        if analysis:
            await send_telegram_alert(analysis)

    return {
        "status": "SAVED",
        "multiplier": multiplier,
        "history": count,
    }


@asynccontextmanager
async def lifespan(app):
    init_db()

    print("CrashSignalAI database ready")
    print("Telegram alert system ready")
    print("Auto Betting: OFF")

    yield


app.router.lifespan_context = lifespan


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
    )
