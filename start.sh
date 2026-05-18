#!/usr/bin/env bash
# start.sh — Starts backend (FastAPI) and frontend (Vite) in the same terminal.
# Run from the project root: ./start.sh
set -e

BACKEND_PORT=${BACKEND_PORT:-3001}
FRONTEND_PORT=${FRONTEND_PORT:-5173}
ROOT="$(cd "$(dirname "$0")" && pwd)"

# Detect Windows (Git Bash / MSYS2)
IS_WINDOWS=false
[[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || -n "$WINDIR" ]] && IS_WINDOWS=true

# Kill whatever process is currently listening on a port (cross-platform)
kill_port() {
  local port="$1"
  if $IS_WINDOWS; then
    local pid
    pid=$(netstat -ano 2>/dev/null | awk "/:${port}[[:space:]].*LISTENING/{print \$5}" | head -1)
    [[ -n "$pid" ]] && taskkill //PID "$pid" //F 2>/dev/null || true
  else
    local pid
    pid=$(lsof -ti ":${port}" 2>/dev/null | head -1)
    [[ -n "$pid" ]] && kill -9 "$pid" 2>/dev/null || true
  fi
}

# Support both Unix (.venv/bin/python) and Windows (.venv/Scripts/python.exe)
if [ -f "$ROOT/backend/.venv/Scripts/python.exe" ]; then
  PYTHON="$ROOT/backend/.venv/Scripts/python.exe"
elif [ -f "$ROOT/backend/.venv/bin/python" ]; then
  PYTHON="$ROOT/backend/.venv/bin/python"
else
  echo "Error: Python venv not found at backend/.venv"
  echo "  Windows: cd backend && python -m venv .venv && .venv\\Scripts\\pip install -r requirements.txt"
  echo "  Unix:    cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
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

# Clear any leftover processes from a previous session
kill_port "$BACKEND_PORT"
kill_port "$FRONTEND_PORT"
sleep 1

cleanup() {
  echo ""
  echo "  Stopping..."
  kill_port "$BACKEND_PORT"
  kill_port "$FRONTEND_PORT"
  echo "  Done."
  exit 0
}
trap cleanup INT TERM

# Start backend — no --reload so it runs as a single killable process.
# For hot-reload during development run uvicorn directly with --reload.
(cd "$ROOT/backend" && "$PYTHON" -m uvicorn app.main:app --port "$BACKEND_PORT") &
BACKEND_PID=$!

# Wait for backend to bind its port before starting the frontend
for i in $(seq 1 15); do
  if $IS_WINDOWS; then
    netstat -ano 2>/dev/null | grep -q ":${BACKEND_PORT}.*LISTENING" && break
  else
    nc -z 127.0.0.1 "$BACKEND_PORT" 2>/dev/null && break
  fi
  sleep 1
done

# Start frontend — call vite.js via node directly to avoid npm shell-script
# issues on Windows/WSL
(cd "$ROOT/frontend" && node node_modules/vite/bin/vite.js --port "$FRONTEND_PORT") &
FRONTEND_PID=$!

# Wait for either process to exit, then clean up
wait -n "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || wait "$BACKEND_PID" "$FRONTEND_PID"
cleanup
