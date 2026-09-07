# Cross-service end-to-end checks only. Unit suites live with their service
# (mcp-shop/tests, chat-host/tests, crawler/tests) and do not need the stack up.
FROM python:3.13-slim
WORKDIR /app
RUN pip install --no-cache-dir httpx requests pytest "mcp>=1.18,<2"
COPY tests ./tests
COPY pyproject.toml ./
# test_docker_model_init runs this script directly.
COPY docker/model-init.sh ./docker/model-init.sh
ENV PYTEST_ADDOPTS="-o cache_dir=/tmp/pytest-cache"
CMD ["python", "-m", "pytest", "-q"]
