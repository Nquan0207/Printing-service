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
            # Checked against what the sign-in form submits. Unset means no
            # admin can ever sign in -- fail closed, because "unset == no
            # check" is how a gate like this quietly stops being one.
            admin_passcode=os.getenv("STOCKROOM_ADMIN_PASSCODE", ""),
            host=os.getenv("MCP_HOST", "127.0.0.1"),
            port=int(os.getenv("MCP_PORT", "3001")),
        )
