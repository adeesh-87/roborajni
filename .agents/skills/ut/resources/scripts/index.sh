#!/usr/bin/env bash
# index.sh - the code index of the ut skill: the Graphify graph (with the ut fixes) exported to ONE index.json that
# every query reads. Agents ask these commands instead of reading or grepping source files.
#
#   index.sh setup                               skill venv (Python 3.10+) with the bundled Graphify
#   index.sh build [--cdb FILE] OUT_DIR PATH...  Graphify graph of PATH... (--cdb: preprocess with the build's flags)
#   index.sh refresh OUT_DIR                     rebuild with the last arguments; regenerate KB cards (+ diagrams); delta
#   index.sh card    OUT_DIR FUNCTION|FILE       test-planning card (decisions, calls, callers, tests, runtime reach)
#   index.sh find    OUT_DIR PATTERN             functions / TEST blocks / types / macros / globals matching (instead of grep)
#   index.sh defs    OUT_DIR NAME                every definition of NAME: overloads, mocks, fakes
#   index.sh list    OUT_DIR FILE                a file's types, macros, globals and functions with line ranges
#   index.sh source  OUT_DIR NAME[@LINE]|"TEST(G, N)"   the lines of one function, TEST block, type, macro or constant
#   index.sh refs    OUT_DIR NAME                callers with call lines, TEST blocks, pointers, overrides, doubles
#   index.sh deps    OUT_DIR FUNCTION|FILE       what it calls outside itself: mock/stub candidates first
#   index.sh tests   OUT_DIR FUNCTION [HOPS]     TEST blocks that reach it through calls
#   index.sh impact  OUT_DIR --base REF|--uncommitted|--range A..B [--out FILE] [--context FILE]
#   index.sh flow    OUT_DIR FUNCTION [--no-cov] Mermaid flowchart text (T/F edges, coverage counts when imported)
#   index.sh seq     OUT_DIR FUNCTION [--depth 1] Mermaid sequence text (calls in order, alt/loop, test doubles)
#   index.sh diagrams  OUT_DIR DEST_DIR          flow/seq files for every function worth one + scenarios + INDEX.md
#   index.sh scenarios OUT_DIR DEST_DIR          one sequence per entry point + SCENARIOS.md
#   index.sh cov-import OUT_DIR --lcov F | --gcov-dir BUILD_DIR | --ctc profile.txt | --json F
#   index.sh uncovered  OUT_DIR [FILE|FUNCTION]  never-run functions and never-taken decision outcomes
#   index.sh trace   OUT_DIR --run "CMD" [--cmake SRC --build-dir DIR --cmake-args ".." --target T | --build "CMD {cflags} {ldflags}"]
#                                                runtime sequence per TEST (what really ran); runtime reach in the cards
#   index.sh kb-cards OUT_DIR KB_DIR FILE...     write KB_DIR/modules/<file>.cards.md (cards + dependencies)
#   index.sh selftest                            build the bundled fixture, check 15 known answers
# OUT_DIR holds index.json, BUILD_ARGS, graphify/ (the graph), coverage.json, traces.json. Paths inside are relative to
# the repository root of the first PATH. Graphify-only commands (explain, path, query): graphify.sh ... OUT_DIR/graphify.
set -u
HERE=$(cd "$(dirname "$0")" && pwd -P)
VENV="$HERE/../vendor/graphify/.venv"
die() { echo "index.sh: $*" >&2; exit 2; }
[ $# -ge 1 ] || { sed -n '2,29p' "$0"; exit 2; }
CMD=$1; shift

py() {
  if [ -x "$VENV/bin/python" ]; then echo "$VENV/bin/python"
  elif [ -x "$VENV/Scripts/python.exe" ]; then echo "$VENV/Scripts/python.exe"
  else echo ""; fi
}
run_py() { local p; p=$(py); [ -n "$p" ] || die "skill venv missing: run index.sh setup (Python 3.10+)"; PYTHONPATH="$HERE${PYTHONPATH:+:$PYTHONPATH}" "$p" -m codeindex "$@"; }
need_index() { [ -f "$1/index.json" ] || die "no index in $1 (run: index.sh build ...)"; }

do_build() {
  local cdb="" out
  while [ $# -gt 0 ]; do case $1 in
    --cdb) [ -f "$2" ] || die "compile DB not found: $2"; cdb=$(cd "$(dirname "$2")" && pwd -P)/$(basename "$2"); shift 2 ;;
    --backend) shift 2 ;;                       # accepted and ignored: Graphify is the only backend
    *) break ;; esac; done
  [ $# -ge 2 ] || die "usage: build [--cdb FILE] OUT_DIR PATH..."
  out=$1; shift
  mkdir -p "$out" || die "cannot create $out"; out=$(cd "$out" && pwd -P)
  { echo "cwd=$PWD"; echo "cdb=$cdb"; for p in "$@"; do echo "path=$p"; done; } > "$out/BUILD_ARGS"
  rm -f "$out/index.json"
  "$HERE/graphify.sh" build ${cdb:+--cdb "$cdb"} "$out/graphify" "$@" | grep -E 'preprocessed|augmented|WARNING|FAILED'
  [ -f "$out/graphify/out/graph.json" ] || die "graphify build failed (see $out/graphify/build.log)"
  run_py export-graphify "$out/graphify" "$out/index.json"
  [ -f "$out/index.json" ] || die "build FAILED: no index written"
}

do_selftest() {
  local tmp rc=0
  tmp=$(mktemp -d 2>/dev/null || echo "${TMPDIR:-/tmp}/ut-ixtest-$$"); mkdir -p "$tmp"
  cp -r "$HERE/selftest/." "$tmp/fx"; ( cd "$tmp/fx" && git init -q . 2>/dev/null )
  if run_py mkcdb "$tmp/fx" >/dev/null 2>&1; then cdb="--cdb compile_commands.json"; mode=""; else cdb=""; mode=plain; fi
  if ( cd "$tmp/fx" && do_build $cdb "$tmp/ix" src tests tests/mocks ) > "$tmp/build.log" 2>&1; then
    run_py check "$tmp/ix/index.json" $mode > "$tmp/check" || rc=1
    grep FAIL "$tmp/check"; tail -1 "$tmp/check"
  else echo "self-test: build FAILED"; tail -5 "$tmp/build.log"; rc=1; fi
  rm -rf "$tmp"; exit $rc
}

case $CMD in
  setup)    "$HERE/graphify.sh" setup ;;
  build)    do_build "$@" ;;
  refresh)  [ $# -eq 1 ] || die "usage: refresh OUT_DIR"; need_index "$1"; run_py refresh "$1" ;;
  card|deps|tests|find|defs|list|source|refs|impact|flow|seq|uncovered|stats|cov-import|trace)
            [ $# -ge 2 ] || [ "$CMD" = stats ] || [ "$CMD" = uncovered ] || die "usage: $CMD OUT_DIR ..."
            need_index "$1"; o=$1; shift; run_py "$CMD" "$o/index.json" "$@" ;;
  diagrams|scenarios)
            [ $# -ge 2 ] || die "usage: $CMD OUT_DIR DEST_DIR"; need_index "$1"; o=$1; shift; run_py "$CMD" "$o/index.json" "$@" ;;
  kb-cards) [ $# -ge 3 ] || die "usage: kb-cards OUT_DIR KB_DIR FILE..."; need_index "$1"; run_py kb-cards "$@" ;;
  selftest) do_selftest ;;
  *) die "unknown command '$CMD' (setup|build|refresh|card|find|defs|list|source|refs|deps|tests|impact|flow|seq|diagrams|scenarios|cov-import|uncovered|trace|kb-cards|selftest)" ;;
esac
