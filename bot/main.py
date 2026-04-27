"""Long-polling entry point — used locally / on Replit.

For production webhook deployment (Vercel), see api/webhook.py.
"""

import logging
from telegram import Update
from telegram.ext import Application

from db import init_db
import dropmail
from handlers import (
    BOT_TOKEN, POLL_INTERVAL, RESTORE_INTERVAL,
    register_handlers, poll_emails_job, restore_all_job,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main():
    init_db()
    logger.info("Database initialized.")

    if not BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set!")
    if not dropmail.DROPMAIL_TOKEN:
        raise ValueError("DROPMAIL_API_TOKEN is not set!")

    app = Application.builder().token(BOT_TOKEN).build()

    register_handlers(app)

    app.job_queue.run_repeating(poll_emails_job,  interval=POLL_INTERVAL,    first=5)
    app.job_queue.run_repeating(restore_all_job,  interval=RESTORE_INTERVAL, first=30)

    logger.info("Bot starting in long-polling mode...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
