from __future__ import annotations

import os
import time
from typing import Any

import requests
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

bearer_scheme = HTTPBearer(auto_error=True)

_JWKS_CACHE: dict[str, Any] = {"keys": None, "expires_at": 0.0}
_JWKS_TTL_SECONDS = 60 * 10


class AuthConfigError(RuntimeError):
    """Raised when required Auth0 environment variables are missing."""


def _get_auth0_config() -> tuple[str, str]:
    domain = os.getenv("AUTH0_DOMAIN")
    audience = os.getenv("AUTH0_AUDIENCE")
    if not domain or not audience:
        raise AuthConfigError("AUTH0_DOMAIN and AUTH0_AUDIENCE are required")
    return domain, audience


def _jwks_url(domain: str) -> str:
    return f"https://{domain}/.well-known/jwks.json"


def _fetch_jwks(domain: str) -> list[dict[str, Any]]:
    now = time.time()
    if _JWKS_CACHE["keys"] and _JWKS_CACHE["expires_at"] > now:
        return _JWKS_CACHE["keys"]

    response = requests.get(_jwks_url(domain), timeout=5)
    response.raise_for_status()
    data = response.json()

    keys = data.get("keys", [])
    _JWKS_CACHE["keys"] = keys
    _JWKS_CACHE["expires_at"] = now + _JWKS_TTL_SECONDS
    return keys


def _decode_token(token: str) -> dict[str, Any]:
    domain, audience = _get_auth0_config()

    try:
        unverified_header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization token header",
        ) from exc

    kid = unverified_header.get("kid")
    if not kid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization token key id",
        )

    keys = _fetch_jwks(domain)
    matching_key = next((key for key in keys if key.get("kid") == kid), None)

    if not matching_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unable to find appropriate signing key",
        )

    try:
        return jwt.decode(
            token,
            matching_key,
            algorithms=["RS256"],
            audience=audience,
            issuer=f"https://{domain}/",
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token validation failed",
        ) from exc


def get_current_token_payload(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
) -> dict[str, Any]:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization scheme",
        )

    try:
        return _decode_token(credentials.credentials)
    except AuthConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server auth configuration is incomplete",
        ) from exc
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unable to fetch signing keys",
        ) from exc


def require_auth(payload: dict[str, Any] = Depends(get_current_token_payload)) -> dict[str, Any]:
    return payload
