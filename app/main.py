import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

APP_VERSION = os.getenv("APP_VERSION", "0.1.0")
AUTO_BETTING = os.getenv("AUTO_BETTING", "false").lower() == "true"


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


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")

    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")

    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status))

    print(f"CrashSignalAI {APP_VERSION} starting...")
    print(f"Auto Betting: {'ON' if AUTO_BETTING else 'OFF'}")

    application.run_polling()


if __name__ == "__main__":
    main()
