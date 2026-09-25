#!/usr/bin/env bash
# index.sh - the code index of the ut skill. ONE index.json, written by the backend you pick, read by every query.
#
#   index.sh setup [graphify|clang|clangd|all]   skill venv (Python 3.10+) + what the backend needs (default: graphify)
#   index.sh detect ROOT [--cdb FILE] [--json]    which backends work HERE for THIS code, and the recommended one
#   index.sh build --backend auto|clang|gcc|graphify|codemap [--cdb FILE] OUT_DIR PATH...
#        clang     libclang + the build flags: exact calls (overloads, templates, virtual, macros), lambdas, callbacks
#        gcc       your own gcc (cross too, >= 10) writes the call graph (-fcallgraph-info); branches via tree-sitter
#        graphify  tree-sitter graph (bundled Graphify) + fixes; no compile DB needed; tolerates broken code
#        codemap   bash + grep, no Python (card/deps/tests only)
#   index.sh refresh OUT_DIR                     rebuild with the last arguments; regenerate KB cards (+ diagrams); delta
#   index.sh card    OUT_DIR FUNCTION|FILE       test-planning card (decisions, calls, callers, tests, runtime reach)
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
#   index.sh lsp     OUT_DIR callers|callees|refs|def|hover NAME   ask clangd (interactive; needs a compile DB)
#   index.sh compare OUT_A OUT_B                 where two backends disagree
#   index.sh kb-cards OUT_DIR KB_DIR FILE...     write KB_DIR/modules/<file>.cards.md (cards + dependencies)
#   index.sh selftest [clang|gcc|graphify|all]   build the bundled fixture with each backend, check 15 known answers
# OUT_DIR holds index.json (+ BUILD_ARGS, coverage.json, traces.json, backend work files). Paths inside are relative
# to the repository root of the first PATH. Env: UT_JOBS (parallel units), UT_LIBCLANG, UT_CLANG_EXTRA, UT_CLANGD.
set -u
HERE=$(cd "$(dirname "$0")" && pwd -P)
VENV="$HERE/../vendor/graphify/.venv"
die() { echo "index.sh: $*" >&2; exit 2; }
[ $# -ge 1 ] || { sed -n '2,34p' "$0"; exit 2; }
CMD=$1; shift

py() {
  if [ -x "$VENV/bin/python" ]; then echo "$VENV/bin/python"
  elif [ -x "$VENV/Scripts/python.exe" ]; then echo "$VENV/Scripts/python.exe"
  else for c in ${UT_PYTHON:-} python3 python; do
         [ -n "$c" ] && $c -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null && { echo "$c"; return; }
       done; echo ""; fi
}
run_py() { local p; p=$(py); [ -n "$p" ] || die "Python 3.10+ needed (or use --backend codemap)"; PYTHONPATH="$HERE${PYTHONPATH:+:$PYTHONPATH}" "$p" -m codeindex "$@"; }
mode_of() { [ -f "$1/index.json" ] && echo index || { [ -f "$1/codemap/functions.tsv" ] && echo codemap || echo none; }; }
need_index() { case $(mode_of "$1") in index) return 0 ;; codemap) echo "index.sh: '$CMD' needs a real index; $1 has the bash code map only (card/deps/tests work)" >&2; exit 1 ;;
               *) echo "index.sh: no index in $1 (run: index.sh build ...)" >&2; exit 1 ;; esac; }

pipi() {   # pip install, from the offline wheelhouse when it exists
  local w="$HERE/../vendor/graphify/wheels"
  if [ -d "$w" ]; then "$(py)" -m pip install -q --disable-pip-version-check --no-index --find-links "$w" "$@"
  else "$(py)" -m pip install -q --disable-pip-version-check "$@"; fi
}

do_setup() {
  local what=${1:-graphify} vpy major
  "$HERE/graphify.sh" setup || die "skill venv setup failed"
  vpy=$(py)
  case $what in
    graphify) ;;
    clang|all)
      if "$vpy" -c 'import clang.cindex' 2>/dev/null; then echo "libclang bindings already installed"
      else
        major=$(PYTHONPATH="$HERE" "$vpy" -c 'from codeindex.clangload import system_major; print(system_major() or "")')
        if [ -n "$major" ]; then echo "system libclang $major found: installing matching bindings (clang==$major.*)"
             pipi "clang==$major.*" || die "pip install clang==$major.* failed"
        else echo "no system libclang: installing the self-contained 'libclang' wheel"
             pipi libclang || die "pip install libclang failed (offline? see vendor/graphify/README.md)"
        fi
      fi
      PYTHONPATH="$HERE" "$vpy" -c 'from codeindex.clangload import load; load(); print("libclang OK")' || die "libclang does not load (set UT_LIBCLANG)"
      [ "$what" = all ] && do_setup clangd ;;
    clangd)
      if [ -n "$(PYTHONPATH="$HERE" "$vpy" -c 'from codeindex.lsp import find_clangd; print(find_clangd() or "")')" ]; then echo "clangd found"
      else pipi clangd || die "pip install clangd failed (or install clangd and set UT_CLANGD)"; fi ;;
    *) die "setup what? graphify|clang|clangd|all" ;;
  esac
}

do_build() {
  local backend=auto cdb="" out
  while [ $# -gt 0 ]; do case $1 in
    --backend) backend=$2; shift 2 ;;
    --cdb) [ -f "$2" ] || die "compile DB not found: $2"; cdb=$(cd "$(dirname "$2")" && pwd -P)/$(basename "$2"); shift 2 ;;
    *) break ;; esac; done
  [ $# -ge 2 ] || die "usage: build --backend B [--cdb FILE] OUT_DIR PATH..."
  out=$1; shift
  mkdir -p "$out" || die "cannot create $out"; out=$(cd "$out" && pwd -P)
  if [ "$backend" = auto ]; then
    backend=$(run_py detect . ${cdb:+--cdb "$cdb"} --json 2>/dev/null | sed -n 's/.*"recommended": "\([a-z]*\)".*/\1/p')
    [ -n "$backend" ] || backend=codemap
    echo "backend: $backend (auto)"
  fi
  { echo "backend=$backend"; echo "cwd=$PWD"; echo "cdb=$cdb"; for p in "$@"; do echo "path=$p"; done; } > "$out/BUILD_ARGS"
  rm -f "$out/index.json"
  case $backend in
    clang) [ -n "$cdb" ] || die "clang backend needs --cdb compile_commands.json"; run_py build-clang "$out/index.json" "$cdb" "$@" ;;
    gcc)   [ -n "$cdb" ] || die "gcc backend needs --cdb compile_commands.json"; run_py build-gcc "$out/index.json" "$cdb" "$@" ;;
    graphify) "$HERE/graphify.sh" build ${cdb:+--cdb "$cdb"} "$out/graphify" "$@" | grep -E 'preprocessed|augmented|MODE|WARNING|FAILED'
              [ -f "$out/graphify/out/graph.json" ] || die "graphify build failed (see $out/graphify/build.log)"
              run_py export-graphify "$out/graphify" "$out/index.json" ;;
    codemap) mkdir -p "$out/codemap"; "$HERE/codemap.sh" build "$out/codemap" "$@"; echo "MODE: codemap (no index.json; card/deps/tests only)" ;;
    *) die "unknown backend $backend (auto|clang|gcc|graphify|codemap)" ;;
  esac
  [ "$backend" = codemap ] || [ -f "$out/index.json" ] || die "build FAILED: no index written"
}

do_selftest() {
  local which=${1:-all} tmp rc=0 b list
  tmp=$(mktemp -d 2>/dev/null || echo "${TMPDIR:-/tmp}/ut-ixtest-$$"); mkdir -p "$tmp"
  cp -r "$HERE/selftest/." "$tmp/fx"; ( cd "$tmp/fx" && git init -q . 2>/dev/null )
  run_py mkcdb "$tmp/fx" >/dev/null 2>&1 || PYTHONPATH="$HERE" "$(py)" "$HERE/graphify_ut.py" mkcdb "$tmp/fx" >/dev/null || { echo "no compiler: cannot self-test"; exit 3; }
  [ "$which" = all ] && list="graphify clang gcc" || list=$which
  for b in $list; do
    if ( cd "$tmp/fx" && do_build --backend "$b" --cdb compile_commands.json "$tmp/$b" src tests tests/mocks ) > "$tmp/$b.log" 2>&1; then
      run_py check "$tmp/$b/index.json" > "$tmp/$b.check" || rc=1
      grep FAIL "$tmp/$b.check"; tail -1 "$tmp/$b.check"
    else echo "self-test [$b]: build FAILED (not usable here?)"; tail -3 "$tmp/$b.log"; [ "$which" = all ] || rc=1; fi
  done
  rm -rf "$tmp"; exit $rc
}

case $CMD in
  setup)    do_setup "${1:-graphify}" ;;
  detect)   run_py detect "$@" ;;
  build)    do_build "$@" ;;
  refresh)  [ $# -eq 1 ] || die "usage: refresh OUT_DIR"; need_index "$1"; run_py refresh "$1" ;;
  card|deps|tests)
            [ $# -ge 2 ] || die "usage: $CMD OUT_DIR NAME [..]"
            case $(mode_of "$1") in index) o=$1; shift; run_py "$CMD" "$o/index.json" "$@" ;;
              codemap) o=$1; shift; "$HERE/codemap.sh" "$CMD" "$o/codemap" "$@" ;; *) die "no index in $1 (run: index.sh build ...)" ;; esac ;;
  impact|flow|seq|uncovered|lsp|stats)
            [ $# -ge 1 ] || die "usage: $CMD OUT_DIR ..."; need_index "$1"; o=$1; shift; run_py "$CMD" "$o/index.json" "$@" ;;
  diagrams|scenarios)
            [ $# -ge 2 ] || die "usage: $CMD OUT_DIR DEST_DIR"; need_index "$1"; o=$1; shift; run_py "$CMD" "$o/index.json" "$@" ;;
  cov-import|trace)
            [ $# -ge 2 ] || die "usage: $CMD OUT_DIR ..."; need_index "$1"; o=$1; shift; run_py "$CMD" "$o/index.json" "$@" ;;
  kb-cards) [ $# -ge 3 ] || die "usage: kb-cards OUT_DIR KB_DIR FILE..."; need_index "$1"; run_py kb-cards "$@" ;;
  compare)  [ $# -ge 2 ] || die "usage: compare OUT_A OUT_B"; need_index "$1"; need_index "$2"; run_py compare "$1/index.json" "$2/index.json" "${@:3}" ;;
  selftest) do_selftest "${1:-all}" ;;
  *) die "unknown command '$CMD' (setup|detect|build|refresh|card|deps|tests|impact|flow|seq|diagrams|scenarios|cov-import|uncovered|trace|lsp|compare|selftest)" ;;
esac
