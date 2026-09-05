"""Client for the Go service.

This server never touches SQL or MinIO; the Go service owns both. Every call
carries the admin user id in X-Stockroom-User, matching the UserContext pattern
in docs/api-contract.md.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)


class ApiError(RuntimeError):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.status = status
        self.code = code


class StockroomApi:
    def __init__(self, base_url: str, admin_email: str):
        self._base = base_url.rstrip("/")
        self._admin_email = admin_email
        self._client = httpx.AsyncClient(base_url=self._base, timeout=15)
        self._user_id: int | None = None

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _ensure_admin(self) -> int:
        """Resolve the admin account to an id, once."""
        if self._user_id is None:
            data = await self._request(
                "POST", "/api/v1/login", json={"email": self._admin_email}, identify=False
            )
            if not data.get("is_admin"):
                raise RuntimeError(
                    f"{self._admin_email} is not an admin; add it to "
                    "STOCKROOM_ADMIN_EMAILS on the API and restart it."
                )
            self._user_id = int(data["user_id"])
            log.info("acting as %s (user_id=%s)", self._admin_email, self._user_id)
        return self._user_id

    async def _request(
        self, method: str, path: str, *, identify: bool = True, **kwargs: Any
    ) -> Any:
        headers = dict(kwargs.pop("headers", {}))
        if identify:
            headers["X-Stockroom-User"] = str(await self._ensure_admin())
        response = await self._client.request(method, path, headers=headers, **kwargs)
        if response.status_code >= 400:
            body = {}
            try:
                body = response.json().get("error", {})
            except Exception:  # non-JSON error page
                pass
            raise ApiError(
                response.status_code,
                body.get("code", "unknown"),
                body.get("message", response.reason_phrase),
            )
        return response.json()

    async def stats(self, days: int = 30) -> dict[str, Any]:
        return await self._request("GET", "/api/v1/admin/stats", params={"days": days})
