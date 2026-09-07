"""Per-session admin authentication.

The server used to resolve one admin at startup and send that id on every
call, which made the real access rule "whoever can reach this port is admin" --
a configuration accident rather than a credential. Identity is now a property
of the connection: nothing is admin until someone signs in on it.

The passcode is checked here and never leaves this process. It is compared in
constant time and never logged, and the tool that takes it is app-only so the
model is never offered a way to ask for it.
"""

from __future__ import annotations

import hmac
import logging
import secrets
import threading
from typing import Any

log = logging.getLogger(__name__)

_LOCK = threading.Lock()
_SESSIONS: dict[str, dict[str, Any]] = {}

STDIO_KEY = "stdio-connection"
_stdio = False


def set_stdio(enabled: bool) -> None:
    global _stdio
    _stdio = enabled


def owner(ctx: Any) -> str:
    """A stable key for the connection behind this call."""
    headers = getattr(ctx, "headers", None) or {}
    session_id = headers.get("mcp-session-id") or headers.get("Mcp-Session-Id")
    if session_id:
        return "http:" + str(session_id)
    if _stdio:
        return STDIO_KEY
    return "unbindable:" + secrets.token_urlsafe(9)


def forget(key: str) -> None:
    with _LOCK:
        _SESSIONS.pop(key, None)


def admin(owner_key: str) -> dict[str, Any] | None:
    """The signed-in admin for this connection, or None."""
    with _LOCK:
        return _SESSIONS.get(owner_key)


def user_id(owner_key: str) -> int | None:
    session = admin(owner_key)
    return session["user_id"] if session else None


def public(owner_key: str) -> dict[str, Any] | None:
    """Who is signed in, for the panel to show beside its sign-out control.

    Only the name and address -- the user_id is this server's business.
    """
    session = admin(owner_key)
    if not session:
        return None
    return {"email": session["email"], "name": session.get("name", "")}


def sign_in(owner_key: str, user: dict[str, Any]) -> dict[str, Any]:
    """Bind a verified admin to this connection."""
    grant = {"user_id": int(user["user_id"]), "email": user["email"], "name": user.get("name", "")}
    with _LOCK:
        _SESSIONS[owner_key] = grant
    log.info("admin session opened for %s", grant["email"])
    return grant


def sign_out(owner_key: str) -> None:
    session = admin(owner_key)
    forget(owner_key)
    if session:
        log.info("admin session closed for %s", session["email"])


def passcode_ok(presented: str, expected: str) -> bool:
    """Constant-time compare, so a wrong guess costs the same whatever it is.

    An unset expected passcode never matches. Treating "no passcode
    configured" as "no check" is how this class of gate silently fails open.
    """
    if not expected or not presented:
        return False
    return hmac.compare_digest(presented, expected)


AUTH_REQUIRED = {
    "error": {
        "code": "auth_required",
        "message": "Sign in with an administrator email and passcode to view this.",
    }
}
