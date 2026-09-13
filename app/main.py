import asyncio
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from fastapi.middleware.cors import CORSMiddleware

APP_VERSION = os.getenv("APP_VERSION", "0.1.0")
AUTO_BETTING = os.getenv("AUTO_BETTING", "false").lower() == "true"


class CrashResult(BaseModel):
    multiplier: float


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🟢 CrashSignalAI\n\n"
        f"Version: {APP_VERSION}\n"
        "Mode: RESEARCH / DEMO\n"
        f"Auto Betting: {'ON' if AUTO_BETTING else 'OFF'}"
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🟢 CrashSignalAI Status\n"
        "Bot: ONLINE\n"
        "Engine: WAITING_FOR_DATA\n"
        f"Version: {APP_VERSION}\n"
        "Mode: RESEARCH / DEMO\n"
        f"Auto Betting: {'ON' if AUTO_BETTING else 'OFF'}\n"
        "History: 0/500\n"
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
    }


@app.post("/ingest")
async def ingest(result: CrashResult):
    print(f"Received crash result: {result.multiplier}x")

    return {
        "status": "RECEIVED",
        "multiplier": result.multiplier,
    }


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
    )
