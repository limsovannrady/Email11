import os
import psycopg2
import psycopg2.extras
from typing import Optional

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_conn():
    return psycopg2.connect(DATABASE_URL)


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bot_sessions (
            id                  SERIAL PRIMARY KEY,
            telegram_user_id    BIGINT UNIQUE NOT NULL,
            telegram_username   TEXT,
            telegram_first_name TEXT,
            dropmail_session_id TEXT,
            email_address       TEXT,
            address_id          TEXT,
            restore_key         TEXT,
            last_mail_id        TEXT,
            is_active           BOOLEAN DEFAULT FALSE,
            created_at          TIMESTAMP DEFAULT NOW(),
            updated_at          TIMESTAMP DEFAULT NOW()
        )
    """)
    # Add new columns to existing table if they don't exist yet
    for col, col_def in [
        ("address_id",  "TEXT"),
        ("restore_key", "TEXT"),
    ]:
        cur.execute(f"""
            DO $$ BEGIN
                ALTER TABLE bot_sessions ADD COLUMN {col} {col_def};
            EXCEPTION WHEN duplicate_column THEN NULL;
            END $$;
        """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS mail_log (
            id               SERIAL PRIMARY KEY,
            telegram_user_id BIGINT NOT NULL,
            from_addr        TEXT,
            to_addr          TEXT,
            subject          TEXT,
            body             TEXT,
            received_at      TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()
    cur.close()
    conn.close()


def upsert_session(telegram_user_id: int, telegram_username: Optional[str],
                   telegram_first_name: Optional[str],
                   dropmail_session_id: str, email_address: str,
                   address_id: Optional[str] = None,
                   restore_key: Optional[str] = None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO bot_sessions
            (telegram_user_id, telegram_username, telegram_first_name,
             dropmail_session_id, email_address, address_id, restore_key,
             is_active, last_mail_id, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, NULL, NOW())
        ON CONFLICT (telegram_user_id) DO UPDATE SET
            telegram_username   = EXCLUDED.telegram_username,
            telegram_first_name = EXCLUDED.telegram_first_name,
            dropmail_session_id = EXCLUDED.dropmail_session_id,
            email_address       = EXCLUDED.email_address,
            address_id          = EXCLUDED.address_id,
            restore_key         = EXCLUDED.restore_key,
            is_active           = TRUE,
            last_mail_id        = NULL,
            updated_at          = NOW()
    """, (telegram_user_id, telegram_username, telegram_first_name,
          dropmail_session_id, email_address, address_id, restore_key))
    conn.commit()
    cur.close()
    conn.close()


def update_session_after_restore(telegram_user_id: int,
                                 new_session_id: str,
                                 new_address_id: Optional[str],
                                 new_restore_key: Optional[str]):
    """Update session ID + keys after auto-restore, keep email address."""
    conn = get_conn()
    cur = conn.cursor()
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
    cur.close()
    conn.close()


def get_session(telegram_user_id: int) -> Optional[dict]:
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM bot_sessions WHERE telegram_user_id = %s",
                (telegram_user_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else None


def get_all_active_sessions() -> list:
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT * FROM bot_sessions WHERE is_active = TRUE AND dropmail_session_id IS NOT NULL"
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


def update_last_mail_id(telegram_user_id: int, mail_id: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE bot_sessions SET last_mail_id = %s, updated_at = NOW() WHERE telegram_user_id = %s",
        (mail_id, telegram_user_id)
    )
    conn.commit()
    cur.close()
    conn.close()


def deactivate_session(telegram_user_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE bot_sessions SET
            is_active = FALSE,
            dropmail_session_id = NULL,
            email_address = NULL,
            address_id = NULL,
            restore_key = NULL,
            last_mail_id = NULL,
            updated_at = NOW()
        WHERE telegram_user_id = %s
    """, (telegram_user_id,))
    conn.commit()
    cur.close()
    conn.close()


def log_mail(telegram_user_id: int, from_addr: str, to_addr: str,
             subject: str, body: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO mail_log (telegram_user_id, from_addr, to_addr, subject, body)
        VALUES (%s, %s, %s, %s, %s)
    """, (telegram_user_id, from_addr, to_addr, subject, body))
    conn.commit()
    cur.close()
    conn.close()


def get_stats() -> dict:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM bot_sessions")
    total_users = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM bot_sessions WHERE is_active = TRUE")
    active_sessions = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM mail_log")
    total_emails = cur.fetchone()[0]
    cur.close()
    conn.close()
    return {
        "total_users": total_users,
        "active_sessions": active_sessions,
        "total_emails": total_emails,
    }
