from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _local_url(name: str, value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError(f"{name} must use a loopback HTTP(S) URL")
    return value.rstrip("/")


@dataclass(frozen=True)
class ChatSettings:
    project_root: Path
    stockroom_api_url: str
    ollama_url: str
    ollama_model: str
    host: str
    port: int
    session_ttl_seconds: int
    max_model_rounds: int = 6
    max_tool_calls: int = 8
    max_sessions: int = 20

    @classmethod
    def from_env(cls) -> "ChatSettings":
        load_dotenv(PROJECT_ROOT / ".env")
        host = os.getenv("CHAT_HOST", "127.0.0.1")
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("CHAT_HOST must be a loopback address")
        port = int(os.getenv("CHAT_PORT", "3000"))
        if not 1 <= port <= 65535:
            raise ValueError("CHAT_PORT must be between 1 and 65535")
        return cls(
            project_root=PROJECT_ROOT,
            stockroom_api_url=_local_url(
                "STOCKROOM_API_URL",
                os.getenv("STOCKROOM_API_URL", "http://127.0.0.1:8080"),
            ),
            ollama_url=_local_url(
                "OLLAMA_URL", os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
            ),
            ollama_model=os.getenv("OLLAMA_MODEL", "qwen3:8b"),
            host=host,
            port=port,
            session_ttl_seconds=max(60, int(os.getenv("CHAT_SESSION_TTL_SECONDS", "86400"))),
        )
