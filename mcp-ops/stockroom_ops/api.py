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


def _params(limit: int, filters: dict[str, Any]) -> dict[str, Any]:
    """Drop unset filters -- and only those.

    "Unset" is None or the empty string, never 0. `max_orders=0` means
    "customers who never ordered", which a falsy check silently discards; the
    caller decides what counts as unset and simply omits it.
    """
    params: dict[str, Any] = {"limit": limit}
    for key, value in filters.items():
        if value is not None and value != "":
            params[key] = value
    return params


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

    async def verify_admin_identity(self, name: str, email: str) -> None:
        """Re-read the submitted ops identity and admin flag from PostgreSQL."""
        data = await self._request(
            "POST",
            "/api/v1/admin/verify-identity",
            json={"name": name, "email": email},
            identify=False,
        )
        self._user_id = int(data["user_id"])

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

    async def orders(self, limit: int = 50, **filters: Any) -> dict[str, Any]:
        """List orders. Filters map straight onto the query string; the API
        resolves and echoes them back as `applied`."""
        return await self._request(
            "GET", "/api/v1/admin/orders", params=_params(limit, filters)
        )

    async def products(
        self,
        query: str | None = None,
        categories: list[str] | None = None,
        include_inactive: bool = True,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"include_inactive": str(include_inactive).lower()}
        if query:
            params["q"] = query
        if categories:
            # Raw words, not slugs -- the API resolves them. One comma-separated
            # value covers any number of them.
            params["category"] = ",".join(categories)
        return await self._request("GET", "/api/v1/admin/products", params=params)

    async def product(self, product_id: int) -> dict[str, Any]:
        return await self._request("GET", f"/api/v1/products/{product_id}")

    async def users(self, limit: int = 50, **filters: Any) -> dict[str, Any]:
        """List user accounts, with the same filter convention as `orders`."""
        return await self._request(
            "GET", "/api/v1/admin/users", params=_params(limit, filters)
        )
