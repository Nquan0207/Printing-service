import asyncio
import json
from types import SimpleNamespace

from stockroom_chat.apps import MCPRouter, browser_result
from stockroom_chat.sessions import model_payload


class Connection:
    def __init__(self, url):
        self.url = url
        self.closed = False
        self.calls = []
        names = ["get_dashboard", "list_users"] if url == "ops" else ["open_storefront", "get_cart", "place_order"]
        self.tools = {name: SimpleNamespace(meta={"ui": {"resourceUri": f"ui://{name}"}}) for name in names}
        self.model_tools = [{"function": {"name": name, "parameters": {}}} for name in names if name != "place_order"]
    async def start(self):
        if self.url == "offline":
            raise RuntimeError("offline")
    async def close(self):
        self.closed = True
    async def call(self, name, arguments):
        self.calls.append((name, arguments))
        return {"status": "ok", "count": 3}


def test_routing_identity_and_app_capabilities():
    async def run():
        router = MCPRouter("shop", "ops", Connection)
        await router.start()
        assert "ops__get_dashboard" in router.allowed_model_tools
        assert "shop__open_storefront" in router.allowed_model_tools
        assert "shop__place_order" not in router.allowed_model_tools
        pending = await router.call("ops__get_dashboard", {"days": 7, "admin_name": "guessed", "admin_email": "guessed"})
        assert not router.connections["ops"].calls
        stored = router.pending[pending["_ops_request"]["id"]]
        assert stored["arguments"] == {"days": 7}
        dashboard = await router.execute("ops", "get_dashboard", {"days": 7})
        ident = dashboard["_mcp_app"]["id"]
        for name in ("shop__get_cart", "place_order", "unknown"):
            rejected = await router.app_call(ident, name, {}, {"name": "a", "email": "a@b.com"})
            assert rejected["error"]["code"] == "tool_not_allowed"
        missing = await router.app_call(ident, "get_dashboard", {"admin_name": "guess"}, None)
        assert missing["error"]["code"] == "identity_required"
        await router.app_call(ident, "get_dashboard", {"days": 30, "admin_email": "guess"}, {"name": "Admin", "email": "a@b.com"})
        assert router.connections["ops"].calls[-1][1] == {"days": 30, "admin_name": "Admin", "admin_email": "a@b.com"}
        again = await router.app_call(ident, "get_dashboard", {}, None)
        assert again["error"]["code"] == "identity_required"
        count = len(router.connections["ops"].calls)
        router.restore(dashboard)
        assert dashboard["_mcp_app"]["id"] != ident
        assert len(router.connections["ops"].calls) == count
        await router.close()
        assert all(c.closed for c in router.connections.values())
        assert not router.bindings
    asyncio.run(run())


def test_ops_outage_does_not_block_shopping():
    async def run():
        router = MCPRouter("shop", "offline", Connection)
        await router.start()
        assert router.available == {"shop"}
        assert (await router.call("get_cart"))["status"] == "ok"
        assert (await router.call("ops__get_dashboard"))["error"]["code"] == "mcp_unavailable"
        await router.close()
    asyncio.run(run())


def test_private_fields_and_ui_do_not_reach_model():
    payload = {"confirmation": {"token": "private", "shipping_address": "Tokyo"},
               "_mcp_result": {"structuredContent": {"confirmation": {"token": "private"}},
                               "content": [{"type": "text", "text": '{"token":"private"}'}]},
               "_mcp_app": {"id": "view-id", "input": {"admin_email": "private"}}}
    public = browser_result(payload)
    assert "private" not in json.dumps(public)
    model = model_payload(payload)
    assert model["confirmation"]["shipping_address"] == "Tokyo"
    assert set(model) == {"confirmation"}
    assert "token" not in model["confirmation"]
    assert payload["confirmation"]["token"] == "private"


def test_http_app_isolation_identity_checkout_and_csp():
    from fastapi.testclient import TestClient
    from stockroom_chat.main import create_app, COOKIE_NAME
    from stockroom_chat.sessions import SessionStore
    from test_chat_app import settings, FakeHTTP, FakeMCP, EchoAgent

    class EndpointConnection(FakeMCP):
        def __init__(self, url):
            super().__init__(url)
            self.tools = {name: SimpleNamespace(meta={"ui": {"resourceUri": "ui://" + name}})
                          for name in ("get_dashboard", "open_storefront", "get_cart", "place_order")}
        async def call(self, name, arguments=None):
            if name == "__read_resource":
                return {"contents": [{"text": "<html>panel</html>", "_meta": {"ui": {"csp": {"resourceDomains": ["http://127.0.0.1:8080"]}}}}]}
            if name == "get_dashboard":
                if arguments.get("admin_name") != "Test Admin" or arguments.get("admin_email") != "admin@example.com":
                    return {"error": {"code": "forbidden", "message": "Invalid administrator"}}
                return {"days": arguments.get("days", 30), "revenue": 42}
            return await super().call(name, arguments)

    store = SessionStore(mcp_url="shop", ttl_seconds=600, mcp_factory=lambda url: MCPRouter(url, "ops", EndpointConnection))
    app = create_app(settings(), session_store=store, http_client=FakeHTTP(), agent=EchoAgent())
    with TestClient(app) as client:
        assert client.get('/api/apps/invalid/resource').status_code == 401
        client.post('/api/session/login', json={'name':'A', 'email':'a@example.com'}).raise_for_status()
        token = client.cookies.get(COOKIE_NAME)
        state = store._sessions[token]
        pending = client.portal.call(state.mcp.call, "ops__get_dashboard", {"days":7})
        ident = pending['_ops_request']['id']
        invalid = client.post('/api/apps/identity/'+ident, json={'name':'Wrong', 'email':'admin@example.com'})
        assert invalid.json()['error']['code'] == 'forbidden'
        result = client.post('/api/apps/identity/'+ident, json={'name':'Test Admin', 'email':'admin@example.com'}).json()
        binding = result['_mcp_app']['id']
        assert result['revenue'] == 42
        assert client.post('/api/apps/identity/'+ident, json={'name':'Test Admin', 'email':'admin@example.com'}).status_code == 410
        assert client.get('/api/apps/'+binding+'/resource').status_code == 200
        sandbox = client.get('/api/apps/'+binding+'/sandbox')
        assert "default-src 'none'" in sandbox.headers['content-security-policy']
        assert 'http://127.0.0.1:8080' in sandbox.headers['content-security-policy']
        missing = client.post('/api/apps/'+binding+'/tools', json={'name':'get_dashboard', 'arguments':{'days':30}})
        assert missing.json()['error']['code'] == 'identity_required'
        blocked = client.post('/api/apps/'+binding+'/tools', json={'name':'place_order'})
        assert blocked.json()['error']['code'] == 'tool_not_allowed'
        cross_origin = client.post('/api/order/decision', headers={'Origin':'http://testserver:3005'}, json={'decision':'approve'})
        assert cross_origin.status_code == 403
        assert client.post('/api/order/decision', json={'decision':'approve'}).status_code == 409
        client.cookies.clear()
        client.post('/api/session/login', json={'name':'B', 'email':'b@example.com'}).raise_for_status()
        assert client.get('/api/apps/'+binding+'/resource').status_code == 404
        assert client.post('/api/apps/'+binding+'/tools', json={'name':'get_dashboard'}).status_code == 404
        client.portal.call(store.close)
