"""Minimal login (D-47): two users from env, a signed session cookie, no registration.

ZIRO_ADMIN_USER / ZIRO_ADMIN_PASSWORD and ZIRO_REVIEWER_USER / ZIRO_REVIEWER_PASSWORD; the
cookie is HMAC-signed with ZIRO_SESSION_SECRET (a random one per process if unset, so logins
end on restart). Both users review gates, and every decision records the logged-in name; only
the admin adds or starts planned topics. Stdlib only.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

COOKIE = "ziro_session"
HOURS = 12
OPEN = ("/login", "/static/")
_SECRET = os.environ.get("ZIRO_SESSION_SECRET") or secrets.token_hex(32)


def users() -> dict[str, tuple[str, str]]:
    """name -> (password, role) for the two seeded users; unset ones are left out."""
    found = {}
    for role in ("admin", "reviewer"):
        name = os.environ.get(f"ZIRO_{role.upper()}_USER", "")
        password = os.environ.get(f"ZIRO_{role.upper()}_PASSWORD", "")
        if name and password:
            found[name] = (password, role)
    return found


def check(name: str, password: str) -> str | None:
    """The user's role when the password matches, else None."""
    known = users().get(name)
    if known and hmac.compare_digest(known[0].encode(), password.encode()):
        return known[1]
    return None


def cookie(name: str, role: str) -> str:
    body = base64.urlsafe_b64encode(json.dumps(
        {"name": name, "role": role, "exp": int(time.time()) + HOURS * 3600}).encode()).decode()
    return f"{body}.{_sign(body)}"


def current(request: Request) -> dict[str, Any] | None:
    body, _, signature = request.cookies.get(COOKIE, "").partition(".")
    if not body or not hmac.compare_digest(signature, _sign(body)):
        return None
    session: dict[str, Any] = json.loads(base64.urlsafe_b64decode(body))
    if session["exp"] < time.time() or session["name"] not in users():
        return None
    return session


def _sign(body: str) -> str:
    return hmac.new(_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()


async def middleware(request: Request, call_next: Any) -> Response:
    """Every page and API call needs a session, except the login page and static files."""
    path = request.url.path
    if path.startswith(OPEN):
        response: Response = await call_next(request)
        return response
    session = current(request)
    if session is None:
        if path.startswith("/projects"):  # the JSON API
            return JSONResponse({"detail": "log in first"}, status_code=401)
        return RedirectResponse(f"/login?next={quote(path)}", status_code=303)
    request.state.user = session
    response = await call_next(request)
    return response
