import json
import logging
import os
from typing import Optional
from datetime import datetime
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

logger = logging.getLogger(__name__)

DATABASE_URL = (
    os.environ.get("NEON_DATABASE_URL")
    or os.environ.get("DATABASE_URL")
    or ""
)

if not DATABASE_URL:
    raise RuntimeError(
        "NEON_DATABASE_URL (or DATABASE_URL) is not set. "
        "Cannot start without a Postgres connection string."
    )

_pool: Optional[ThreadedConnectionPool] = None

_data_dir = os.environ.get("DATA_DIR", os.path.dirname(__file__))
LEGACY_DATA_FILE = os.path.join(_data_dir, "data.json")


def _get_pool() -> ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=DATABASE_URL,
        )
    return _pool


@contextmanager
def _conn(commit: bool = False):
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


@contextmanager
def _cursor(commit: bool = False):
    with _conn(commit=commit) as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            yield cur
        finally:
            cur.close()


# ── Schema ────────────────────────────────────────────────────────────────────

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS bot_sessions (
    telegram_user_id      BIGINT PRIMARY KEY,
    telegram_username     TEXT,
    telegram_first_name   TEXT,
    dropmail_session_id   TEXT,
    email_address         TEXT,
    address_id            TEXT,
    restore_key           TEXT,
    last_mail_id          TEXT,
    is_active             BOOLEAN NOT NULL DEFAULT TRUE,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS email_history (
    id                    BIGSERIAL PRIMARY KEY,
    telegram_user_id      BIGINT NOT NULL,
    email_address         TEXT NOT NULL,
    dropmail_session_id   TEXT,
    address_id            TEXT,
    restore_key           TEXT,
    last_mail_id          TEXT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_email_history_user ON email_history(telegram_user_id);

CREATE TABLE IF NOT EXISTS mail_log (
    id                    BIGSERIAL PRIMARY KEY,
    telegram_user_id      BIGINT NOT NULL,
    from_addr             TEXT,
    to_addr               TEXT,
    subject               TEXT,
    body                  TEXT,
    received_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_mail_log_user ON mail_log(telegram_user_id);
"""


def init_db():
    with _cursor(commit=True) as cur:
        cur.execute(_SCHEMA_SQL)
    logger.info("Postgres schema ready.")
    _migrate_legacy_json_if_needed()


# ── Legacy data.json → Postgres migration (one-time) ──────────────────────────

def _parse_ts(value) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _migrate_legacy_json_if_needed():
    if not os.path.exists(LEGACY_DATA_FILE):
        return

    with _cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM bot_sessions")
        sessions_n = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM email_history")
        history_n = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM mail_log")
        log_n = cur.fetchone()["n"]

    if sessions_n or history_n or log_n:
        logger.info("Postgres already has data; skipping legacy import.")
        _archive_legacy_file()
        return

    try:
        with open(LEGACY_DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning(f"Could not read legacy data.json: {e}")
        return

    sessions = data.get("sessions", {}) or {}
    email_history = data.get("email_history", {}) or {}
    mail_log = data.get("mail_log", []) or []

    with _cursor(commit=True) as cur:
        for _, s in sessions.items():
            cur.execute(
                """
                INSERT INTO bot_sessions
                    (telegram_user_id, telegram_username, telegram_first_name,
                     dropmail_session_id, email_address, address_id, restore_key,
                     last_mail_id, is_active, created_at, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,
                        COALESCE(%s, NOW()), COALESCE(%s, NOW()))
                ON CONFLICT (telegram_user_id) DO NOTHING
                """,
                (
                    int(s["telegram_user_id"]),
                    s.get("telegram_username"),
                    s.get("telegram_first_name"),
                    s.get("dropmail_session_id"),
                    s.get("email_address"),
                    s.get("address_id"),
                    s.get("restore_key"),
                    s.get("last_mail_id"),
                    bool(s.get("is_active", True)),
                    _parse_ts(s.get("created_at")),
                    _parse_ts(s.get("updated_at")),
                ),
            )

        for _, entries in email_history.items():
            for _, e in entries.items():
                cur.execute(
                    """
                    INSERT INTO email_history
                        (telegram_user_id, email_address, dropmail_session_id,
                         address_id, restore_key, last_mail_id, created_at)
                    VALUES (%s,%s,%s,%s,%s,%s, COALESCE(%s, NOW()))
                    """,
                    (
                        int(e["telegram_user_id"]),
                        e["email_address"],
                        e.get("dropmail_session_id"),
                        e.get("address_id"),
                        e.get("restore_key"),
                        e.get("last_mail_id"),
                        _parse_ts(e.get("created_at")),
                    ),
                )

        for m in mail_log:
            cur.execute(
                """
                INSERT INTO mail_log
                    (telegram_user_id, from_addr, to_addr, subject, body, received_at)
                VALUES (%s,%s,%s,%s,%s, COALESCE(%s, NOW()))
                """,
                (
                    int(m["telegram_user_id"]),
                    m.get("from_addr"),
                    m.get("to_addr"),
                    m.get("subject"),
                    m.get("body"),
                    _parse_ts(m.get("received_at")),
                ),
            )

    logger.info(
        f"Migrated legacy data.json → Postgres: "
        f"{len(sessions)} sessions, "
        f"{sum(len(v) for v in email_history.values())} history entries, "
        f"{len(mail_log)} mail logs."
    )
    _archive_legacy_file()


def _archive_legacy_file():
    try:
        archived = LEGACY_DATA_FILE + ".migrated"
        os.replace(LEGACY_DATA_FILE, archived)
        logger.info(f"Archived legacy file → {archived}")
    except Exception as e:
        logger.warning(f"Could not archive legacy data.json: {e}")


# ── email_history ──────────────────────────────────────────────────────────────

def add_email_to_history(telegram_user_id: int, email_address: str,
                         dropmail_session_id: Optional[str] = None,
                         address_id: Optional[str] = None,
                         restore_key: Optional[str] = None):
    with _cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO email_history
                (telegram_user_id, email_address, dropmail_session_id,
                 address_id, restore_key)
            VALUES (%s,%s,%s,%s,%s)
            """,
            (telegram_user_id, email_address, dropmail_session_id,
             address_id, restore_key),
        )


def get_email_history(telegram_user_id: int) -> list:
    with _cursor() as cur:
        cur.execute(
            """
            SELECT email_address
              FROM email_history
             WHERE telegram_user_id = %s
             ORDER BY created_at DESC
            """,
            (telegram_user_id,),
        )
        return [r["email_address"] for r in cur.fetchall()]


def get_all_history_entries() -> list:
    with _cursor() as cur:
        cur.execute(
            """
            SELECT id, telegram_user_id, email_address, dropmail_session_id,
                   address_id, restore_key, last_mail_id, created_at
              FROM email_history
             WHERE restore_key IS NOT NULL
            """
        )
        return [dict(r) for r in cur.fetchall()]


def get_user_history_entries(telegram_user_id: int) -> list:
    with _cursor() as cur:
        cur.execute(
            """
            SELECT id, telegram_user_id, email_address, dropmail_session_id,
                   address_id, restore_key, last_mail_id, created_at
              FROM email_history
             WHERE telegram_user_id = %s
             ORDER BY created_at DESC
            """,
            (telegram_user_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def get_history_entry_by_email(telegram_user_id: int, email_address: str) -> Optional[dict]:
    with _cursor() as cur:
        cur.execute(
            """
            SELECT id, telegram_user_id, email_address, dropmail_session_id,
                   address_id, restore_key, last_mail_id, created_at
              FROM email_history
             WHERE telegram_user_id = %s AND email_address = %s
             ORDER BY created_at DESC
             LIMIT 1
            """,
            (telegram_user_id, email_address),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def update_history_session(history_id: int, new_session_id: str,
                           new_address_id: Optional[str],
                           new_restore_key: Optional[str]):
    with _cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE email_history
               SET dropmail_session_id = %s,
                   address_id          = %s,
                   restore_key         = %s,
                   last_mail_id        = NULL
             WHERE id = %s
            """,
            (new_session_id, new_address_id, new_restore_key, history_id),
        )


def update_history_last_mail_id(history_id: int, mail_id: str):
    with _cursor(commit=True) as cur:
        cur.execute(
            "UPDATE email_history SET last_mail_id = %s WHERE id = %s",
            (mail_id, history_id),
        )


def remove_email_from_history(history_id: int):
    with _cursor(commit=True) as cur:
        cur.execute("DELETE FROM email_history WHERE id = %s", (history_id,))


# ── bot_sessions ───────────────────────────────────────────────────────────────

def upsert_session(telegram_user_id: int, telegram_username: Optional[str],
                   telegram_first_name: Optional[str],
                   dropmail_session_id: str, email_address: str,
                   address_id: Optional[str] = None,
                   restore_key: Optional[str] = None):
    with _cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO bot_sessions
                (telegram_user_id, telegram_username, telegram_first_name,
                 dropmail_session_id, email_address, address_id, restore_key,
                 last_mail_id, is_active, created_at, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s, NULL, TRUE, NOW(), NOW())
            ON CONFLICT (telegram_user_id) DO UPDATE
               SET telegram_username   = EXCLUDED.telegram_username,
                   telegram_first_name = EXCLUDED.telegram_first_name,
                   dropmail_session_id = EXCLUDED.dropmail_session_id,
                   email_address       = EXCLUDED.email_address,
                   address_id          = EXCLUDED.address_id,
                   restore_key         = EXCLUDED.restore_key,
                   last_mail_id        = NULL,
                   is_active           = TRUE,
                   updated_at          = NOW()
            """,
            (telegram_user_id, telegram_username, telegram_first_name,
             dropmail_session_id, email_address, address_id, restore_key),
        )


def get_session(telegram_user_id: int) -> Optional[dict]:
    with _cursor() as cur:
        cur.execute(
            "SELECT * FROM bot_sessions WHERE telegram_user_id = %s",
            (telegram_user_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def update_session_after_restore(telegram_user_id: int,
                                 new_session_id: str,
                                 new_address_id: Optional[str],
                                 new_restore_key: Optional[str]):
    with _cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE bot_sessions
               SET dropmail_session_id = %s,
                   address_id          = %s,
                   restore_key         = %s,
                   last_mail_id        = NULL,
                   is_active           = TRUE,
                   updated_at          = NOW()
             WHERE telegram_user_id = %s
            """,
            (new_session_id, new_address_id, new_restore_key, telegram_user_id),
        )


def deactivate_session(telegram_user_id: int):
    with _cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE bot_sessions
               SET is_active           = FALSE,
                   dropmail_session_id = NULL,
                   email_address       = NULL,
                   address_id          = NULL,
                   restore_key         = NULL,
                   last_mail_id        = NULL,
                   updated_at          = NOW()
             WHERE telegram_user_id = %s
            """,
            (telegram_user_id,),
        )


# ── mail_log ───────────────────────────────────────────────────────────────────

def log_mail(telegram_user_id: int, from_addr: str, to_addr: str,
             subject: str, body: str):
    with _cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO mail_log
                (telegram_user_id, from_addr, to_addr, subject, body)
            VALUES (%s,%s,%s,%s,%s)
            """,
            (telegram_user_id, from_addr, to_addr, subject, body),
        )


def get_stats() -> dict:
    with _cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM bot_sessions")
        total_users = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM bot_sessions WHERE is_active = TRUE")
        active_sessions = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM mail_log")
        total_emails = cur.fetchone()["n"]
    return {
        "total_users": total_users,
        "active_sessions": active_sessions,
        "total_emails": total_emails,
    }
