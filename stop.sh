#!/usr/bin/env bash
#
# SnapSphere — stop the development servers.
#
#   ./stop.sh          stop Django and Celery
#   ./stop.sh --all    also stop MySQL and Redis
#
# MySQL and Redis are left running by default: they are brew services that
# other projects may also be using, and stopping them is rarely what you want.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$ROOT/.logs"

GREEN=$'\033[0;32m'; YELLOW=$'\033[0;33m'; BOLD=$'\033[1m'; OFF=$'\033[0m'
ok()   { echo "  ${GREEN}✓${OFF} $1"; }
warn() { echo "  ${YELLOW}!${OFF} $1"; }

echo
echo "${BOLD}Stopping SnapSphere${OFF}"
echo

# ─── Django ──────────────────────────────────────────────────────────────────
if [ -f "$LOG_DIR/django.pid" ] && kill -0 "$(cat "$LOG_DIR/django.pid")" 2>/dev/null; then
  kill "$(cat "$LOG_DIR/django.pid")" 2>/dev/null
  rm -f "$LOG_DIR/django.pid"
  ok "Django stopped"
elif pkill -f "manage.py runserver" 2>/dev/null; then
  ok "Django stopped"
else
  warn "Django was not running"
fi

# ─── Celery ──────────────────────────────────────────────────────────────────
if pkill -f "celery -A config" 2>/dev/null; then
  ok "Celery stopped"
else
  warn "Celery was not running"
fi

# ─── Expo ────────────────────────────────────────────────────────────────────
if pkill -f "expo start" 2>/dev/null; then
  ok "Expo bundler stopped"
fi

# ─── Optional: brew services ─────────────────────────────────────────────────
if [[ "${1:-}" == "--all" ]]; then
  brew services stop mysql >/dev/null 2>&1 && ok "MySQL stopped"
  brew services stop redis >/dev/null 2>&1 && ok "Redis stopped"
else
  warn "MySQL and Redis left running (use --all to stop them too)"
fi

echo
