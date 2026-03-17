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
                address
            }
        }
    }
    """
    data = _gql(query)
    session = data.get("data", {}).get("introduceSession")
    if not session:
        return None
    email = session["addresses"][0]["address"] if session.get("addresses") else None
    return {
        "session_id": session["id"],
        "email": email,
        "expires_at": session.get("expiresAt")
    }


def get_new_mails(session_id: str, after_mail_id: Optional[str] = None) -> list:
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
                    downloadUrl
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
                    downloadUrl
                }
            }
        }
        """
        variables = {"id": session_id}

    try:
        data = _gql(query, variables)
        session_data = data.get("data", {}).get("session")
        if not session_data:
            return []
        mails = session_data.get("mailsAfterId") or session_data.get("mails") or []
        return mails
    except Exception:
        return []


def check_session_alive(session_id: str) -> bool:
    query = """
    query Check($id: ID!) {
        session(id: $id) {
            id
            expiresAt
        }
    }
    """
    try:
        data = _gql(query, {"id": session_id})
        return data.get("data", {}).get("session") is not None
    except Exception:
        return False
