#!/usr/bin/env bash
# lock.sh - path locks for parallel ut executors.
#
# A lock protects ONE canonical absolute path (file, dir, executable, script...).
# Locking a directory also blocks locks on anything inside it, and a lock on
# a file blocks locking any of its parent directories (hierarchical conflict).
# Several paths requested in one call are taken ALL-OR-NOTHING (no deadlocks).
#
# Usage (LOCK_DIR is normally <task folder>/locks):
#   lock.sh LOCK_DIR acquire     OWNER PATH...      # exit 0 = got all, 1 = none taken (conflicts printed)
#   lock.sh LOCK_DIR wait        OWNER SECONDS PATH...  # retry acquire until timeout (exit 1 on timeout)
#   lock.sh LOCK_DIR release     OWNER PATH...      # release own locks on these paths
#   lock.sh LOCK_DIR release-all OWNER              # release every lock held by OWNER
#   lock.sh LOCK_DIR check       PATH...            # print holder of each path or conflicting lock (exit 1 if any locked)
#   lock.sh LOCK_DIR list                           # print all locks: owner, age, path
#   lock.sh LOCK_DIR break       PATH...            # FORCE remove locks (only with user approval)
#
# OWNER: short id without spaces, e.g. E1, E2 (executor id from status.md).
# Paths may be relative (to the current dir) and need not exist yet.
# Every action is appended to LOCK_DIR/lock.log.

set -u

die() { echo "lock.sh: $*" >&2; exit 2; }

[ $# -ge 2 ] || { sed -n '2,22p' "$0"; exit 2; }
LOCK_DIR=$1; CMD=$2; shift 2
mkdir -p "$LOCK_DIR/held" || die "cannot create $LOCK_DIR"
LOCK_DIR=$(cd "$LOCK_DIR" && pwd -P)
HELD="$LOCK_DIR/held"
MUTEX="$LOCK_DIR/.mutex"
LOG="$LOCK_DIR/lock.log"
MUTEX_STALE_SECS=60

now() { date +%s; }
stamp() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "$(stamp) $*" >> "$LOG"; }

# canonical absolute path, works for paths that do not exist yet
canon() {
  local p=$1 out
  if out=$(realpath -m -- "$p" 2>/dev/null); then printf '%s' "$out"; return; fi
  case $p in /*) ;; *) p="$PWD/$p" ;; esac
  # manual normalisation: resolve the longest existing parent, keep the rest
  local head=$p tail=""
  while [ ! -d "$head" ]; do tail="/$(basename "$head")$tail"; head=$(dirname "$head"); done
  head=$(cd "$head" && pwd -P)
  out="$head$tail"
  # collapse // and /./
  while :; do case $out in *//*) out=${out//\/\//\/} ;; */./*) out=${out//\/.\//\/} ;; *) break ;; esac; done
  printf '%s' "${out%/}"
}

key_of() {
  local s=$1
  if command -v sha1sum >/dev/null 2>&1; then printf '%s' "$s" | sha1sum | cut -c1-40
  elif command -v shasum >/dev/null 2>&1; then printf '%s' "$s" | shasum | cut -c1-40
  else printf '%s' "$s" | cksum | tr ' ' '_'; fi
}

mutex_lock() {
  local tries=0
  until mkdir "$MUTEX" 2>/dev/null; do
    if [ -d "$MUTEX" ]; then
      local born; born=$(cat "$MUTEX/t" 2>/dev/null)
      # only a mutex with a valid, old timestamp is stale (empty = being created right now)
      case $born in ''|*[!0-9]*) born="" ;; esac
      if [ -n "$born" ] && [ $(( $(now) - born )) -gt $MUTEX_STALE_SECS ]; then
        rm -rf "$MUTEX"; log "WARN stale mutex removed"; continue
      fi
    fi
    tries=$((tries+1)); [ $tries -gt 600 ] && die "mutex busy for too long ($MUTEX)"
    sleep 0.1 2>/dev/null || sleep 1
  done
  now > "$MUTEX/t"
}
mutex_unlock() { rm -rf "$MUTEX"; }

# lock file format: line1 path, line2 owner, line3 epoch
rd_path()  { sed -n 1p "$1"; }
rd_owner() { sed -n 2p "$1"; }
rd_time()  { sed -n 3p "$1"; }

# is a an ancestor-or-equal of b ?
covers() { [ "$1" = "$2" ] || case $2 in "$1"/*) return 0 ;; *) return 1 ;; esac; }

# print conflicts for canonical path $1 against locks not owned by $2 ("" = anyone)
conflicts_for() {
  local p=$1 me=$2 f lp lo found=1
  for f in "$HELD"/*; do
    [ -f "$f" ] || continue
    lp=$(rd_path "$f"); lo=$(rd_owner "$f")
    [ -n "$me" ] && [ "$lo" = "$me" ] && continue
    if covers "$lp" "$p" || covers "$p" "$lp"; then
      echo "CONFLICT: $p  <- held by $lo on $lp (since $(date -d @"$(rd_time "$f")" '+%H:%M:%S' 2>/dev/null || rd_time "$f"))"
      found=0
    fi
  done
  return $found
}

do_acquire() {
  local owner=$1; shift
  [ $# -ge 1 ] || die "acquire: no paths"
  local p c paths=() bad=0
  for p in "$@"; do c=$(canon "$p"); [ "$c" = "/" ] && die "refusing to lock /"; paths+=("$c"); done
  mutex_lock
  for c in "${paths[@]}"; do conflicts_for "$c" "$owner" && bad=1; done
  if [ $bad = 1 ]; then mutex_unlock; log "DENY $owner ${paths[*]}"; return 1; fi
  for c in "${paths[@]}"; do printf '%s\n%s\n%s\n' "$c" "$owner" "$(now)" > "$HELD/$(key_of "$c")"; done
  mutex_unlock
  for c in "${paths[@]}"; do echo "LOCKED: $c by $owner"; done
  log "LOCK $owner ${paths[*]}"
  return 0
}

do_release() {
  local owner=$1; shift
  local p c f rc=0
  mutex_lock
  for p in "$@"; do
    c=$(canon "$p"); f="$HELD/$(key_of "$c")"
    if [ -f "$f" ] && [ "$(rd_owner "$f")" = "$owner" ]; then rm -f "$f"; echo "RELEASED: $c"; log "UNLOCK $owner $c"
    elif [ -f "$f" ]; then echo "NOT OWNER: $c is held by $(rd_owner "$f")"; rc=1
    else echo "NOT LOCKED: $c"; fi
  done
  mutex_unlock
  return $rc
}

do_release_all() {
  local owner=$1 f n=0
  mutex_lock
  for f in "$HELD"/*; do
    [ -f "$f" ] || continue
    if [ "$(rd_owner "$f")" = "$owner" ]; then echo "RELEASED: $(rd_path "$f")"; rm -f "$f"; n=$((n+1)); fi
  done
  mutex_unlock
  log "UNLOCK-ALL $owner ($n)"; echo "released $n lock(s) of $owner"
}

do_check() {
  local p c any=0
  for p in "$@"; do
    c=$(canon "$p")
    if conflicts_for "$c" ""; then any=1; else echo "FREE: $c"; fi
  done
  [ $any = 0 ]
}

do_list() {
  local f n=0 t
  for f in "$HELD"/*; do
    [ -f "$f" ] || continue
    t=$(rd_time "$f"); printf '%-8s %6ss  %s\n' "$(rd_owner "$f")" "$(( $(now) - t ))" "$(rd_path "$f")"; n=$((n+1))
  done
  [ $n = 0 ] && echo "(no locks)"
  return 0
}

do_break() {
  local p c f
  mutex_lock
  for p in "$@"; do
    c=$(canon "$p"); f="$HELD/$(key_of "$c")"
    if [ -f "$f" ]; then log "BREAK $(rd_owner "$f") $c"; rm -f "$f"; echo "BROKEN: $c"; else echo "NOT LOCKED: $c"; fi
  done
  mutex_unlock
}

case $CMD in
  acquire)     [ $# -ge 2 ] || die "usage: acquire OWNER PATH..."; do_acquire "$@" ;;
  wait)        [ $# -ge 3 ] || die "usage: wait OWNER SECONDS PATH..."
               owner=$1 secs=$2; shift 2; end=$(( $(now) + secs ))
               while :; do
                 out=$(do_acquire "$owner" "$@") && { echo "$out"; exit 0; }
                 [ "$(now)" -ge "$end" ] && { echo "$out"; echo "TIMEOUT after ${secs}s"; exit 1; }
                 sleep 5
               done ;;
  release)     [ $# -ge 2 ] || die "usage: release OWNER PATH..."; do_release "$@" ;;
  release-all) [ $# -eq 1 ] || die "usage: release-all OWNER"; do_release_all "$1" ;;
  check)       [ $# -ge 1 ] || die "usage: check PATH..."; do_check "$@" ;;
  list)        do_list ;;
  break)       [ $# -ge 1 ] || die "usage: break PATH..."; do_break "$@" ;;
  *)           die "unknown command '$CMD' (acquire|wait|release|release-all|check|list|break)" ;;
esac
