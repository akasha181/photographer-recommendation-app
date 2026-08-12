#!/usr/bin/env bash
#
# SnapSphere — start everything needed for development.
#
#   ./start.sh            start MySQL, Redis and the Django API
#   ./start.sh --workers  also start the Celery worker and scheduler
#
# Safe to run repeatedly: it checks what is already running instead of
# starting duplicates.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
PY="$BACKEND/.venv/bin/python"
MYSQL_BIN="/usr/local/opt/mysql/bin"
LOG_DIR="$ROOT/.logs"

GREEN=$'\033[0;32m'; RED=$'\033[0;31m'; YELLOW=$'\033[0;33m'
BLUE=$'\033[0;34m'; BOLD=$'\033[1m'; OFF=$'\033[0m'

ok()   { echo "  ${GREEN}✓${OFF} $1"; }
warn() { echo "  ${YELLOW}!${OFF} $1"; }
fail() { echo "  ${RED}✗${OFF} $1"; }
step() { echo; echo "${BOLD}$1${OFF}"; }

mkdir -p "$LOG_DIR"

echo
echo "${BOLD}${BLUE}SnapSphere${OFF} — starting development environment"

# ─── 1. Prerequisites ────────────────────────────────────────────────────────
step "1. Checking prerequisites"

if [ ! -x "$PY" ]; then
  fail "Python venv missing at $BACKEND/.venv"
  echo "     Run:  cd backend && /usr/local/opt/python@3.12/bin/python3.12 -m venv .venv"
  exit 1
fi
ok "python $("$PY" --version 2>&1 | cut -d' ' -f2)"

if [ ! -f "$BACKEND/.env" ]; then
  warn ".env missing — copying from .env.example"
  cp "$BACKEND/.env.example" "$BACKEND/.env"
fi
ok ".env present"

# ─── 2. MySQL ────────────────────────────────────────────────────────────────
step "2. MySQL"

if "$MYSQL_BIN/mysqladmin" ping >/dev/null 2>&1; then
  ok "already running"
else
  warn "not running — starting"
  brew services start mysql >/dev/null 2>&1
  until "$MYSQL_BIN/mysqladmin" ping >/dev/null 2>&1; do sleep 1; done
  ok "started"
fi

TABLES=$("$MYSQL_BIN/mysql" -u snapsphere -psnapsphere snapsphere -N -s \
  -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='snapsphere';" 2>/dev/null)
if [ -z "${TABLES:-}" ]; then
  fail "cannot connect to the 'snapsphere' database"
  echo "     Create it:  mysql -u root -e \"CREATE DATABASE snapsphere CHARACTER SET utf8mb4;\""
  exit 1
fi
ok "database reachable — $TABLES tables"

USERS=$("$MYSQL_BIN/mysql" -u snapsphere -psnapsphere snapsphere -N -s \
  -e "SELECT COUNT(*) FROM users;" 2>/dev/null || echo 0)
if [ "${USERS:-0}" -lt 10 ]; then
  warn "database looks empty ($USERS users) — run:  cd backend && .venv/bin/python manage.py seed_data --flush"
else
  ok "seeded — $USERS users"
fi

# ─── 3. Redis ────────────────────────────────────────────────────────────────
step "3. Redis"

if redis-cli ping >/dev/null 2>&1; then
  ok "already running"
else
  warn "not running — starting"
  brew services start redis >/dev/null 2>&1
  until redis-cli ping >/dev/null 2>&1; do sleep 1; done
  ok "started"
fi

# ─── 4. Django API ───────────────────────────────────────────────────────────
step "4. Django API"

if curl -s -m 3 -o /dev/null http://127.0.0.1:8000/health/ 2>/dev/null; then
  ok "already running on :8000"
else
  warn "not running — starting on :8000"
  cd "$BACKEND"
  nohup "$PY" manage.py runserver 0.0.0.0:8000 > "$LOG_DIR/django.log" 2>&1 &
  echo $! > "$LOG_DIR/django.pid"
  until curl -s -m 2 -o /dev/null http://127.0.0.1:8000/health/ 2>/dev/null; do sleep 1; done
  ok "started (pid $(cat "$LOG_DIR/django.pid"), log: .logs/django.log)"
fi

HEALTH=$(curl -s http://127.0.0.1:8000/health/)
echo "$HEALTH" | grep -q '"status": "healthy"' \
  && ok "health check: database ok, cache ok" \
  || fail "health check reported a problem: $HEALTH"

# ─── 5. Celery (optional) ────────────────────────────────────────────────────
if [[ "${1:-}" == "--workers" ]]; then
  step "5. Celery"
  cd "$BACKEND"

  if pgrep -f "celery -A config worker" >/dev/null; then
    ok "worker already running"
  else
    nohup "$BACKEND/.venv/bin/celery" -A config worker -l info \
      > "$LOG_DIR/celery-worker.log" 2>&1 &
    ok "worker started (log: .logs/celery-worker.log)"
  fi

  if pgrep -f "celery -A config beat" >/dev/null; then
    ok "scheduler already running"
  else
    nohup "$BACKEND/.venv/bin/celery" -A config beat -l info \
      > "$LOG_DIR/celery-beat.log" 2>&1 &
    ok "scheduler started (log: .logs/celery-beat.log)"
  fi
fi

# ─── Ready ───────────────────────────────────────────────────────────────────
LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "127.0.0.1")

echo
echo "${BOLD}${GREEN}Ready.${OFF}"
echo
echo "  API docs (Swagger)   http://127.0.0.1:8000/api/v1/docs/"
echo "  Django admin         http://127.0.0.1:8000/django-admin/"
echo "  Health               http://127.0.0.1:8000/health/"
echo "  From your phone      http://$LAN_IP:8000/api/v1/"
echo
echo "  Test the API         ./test.sh"
echo "  Start the app        cd mobile && npx expo start"
echo "  Stop everything      ./stop.sh"
echo
