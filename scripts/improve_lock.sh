#!/usr/bin/env bash
# One improvement run at a time, across every Claude session on this machine.
#
#   scripts/improve_lock.sh acquire <owner>   exit 0 = got it, exit 1 = busy
#   scripts/improve_lock.sh release <owner>
#   scripts/improve_lock.sh status
#
# The lock is a directory in .git/ (mkdir is atomic; nothing gets committed).
# A lock older than STALE_MINUTES (default 180) is treated as abandoned.
set -euo pipefail

root="$(git rev-parse --show-toplevel)"
lock="$root/.git/teamguy-improve.lock"
stale_minutes="${STALE_MINUTES:-180}"
cmd="${1:-status}"
owner="${2:-unknown}"

info() { [ -f "$lock/owner" ] && cat "$lock/owner" || echo "?"; }

case "$cmd" in
  acquire)
    if mkdir "$lock" 2>/dev/null; then
      printf '%s since %s\n' "$owner" "$(date '+%Y-%m-%d %H:%M:%S')" > "$lock/owner"
      echo "acquired by $owner"
      exit 0
    fi
    if [ -n "$(find "$lock" -maxdepth 0 -mmin +"$stale_minutes" 2>/dev/null)" ]; then
      echo "stale lock ($(info)), taking over"
      rm -rf "$lock"
      exec "$0" acquire "$owner"
    fi
    echo "busy: $(info)"
    exit 1
    ;;
  release)
    if [ -d "$lock" ] && grep -q "^$owner since" "$lock/owner" 2>/dev/null; then
      rm -rf "$lock"
      echo "released by $owner"
    else
      echo "not held by $owner (holder: $(info)); leaving it"
    fi
    ;;
  status)
    [ -d "$lock" ] && echo "held: $(info)" || echo "free"
    ;;
  *)
    echo "usage: $0 acquire|release <owner> | status" >&2
    exit 2
    ;;
esac
