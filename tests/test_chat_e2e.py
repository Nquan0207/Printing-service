from __future__ import annotations

import os

import httpx
import pytest


CHAT_URL = os.getenv("STOCKROOM_CHAT_E2E_URL")


@pytest.mark.skipif(not CHAT_URL, reason="set STOCKROOM_CHAT_E2E_URL to test the running Ollama chat")
def test_running_chat_can_sign_in_and_use_an_mcp_tool():
    with httpx.Client(base_url=CHAT_URL, timeout=int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "600")) + 60) as client:
        health = client.get("/healthz")
        assert health.status_code == 200, health.text
        login = client.post(
            "/api/session/login",
            json={"name": "Ollama E2E", "email": "ollama-e2e@stockroom.local"},
        )
        assert login.status_code == 200, login.text
        # Start from an empty thread. Chat history is persisted per demo user
        # now, so a second run would otherwise resume the first run's answer
        # and the model would reply from context without calling the tool.
        assert client.delete("/api/chat/messages").status_code == 200
        response = client.post(
            "/api/chat",
            json={"message": "Use list_categories and briefly tell me how many categories are available."},
        )
        assert response.status_code == 200, response.text
        assert "event: tool_result" in response.text
        assert '"tool": "list_categories"' in response.text
        assert "event: done" in response.text


@pytest.mark.skipif(not CHAT_URL or not os.getenv('STOCKROOM_E2E_URL'), reason='running chat and API required')
def test_chat_cart_requires_confirmation_before_mock_checkout():
    import uuid
    with httpx.Client(base_url=CHAT_URL, timeout=30) as client:
        catalog = httpx.get(os.environ['STOCKROOM_E2E_URL'] + '/api/v1/products?limit=1').json()
        product = catalog['groups'][0]['products'][0]
        login = client.post('/api/session/login', json={'name': 'Docker checkout', 'email': f'docker-{uuid.uuid4().hex}@example.test'})
        assert login.status_code == 200, login.text
        assert client.post('/api/order/decision', json={'decision': 'approve'}).status_code == 409
        added = client.post('/api/cart/items', json={'product_id': product['id'], 'size_id': product['sizes'][0]['id'], 'quantity': 1})
        assert added.status_code == 200, added.text
        prepared = client.post('/api/order/prepare', json={'shipping_address': 'Docker test address'})
        assert prepared.status_code == 200, prepared.text
        assert 'token' not in prepared.json()['confirmation']
        rejected = client.post('/api/order/decision', json={'decision': 'reject'})
        assert rejected.status_code == 200, rejected.text
        prepared = client.post('/api/order/prepare', json={'shipping_address': 'Docker test address'})
        assert prepared.status_code == 200, prepared.text
        approved = client.post('/api/order/decision', json={'decision': 'approve'})
        assert approved.status_code == 200, approved.text
        assert approved.json()['order']['order_number']
        assert client.get('/api/session').json()['cart']['item_count'] == 0
