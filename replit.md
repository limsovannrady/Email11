# TempMail Telegram Bot

A Python Telegram bot that creates disposable email addresses using the dropmail.me API and forwards incoming emails directly to users in Telegram.

## Architecture

- **Language**: Python 3.11
- **Bot Framework**: python-telegram-bot v22 (async, with job-queue for polling)
- **Email API**: dropmail.me GraphQL API
- **Database**: PostgreSQL (via psycopg2-binary)

## Project Structure

```
bot/
  main.py       — Main bot logic, commands, handlers, polling jobs
  dropmail.py   — DropMail GraphQL API client
  db.py         — PostgreSQL database operations
Dockerfile      — Docker image for Render deployment
requirements.txt— Python dependencies
```

## Environment Variables Required

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | From @BotFather on Telegram |
| `DROPMAIL_API_TOKEN` | Free `af_...` token from https://dropmail.me/api/ |
| `DATABASE_URL` | PostgreSQL connection string |

## Background Jobs

| Job | Interval | Purpose |
|-----|----------|---------|
| `poll_emails` | Every 15 seconds | Check and forward new emails to users |
| `proactive_restore_all` | Every 10 minutes | Restore ALL sessions in history to keep them active |

## Deploying to Render

### Service Type: **Background Worker** (no HTTP port needed)

1. Push this repo to GitHub
2. On Render → **New Background Worker**
3. Choose **Docker** as runtime
4. Set environment variables:
   - `TELEGRAM_BOT_TOKEN`
   - `DROPMAIL_API_TOKEN`
   - `DATABASE_URL` (from a Render PostgreSQL instance or external DB)
5. Deploy — Render will build the Docker image and start the bot

### Docker Details

- **Base image**: `python:3.11-slim`
- **Command**: `python bot/main.py`
- **No port exposed** (background worker, not a web server)

## Running on Replit

The workflow "Start application" runs: `cd bot && python3 main.py`
