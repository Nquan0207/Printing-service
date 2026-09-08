from __future__ import annotations

import os
from urllib.parse import urlencode

import requests


class StockroomAPIError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int = 500):
        super().__init__(message)
        self.code, self.status_code = code, status_code


class StockroomClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 10.0,
        public_asset_url: str | None = None,
    ):
        # Server-to-server API address. It may safely be loopback when Python MCP and Go run together.
        self.base_url = (base_url or os.getenv("STOCKROOM_API_URL", "http://127.0.0.1:8080")).rstrip("/")
        self.timeout = timeout

        # Browser-visible product images MUST use a public HTTPS origin when the MCP app is remote.
        # Example: https://stockroom.example.com
        self.public_asset_url = (
            public_asset_url
            or os.getenv("STOCKROOM_PUBLIC_ASSET_URL")
            or self.base_url
        ).rstrip("/")

    def _request(self, method: str, path: str, *, user_id: int | None = None, json=None):
        headers = {"Accept": "application/json"}
        if user_id is not None:
            headers["X-Stockroom-User"] = str(user_id)
        try:
            response = requests.request(
                method,
                self.base_url + path,
                headers=headers,
                json=json,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise StockroomAPIError(
                "backend_unavailable",
                f"Stockroom backend is unavailable at {self.base_url}.",
                503,
            ) from exc

        if response.ok:
            return response.json()

        try:
            error = response.json().get("error", {})
        except ValueError:
            error = {}
        raise StockroomAPIError(
            error.get("code", "backend_error"),
            error.get("message", f"Stockroom backend returned HTTP {response.status_code}."),
            response.status_code,
        )

    def health(self):
        return self._request("GET", "/healthz")

    def login(self, email: str, name: str = ""):
        return self._request("POST", "/api/v1/login", json={"email": email, "name": name})

    def categories(self):
        return self._request("GET", "/api/v1/categories")

    def search_products(self, **filters):
        query = {key: value for key, value in filters.items() if value is not None and value != ""}
        path = "/api/v1/products" + (("?" + urlencode(query)) if query else "")
        return self._public_images(self._request("GET", path))

    def product(self, product_id: int):
        return self._public_images(self._request("GET", f"/api/v1/products/{product_id}"))

    def quote(self, product_id: int, size_id: int, quantity: int, user_id: int | None = None):
        return self._request(
            "POST",
            "/api/v1/quote",
            user_id=user_id,
            json={"product_id": product_id, "size_id": size_id, "quantity": quantity},
        )

    def cart(self, user_id: int | None = None):
        return self._public_images(self._request("GET", "/api/v1/cart", user_id=user_id))

    def add_to_cart(self, product_id: int, size_id: int, quantity: int, user_id: int | None = None):
        return self._public_images(
            self._request(
                "POST",
                "/api/v1/cart/items",
                user_id=user_id,
                json={"product_id": product_id, "size_id": size_id, "quantity": quantity},
            )
        )

    def update_cart_item(self, item_id: int, size_id: int, quantity: int, user_id: int | None = None):
        return self._public_images(self._request(
            "PATCH", f"/api/v1/cart/items/{item_id}",
            json={"size_id": size_id, "quantity": quantity}, user_id=user_id))

    def remove_cart_item(self, item_id: int, user_id: int | None = None):
        return self._public_images(self._request("DELETE", f"/api/v1/cart/items/{item_id}", user_id=user_id))

    def place_order(self, shipping_address: str, user_id: int | None = None):
        return self._request("POST", "/api/v1/orders", user_id=user_id, json={"shipping_address": shipping_address})

    def orders(self, user_id: int | None = None, limit: int = 20):
        # Query strings are built here, like search_products: _request takes a
        # path, not params.
        return self._request(
            "GET", "/api/v1/orders?" + urlencode({"limit": limit}), user_id=user_id
        )

    def order(self, order_number: str, user_id: int | None = None):
        return self._request("GET", f"/api/v1/orders/{order_number}", user_id=user_id)

    def _image_url(self, value):
        if not isinstance(value, str):
            return value

        if value.startswith("https://"):
            return value

        if value.startswith("http://127.0.0.1:") or value.startswith(
            "http://localhost:"
        ):
            return value

        if value.startswith("/"):
            return self.public_asset_url + value

        return None

    def _public_images(self, value):
        if isinstance(value, list):
            return [self._public_images(item) for item in value]
        if not isinstance(value, dict):
            return value

        output = {}
        for key, item in value.items():
            if key == "images" and isinstance(item, list):
                output[key] = [url for url in (self._image_url(path) for path in item) if url]
            elif key == "image":
                output[key] = self._image_url(item)
            else:
                output[key] = self._public_images(item)
        return output
