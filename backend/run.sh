#!/usr/bin/env bash
# Run the NovelBridge backend (macOS / Linux).
#
#   ./run.sh            # default engine (Ollama), port 8000
#   ./run.sh --mock     # offline deterministic mock engine
#   PORT=9000 ./run.sh  # custom port
#
# Uses the project virtualenv at ./.venv so you don't type the full python path.

set -euo pipefail
cd "$(dirname "$0")"

PYTHON="./.venv/bin/python"
PORT="${PORT:-8000}"

if [ ! -x "$PYTHON" ]; then
  echo "venv not found at $PYTHON. Create it first:" >&2
  echo "  python -m venv .venv && ./.venv/bin/python -m pip install -r requirements.txt" >&2
  exit 1
fi

if [ "${1:-}" = "--mock" ]; then
  export NB_ENGINE="mock"
  echo "Starting backend with the MOCK engine (offline) on port $PORT"
else
  echo "Starting backend on port $PORT"
fi

exec "$PYTHON" -m uvicorn app.main:app --port "$PORT"
