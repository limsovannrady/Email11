# TempMail Telegram Bot

A Python Telegram bot that creates disposable email addresses using the dropmail.me API and forwards incoming emails directly to users in Telegram.

## Architecture

- **Language**: Python 3.11
- **Bot Framework**: python-telegram-bot v22 (async, with job-queue for polling)
- **Email API**: dropmail.me GraphQL API
- **Database**: PostgreSQL (via psycopg2)

## Files

- `bot/main.py` — Main Telegram bot logic, commands, handlers, email polling
- `bot/dropmail.py` — DropMail GraphQL API client
- `bot/db.py` — PostgreSQL database operations

## Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message and instructions |
| `/newmail` | Create a new temporary email address |
| `/myemail` | Show your current email address |
| `/inbox` | Manually check your inbox |
| `/delete` | Delete your current session |
| `/stats` | Show bot statistics |
| `/help` | Show help message |

## How It Works

1. User sends `/newmail` → bot calls dropmail.me API to create a session + email address
2. Session is stored in PostgreSQL (telegram_user_id → dropmail_session_id)
3. Every 15 seconds, the bot polls dropmail.me for new emails for all active sessions
4. New emails are forwarded to the user's Telegram chat
5. Incremental polling using `mailsAfterId` to avoid duplicates

## Environment Variables Required

- `TELEGRAM_BOT_TOKEN` — From @BotFather on Telegram
- `DROPMAIL_API_TOKEN` — Free `af_...` token from https://dropmail.me/api/
- `DATABASE_URL` — PostgreSQL connection string (provided by Replit)

## Running

The workflow "Start application" runs `cd bot && python3 main.py`
