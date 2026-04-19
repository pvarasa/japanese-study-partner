#!/bin/bash
# Stop dev servers
cd "$(dirname "$0")"
PID_FILE=".dev-pids.json"
KILLED=0

is_win() {
  case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) return 0 ;; *) return 1 ;; esac
}

# Kill a process and its descendants. taskkill /T is required on Git Bash
# because uvicorn --reload and npm -> node spawn grandchildren that plain
# `kill` won't reach.
kill_tree() {
  local pid=$1
  [ -z "$pid" ] && return
  if is_win; then
    taskkill //F //T //PID "$pid" >/dev/null 2>&1 && KILLED=$((KILLED+1))
  else
    pkill -P "$pid" 2>/dev/null
    kill -9 "$pid" 2>/dev/null && KILLED=$((KILLED+1))
  fi
}

# Read saved PIDs (JSON format matches stop.ps1's .dev-pids.json)
if [ -f "$PID_FILE" ]; then
  for name in backend frontend; do
    pid=$(grep -oE "\"$name\"[[:space:]]*:[[:space:]]*[0-9]+" "$PID_FILE" | grep -oE '[0-9]+$')
    kill_tree "$pid"
  done
  rm -f "$PID_FILE"
fi

# Fallback: kill anything listening on our ports
for port in 8000 5173; do
  if is_win; then
    pids=$(netstat -ano 2>/dev/null | awk -v p=":$port\$" '$1=="TCP" && $2 ~ p && $4=="LISTENING" {print $5}' | sort -u)
  else
    pids=$(lsof -ti tcp:"$port" -sTCP:LISTEN 2>/dev/null)
  fi
  for pid in $pids; do
    kill_tree "$pid"
  done
done

if [ "$KILLED" -gt 0 ]; then
  echo "Stopped dev servers."
else
  echo "No dev servers running."
fi
