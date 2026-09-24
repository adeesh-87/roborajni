#!/usr/bin/env bash
# lock.sh - path locks for parallel ut executors, with heartbeats and stale detection.
#
# A lock protects ONE canonical absolute path (file, dir, executable, script, or a name that
# does not exist yet). Locking a directory also blocks everything inside it, and a lock on a
# file blocks locking its parent directories. Paths in one call are taken ALL-OR-NOTHING.
# Locks are files on disk: they survive sessions, reboots and crashed agents.
#
# Every command that names an OWNER is also a heartbeat for that owner. An owner is STALE when
# it has not been seen for STALE_AFTER seconds (default 1800) and is not inside a declared busy
# window. Stale owners are reported on every call; they are never removed automatically.
#
# Usage (LOCK_DIR is normally <task folder>/locks):
#   lock.sh LOCK_DIR acquire     OWNER PATH...          exit 0 got all | 1 held by active owner | 3 held only by STALE owners
#   lock.sh LOCK_DIR wait        OWNER SECONDS PATH...  retry acquire until timeout (same exit codes)
#   lock.sh LOCK_DIR release     OWNER PATH...
#   lock.sh LOCK_DIR release-all OWNER
#   lock.sh LOCK_DIR alive       OWNER [BUSY_SECONDS [NOTE...]]   heartbeat; optionally "busy up to N s, doing NOTE"
#   lock.sh LOCK_DIR check       PATH...                exit 1 if any path is locked
#   lock.sh LOCK_DIR list                               locks: owner, state, age, path
#   lock.sh LOCK_DIR status                             owners (ACTIVE/BUSY/STALE), locks, recent log
#   lock.sh LOCK_DIR watch       [INTERVAL_SECONDS]     refresh status until Ctrl-C (for a human terminal)
#   lock.sh LOCK_DIR reap        OWNER [--force]        remove all locks of a STALE owner (user approval!)
#   lock.sh LOCK_DIR break       PATH...                force-remove single locks (user approval!)
#
# OWNER: short id without spaces, e.g. E1. STALE_AFTER: env UT_LOCK_STALE_AFTER, or a line
# "stale_after=SECONDS" in LOCK_DIR/config. All actions are logged in LOCK_DIR/lock.log.

set -u

die() { echo "lock.sh: $*" >&2; exit 2; }

[ $# -ge 2 ] || { sed -n '2,31p' "$0"; exit 2; }
LOCK_DIR=$1; CMD=$2; shift 2
mkdir -p "$LOCK_DIR/held" "$LOCK_DIR/owners" || die "cannot create $LOCK_DIR"
LOCK_DIR=$(cd "$LOCK_DIR" && pwd -P)
HELD="$LOCK_DIR/held"
OWNERS="$LOCK_DIR/owners"
MUTEX="$LOCK_DIR/.mutex"
LOG="$LOCK_DIR/lock.log"
MUTEX_STALE_SECS=60

STALE_AFTER=${UT_LOCK_STALE_AFTER:-}
if [ -z "$STALE_AFTER" ] && [ -f "$LOCK_DIR/config" ]; then
  STALE_AFTER=$(sed -n 's/^stale_after=\([0-9][0-9]*\).*/\1/p' "$LOCK_DIR/config" | head -1)
fi
case ${STALE_AFTER:-} in ''|*[!0-9]*) STALE_AFTER=1800 ;; esac

now() { date +%s; }
stamp() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "$(stamp) $*" >> "$LOG"; }
host() { hostname 2>/dev/null || uname -n; }

age() {   # seconds -> 45s | 12m | 2h13m | 3d4h
  local s=$1
  if   [ "$s" -lt 60 ];    then echo "${s}s"
  elif [ "$s" -lt 3600 ];  then echo "$((s/60))m"
  elif [ "$s" -lt 86400 ]; then echo "$((s/3600))h$(( (s%3600)/60 ))m"
  else echo "$((s/86400))d$(( (s%86400)/3600 ))h"; fi
}

canon() {   # canonical absolute path, also for paths that do not exist yet
  local p=$1 out
  if out=$(realpath -m -- "$p" 2>/dev/null); then printf '%s' "$out"; return; fi
  case $p in /*) ;; *) p="$PWD/$p" ;; esac
  local head=$p tail=""
  while [ ! -d "$head" ]; do tail="/$(basename "$head")$tail"; head=$(dirname "$head"); done
  head=$(cd "$head" && pwd -P)
  out="$head$tail"
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
  local tries=0 born
  until mkdir "$MUTEX" 2>/dev/null; do
    born=$(cat "$MUTEX/t" 2>/dev/null)
    case $born in ''|*[!0-9]*) born="" ;; esac     # empty = being created right now, not stale
    if [ -n "$born" ] && [ $(( $(now) - born )) -gt $MUTEX_STALE_SECS ]; then
      rm -rf "$MUTEX"; log "WARN stale mutex removed"; continue
    fi
    tries=$((tries+1)); [ $tries -gt 600 ] && die "mutex busy for too long ($MUTEX)"
    sleep 0.1 2>/dev/null || sleep 1
  done
  now > "$MUTEX/t"
}
mutex_unlock() { rm -rf "$MUTEX"; }

# ---- lock files: line1 path, line2 owner, line3 epoch acquired, line4 host
rd_path()  { sed -n 1p "$1"; }
rd_owner() { sed -n 2p "$1"; }

# Snapshot of all locks, read in ONE pass: arrays LP (path), LO (owner), LT (time).
load_locks() {
  LP=(); LO=(); LT=(); STATE_CACHE=" "
  local p o t
  set -- "$HELD"/*
  [ -f "$1" ] || return 0
  while IFS="$(printf '\t')" read -r p o t; do LP+=("$p"); LO+=("$o"); LT+=("$t"); done < <(
    awk 'FNR==1{p=$0} FNR==2{o=$0} FNR==3{printf "%s\t%s\t%s\n", p, o, $0}' "$@")
}

# ---- owner files: key=value lines last_seen, busy_until, host, note
ofield() { sed -n "s/^$2=//p" "$OWNERS/$1" 2>/dev/null | head -1; }

heartbeat() {   # heartbeat OWNER [BUSY_SECONDS [NOTE]]
  local o=$1 busy=${2:-} note=${3:-} t; t=$(now)
  local bu; bu=$(ofield "$o" busy_until); case ${bu:-} in ''|*[!0-9]*) bu=0 ;; esac
  [ -z "$note" ] && note=$(ofield "$o" note)
  if [ -n "$busy" ]; then bu=$(( t + busy )); fi
  printf 'last_seen=%s\nbusy_until=%s\nhost=%s\nnote=%s\n' "$t" "$bu" "$(host)" "$note" > "$OWNERS/$o.tmp.$$" \
    && mv -f "$OWNERS/$o.tmp.$$" "$OWNERS/$o"
}

last_seen_of() {   # owner file, or newest lock of that owner (needs load_locks)
  local o=$1 ls i; ls=$(ofield "$o" last_seen)
  case ${ls:-} in ''|*[!0-9]*) ls=0 ;; esac
  for i in "${!LO[@]}"; do [ "${LO[$i]}" = "$o" ] && [ "${LT[$i]}" -gt "$ls" ] 2>/dev/null && ls=${LT[$i]}; done
  echo "$ls"
}

state_of() {   # ACTIVE | BUSY | STALE (cached per call)
  local o=$1 hit t ls bu st
  hit=${STATE_CACHE#* $o=}; if [ "$hit" != "$STATE_CACHE" ]; then echo "${hit%% *}"; return; fi
  t=$(now); ls=$(last_seen_of "$o")
  bu=$(ofield "$o" busy_until); case ${bu:-} in ''|*[!0-9]*) bu=0 ;; esac
  if [ $(( t - ls )) -le "$STALE_AFTER" ]; then st=ACTIVE
  elif [ "$t" -le "$bu" ]; then st=BUSY
  else st=STALE; fi
  STATE_CACHE="$STATE_CACHE$o=$st "
  echo "$st"
}

count_of() { local o=$1 i n=0; for i in "${!LO[@]}"; do [ "${LO[$i]}" = "$o" ] && n=$((n+1)); done; echo "$n"; }

covers() { [ "$1" = "$2" ] || case $2 in "$1"/*) return 0 ;; *) return 1 ;; esac; }

# conflicts_for PATH ME: prints conflicts; adds to N_ACTIVE / N_STALE; returns 0 if any conflict
N_ACTIVE=0; N_STALE=0
conflicts_for() {
  local p=$1 me=$2 i lp lo st found=1
  for i in "${!LP[@]}"; do
    lp=${LP[$i]}; lo=${LO[$i]}
    [ -n "$me" ] && [ "$lo" = "$me" ] && continue
    if covers "$lp" "$p" || covers "$p" "$lp"; then
      st=$(state_of "$lo"); STATE_CACHE="$STATE_CACHE$lo=$st "
      if [ "$st" = STALE ]; then N_STALE=$((N_STALE+1)); else N_ACTIVE=$((N_ACTIVE+1)); fi
      echo "CONFLICT: $p  <- held by $lo [$st, last seen $(age $(( $(now) - $(last_seen_of "$lo") ))) ago] on $lp (locked $(age $(( $(now) - ${LT[$i]} ))) ago)"
      found=0
    fi
  done
  return $found
}

stale_warning() {   # one line per stale owner that still holds locks (except $1)
  local me=${1:-} i o seen=" " st
  load_locks
  for i in "${!LO[@]}"; do
    o=${LO[$i]}; [ "$o" = "$me" ] && continue
    case $seen in *" $o "*) continue ;; esac; seen="$seen$o "
    st=$(state_of "$o")
    if [ "$st" = STALE ]; then
      echo "STALE-WARNING: owner $o last seen $(age $(( $(now) - $(last_seen_of "$o") ))) ago still holds $(count_of "$o") lock(s). Tell the user; only with approval run: lock.sh $LOCK_DIR reap $o"
    fi
  done
}

do_acquire() {   # sets ACQ_RC 0/1/3
  local owner=$1; shift
  local p c paths=() bad=0
  for p in "$@"; do c=$(canon "$p"); [ "$c" = "/" ] && die "refusing to lock /"; paths+=("$c"); done
  N_ACTIVE=0; N_STALE=0
  mutex_lock
  load_locks
  for c in "${paths[@]}"; do conflicts_for "$c" "$owner" && bad=1; done
  if [ $bad = 1 ]; then
    mutex_unlock; log "DENY $owner ${paths[*]}"
    if [ $N_ACTIVE -eq 0 ]; then ACQ_RC=3; else ACQ_RC=1; fi
    return
  fi
  for c in "${paths[@]}"; do printf '%s\n%s\n%s\n%s\n' "$c" "$owner" "$(now)" "$(host)" > "$HELD/$(key_of "$c")"; done
  mutex_unlock
  for c in "${paths[@]}"; do echo "LOCKED: $c by $owner"; done
  log "LOCK $owner ${paths[*]}"
  ACQ_RC=0
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

remove_all_of() {   # remove_all_of OWNER VERB
  local owner=$1 verb=$2 f n=0
  mutex_lock
  for f in "$HELD"/*; do
    [ -f "$f" ] || continue
    if [ "$(rd_owner "$f")" = "$owner" ]; then echo "$verb: $(rd_path "$f")"; rm -f "$f"; n=$((n+1)); fi
  done
  mutex_unlock
  echo "$n lock(s) of $owner removed"
  log "$verb-ALL $owner ($n)"
}

do_list() {
  local i n=0 o
  load_locks
  for i in "${!LP[@]}"; do
    o=${LO[$i]}
    printf '%-8s %-6s locked %-7s ago  %s\n' "$o" "$(state_of "$o")" "$(age $(( $(now) - ${LT[$i]} )))" "${LP[$i]}"; n=$((n+1))
  done
  [ $n = 0 ] && echo "(no locks)"
  return 0
}

do_status() {
  local f o t n st bu note owners=" "
  echo "== ut locks: $LOCK_DIR   ($(stamp), stale after $(age "$STALE_AFTER") without heartbeat)"
  load_locks
  for f in "$OWNERS"/*; do
    [ -f "$f" ] || continue
    case $f in *.tmp.*) continue ;; esac
    o=$(basename "$f"); case $owners in *" $o "*) ;; *) owners="$owners$o " ;; esac
  done
  for o in "${LO[@]}"; do case $owners in *" $o "*) ;; *) owners="$owners$o " ;; esac; done
  printf '%-8s %-6s %-10s %-6s %-10s %s\n' OWNER STATE LAST_SEEN LOCKS BUSY_LEFT NOTE
  for o in $owners; do
    n=$(count_of "$o")
    t=$(now); st=$(state_of "$o")
    [ "$n" = 0 ] && [ "$st" = STALE ] && continue          # finished / old owners without locks
    bu=$(ofield "$o" busy_until); case ${bu:-} in ''|*[!0-9]*) bu=0 ;; esac
    if [ "$bu" -gt "$t" ]; then bu=$(age $((bu - t))); else bu=-; fi
    note=$(ofield "$o" note)
    printf '%-8s %-6s %-10s %-6s %-10s %s\n' "$o" "$st" "$(age $(( t - $(last_seen_of "$o") )))" "$n" "$bu" "${note:--}"
  done
  echo "-- locks"
  do_list
  stale_warning ""
  echo "-- last log lines"
  tail -n 5 "$LOG" 2>/dev/null || true
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
  acquire)
    [ $# -ge 2 ] || die "usage: acquire OWNER PATH..."
    heartbeat "$1"; do_acquire "$@"; stale_warning "$1"; exit $ACQ_RC ;;
  wait)
    [ $# -ge 3 ] || die "usage: wait OWNER SECONDS PATH..."
    owner=$1 secs=$2; shift 2; end=$(( $(now) + secs ))
    while :; do
      heartbeat "$owner"                            # a waiting executor is alive, not stale
      out=$(do_acquire "$owner" "$@"; echo "rc=$ACQ_RC")
      rc=${out##*rc=}; out=${out%rc=*}
      if [ "$rc" = 0 ]; then printf '%s' "$out"; stale_warning "$owner"; exit 0; fi
      if [ "$(now)" -ge "$end" ]; then printf '%s' "$out"; echo "TIMEOUT after ${secs}s"; stale_warning "$owner"; exit "$rc"; fi
      if [ "$rc" = 3 ]; then printf '%s' "$out"; echo "Only STALE owners block these paths; not waiting."; stale_warning "$owner"; exit 3; fi
      sleep 5
    done ;;
  release)
    [ $# -ge 2 ] || die "usage: release OWNER PATH..."
    heartbeat "$1"; do_release "$@"; rc=$?; stale_warning "$1"; exit $rc ;;
  release-all)
    [ $# -eq 1 ] || die "usage: release-all OWNER"
    heartbeat "$1" 0 "finished"; remove_all_of "$1" RELEASED ;;
  alive)
    [ $# -ge 1 ] || die "usage: alive OWNER [BUSY_SECONDS [NOTE...]]"
    o=$1; shift; busy=${1:-}; [ $# -gt 0 ] && shift
    case ${busy:-} in ''|*[!0-9]*) [ -n "${busy:-}" ] && die "BUSY_SECONDS must be a number" ;; esac
    heartbeat "$o" "$busy" "$*"; echo "ALIVE: $o${busy:+ busy for up to $(age "$busy")}${*:+ ($*)}"; stale_warning "$o" ;;
  check)
    [ $# -ge 1 ] || die "usage: check PATH..."
    any=0; load_locks
    for p in "$@"; do c=$(canon "$p"); if conflicts_for "$c" ""; then any=1; else echo "FREE: $c"; fi; done
    stale_warning ""; [ $any = 0 ] ;;
  list)   do_list; stale_warning "" ;;
  status) do_status ;;
  watch)
    iv=${1:-10}; case $iv in *[!0-9]*|'') die "INTERVAL must be a number" ;; esac
    while :; do [ -t 1 ] && clear; do_status; sleep "$iv"; done ;;
  reap)
    [ $# -ge 1 ] || die "usage: reap OWNER [--force]"
    load_locks
    if [ "$(state_of "$1")" != STALE ] && [ "${2:-}" != "--force" ]; then
      echo "REFUSED: $1 is $(state_of "$1") (last seen $(age $(( $(now) - $(last_seen_of "$1") ))) ago). Use --force only if the user confirms it is dead."
      exit 1
    fi
    remove_all_of "$1" REAPED ;;
  break)
    [ $# -ge 1 ] || die "usage: break PATH..."; do_break "$@" ;;
  *) die "unknown command '$CMD' (acquire|wait|release|release-all|alive|check|list|status|watch|reap|break)" ;;
esac
