# ---- build the View ----
# Browser code regardless of the server being Python: it runs in the host's
# sandboxed iframe. Bundled to one self-contained file because that iframe's
# CSP is deny-by-default.
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

COPY stockroom_shop ./stockroom_shop
# storefront_widget.py resolves parents[1]/views/dist -> /app/views/dist
COPY --from=views /views/dist ./views/dist

RUN useradd -u 10001 -m stockroom && chown -R stockroom /app
USER stockroom
EXPOSE 3003

# A plain socket check: posting to /mcp would open an MCP session on every
# probe and leak them. Same reasoning as mcp-ops.
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=5 \
    CMD python -c "import socket; socket.create_connection(('127.0.0.1',3003),2).close()" || exit 1

ENV MCP_HOST=0.0.0.0 MCP_PORT=3003
ENTRYPOINT ["python", "-m", "stockroom_shop.server"]
CMD ["--transport", "streamable-http"]
