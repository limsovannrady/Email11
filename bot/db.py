import json
import logging
import os
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)

_data_dir = os.environ.get("DATA_DIR", os.path.dirname(__file__))
os.makedirs(_data_dir, exist_ok=True)
DATA_FILE = os.path.join(_data_dir, "data.json")

_sessions = {}
_email_history = {}
_history_counter = 0
_mail_log = []


def _now_str():
    return datetime.now().isoformat()


def _load():
    global _sessions, _email_history, _history_counter, _mail_log
    if not os.path.exists(DATA_FILE):
        return
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        _sessions         = {int(k): v for k, v in data.get("sessions", {}).items()}
        raw_history       = data.get("email_history", {})
        _email_history    = {
            int(uid): {int(hid): entry for hid, entry in entries.items()}
            for uid, entries in raw_history.items()
        }
        _history_counter  = data.get("history_counter", 0)
        _mail_log         = data.get("mail_log", [])
        logger.info(f"Loaded data from {DATA_FILE}")
    except Exception as e:
        logger.warning(f"Could not load data file: {e}")


def _save():
    try:
        data = {
            "sessions":        _sessions,
            "email_history":   {
                str(uid): {str(hid): entry for hid, entry in entries.items()}
                for uid, entries in _email_history.items()
            },
            "history_counter": _history_counter,
            "mail_log":        _mail_log[-500:],
        }
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, default=str)
    except Exception as e:
        logger.warning(f"Could not save data file: {e}")


def init_db():
    _load()
    logger.info("Using file-based storage (no database required).")


# ── email_history ──────────────────────────────────────────────────────────────

def add_email_to_history(telegram_user_id: int, email_address: str,
                         dropmail_session_id: Optional[str] = None,
                         address_id: Optional[str] = None,
                         restore_key: Optional[str] = None):
    global _history_counter
    _history_counter += 1
    if telegram_user_id not in _email_history:
        _email_history[telegram_user_id] = {}
    _email_history[telegram_user_id][_history_counter] = {
        "id": _history_counter,
        "telegram_user_id": telegram_user_id,
        "email_address": email_address,
        "dropmail_session_id": dropmail_session_id,
        "address_id": address_id,
        "restore_key": restore_key,
        "last_mail_id": None,
        "created_at": _now_str(),
    }
    _save()


def get_email_history(telegram_user_id: int) -> list:
    user_history = _email_history.get(telegram_user_id, {})
    entries = sorted(user_history.values(), key=lambda x: x["created_at"], reverse=True)
    return [e["email_address"] for e in entries]


def get_all_history_entries() -> list:
    all_entries = []
    for user_history in _email_history.values():
        for entry in user_history.values():
            if entry.get("restore_key"):
                all_entries.append(dict(entry))
    return all_entries


def get_user_history_entries(telegram_user_id: int) -> list:
    user_history = _email_history.get(telegram_user_id, {})
    entries = sorted(user_history.values(), key=lambda x: x["created_at"], reverse=True)
    return [dict(e) for e in entries]


def get_history_entry_by_email(telegram_user_id: int, email_address: str) -> Optional[dict]:
    user_history = _email_history.get(telegram_user_id, {})
    for entry in user_history.values():
        if entry["email_address"] == email_address:
            return dict(entry)
    return None


def update_history_session(history_id: int, new_session_id: str,
                           new_address_id: Optional[str],
                           new_restore_key: Optional[str]):
    for user_history in _email_history.values():
        if history_id in user_history:
            user_history[history_id]["dropmail_session_id"] = new_session_id
            user_history[history_id]["address_id"] = new_address_id
            user_history[history_id]["restore_key"] = new_restore_key
            user_history[history_id]["last_mail_id"] = None
            _save()
            return


def update_history_last_mail_id(history_id: int, mail_id: str):
    for user_history in _email_history.values():
        if history_id in user_history:
            user_history[history_id]["last_mail_id"] = mail_id
            _save()
            return


def remove_email_from_history(history_id: int):
    for user_history in _email_history.values():
        if history_id in user_history:
            del user_history[history_id]
            _save()
            return


# ── bot_sessions ───────────────────────────────────────────────────────────────

def upsert_session(telegram_user_id: int, telegram_username: Optional[str],
                   telegram_first_name: Optional[str],
                   dropmail_session_id: str, email_address: str,
                   address_id: Optional[str] = None,
                   restore_key: Optional[str] = None):
    existing = _sessions.get(telegram_user_id, {})
    _sessions[telegram_user_id] = {
        "telegram_user_id": telegram_user_id,
        "telegram_username": telegram_username,
        "telegram_first_name": telegram_first_name,
        "dropmail_session_id": dropmail_session_id,
        "email_address": email_address,
        "address_id": address_id,
        "restore_key": restore_key,
        "last_mail_id": None,
        "is_active": True,
        "created_at": existing.get("created_at", _now_str()),
        "updated_at": _now_str(),
    }
    _save()


def get_session(telegram_user_id: int) -> Optional[dict]:
    return dict(_sessions[telegram_user_id]) if telegram_user_id in _sessions else None


def get_all_active_sessions() -> list:
    return [
        dict(s) for s in _sessions.values()
        if s.get("is_active") and s.get("dropmail_session_id")
    ]


def update_last_mail_id(telegram_user_id: int, mail_id: str):
    if telegram_user_id in _sessions:
        _sessions[telegram_user_id]["last_mail_id"] = mail_id
        _save()


def update_session_after_restore(telegram_user_id: int,
                                 new_session_id: str,
                                 new_address_id: Optional[str],
                                 new_restore_key: Optional[str]):
    if telegram_user_id in _sessions:
        _sessions[telegram_user_id]["dropmail_session_id"] = new_session_id
        _sessions[telegram_user_id]["address_id"] = new_address_id
        _sessions[telegram_user_id]["restore_key"] = new_restore_key
        _sessions[telegram_user_id]["last_mail_id"] = None
        _sessions[telegram_user_id]["is_active"] = True
        _sessions[telegram_user_id]["updated_at"] = _now_str()
        _save()


def deactivate_session(telegram_user_id: int):
    if telegram_user_id in _sessions:
        _sessions[telegram_user_id]["is_active"] = False
        _sessions[telegram_user_id]["dropmail_session_id"] = None
        _sessions[telegram_user_id]["email_address"] = None
        _sessions[telegram_user_id]["address_id"] = None
        _sessions[telegram_user_id]["restore_key"] = None
        _sessions[telegram_user_id]["last_mail_id"] = None
        _sessions[telegram_user_id]["updated_at"] = _now_str()
        _save()


# ── mail_log ───────────────────────────────────────────────────────────────────

def log_mail(telegram_user_id: int, from_addr: str, to_addr: str,
             subject: str, body: str):
    _mail_log.append({
        "telegram_user_id": telegram_user_id,
        "from_addr": from_addr,
        "to_addr": to_addr,
        "subject": subject,
        "body": body,
        "received_at": _now_str(),
    })
    _save()


def get_stats() -> dict:
    total_users = len(_sessions)
    active_sessions = sum(1 for s in _sessions.values() if s.get("is_active"))
    total_emails = len(_mail_log)
    return {
        "total_users": total_users,
        "active_sessions": active_sessions,
        "total_emails": total_emails,
    }
