FROM python:3.13-slim AS runtime
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
RUN useradd -u 10001 -m stockroom
USER stockroom
ENV STOCKROOM_RUNTIME=docker
CMD ["python", "-m", "app.chat_app.main"]

FROM runtime AS test
COPY crawler/stockroom_crawler ./crawler/stockroom_crawler
COPY backend-ops/schema.sql ./backend-ops/schema.sql
COPY tests ./tests
COPY docker/model-init.sh ./docker/model-init.sh
ENV PYTHONPATH=/app:/app/crawler
ENV PYTEST_ADDOPTS="-o cache_dir=/tmp/pytest-cache"
CMD ["python", "-m", "pytest", "-q"]
