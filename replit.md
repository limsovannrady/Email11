# TempMail Telegram Bot

A Python Telegram bot that creates disposable email addresses using the dropmail.me API and forwards incoming emails directly to users in Telegram.

## Architecture

- **Language**: Python 3.12 (Vercel) / Python 3.11 (Replit)
- **Bot Framework**: python-telegram-bot v22 (async, with job-queue for polling)
- **Email API**: dropmail.me GraphQL API
- **Storage**: PostgreSQL on Neon (persistent — sessions, history, mail log)

## Project Structure

```
bot/
  main.py        — Long-polling entry point (Replit)
  handlers.py    — Reusable handlers + jobs (used by main.py and api/)
  dropmail.py    — DropMail GraphQL API client
  db.py          — Postgres storage (sessions, history, mail log)
api/
  webhook.py     — Vercel: Telegram webhook receiver (POST)
  cron.py        — Vercel: cron entry — polls mail + restores sessions
  set_webhook.py — Vercel: one-click helper to register webhook URL
vercel.json      — Vercel cron schedule + function timeouts
requirements.txt — Python dependencies
```

## Environment Variables Required

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | From @BotFather on Telegram |
| `DROPMAIL_API_TOKEN` | Free `af_...` token from https://dropmail.me/api/ |
| `NEON_DATABASE_URL`  | Neon Postgres connection string (sslmode=require) |

## Running on Replit (long-polling)

The workflow "Start application" runs: `cd bot && python3 main.py`

Secrets required in Replit:
- `TELEGRAM_BOT_TOKEN`
- `DROPMAIL_API_TOKEN`
- `NEON_DATABASE_URL` (set as a shared env var)

## Deploying to Vercel (webhook)

Vercel runs each `api/*.py` as a stateless serverless function.

### Steps

1. Push the repo to GitHub.
2. Import the GitHub repo in [vercel.com](https://vercel.com) → **Add New Project**.
3. In **Project → Settings → Environment Variables**, add:
   - `TELEGRAM_BOT_TOKEN`
   - `DROPMAIL_API_TOKEN`
   - `NEON_DATABASE_URL`
4. Deploy. After the first successful deploy, open this URL **once** in your browser:
   ```
   https://<your-app>.vercel.app/api/set_webhook
   ```
   This calls Telegram's `setWebhook` and points it at `/api/webhook`.
5. Verify the response shows `"ok": true`.

### How it works on Vercel

| Component | How it runs |
|-----------|-------------|
| `/api/webhook` | Telegram POSTs each update here instantly |
| `/api/cron` | Vercel cron calls this every minute to poll new mail |
| `/api/set_webhook` | One-time helper to register the webhook URL with Telegram |

> **Note:** On Vercel Hobby plan, cron minimum interval = 1 minute, so new mail
> arrives within ~60 s. User commands (buttons, /start, etc.) are still instant
> because Telegram pushes them via webhook.

## Background Jobs (Replit long-polling mode only)

| Job | Interval | Purpose |
|-----|----------|---------|
| `poll_emails` | Every 3 seconds  | Check and forward new emails to users |
| `proactive_restore_all` | Every 10 minutes | Restore ALL sessions to keep emails active |

## Storage Schema

All sessions, email history, and forwarded mail are stored in Neon Postgres.
Data persists across restarts and redeploys.

Tables:
- `bot_sessions` — active session per user
- `email_history` — all email addresses ever created per user
- `mail_log` — log of every email received and forwarded
