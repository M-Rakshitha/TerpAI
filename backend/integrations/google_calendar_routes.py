from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from backend.auth.jwt_validator import get_current_token_payload
from backend.integrations import google_calendar_service
from backend.integrations.google_calendar_store import (
    delete_refresh_token,
    get_refresh_token,
    save_refresh_token,
)
from backend.models.schemas import (
    GoogleCalendarEventCreate,
    GoogleCalendarEventLinkCreate,
    GoogleCalendarEventResponse,
    GoogleCalendarLinkTokenPayload,
    GoogleCalendarStatusResponse,
    GoogleCalendarTokenPayload,
)

router = APIRouter(prefix="/api/integrations/google-calendar", tags=["google-calendar"])


def _user_sub(payload: dict[str, Any]) -> str:
    sub = payload.get("sub")
    if not sub or not isinstance(sub, str):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing sub")
    return sub


@router.get("/status", response_model=GoogleCalendarStatusResponse)
async def calendar_status(payload: dict[str, Any] = Depends(get_current_token_payload)) -> GoogleCalendarStatusResponse:
    if not google_calendar_service.google_calendar_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Calendar OAuth is not configured on the server",
        )
    sub = _user_sub(payload)
    return GoogleCalendarStatusResponse(connected=bool(get_refresh_token(sub)))


@router.post("/token", status_code=status.HTTP_204_NO_CONTENT)
async def store_google_refresh_token(
    body: GoogleCalendarTokenPayload,
    payload: dict[str, Any] = Depends(get_current_token_payload),
) -> None:
    if not google_calendar_service.google_calendar_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Calendar OAuth is not configured on the server",
        )
    sub = _user_sub(payload)
    save_refresh_token(sub, body.refresh_token)


@router.post("/token/link", status_code=status.HTTP_204_NO_CONTENT)
async def link_google_calendar_server(
    body: GoogleCalendarLinkTokenPayload,
    x_terpai_calendar_secret: str | None = Header(default=None, alias="X-TerpAI-Calendar-Secret"),
) -> None:
    """Called only from the Next.js server after Google OAuth (shared secret)."""
    _verify_calendar_link_secret(x_terpai_calendar_secret)
    if not google_calendar_service.google_calendar_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Calendar OAuth is not configured on the server",
        )
    save_refresh_token(body.user_sub.strip(), body.refresh_token)


@router.delete("/token", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_google_calendar(payload: dict[str, Any] = Depends(get_current_token_payload)) -> None:
    sub = _user_sub(payload)
    delete_refresh_token(sub)


@router.post("/events", response_model=GoogleCalendarEventResponse)
async def create_event(
    body: GoogleCalendarEventCreate,
    payload: dict[str, Any] = Depends(get_current_token_payload),
) -> GoogleCalendarEventResponse:
    if not google_calendar_service.google_calendar_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Calendar OAuth is not configured on the server",
        )
    sub = _user_sub(payload)
    refresh = get_refresh_token(sub)
    if not refresh:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google Calendar is not connected. Complete OAuth from the TerpAI app first.",
        )
    try:
        result = google_calendar_service.create_calendar_event(
            refresh,
            title=body.title,
            location=body.location,
            start=body.start,
            end=body.end,
            description=body.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    if not result.get("ok"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=result.get("detail") or "Failed to create calendar event",
        )
    return GoogleCalendarEventResponse(
        ok=True,
        event_id=result.get("event_id"),
        html_link=result.get("html_link"),
        detail=None,
    )


def _verify_calendar_link_secret(x_terpai_calendar_secret: str | None) -> None:
    expected = os.getenv("CALENDAR_LINK_SECRET", "").strip()
    if not expected or not x_terpai_calendar_secret or x_terpai_calendar_secret != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid calendar link secret")


@router.post("/events/link", response_model=GoogleCalendarEventResponse)
async def create_event_via_server_link(
    body: GoogleCalendarEventLinkCreate,
    x_terpai_calendar_secret: str | None = Header(default=None, alias="X-TerpAI-Calendar-Secret"),
) -> GoogleCalendarEventResponse:
    """Create a primary-calendar event for user_sub (trusted Next.js server + shared secret)."""
    _verify_calendar_link_secret(x_terpai_calendar_secret)
    if not google_calendar_service.google_calendar_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Calendar OAuth is not configured on the server",
        )
    sub = body.user_sub.strip()
    refresh = get_refresh_token(sub)
    if not refresh:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google Calendar is not connected for this user.",
        )
    try:
        result = google_calendar_service.create_calendar_event(
            refresh,
            title=body.title,
            location=body.location,
            start=body.start,
            end=body.end,
            description=body.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    if not result.get("ok"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=result.get("detail") or "Failed to create calendar event",
        )
    return GoogleCalendarEventResponse(
        ok=True,
        event_id=result.get("event_id"),
        html_link=result.get("html_link"),
        detail=None,
    )


@router.get("/status/link", response_model=GoogleCalendarStatusResponse)
async def calendar_status_via_server_link(
    user_sub: str = Query(..., min_length=1),
    x_terpai_calendar_secret: str | None = Header(default=None, alias="X-TerpAI-Calendar-Secret"),
) -> GoogleCalendarStatusResponse:
    _verify_calendar_link_secret(x_terpai_calendar_secret)
    if not google_calendar_service.google_calendar_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Calendar OAuth is not configured on the server",
        )
    return GoogleCalendarStatusResponse(connected=bool(get_refresh_token(user_sub.strip())))
