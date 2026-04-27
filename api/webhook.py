"""Telegram webhook receiver for Vercel.

Telegram POSTs every update here. We build a fresh Application per
invocation (serverless = stateless) and process the single update.

Set webhook once via /api/set_webhook.
"""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bot"))

import json
import asyncio
import logging
from http.server import BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import Application

from handlers import BOT_TOKEN, register_handlers
from db import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize DB schema once per cold start.
_db_ready = False
def _ensure_db():
    global _db_ready
    if not _db_ready:
        init_db()
        _db_ready = True


async def _process_update(body: dict):
    app = Application.builder().token(BOT_TOKEN).updater(None).build()
    register_handlers(app)
    async with app:
        update = Update.de_json(body, app.bot)
        await app.process_update(update)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            _ensure_db()
            length = int(self.headers.get("content-length", 0))
            raw    = self.rfile.read(length)
            body   = json.loads(raw)
            asyncio.run(_process_update(body))
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")
        except Exception as e:
            logger.exception("Webhook handler error")
            self.send_response(500)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"error: {e}".encode())

    def do_GET(self):
        # Health check
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"webhook alive")
