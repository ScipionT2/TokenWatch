"""Lightweight admin-key protection for TokenWatch control-plane APIs."""

from __future__ import annotations

import hashlib
import html
import secrets

from fastapi import Header, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse

from config import settings


_ADMIN_HEADER = "X-TokenWatch-Admin-Key"


def admin_auth_enabled() -> bool:
    """Return True when admin API protection is configured."""
    return bool(settings.tokenwatch_admin_key)


def demo_mode_enabled() -> bool:
    """Return True when the HTML dashboard/setup should be public read-only."""
    return bool(settings.tokenwatch_demo_mode)


def admin_key_matches(candidate: str | None) -> bool:
    """Constant-time admin key comparison when protection is configured."""
    expected = settings.tokenwatch_admin_key
    return bool(expected and candidate and secrets.compare_digest(candidate, expected))


def admin_session_token() -> str:
    """Stable session token derived from the admin key without storing it raw."""
    expected = settings.tokenwatch_admin_key
    if not expected:
        return ""
    return hashlib.sha256(f"tokenwatch-admin-session:{expected}".encode()).hexdigest()


def admin_session_matches(candidate: str | None) -> bool:
    """Return True when a browser session cookie matches the configured key."""
    expected = admin_session_token()
    return bool(expected and candidate and secrets.compare_digest(candidate, expected))


def _safe_next_path(next_path: str = "/dashboard") -> str:
    """Keep browser login redirects relative to this TokenWatch instance."""
    return next_path if next_path.startswith("/") and not next_path.startswith("//") else "/dashboard"


def set_admin_session_cookie(response: Response) -> None:
    """Set the derived browser admin session cookie on a response."""
    response.set_cookie(
        "tokenwatch_admin_session",
        admin_session_token(),
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=60 * 60 * 12,
    )


def html_admin_session_response(next_path: str = "/dashboard") -> RedirectResponse:
    """Issue an HttpOnly browser session cookie after query-string admin unlock."""
    response = RedirectResponse(url=_safe_next_path(next_path), status_code=status.HTTP_303_SEE_OTHER)
    set_admin_session_cookie(response)
    return response


def admin_gate_page(next_path: str = "/dashboard", message: str = "Admin key required") -> HTMLResponse:
    """Small zero-dependency admin gate page for protected HTML routes."""
    safe_next = _safe_next_path(next_path)
    escaped_message = html.escape(message)
    html_content = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TokenWatch — Admin Login</title>
<style>
body {{ margin:0; min-height:100vh; display:grid; place-items:center; background:#070b14; color:#e2e8f0; font-family:-apple-system,BlinkMacSystemFont,Segoe UI,system-ui,sans-serif; }}
.card {{ width:min(92vw,460px); background:rgba(15,23,42,.9); border:1px solid rgba(148,163,184,.24); border-radius:22px; padding:1.5rem; box-shadow:0 24px 70px rgba(0,0,0,.32); }}
h1 {{ margin:0 0 .45rem; }}
p {{ color:#94a3b8; line-height:1.5; }}
input,button {{ width:100%; box-sizing:border-box; font:inherit; border-radius:14px; padding:.85rem .95rem; }}
input {{ background:rgba(2,6,23,.68); color:#e2e8f0; border:1px solid rgba(148,163,184,.24); margin:.7rem 0; }}
button {{ cursor:pointer; border:0; font-weight:800; color:#06111f; background:linear-gradient(135deg,#38bdf8,#a78bfa); }}
.err {{ color:#fca5a5; font-size:.9rem; min-height:1.2rem; }}
</style>
</head>
<body>
<form class="card" onsubmit="login(event)">
<h1>👁️ TokenWatch</h1>
<p>{escaped_message}. Paste your <code>X-TokenWatch-Admin-Key</code> to open this page.</p>
<input id="key" type="password" autocomplete="current-password" placeholder="Admin key" autofocus>
<div id="err" class="err"></div>
<button>Unlock</button>
</form>
<script>
const nextPath = {safe_next!r};
async function login(e) {{
  e.preventDefault();
  const key = document.getElementById('key').value.trim();
  const res = await fetch(`/api/v1/admin/verify?next=${{encodeURIComponent(nextPath)}}`, {{headers: {{'X-TokenWatch-Admin-Key': key}}}});
  if (res.ok) {{
    localStorage.setItem('tokenwatch_admin_key', key);
    window.location.href = nextPath;
    return;
  }}
  document.getElementById('err').textContent = 'Invalid admin key';
}}
</script>
</body>
</html>"""
    return HTMLResponse(content=html_content, status_code=status.HTTP_401_UNAUTHORIZED)


def require_html_admin(request: Request) -> Response | None:
    """Gate HTML pages when an admin key is set, unless public demo mode is enabled."""
    if not admin_auth_enabled() or demo_mode_enabled():
        return None
    safe_path = _safe_next_path(str(request.url.path))
    query_key = request.query_params.get("admin_key")
    session_cookie = request.cookies.get("tokenwatch_admin_session")
    if admin_key_matches(query_key):
        return html_admin_session_response(safe_path)
    if admin_session_matches(session_cookie):
        return None
    return admin_gate_page(next_path=safe_path)


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
