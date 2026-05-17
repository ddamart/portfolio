#!/usr/bin/env bash
# start.sh — Starts backend (FastAPI) and frontend (Vite) in the same terminal.
# Run from the project root: ./start.sh
set -e

BACKEND_PORT=${BACKEND_PORT:-8000}
FRONTEND_PORT=${FRONTEND_PORT:-5173}
ROOT="$(cd "$(dirname "$0")" && pwd)"

PYTHON="$ROOT/backend/.venv/bin/python"
if [ ! -f "$PYTHON" ]; then
  echo "Error: Python venv not found at backend/.venv"
  echo "Run: cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

if [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo "Error: Frontend dependencies not installed."
  echo "Run: cd frontend && npm install"
  exit 1
fi

echo ""
echo "  Starting Portfolio Manager"
echo "  Backend  → http://localhost:$BACKEND_PORT"
echo "  Frontend → http://localhost:$FRONTEND_PORT"
echo "  API docs → http://localhost:$BACKEND_PORT/docs"
echo "  Press Ctrl+C to stop both."
echo ""

# Trap Ctrl+C and kill both child processes
cleanup() {
  echo ""
  echo "  Stopping..."
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null
  wait "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null
  echo "  Done."
}
trap cleanup INT TERM

# Start backend in background
(cd "$ROOT/backend" && "$PYTHON" -m uvicorn app.main:app --reload --port "$BACKEND_PORT") &
BACKEND_PID=$!

# Give uvicorn a moment to bind the port
sleep 2

# Start frontend in background
(cd "$ROOT/frontend" && npm run dev -- --port "$FRONTEND_PORT") &
FRONTEND_PID=$!

# Wait for either process to exit
wait -n "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || wait "$BACKEND_PID" "$FRONTEND_PID"
cleanup
