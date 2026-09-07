#!/bin/sh
set -eu
if ollama show "$OLLAMA_MODEL" >/dev/null 2>&1; then
  echo "Model $OLLAMA_MODEL already installed"
else
  ollama pull "$OLLAMA_MODEL"
fi
