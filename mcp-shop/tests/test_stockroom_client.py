import requests

from stockroom_shop.stockroom_client import StockroomAPIError, StockroomClient


class Response:
    ok = True
    status_code = 200
    def __init__(self, body): self.body = body
    def json(self): return self.body


def test_client_sends_identity_and_converts_media_paths(monkeypatch):
    captured = {}
    def request(method, url, **kwargs):
        captured.update(method=method, url=url, **kwargs)
        return Response({"items": [{"image": "/media/a.jpg"}], "images": ["/media/b.jpg"]})
    monkeypatch.setattr(requests, "request", request)
    client = StockroomClient("http://127.0.0.1:8080")
    result = client.cart(42)
    assert captured["headers"]["X-Stockroom-User"] == "42"
    assert result["items"][0]["image"] == "http://127.0.0.1:8080/media/a.jpg"
    assert result["images"][0].endswith("/media/b.jpg")


def test_client_maps_backend_error(monkeypatch):
    response = Response({"error": {"code": "cart_empty", "message": "Empty"}})
    response.ok, response.status_code = False, 409
    monkeypatch.setattr(requests, "request", lambda *a, **k: response)
    try:
        StockroomClient().cart()
        assert False
    except StockroomAPIError as exc:
        assert exc.code == "cart_empty"
