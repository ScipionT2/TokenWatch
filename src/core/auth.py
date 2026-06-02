"""Lightweight admin-key protection for TokenWatch control-plane APIs."""

from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, status

from config import settings


_ADMIN_HEADER = "X-TokenWatch-Admin-Key"


def admin_auth_enabled() -> bool:
    """Return True when admin API protection is configured."""
    return bool(settings.tokenwatch_admin_key)


def require_admin_key(
    x_tokenwatch_admin_key: str | None = Header(default=None, alias=_ADMIN_HEADER),
) -> bool:
    """Require the configured admin key for sensitive control-plane endpoints.

    TokenWatch stays zero-config for local demos: if TOKENWATCH_ADMIN_KEY is not
    set, routes remain open. In production, setting the env var turns this into a
    constant-time header check for endpoints that mutate/export operational data.
    """
    expected = settings.tokenwatch_admin_key
    if not expected:
        return True
    if not x_tokenwatch_admin_key or not secrets.compare_digest(x_tokenwatch_admin_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "admin_key_required",
                "message": f"Set {_ADMIN_HEADER} to access this TokenWatch admin endpoint.",
            },
        )
    return True
