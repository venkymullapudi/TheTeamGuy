#!/usr/bin/env bash
# Live smoke test: a brand-new guy, the real Claude brain, a throwaway folder.
#
#   scripts/live_smoke.sh            onboard → work → standup --join, then clean up
#   KEEP=1 scripts/live_smoke.sh     keep the temp folder for a look around
#   TEAMGUY_BIN=/path/to/teamguy     use a specific teamguy (default: .venv, then PATH)
#
# Exits 0 and prints "skipped" when there's nothing to talk to: no Anthropic
# SDK, or no ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN in the environment (an
# OAuth token, sk-ant-oat…, doesn't count: it's for Claude Code, not the API).
# Set TEAMGUY_SMOKE_FORCE=1 to run anyway, e.g. with `ant auth login` creds.
# This spends a few real tokens. The pytest suite never runs it live.
set -uo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
bin="${TEAMGUY_BIN:-}"
if [ -z "$bin" ]; then
  if [ -x "$here/.venv/bin/teamguy" ]; then bin="$here/.venv/bin/teamguy"
  else bin="$(command -v teamguy || true)"; fi
fi

skip() { echo "⏭️  skipped: $1"; exit 0; }

[ -n "$bin" ] && [ -x "$bin" ] || skip "no teamguy found (pip install -e '.[claude]' first)"
py="$(dirname "$bin")/python"
[ -x "$py" ] || py="$(command -v python3 || true)"
[ -n "$py" ] && "$py" -c "import anthropic" 2>/dev/null || skip "the Anthropic SDK isn't installed (pip install 'teamguy[claude]')"

if [ "${TEAMGUY_SMOKE_FORCE:-}" != "1" ]; then
  key="${ANTHROPIC_API_KEY:-}"
  case "$key" in sk-ant-oat*) key="" ;; esac
  [ -n "$key" ] || [ -n "${ANTHROPIC_AUTH_TOKEN:-}" ] \
    || skip "no Claude credentials in the environment (set ANTHROPIC_API_KEY, or TEAMGUY_SMOKE_FORCE=1)"
fi

dir="$(mktemp -d "${TMPDIR:-/tmp}/teamguy-smoke.XXXXXX")"
if [ "${KEEP:-}" = "1" ]; then echo "📁 Keeping $dir"
else trap 'rm -rf "$dir"' EXIT; fi
cd "$dir" || exit 1
unset TEAMGUY_BRAIN

fails=0
step() {
  local name="$1"; shift
  echo "── $name"
  if "$@"; then echo "✅ $name"; else echo "❌ $name (exit $?)"; fails=$((fails + 1)); fi
}

"$bin" init SMOKE >/dev/null || { echo "❌ init failed"; exit 1; }
step "onboard" "$bin" --brain claude onboard
step "work" "$bin" --brain claude work --effort 1 "Write a two-line haiku about flaky tests."
printf 'Ada: fixed the login bug, reviewing PRs today\nLin: blocked on the staging deploy, could use a hand\n' > updates.txt
step "standup" "$bin" --brain claude standup --join --updates updates.txt

if [ "$fails" -eq 0 ]; then
  echo "🎉 Smoke test passed. TheSMOKEGuy survived contact with reality."
else
  echo "🔥 $fails step(s) failed. TheSMOKEGuy needs a minute."
  exit 1
fi
