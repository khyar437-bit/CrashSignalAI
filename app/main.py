import asyncio
import os
import sqlite3
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from telegram import Bot


APP_VERSION = os.getenv("APP_VERSION", "0.2.0")
AUTO_BETTING = False

DB_FILE = "crash_history.db"
MAX_HISTORY = 500
MIN_DATA = 20

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


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


def get_history():
    conn = sqlite3.connect(DB_FILE)

    rows = conn.execute("""
        SELECT multiplier
        FROM crash_results
        ORDER BY id DESC
        LIMIT ?
    """, (MAX_HISTORY,)).fetchall()

    conn.close()

    return [float(row[0]) for row in rows]


def history_count():
    conn = sqlite3.connect(DB_FILE)

    count = conn.execute(
        "SELECT COUNT(*) FROM crash_results"
    ).fetchone()[0]

    conn.close()

    return count


async def send_telegram(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials are not configured")
        return False

    try:
        bot = Bot(token=TELEGRAM_TOKEN)

        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message
        )

        print("Telegram research alert sent")
        return True

    except Exception as error:
        print(f"Telegram send error: {error}")
        return False


def analyze():
    data = get_history()

    if len(data) < MIN_DATA:
        return None

    recent = data[:MIN_DATA]

    below_2 = sum(x < 2 for x in recent)
    above_2 = sum(x >= 2 for x in recent)
    above_5 = sum(x >= 5 for x in recent)

    average = sum(recent) / len(recent)

    low_ratio = below_2 / len(recent)
    high_ratio = above_5 / len(recent)

    # Research-only classification.
    # This is NOT a betting recommendation.
    if low_ratio >= 0.70:
        level = "HIGH"
        reason = (
            "Recent sample has an unusually high "
            "share of results below 2x."
        )

    elif high_ratio >= 0.20:
        level = "WATCH"
        reason = (
            "Recent sample contains an elevated "
            "number of results at or above 5x."
        )

    else:
        level = "NORMAL"
        reason = (
            "Recent sample does not show a strong "
            "statistical condition."
        )

    return {
        "level": level,
        "reason": reason,
        "average": average,
        "below_2": below_2,
        "above_2": above_2,
        "above_5": above_5,
        "sample": len(recent),
    }


async def process_signal():
    analysis = analyze()

    if not analysis:
        return

    # Avoid sending NORMAL messages continuously.
    if analysis["level"] == "NORMAL":
        return

    message = (
        "📊 CrashSignalAI — Research Alert\n\n"
        f"Level: {analysis['level']}\n"
        f"Sample: {analysis['sample']} results\n"
        f"Below 2x: {analysis['below_2']}\n"
        f"2x or higher: {analysis['above_2']}\n"
        f"5x or higher: {analysis['above_5']}\n"
        f"Sample average: {analysis['average']:.2f}x\n\n"
        f"{analysis['reason']}\n\n"
        "⚠️ Research information only.\n"
        "No betting instruction.\n"
        "Auto Betting: OFF"
    )

    await send_telegram(message)


async def start(update, context):
    await update.message.reply_text(
        "🟢 CrashSignalAI\n\n"
        f"Version: {APP_VERSION}\n"
        "Mode: RESEARCH / DEMO\n"
        "Auto Betting: OFF"
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

    # Start analysis once minimum data exists.
    if count >= MIN_DATA:
        await process_signal()

    return {
        "status": "SAVED",
        "multiplier": multiplier,
        "history": count,
    }


@app.get("/history")
async def get_history_endpoint():

    data = get_history()

    return {
        "count": len(data),
        "results": data,
    }


@app.get("/status")
async def api_status():

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


@asynccontextmanager
async def lifespan(app: FastAPI):
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
