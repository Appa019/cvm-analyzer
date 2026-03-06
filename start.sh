#!/usr/bin/env bash
# CVM Analyzer — Script de inicialização para produção
# Uso: ./start.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
VENV_DIR="$SCRIPT_DIR/.venv"

# Ativar virtualenv
source "$VENV_DIR/bin/activate"

# Build frontend se dist/ não existe
if [ ! -f "$FRONTEND_DIR/dist/index.html" ]; then
    echo "[start.sh] Construindo frontend..."
    cd "$FRONTEND_DIR"
    npm ci --production=false
    npm run build
    cd "$SCRIPT_DIR"
fi

# Iniciar uvicorn (host 127.0.0.1 porque nginx faz o proxy)
cd "$BACKEND_DIR"
exec uvicorn main:app \
    --host 127.0.0.1 \
    --port 8000 \
    --workers 1 \
    --limit-max-requests 1000 \
    --timeout-keep-alive 5 \
    --log-level info
