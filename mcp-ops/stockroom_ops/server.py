"""MCP Apps server: read-only admin operations for the stockroom PoC.

Read-only is deliberate. Product text is crawled from a live website, so it is
attacker-influenceable; exposing order cancellation or price edits as tools
would let a prompt injection trigger them. Nothing here mutates state.
"""

from __future__ import annotations

import argparse
import logging
from typing import Any

from mcp.server.apps import Apps
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from stockroom_ops.api import ApiError, StockroomApi
from stockroom_ops.config import VIEWS_DIR, Settings

log = logging.getLogger(__name__)

DASHBOARD_URI = "ui://stockroom/dashboard"


def read_only() -> ToolAnnotations:
    return ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )


def load_view(name: str) -> str:
    path = VIEWS_DIR / name
    if not path.exists():
        raise SystemExit(
            f"Missing built View {path}.\nRun: cd views && npm install && npm run build"
        )
    return path.read_text(encoding="utf-8")


def build_server(settings: Settings) -> tuple[MCPServer, StockroomApi]:
    apps = Apps()
    api = StockroomApi(settings.api_base, settings.admin_email)

    # The View is a single self-contained HTML file: the host renders ui://
    # resources in a sandboxed iframe under a deny-by-default CSP, so nothing
    # may be loaded from outside the document.
    apps.add_html_resource(
        DASHBOARD_URI,
        load_view("dashboard.html"),
        name="Stockroom dashboard",
        description="Catalog, order and revenue overview.",
    )

    @apps.tool(
        resource_uri=DASHBOARD_URI,
        name="get_dashboard",
        title="Stockroom dashboard",
        description=(
            "Show the stockroom operations dashboard: catalog size, order counts, "
            "revenue, and per-category product totals. Read-only."
        ),
        annotations=read_only(),
        structured_output=True,
    )
    async def get_dashboard(days: int = 30) -> dict[str, Any]:
        """Return dashboard figures for the last `days` days (1-365)."""
        days = max(1, min(int(days), 365))
        try:
            return await api.stats(days)
        except ApiError as exc:
            # Surface a usable message rather than an empty iframe.
            return {"error": {"code": exc.code, "message": str(exc)}}

    server = MCPServer(
        name="stockroom-ops",
        version="0.1.0",
        instructions=(
            "Read-only operations view over a local RAKSUL stockroom PoC. "
            "The catalog is a fixed crawled snapshot, not live inventory."
        ),
        extensions=[apps],
    )
    return server, api


def main() -> None:
    parser = argparse.ArgumentParser(description="Stockroom ops MCP Apps server")
    parser.add_argument(
        "--transport", choices=("stdio", "streamable-http"), default="streamable-http"
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )

    settings = Settings.from_env()
    server, _api = build_server(settings)

    if args.transport == "stdio":
        server.run("stdio")
        return

    import uvicorn

    log.info("MCP endpoint http://%s:%s/mcp", settings.host, settings.port)
    log.info("backend %s as %s", settings.api_base, settings.admin_email)
    uvicorn.run(
        server.streamable_http_app(json_response=True),
        host=settings.host,
        port=settings.port,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
