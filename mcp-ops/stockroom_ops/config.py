"""Settings, defaulting to the docker-compose stack."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

VIEWS_DIR = Path(__file__).resolve().parent.parent / "views" / "dist"


@dataclass(frozen=True)
class Settings:
    api_base: str
    public_api_base: str
    admin_email: str
    admin_passcode: str
    admin_require_passcode: bool
    admin_session_ttl_seconds: int
    host: str
    port: int

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            api_base=os.getenv("STOCKROOM_API_BASE", "http://127.0.0.1:8080"),
            # What the HOST BROWSER can reach, which is not what this server
            # uses: in Docker the server talks to http://api:8080, but the
            # iframe runs on the user's machine and must use localhost. Image
            # URLs and the View's CSP allowance are both built from this.
            public_api_base=os.getenv("STOCKROOM_PUBLIC_API_BASE", "http://127.0.0.1:8080"),
            # No longer resolved at startup: an admin signs in per connection,
            # and this is only the address the sign-in form is checked against.
            admin_email=os.getenv("STOCKROOM_ADMIN_EMAIL", "admin@stockroom.local"),
            # Checked against what the sign-in form submits, when the check is
            # on. Unset still means no admin can sign in -- "unset == no check"
            # is how a gate like this quietly stops being one, so turning the
            # check off is a separate, deliberate flag rather than a side
            # effect of forgetting to set a value.
            admin_passcode=os.getenv("STOCKROOM_ADMIN_PASSCODE", ""),
            # Demo default: an admin email alone is enough. The access rule is
            # then "whoever can reach this port and knows an admin address",
            # which is what the Go API already assumes -- /api/v1/admin/* is
            # gated only on an unverified X-Stockroom-User header. Set
            # STOCKROOM_ADMIN_REQUIRE_PASSCODE=true to put the credential back.
            admin_require_passcode=os.getenv(
                "STOCKROOM_ADMIN_REQUIRE_PASSCODE", "false"
            ).strip().lower() in {"1", "true", "yes", "on"},
            # Idle timeout for a signed-in admin, refreshed on every call.
            # Short by default because this is a demo surface; raise it for
            # real use, where re-authenticating every minute is unusable.
            admin_session_ttl_seconds=int(
                os.getenv("STOCKROOM_ADMIN_SESSION_TTL_SECONDS", "60")
            ),
            host=os.getenv("MCP_HOST", "127.0.0.1"),
            port=int(os.getenv("MCP_PORT", "3001")),
        )
