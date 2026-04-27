"""One-click helper to register the Telegram webhook URL.

Visit https://<your-vercel-domain>/api/set_webhook  ONCE after deploy.

Reads the current host from the request and tells Telegram:
    setWebhook?url=https://<host>/api/webhook
"""

import os
import json
import urllib.request
import urllib.parse
from http.server import BaseHTTPRequestHandler

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")


def _set_webhook(url: str) -> dict:
    api = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
    data = urllib.parse.urlencode({"url": url, "drop_pending_updates": "true"}).encode()
    req  = urllib.request.Request(api, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def _get_info() -> dict:
    api = f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo"
    with urllib.request.urlopen(api, timeout=15) as r:
        return json.loads(r.read().decode())


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            if not BOT_TOKEN:
                raise RuntimeError("TELEGRAM_BOT_TOKEN env var is not set")

            host = self.headers.get("x-forwarded-host") or self.headers.get("host")
            proto = self.headers.get("x-forwarded-proto", "https")
            webhook_url = f"{proto}://{host}/api/webhook"

            result = _set_webhook(webhook_url)
            info   = _get_info()
            payload = {
                "set_webhook_request": webhook_url,
                "set_webhook_response": result,
                "current_webhook_info": info,
            }
            body = json.dumps(payload, indent=2).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"error: {e}".encode())
