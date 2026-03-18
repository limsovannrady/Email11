# TempMail Telegram Bot

A Python Telegram bot that creates disposable email addresses using the dropmail.me API and forwards incoming emails directly to users in Telegram.

## Architecture

- **Language**: Python 3.11
- **Bot Framework**: python-telegram-bot v22 (async, with job-queue for polling)
- **Email API**: dropmail.me GraphQL API
- **Storage**: PostgreSQL (Replit built-in database)

## Project Structure

```
bot/
  main.py       — Main bot logic, commands, handlers, polling jobs
  dropmail.py   — DropMail GraphQL API client
  db.py         — In-memory storage (sessions, history, mail log)
Dockerfile      — Docker image for Render deployment
requirements.txt— Python dependencies (2 packages only)
```

## Environment Variables Required

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | From @BotFather on Telegram |
| `DROPMAIL_API_TOKEN` | Free `af_...` token from https://dropmail.me/api/ |

## Background Jobs

| Job | Interval | Purpose |
|-----|----------|---------|
| `poll_emails` | Every 15 seconds | Check and forward new emails to users |
| `proactive_restore_all` | Every 10 minutes | Restore ALL sessions to keep emails active |

## Deploying to Render

### Service Type: **Background Worker**

1. Push this repo to GitHub
2. Render → **New Background Worker** → **Docker**
3. Set environment variables:
   - `TELEGRAM_BOT_TOKEN`
   - `DROPMAIL_API_TOKEN`
4. Deploy

### Docker Details

- **Base image**: `python:3.11-slim`
- **Command**: `python bot/main.py`
- **No port, no database**

## Note on In-Memory Storage

All session data is stored in RAM. Data resets when the bot restarts.
This is intentional — temporary emails don't need persistence.

## Running on Replit

The workflow "Start application" runs: `cd bot && python3 main.py`
