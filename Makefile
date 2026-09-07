SHELL := /bin/sh
COMPOSE := docker compose

.PHONY: setup up down infra reset-db crawl-smoke crawl api health mcp mcp-http ollama-pull chat chat-health test test-python test-go test-e2e test-chat-e2e stats logs
setup up:
	$(COMPOSE) up -d --build --wait

down:
	$(COMPOSE) down

infra:
	$(COMPOSE) up -d --wait postgres minio

reset-db:
	@test "$(CONFIRM_RESET)" = "1" || (echo "Refusing destructive reset. Re-run with CONFIRM_RESET=1" >&2; exit 2)
	$(COMPOSE) down
	$(COMPOSE) up -d --wait postgres minio
	$(COMPOSE) run --rm --build --no-deps crawler init-db
	$(COMPOSE) run --rm --no-deps crawler bootstrap
	$(COMPOSE) up -d --build --wait

crawl-smoke:
	$(COMPOSE) run --rm --build -e CRAWL_MAX_PRODUCTS=3 -e CRAWL_MAX_CATEGORIES=1 crawler crawl
	$(COMPOSE) run --rm crawler stats

crawl:
	$(COMPOSE) run --rm --build crawler crawl
	$(COMPOSE) run --rm crawler stats

stats:
	$(COMPOSE) run --rm crawler stats

api:
	$(COMPOSE) up -d --build --wait api

health:
	$(COMPOSE) exec -T api wget -qO- http://127.0.0.1:8080/healthz

mcp:
	$(COMPOSE) exec -T shopping-mcp python -m app.mcp_server.server

mcp-http:
	$(COMPOSE) up -d --build --wait mcp shopping-mcp

ollama-pull:
	$(COMPOSE) run --rm model-init

chat:
	$(COMPOSE) up -d --build --wait chat

chat-health:
	$(COMPOSE) exec -T chat python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:3002/healthz').read().decode())"

test-python:
	$(COMPOSE) run --rm --build test-python python -m pytest -q --ignore=tests/test_stockroom_e2e.py --ignore=tests/test_chat_e2e.py

test-go:
	$(COMPOSE) run --rm --build test-go

test: test-python test-go

test-e2e:
	$(COMPOSE) run --rm --build test-python python -m pytest -q tests/test_stockroom_e2e.py

test-chat-e2e:
	$(COMPOSE) run --rm --build test-python python -m pytest -q tests/test_chat_e2e.py

logs:
	$(COMPOSE) logs -f model-init api chat
