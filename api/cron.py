"""Vercel Cron entry point.

Runs poll_all_emails (forwards new mail) and restore_all_sessions
(keeps every email alive). Triggered by vercel.json schedule.

Vercel Hobby plan minimum interval = 1 minute.
"""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bot"))

import asyncio
import logging
from http.server import BaseHTTPRequestHandler

from telegram import Bot

from handlers import BOT_TOKEN, poll_all_emails, restore_all_sessions
from db import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_db_ready = False
_restore_counter = 0  # restore every 10th poll (~10 min if cron is every 1 min)


def _ensure_db():
    global _db_ready
    if not _db_ready:
        init_db()
        _db_ready = True


async def _run():
    global _restore_counter
    bot = Bot(token=BOT_TOKEN)
    async with bot:
        polled = await poll_all_emails(bot)
        _restore_counter += 1
        restored = 0
        if _restore_counter >= 10:
            _restore_counter = 0
            restored = await restore_all_sessions()
        return polled, restored


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            _ensure_db()
            polled, restored = asyncio.run(_run())
            msg = f"polled={polled} restored={restored}"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(msg.encode())
        except Exception as e:
            logger.exception("Cron handler error")
            self.send_response(500)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"error: {e}".encode())

    def do_POST(self):
        self.do_GET()
