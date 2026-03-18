import os
import psycopg2
import psycopg2.extras
from typing import Optional

DATABASE_URL = os.environ.get("DATABASE_URL", "")


def _conn():
    return psycopg2.connect(DATABASE_URL)


def init_db():
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS bot_sessions (
                    telegram_user_id     BIGINT PRIMARY KEY,
                    telegram_username    TEXT,
                    telegram_first_name  TEXT,
                    dropmail_session_id  TEXT,
                    email_address        TEXT,
                    address_id           TEXT,
                    restore_key          TEXT,
                    last_mail_id         TEXT,
                    is_active            BOOLEAN DEFAULT TRUE,
                    created_at           TIMESTAMP DEFAULT NOW(),
                    updated_at           TIMESTAMP DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS email_history (
                    id                   SERIAL PRIMARY KEY,
                    telegram_user_id     BIGINT NOT NULL,
                    email_address        TEXT NOT NULL,
                    dropmail_session_id  TEXT,
                    address_id           TEXT,
                    restore_key          TEXT,
                    last_mail_id         TEXT,
                    created_at           TIMESTAMP DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS mail_log (
                    id                SERIAL PRIMARY KEY,
                    telegram_user_id  BIGINT NOT NULL,
                    from_addr         TEXT,
                    to_addr           TEXT,
                    subject           TEXT,
                    body              TEXT,
                    received_at       TIMESTAMP DEFAULT NOW()
                );
            """)
        conn.commit()


# ── email_history ──────────────────────────────────────────────────────────────

def add_email_to_history(telegram_user_id: int, email_address: str,
                         dropmail_session_id: Optional[str] = None,
                         address_id: Optional[str] = None,
                         restore_key: Optional[str] = None):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO email_history
                    (telegram_user_id, email_address, dropmail_session_id, address_id, restore_key)
                VALUES (%s, %s, %s, %s, %s)
            """, (telegram_user_id, email_address, dropmail_session_id, address_id, restore_key))
        conn.commit()


def get_email_history(telegram_user_id: int) -> list:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT email_address FROM email_history
                WHERE telegram_user_id = %s
                ORDER BY created_at DESC
            """, (telegram_user_id,))
            return [row[0] for row in cur.fetchall()]


def get_all_history_entries() -> list:
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM email_history
                WHERE restore_key IS NOT NULL
            """)
            return [dict(r) for r in cur.fetchall()]


def get_user_history_entries(telegram_user_id: int) -> list:
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM email_history
                WHERE telegram_user_id = %s
                ORDER BY created_at DESC
            """, (telegram_user_id,))
            return [dict(r) for r in cur.fetchall()]


def get_history_entry_by_email(telegram_user_id: int, email_address: str) -> Optional[dict]:
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM email_history
                WHERE telegram_user_id = %s AND email_address = %s
                LIMIT 1
            """, (telegram_user_id, email_address))
            row = cur.fetchone()
            return dict(row) if row else None


def update_history_session(history_id: int, new_session_id: str,
                           new_address_id: Optional[str],
                           new_restore_key: Optional[str]):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE email_history
                SET dropmail_session_id = %s,
                    address_id          = %s,
                    restore_key         = %s,
                    last_mail_id        = NULL
                WHERE id = %s
            """, (new_session_id, new_address_id, new_restore_key, history_id))
        conn.commit()


def update_history_last_mail_id(history_id: int, mail_id: str):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE email_history SET last_mail_id = %s WHERE id = %s
            """, (mail_id, history_id))
        conn.commit()


def remove_email_from_history(history_id: int):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM email_history WHERE id = %s", (history_id,))
        conn.commit()


# ── bot_sessions ───────────────────────────────────────────────────────────────

def upsert_session(telegram_user_id: int, telegram_username: Optional[str],
                   telegram_first_name: Optional[str],
                   dropmail_session_id: str, email_address: str,
                   address_id: Optional[str] = None,
                   restore_key: Optional[str] = None):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO bot_sessions
                    (telegram_user_id, telegram_username, telegram_first_name,
                     dropmail_session_id, email_address, address_id, restore_key,
                     last_mail_id, is_active, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, TRUE, NOW())
                ON CONFLICT (telegram_user_id) DO UPDATE SET
                    telegram_username    = EXCLUDED.telegram_username,
                    telegram_first_name  = EXCLUDED.telegram_first_name,
                    dropmail_session_id  = EXCLUDED.dropmail_session_id,
                    email_address        = EXCLUDED.email_address,
                    address_id           = EXCLUDED.address_id,
                    restore_key          = EXCLUDED.restore_key,
                    last_mail_id         = NULL,
                    is_active            = TRUE,
                    updated_at           = NOW()
            """, (telegram_user_id, telegram_username, telegram_first_name,
                  dropmail_session_id, email_address, address_id, restore_key))
        conn.commit()


def get_session(telegram_user_id: int) -> Optional[dict]:
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM bot_sessions WHERE telegram_user_id = %s
            """, (telegram_user_id,))
            row = cur.fetchone()
            return dict(row) if row else None


def get_all_active_sessions() -> list:
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM bot_sessions
                WHERE is_active = TRUE AND dropmail_session_id IS NOT NULL
            """)
            return [dict(r) for r in cur.fetchall()]


def update_last_mail_id(telegram_user_id: int, mail_id: str):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE bot_sessions SET last_mail_id = %s WHERE telegram_user_id = %s
            """, (mail_id, telegram_user_id))
        conn.commit()


def update_session_after_restore(telegram_user_id: int,
                                 new_session_id: str,
                                 new_address_id: Optional[str],
                                 new_restore_key: Optional[str]):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE bot_sessions SET
                    dropmail_session_id = %s,
                    address_id          = %s,
                    restore_key         = %s,
                    last_mail_id        = NULL,
                    is_active           = TRUE,
                    updated_at          = NOW()
                WHERE telegram_user_id = %s
            """, (new_session_id, new_address_id, new_restore_key, telegram_user_id))
        conn.commit()


def deactivate_session(telegram_user_id: int):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE bot_sessions SET
                    is_active           = FALSE,
                    dropmail_session_id = NULL,
                    email_address       = NULL,
                    address_id          = NULL,
                    restore_key         = NULL,
                    last_mail_id        = NULL,
                    updated_at          = NOW()
                WHERE telegram_user_id = %s
            """, (telegram_user_id,))
        conn.commit()


# ── mail_log ───────────────────────────────────────────────────────────────────

def log_mail(telegram_user_id: int, from_addr: str, to_addr: str,
             subject: str, body: str):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO mail_log (telegram_user_id, from_addr, to_addr, subject, body)
                VALUES (%s, %s, %s, %s, %s)
            """, (telegram_user_id, from_addr, to_addr, subject, body))
        conn.commit()


def get_stats() -> dict:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM bot_sessions")
            total_users = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM bot_sessions WHERE is_active = TRUE")
            active_sessions = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM mail_log")
            total_emails = cur.fetchone()[0]
    return {
        "total_users":    total_users,
        "active_sessions": active_sessions,
        "total_emails":   total_emails,
    }
