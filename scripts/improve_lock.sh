#!/usr/bin/env bash
# One improvement run at a time, across every Claude session anywhere:
# cloud routines and local sessions all take the same lock on GitHub.
#
#   scripts/improve_lock.sh acquire <owner>   exit 0 = got it, 1 = busy, 3 = can't push
#   scripts/improve_lock.sh release <owner>
#   scripts/improve_lock.sh status
#
# The lock is the branch `teamguy-loop-lock` on origin, pointing at a one-off
# orphan commit. Creating it is atomic: if another run holds it, our push is
# rejected (our orphan commit is never a fast-forward of theirs). A lock older
# than STALE_MINUTES (default 180) is treated as abandoned and taken over.
set -euo pipefail

ref="teamguy-loop-lock"
stale_minutes="${STALE_MINUTES:-180}"
cmd="${1:-status}"
owner="${2:-unknown}"

remote_sha() { git ls-remote origin "refs/heads/$ref" 2>/dev/null | cut -f1 || true; }

holder() {  # prints "<owner> since <iso time>" for the current lock commit
  local sha="$1"
  git fetch -q origin "refs/heads/$ref" 2>/dev/null || true
  git log -1 --format='%s since %cI' "$sha" 2>/dev/null | sed 's/^lock: //' || echo "?"
}

age_minutes() {
  local sha="$1" then now
  git fetch -q origin "refs/heads/$ref" 2>/dev/null || true
  then="$(git log -1 --format=%ct "$sha" 2>/dev/null || echo 0)"
  now="$(date +%s)"
  echo $(( (now - then) / 60 ))
}

case "$cmd" in
  acquire)
    tree="$(git hash-object -t tree /dev/null)"
    commit="$(git commit-tree "$tree" -m "lock: $owner")"
    if push_err="$(git push -q origin "$commit:refs/heads/$ref" 2>&1)"; then
      echo "acquired by $owner"
      exit 0
    fi
    sha="$(remote_sha)"
    if [ -z "$sha" ]; then  # nobody holds it, so the push failed for another reason
      echo "error: couldn't push the lock branch (no push access?):" >&2
      echo "$push_err" | sed 's/^/  /' >&2
      exit 3
    fi
    if [ -n "$sha" ] && [ "$(age_minutes "$sha")" -ge "$stale_minutes" ]; then
      echo "stale lock ($(holder "$sha")), taking over"
      git push -q origin --force-with-lease="refs/heads/$ref:$sha" "$commit:refs/heads/$ref" && {
        echo "acquired by $owner"; exit 0; }
    fi
    echo "busy: $( [ -n "$sha" ] && holder "$sha" || echo '?')"
    exit 1
    ;;
  release)
    sha="$(remote_sha)"
    if [ -z "$sha" ]; then
      echo "free already"
    elif [ "$(holder "$sha" | cut -d' ' -f1)" = "$owner" ]; then
      git push -q origin --force-with-lease="refs/heads/$ref:$sha" --delete "$ref"
      echo "released by $owner"
    else
      echo "not held by $owner (holder: $(holder "$sha")); leaving it"
    fi
    ;;
  status)
    sha="$(remote_sha)"
    [ -n "$sha" ] && echo "held: $(holder "$sha")" || echo "free"
    ;;
  *)
    echo "usage: $0 acquire|release <owner> | status" >&2
    exit 2
    ;;
esac
