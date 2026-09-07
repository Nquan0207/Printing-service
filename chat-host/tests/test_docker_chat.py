import httpx
import pytest
from fastapi.testclient import TestClient

from stockroom_chat.config import ChatSettings, _local_url
from stockroom_chat.main import create_app


def test_docker_allows_only_expected_service_names(monkeypatch):
    monkeypatch.setenv('STOCKROOM_RUNTIME', 'docker')
    monkeypatch.setenv('CHAT_HOST', '0.0.0.0')
    monkeypatch.setenv('STOCKROOM_API_URL', 'http://api:8080')
    monkeypatch.setenv('OLLAMA_URL', 'http://ollama:11434')
    assert ChatSettings.from_env().stockroom_api_url == 'http://api:8080'
    with pytest.raises(ValueError):
        _local_url('STOCKROOM_API_URL', 'http://external.example')
    monkeypatch.setenv('STOCKROOM_RUNTIME', 'native')
    with pytest.raises(ValueError):
        _local_url('STOCKROOM_API_URL', 'http://api:8080')
    with pytest.raises(ValueError):
        ChatSettings.from_env()


@pytest.mark.parametrize('models,status', [([], 503), ([{'name': 'qwen3:8b'}], 200), ([{'name': 'other:latest'}], 503)])
def test_chat_health_requires_configured_model(monkeypatch, models, status):
    monkeypatch.setenv('CHAT_HOST', '127.0.0.1')
    monkeypatch.setenv('STOCKROOM_API_URL', 'http://127.0.0.1:8080')
    monkeypatch.setenv('OLLAMA_URL', 'http://127.0.0.1:11434')
    monkeypatch.setenv('OLLAMA_MODEL', 'qwen3:8b')
    def handler(request):
        return httpx.Response(200, json={'models': models} if request.url.path == '/api/tags' else {'status': 'ok'})
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with TestClient(create_app(ChatSettings.from_env(), http_client=client)) as app:
        assert app.get('/healthz').status_code == status
