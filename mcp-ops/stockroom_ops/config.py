"""Settings, defaulting to the docker-compose stack."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

VIEWS_DIR = Path(__file__).resolve().parent.parent / "views" / "dist"


@dataclass(frozen=True)
class Settings:
    api_base: str
    admin_email: str
    host: str
    port: int

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            api_base=os.getenv("STOCKROOM_API_BASE", "http://127.0.0.1:8080"),
            # The Go service falls back to Alice when no identity header
            # arrives, and Alice is not an admin -- so every admin call would
            # 403. This account is resolved to an id at startup instead.
            admin_email=os.getenv("STOCKROOM_ADMIN_EMAIL", "admin@stockroom.local"),
            host=os.getenv("MCP_HOST", "127.0.0.1"),
            port=int(os.getenv("MCP_PORT", "3001")),
        )
