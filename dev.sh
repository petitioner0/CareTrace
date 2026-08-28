#!/usr/bin/env bash

set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
BACKEND_PYTHON="$BACKEND_DIR/.venv/bin/python"
BACKEND_PORT="${CARETRACE_BACKEND_PORT:-8000}"
FRONTEND_PORT="${CARETRACE_FRONTEND_PORT:-5173}"

if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
fi

if [[ ! -x "$BACKEND_PYTHON" ]]; then
  echo "Backend environment is missing. Run the backend setup steps in README.md first." >&2
  exit 1
fi

if ! command -v pnpm >/dev/null 2>&1; then
  echo "pnpm is required but was not found in PATH." >&2
  exit 1
fi

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  echo "Frontend dependencies are missing. Run 'pnpm --dir frontend install' first." >&2
  exit 1
fi

backend_pid=""
frontend_pid=""

cleanup() {
  trap - EXIT INT TERM
  [[ -n "$frontend_pid" ]] && kill "$frontend_pid" 2>/dev/null || true
  [[ -n "$backend_pid" ]] && kill "$backend_pid" 2>/dev/null || true
  [[ -n "$frontend_pid" ]] && wait "$frontend_pid" 2>/dev/null || true
  [[ -n "$backend_pid" ]] && wait "$backend_pid" 2>/dev/null || true
}

handle_signal() {
  exit 130
}

trap cleanup EXIT
trap handle_signal INT TERM

echo "Starting CareTrace"
echo "  App: http://127.0.0.1:$FRONTEND_PORT"
echo "  API: http://127.0.0.1:$BACKEND_PORT"
echo "  Docs: http://127.0.0.1:$BACKEND_PORT/docs"
echo "Press Ctrl+C to stop both services."

(
  cd "$BACKEND_DIR"
  exec "$BACKEND_PYTHON" -m uvicorn app.main:app --reload --host 127.0.0.1 --port "$BACKEND_PORT"
) &
backend_pid=$!

(
  cd "$FRONTEND_DIR"
  export VITE_API_URL="${VITE_API_URL:-http://127.0.0.1:$BACKEND_PORT/api}"
  exec pnpm dev -- --port "$FRONTEND_PORT"
) &
frontend_pid=$!

exit_status=0
while true; do
  if ! kill -0 "$backend_pid" 2>/dev/null; then
    wait "$backend_pid" || exit_status=$?
    echo "Backend stopped; shutting down CareTrace." >&2
    break
  fi
  if ! kill -0 "$frontend_pid" 2>/dev/null; then
    wait "$frontend_pid" || exit_status=$?
    echo "Frontend stopped; shutting down CareTrace." >&2
    break
  fi
  sleep 1
done

exit "$exit_status"
