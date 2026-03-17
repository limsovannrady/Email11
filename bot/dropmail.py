import os
import requests
from typing import Optional

DROPMAIL_TOKEN = os.environ.get("DROPMAIL_API_TOKEN", "")
GRAPHQL_URL = f"https://dropmail.me/api/graphql/{DROPMAIL_TOKEN}"


def _gql(query: str, variables: Optional[dict] = None) -> dict:
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    resp = requests.post(GRAPHQL_URL, json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()


def create_session() -> Optional[dict]:
    query = """
    mutation {
        introduceSession {
            id
            expiresAt
            addresses {
                id
                address
                restoreKey
            }
        }
    }
    """
    data = _gql(query)
    session = data.get("data", {}).get("introduceSession")
    if not session:
        return None
    addr = session["addresses"][0] if session.get("addresses") else {}
    return {
        "session_id": session["id"],
        "email":       addr.get("address"),
        "address_id":  addr.get("id"),
        "restore_key": addr.get("restoreKey"),
        "expires_at":  session.get("expiresAt"),
    }


def restore_session(mail_address: str, restore_key: str) -> Optional[dict]:
    """Create a fresh session then restore the old address into it."""
    # Step 1: create empty session
    new_session_query = """
    mutation {
        introduceSession(input: { withAddress: false }) {
            id
        }
    }
    """
    data = _gql(new_session_query)
    new_session = data.get("data", {}).get("introduceSession")
    if not new_session:
        return None
    new_session_id = new_session["id"]

    # Step 2: restore address into new session
    restore_query = """
    mutation Restore($mailAddress: String!, $restoreKey: String!, $sessionId: ID!) {
        restoreAddress(input: {
            mailAddress: $mailAddress,
            restoreKey:  $restoreKey,
            sessionId:   $sessionId
        }) {
            id
            address
            restoreKey
        }
    }
    """
    r = _gql(restore_query, {
        "mailAddress": mail_address,
        "restoreKey":  restore_key,
        "sessionId":   new_session_id,
    })
    addr = r.get("data", {}).get("restoreAddress")
    if not addr:
        return None
    return {
        "session_id":  new_session_id,
        "email":       addr.get("address"),
        "address_id":  addr.get("id"),
        "restore_key": addr.get("restoreKey"),
    }


def delete_address(address_id: str) -> bool:
    """Permanently delete an email address."""
    query = """
    mutation Delete($addressId: ID!) {
        deleteAddress(input: { addressId: $addressId })
    }
    """
    try:
        data = _gql(query, {"addressId": address_id})
        return bool(data.get("data", {}).get("deleteAddress"))
    except Exception:
        return False


def get_new_mails(session_id: str, after_mail_id: Optional[str] = None):
    """
    Returns list of mails, or None if the session no longer exists (expired).
    """
    if after_mail_id:
        query = """
        query GetMails($id: ID!, $mailId: ID!) {
            session(id: $id) {
                mailsAfterId(mailId: $mailId) {
                    id
                    fromAddr
                    toAddr
                    headerSubject
                    text
                    rawSize
                }
            }
        }
        """
        variables = {"id": session_id, "mailId": after_mail_id}
    else:
        query = """
        query GetMails($id: ID!) {
            session(id: $id) {
                mails {
                    id
                    fromAddr
                    toAddr
                    headerSubject
                    text
                    rawSize
                }
            }
        }
        """
        variables = {"id": session_id}

    data = _gql(query, variables)
    session_data = data.get("data", {}).get("session")

    # session is None means it expired
    if session_data is None:
        return None

    mails = session_data.get("mailsAfterId") or session_data.get("mails") or []
    return mails


def check_session_alive(session_id: str) -> bool:
    query = """
    query Check($id: ID!) {
        session(id: $id) { id }
    }
    """
    try:
        data = _gql(query, {"id": session_id})
        return data.get("data", {}).get("session") is not None
    except Exception:
        return False
