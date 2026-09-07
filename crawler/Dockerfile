# Build context is the repo ROOT, not crawler/ — `init-db` reads
# backend-ops/schema.sql at runtime, resolved relative to the package.
FROM python:3.13-slim

WORKDIR /app

COPY crawler/requirements.txt crawler/requirements.txt
RUN pip install --no-cache-dir -r crawler/requirements.txt

COPY crawler/stockroom_crawler crawler/stockroom_crawler
COPY crawler/pyproject.toml crawler/pyproject.toml
# db.py resolves parents[2]/backend-ops/schema.sql -> /app/backend-ops/schema.sql
COPY backend-ops/schema.sql backend-ops/schema.sql

RUN useradd -u 10001 -m crawler && chown -R crawler /app
USER crawler
WORKDIR /app/crawler

# One-shot tool, not a service: `docker compose run --rm crawler <command>`.
ENTRYPOINT ["python", "-m", "stockroom_crawler.cli"]
CMD ["--help"]
