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
            # The Go service falls back to Alice when no identity header
            # arrives, and Alice is not an admin -- so every admin call would
            # 403. This account is resolved to an id at startup instead.
            # Ops access is intentionally pinned to one exact address. Keep
            # this in sync with the API's granted admin in docker-compose.yml.
            admin_email="admin@gmail.com",
            host=os.getenv("MCP_HOST", "127.0.0.1"),
            port=int(os.getenv("MCP_PORT", "3001")),
        )
