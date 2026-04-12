from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

_SCOPES = ("https://www.googleapis.com/auth/calendar.events",)


def _google_client_config() -> tuple[str, str]:
    cid = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip()
    secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
    return cid, secret


def google_calendar_configured() -> bool:
    cid, secret = _google_client_config()
    return bool(cid and secret)


def _parse_start_end(start_raw: str, end_raw: str | None) -> tuple[datetime, datetime]:
    start_raw = start_raw.strip()
    try:
        if len(start_raw) == 10 and start_raw[4] == "-" and start_raw[7] == "-":
            start_dt = datetime.strptime(start_raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            start_dt = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError(f"Invalid start datetime: {start_raw}") from exc

    if end_raw and str(end_raw).strip():
        end_str = str(end_raw).strip()
        try:
            if len(end_str) == 10 and end_str[4] == "-" and end_str[7] == "-":
                end_dt = datetime.strptime(end_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            else:
                end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise ValueError(f"Invalid end datetime: {end_str}") from exc
    else:
        end_dt = start_dt + timedelta(hours=1)

    if end_dt <= start_dt:
        end_dt = start_dt + timedelta(hours=1)
    return start_dt, end_dt


def create_calendar_event(
    refresh_token: str,
    *,
    title: str,
    location: str | None,
    start: str,
    end: str | None,
    description: str | None,
) -> dict[str, Any]:
    client_id, client_secret = _google_client_config()
    if not client_id or not client_secret:
        raise RuntimeError("Google OAuth client is not configured")

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=_SCOPES,
    )
    creds.refresh(Request())

    start_dt, end_dt = _parse_start_end(start, end)
    body: dict[str, Any] = {
        "summary": title,
        "start": {"dateTime": start_dt.isoformat()},
        "end": {"dateTime": end_dt.isoformat()},
    }
    if location:
        body["location"] = location
    if description:
        body["description"] = description

    try:
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        created = service.events().insert(calendarId="primary", body=body).execute()
        return {
            "ok": True,
            "event_id": created.get("id"),
            "html_link": created.get("htmlLink"),
            "detail": None,
        }
    except HttpError as exc:
        return {
            "ok": False,
            "event_id": None,
            "html_link": None,
            "detail": f"Google Calendar API error: {exc.reason or str(exc)}",
        }
