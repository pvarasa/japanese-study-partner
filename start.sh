#!/bin/bash
# Start both backend and frontend for development

cd "$(dirname "$0")"

# Find uv on PATH or common install location
if ! command -v uv &>/dev/null; then
  export PATH="$HOME/.local/bin:$PATH"
fi
if ! command -v uv &>/dev/null; then
  echo "Error: uv not found. Install from https://docs.astral.sh/uv/"
  exit 1
fi

# Kill any existing processes on our ports
bash ./stop.sh 2>/dev/null

echo ""
echo "Starting backend on :8000 ..."
(cd backend && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000) &
PID1=$!

echo "Starting frontend on :5173 ..."
(cd frontend && npm run dev -- --host 0.0.0.0) &
PID2=$!

# Save PIDs for stop script
cat > .dev-pids.json <<EOF
{
  "backend": $PID1,
  "frontend": $PID2
}
EOF

echo ""
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:5173"
echo ""
echo "  Press Ctrl+C to stop both servers"
echo ""

cleanup() {
  echo ""
  echo "Stopping servers..."
  # On Windows (Git Bash / MSYS), `kill` often doesn't reach grandchildren
  # (uvicorn --reload worker, npm -> node under cmd.exe). Use taskkill to
  # terminate the whole process tree. Fall back to pkill -P + kill elsewhere.
  case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*)
      for PID in $PID1 $PID2; do
        [ -n "$PID" ] && taskkill //F //T //PID "$PID" >/dev/null 2>&1
      done
      ;;
    *)
      for PID in $PID1 $PID2; do
        [ -n "$PID" ] && pkill -P "$PID" 2>/dev/null
        [ -n "$PID" ] && kill -9 "$PID" 2>/dev/null
      done
      ;;
  esac
  rm -f .dev-pids.json
}
trap cleanup EXIT INT TERM
wait
