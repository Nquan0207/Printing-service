from __future__ import annotations

import os

import httpx
import pytest


CHAT_URL = os.getenv("STOCKROOM_CHAT_E2E_URL")


@pytest.mark.skipif(not CHAT_URL, reason="set STOCKROOM_CHAT_E2E_URL to test the running Ollama chat")
def test_running_chat_can_sign_in_and_use_an_mcp_tool():
    with httpx.Client(base_url=CHAT_URL, timeout=180) as client:
        health = client.get("/healthz")
        assert health.status_code == 200, health.text
        login = client.post(
            "/api/session/login",
            json={"name": "Ollama E2E", "email": "ollama-e2e@stockroom.local"},
        )
        assert login.status_code == 200, login.text
        response = client.post(
            "/api/chat",
            json={"message": "Use list_categories and briefly tell me how many categories are available."},
        )
        assert response.status_code == 200, response.text
        assert "event: tool_result" in response.text
        assert '"tool": "list_categories"' in response.text
        assert "event: done" in response.text
