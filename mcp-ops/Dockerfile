# ---- build the View ----
# The View runs in the host's sandboxed iframe, so it is browser JS regardless
# of the server being Python. Bundled to a single self-contained HTML file
# because the iframe CSP is deny-by-default.
FROM node:26-alpine AS views
WORKDIR /views
COPY views/package.json views/package-lock.json ./
RUN npm ci
COPY views/ ./
RUN npm run build

# ---- runtime ----
FROM python:3.13-slim
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY stockroom_ops ./stockroom_ops
# config.py looks for ../views/dist relative to the package.
COPY --from=views /views/dist ./views/dist

RUN useradd -u 10001 -m mcp && chown -R mcp /app
USER mcp
EXPOSE 3001

# A plain socket check: posting to /mcp would open an MCP session on every
# probe and leak them.
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=5 \
    CMD python -c "import socket,sys; s=socket.create_connection(('127.0.0.1',3001),2); s.close()" || exit 1

ENV MCP_HOST=0.0.0.0
ENTRYPOINT ["python", "-m", "stockroom_ops.server"]
CMD ["--transport", "streamable-http"]
