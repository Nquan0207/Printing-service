SHELL := /bin/sh
PYTHON := .venv/bin/python
PIP := .venv/bin/pip

.PHONY: setup infra reset-db crawl-smoke crawl api health mcp mcp-http ollama-pull chat chat-health test test-python test-go test-e2e test-chat-e2e stats

setup:
	@test -x "$(PYTHON)" || python3 -m venv .venv
	$(PIP) install -r requirements.txt

infra:
	docker compose up -d --wait postgres minio

reset-db:
	@test "$(CONFIRM_RESET)" = "1" || (echo "Refusing destructive reset. Re-run with CONFIRM_RESET=1" >&2; exit 2)
	docker compose down -v --remove-orphans
	docker compose up -d --wait postgres minio
	$(PYTHON) -m stockroom_crawler.cli init-db

crawl-smoke: infra
	CRAWL_MAX_PRODUCTS=3 CRAWL_MAX_CATEGORIES=1 $(PYTHON) -m stockroom_crawler.cli crawl
	$(PYTHON) -m stockroom_crawler.cli stats

crawl: infra
	$(PYTHON) -m stockroom_crawler.cli crawl
	$(PYTHON) -m stockroom_crawler.cli stats

stats:
	$(PYTHON) -m stockroom_crawler.cli stats

api:
	docker compose up -d --build --wait api

health:
	curl --fail --silent --show-error http://127.0.0.1:8080/healthz

mcp:
	$(PYTHON) -m app.mcp_server.server

mcp-http:
	$(PYTHON) -m app.mcp_server.server --transport streamable-http

ollama-pull:
	ollama pull "$${OLLAMA_MODEL:-qwen3:8b}"

chat:
	$(PYTHON) -m app.chat_app.main

chat-health:
	curl --fail --silent --show-error "http://$${CHAT_HOST:-127.0.0.1}:$${CHAT_PORT:-3000}/healthz"

test-python:
	$(PYTHON) -m pytest -q

test-go:
	docker run --rm -v "$(CURDIR)/go-backend:/src" -w /src golang:1.26-alpine go test ./...

test: test-python test-go

test-e2e:
	STOCKROOM_E2E_URL=http://127.0.0.1:8080 $(PYTHON) -m pytest -q tests/test_stockroom_e2e.py

test-chat-e2e:
	STOCKROOM_CHAT_E2E_URL=http://127.0.0.1:3000 $(PYTHON) -m pytest -q tests/test_chat_e2e.py
