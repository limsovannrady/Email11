# TempMail Telegram Bot

A Python Telegram bot that creates disposable email addresses using the dropmail.me API and forwards incoming emails directly to users in Telegram.

## Architecture

- **Language**: Python 3.11
- **Bot Framework**: python-telegram-bot v22 (async, with job-queue for polling)
- **Email API**: dropmail.me GraphQL API
- **Storage**: PostgreSQL on Neon (persistent — sessions, history, mail log)

## Project Structure

```
bot/
  main.py        — Long-polling entry point (local / Replit)
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

## Background Jobs

| Job | Interval | Purpose |
|-----|----------|---------|
| `poll_emails` | Every 3 seconds  | Check and forward new emails to users |
| `proactive_restore_all` | Every 10 minutes | Restore ALL sessions to keep emails active |

## Storage

All sessions, email history, and forwarded mail are stored in Neon Postgres.
Data persists across restarts and redeploys.

On first startup, if a legacy `bot/data.json` file is present and the DB tables
are empty, the contents are imported automatically and the file is renamed to
`bot/data.json.migrated`.

## Running on Replit (long-polling)

The workflow "Start application" runs: `cd bot && python3 main.py`

## Deploying to Vercel (webhook)

Vercel runs each `api/*.py` as a stateless serverless function.

1. Push the repo to GitHub and import it in Vercel.
2. In **Project → Settings → Environment Variables**, add:
   - `TELEGRAM_BOT_TOKEN`
   - `DROPMAIL_API_TOKEN`
   - `NEON_DATABASE_URL`
   - (optional) `ADMIN_ID`, `CHANNEL_ID`
3. Deploy. After the first deploy succeeds, open **once** in your browser:
   `https://<your-app>.vercel.app/api/set_webhook`
   This calls Telegram's `setWebhook` and points it at `/api/webhook`.
4. The cron in `vercel.json` calls `/api/cron` every minute. That endpoint
   forwards new mail to users and (every 10th run, ~10 min) restores all
   sessions to keep them alive.

> **Note:** Vercel Hobby cron min interval = 1 minute, so on Vercel new mail
> arrives within ~60s instead of ~3s on Replit. User commands (buttons,
> /start, etc.) are still instant because Telegram pushes them via webhook.
