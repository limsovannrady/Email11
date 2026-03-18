from typing import Optional

_sessions = {}       # telegram_user_id -> dict
_history = {}        # history_id -> dict
_history_counter = 0
_mail_log = []


def init_db():
    pass


# ── email_history ─────────────────────────────────────────────────────────────

def add_email_to_history(telegram_user_id: int, email_address: str,
                         dropmail_session_id: Optional[str] = None,
                         address_id: Optional[str] = None,
                         restore_key: Optional[str] = None):
    global _history_counter
    _history_counter += 1
    _history[_history_counter] = {
        "id":                   _history_counter,
        "telegram_user_id":     telegram_user_id,
        "email_address":        email_address,
        "dropmail_session_id":  dropmail_session_id,
        "address_id":           address_id,
        "restore_key":          restore_key,
        "last_mail_id":         None,
    }


def get_email_history(telegram_user_id: int) -> list:
    return [
        e["email_address"]
        for e in reversed(list(_history.values()))
        if e["telegram_user_id"] == telegram_user_id
    ]


def get_all_history_entries() -> list:
    return [e for e in _history.values() if e.get("restore_key")]


def update_history_session(history_id: int, new_session_id: str,
                           new_address_id: Optional[str],
                           new_restore_key: Optional[str]):
    if history_id in _history:
        _history[history_id]["dropmail_session_id"] = new_session_id
        _history[history_id]["address_id"]          = new_address_id
        _history[history_id]["restore_key"]          = new_restore_key
        _history[history_id]["last_mail_id"]         = None


def update_history_last_mail_id(history_id: int, mail_id: str):
    if history_id in _history:
        _history[history_id]["last_mail_id"] = mail_id


def get_history_entry_by_email(telegram_user_id: int, email_address: str) -> Optional[dict]:
    for entry in _history.values():
        if entry["telegram_user_id"] == telegram_user_id and entry["email_address"] == email_address:
            return entry
    return None


def remove_email_from_history(history_id: int):
    _history.pop(history_id, None)


# ── bot_sessions ──────────────────────────────────────────────────────────────

def upsert_session(telegram_user_id: int, telegram_username: Optional[str],
                   telegram_first_name: Optional[str],
                   dropmail_session_id: str, email_address: str,
                   address_id: Optional[str] = None,
                   restore_key: Optional[str] = None):
    _sessions[telegram_user_id] = {
        "telegram_user_id":    telegram_user_id,
        "telegram_username":   telegram_username,
        "telegram_first_name": telegram_first_name,
        "dropmail_session_id": dropmail_session_id,
        "email_address":       email_address,
        "address_id":          address_id,
        "restore_key":         restore_key,
        "last_mail_id":        None,
        "is_active":           True,
    }


def get_session(telegram_user_id: int) -> Optional[dict]:
    return _sessions.get(telegram_user_id)


def get_all_active_sessions() -> list:
    return [
        s for s in _sessions.values()
        if s.get("is_active") and s.get("dropmail_session_id")
    ]


def update_last_mail_id(telegram_user_id: int, mail_id: str):
    if telegram_user_id in _sessions:
        _sessions[telegram_user_id]["last_mail_id"] = mail_id


def update_session_after_restore(telegram_user_id: int,
                                 new_session_id: str,
                                 new_address_id: Optional[str],
                                 new_restore_key: Optional[str]):
    if telegram_user_id in _sessions:
        s = _sessions[telegram_user_id]
        s["dropmail_session_id"] = new_session_id
        s["address_id"]          = new_address_id
        s["restore_key"]         = new_restore_key
        s["last_mail_id"]        = None
        s["is_active"]           = True


def deactivate_session(telegram_user_id: int):
    if telegram_user_id in _sessions:
        s = _sessions[telegram_user_id]
        s["is_active"]           = False
        s["dropmail_session_id"] = None
        s["email_address"]       = None
        s["address_id"]          = None
        s["restore_key"]         = None
        s["last_mail_id"]        = None


def log_mail(telegram_user_id: int, from_addr: str, to_addr: str,
             subject: str, body: str):
    _mail_log.append({
        "telegram_user_id": telegram_user_id,
        "from_addr":        from_addr,
        "to_addr":          to_addr,
        "subject":          subject,
        "body":             body,
    })


def get_stats() -> dict:
    active = sum(1 for s in _sessions.values() if s.get("is_active"))
    return {
        "total_users":   len(_sessions),
        "active_sessions": active,
        "total_emails":  len(_mail_log),
    }
