"""Cliente Google APIs para Ramon.

Usa el refresh_token del hub ARTES-BUHO_API-GOOGLE para conectar a
Gmail, Calendar, Drive, Sheets, etc. sin flow OAuth adicional.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/contacts",
]


class GoogleAuthError(Exception):
    pass


@lru_cache(maxsize=1)
def get_credentials() -> Credentials:
    """Construye credenciales desde env vars. Cacheada."""
    client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
    refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN", "")
    if not (client_id and client_secret and refresh_token):
        raise GoogleAuthError("Faltan credenciales Google en env vars")
    return Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )


def gmail():
    return build("gmail", "v1", credentials=get_credentials(), cache_discovery=False)


def calendar():
    return build("calendar", "v3", credentials=get_credentials(), cache_discovery=False)


def drive():
    return build("drive", "v3", credentials=get_credentials(), cache_discovery=False)


def sheets():
    return build("sheets", "v4", credentials=get_credentials(), cache_discovery=False)


def gmail_profile() -> dict[str, Any]:
    """Devuelve perfil de Gmail del usuario autenticado."""
    return gmail().users().getProfile(userId="me").execute()


def gmail_list_labels() -> list[dict[str, Any]]:
    resp = gmail().users().labels().list(userId="me").execute()
    return resp.get("labels", [])


def gmail_inbox_count(query: str = "in:inbox") -> int:
    resp = gmail().users().messages().list(userId="me", q=query, maxResults=1).execute()
    return int(resp.get("resultSizeEstimate", 0))


def calendar_upcoming(max_results: int = 5) -> list[dict[str, Any]]:
    """Lista proximos eventos del calendario primario."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    cal_id = os.getenv("GOOGLE_CALENDAR_ID", "primary")
    resp = calendar().events().list(
        calendarId=cal_id,
        timeMin=now,
        maxResults=max_results,
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    return resp.get("items", [])
