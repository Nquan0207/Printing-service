FROM python:3.13-slim
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY stockroom_chat ./stockroom_chat

RUN useradd -u 10001 -m stockroom && chown -R stockroom /app
USER stockroom
EXPOSE 3002

HEALTHCHECK --interval=15s --timeout=10s --start-period=5s --retries=10 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3002/healthz',timeout=8)" || exit 1

# Serves JSON and the SSE stream only -- the browser UI is chat-ui/.
ENV STOCKROOM_RUNTIME=docker CHAT_HOST=0.0.0.0 CHAT_PORT=3002
CMD ["python", "-m", "stockroom_chat.main"]
