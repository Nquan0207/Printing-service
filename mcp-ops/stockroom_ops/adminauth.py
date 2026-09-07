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
import time
import secrets
import threading
from typing import Any

log = logging.getLogger(__name__)

_LOCK = threading.Lock()
_SESSIONS: dict[str, dict[str, Any]] = {}

STDIO_KEY = "stdio-connection"
_stdio = False

# Idle timeout, refreshed on every authenticated call. A long-lived host
# connection would otherwise stay admin until someone remembered to click sign
# out, which on a shared screen is indefinitely.
_ttl_seconds = 60.0
# Keys whose grant we just expired, so the panel can say "timed out" instead of
# silently showing a login form over what used to be a dashboard. Read once.
_EXPIRED: dict[str, float] = {}


def set_ttl(seconds: float) -> None:
    global _ttl_seconds
    _ttl_seconds = max(1.0, float(seconds))


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
    """The signed-in admin for this connection, or None if absent or idle.

    Sliding window: an admin who is using the panel stays signed in, and one
    who walked away does not. monotonic() so a clock change cannot extend or
    revoke a session.
    """
    now = time.monotonic()
    with _LOCK:
        session = _SESSIONS.get(owner_key)
        if session is None:
            return None
        if now - session["last_seen"] > _ttl_seconds:
            _SESSIONS.pop(owner_key, None)
            _EXPIRED[owner_key] = now
            if len(_EXPIRED) > 256:  # bounded: this is a hint, not a record
                _EXPIRED.clear()
            log.info("admin session expired for %s", session["email"])
            return None
        session["last_seen"] = now
        return session


def just_expired(owner_key: str) -> bool:
    """True once, for the call that discovered the grant had timed out."""
    with _LOCK:
        return _EXPIRED.pop(owner_key, None) is not None


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
    return {
        "email": session["email"],
        "name": session.get("name", ""),
        # So the panel can show how long it has before it locks.
        "idle_timeout_seconds": int(_ttl_seconds),
    }


def sign_in(owner_key: str, user: dict[str, Any]) -> dict[str, Any]:
    """Bind a verified admin to this connection."""
    grant = {
        "user_id": int(user["user_id"]),
        "email": user["email"],
        "name": user.get("name", ""),
        "last_seen": time.monotonic(),
    }
    with _LOCK:
        _SESSIONS[owner_key] = grant
        _EXPIRED.pop(owner_key, None)
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


def auth_required(owner_key: str) -> dict[str, Any]:
    """The refusal, saying whether this was a timeout or never signed in."""
    if just_expired(owner_key):
        return {
            "error": {
                "code": "auth_required",
                "message": (
                    f"Signed out after {int(_ttl_seconds)}s of inactivity. "
                    "Sign in again to continue."
                ),
            }
        }
    return AUTH_REQUIRED
