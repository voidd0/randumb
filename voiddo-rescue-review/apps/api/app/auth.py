from __future__ import annotations

from fastapi import Header, HTTPException, Request

from .config import get_settings


def _token_from_header(authorization: str | None, x_admin_token: str | None) -> str:
    if x_admin_token:
        return x_admin_token.strip()
    if authorization:
        value = authorization.strip()
        if value.lower().startswith("bearer "):
            return value[7:].strip()
    return ""


def require_admin(request: Request, authorization: str | None = Header(default=None), x_admin_token: str | None = Header(default=None)) -> None:
    expected = get_settings().admin_auth_token
    if not expected:
        raise HTTPException(status_code=503, detail="admin auth token not configured")
    supplied = _token_from_header(authorization, x_admin_token)
    if supplied != expected:
        raise HTTPException(status_code=401, detail="admin auth required")
