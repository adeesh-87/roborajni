#!/usr/bin/env bash
# graphify.sh - run the bundled, pinned Graphify (tree-sitter code knowledge graph) for the ut skill.
#
#   graphify.sh setup                            create the skill-local venv, install the bundled wheel
#   graphify.sh build [--cdb compile_commands.json] OUT_DIR PATH...
#                                                graph of the C/C++ files in PATH... (files or dirs)
#                                                -> OUT_DIR/out/graph.json, GRAPH_REPORT.md, graph.html
#                                                --cdb: preprocess with the build's real flags first (macros,
#                                                #if variants resolved; lines mapped back). Use the TEST build's DB.
#   graphify.sh query   OUT_DIR "question" [--budget N]   local graph search (no LLM)
#   graphify.sh explain OUT_DIR "name"           one node and its neighbours (callers, callees, file)
#   graphify.sh path    OUT_DIR "A" "B"          shortest chain of calls/references from A to B
#   graphify.sh deps    OUT_DIR FILE|FUNCTION    what it calls outside itself: mock/stub candidates first
#   graphify.sh tests   OUT_DIR FUNCTION [HOPS]  which test blocks reach FUNCTION (default 4 call hops)
#   graphify.sh card    OUT_DIR FUNCTION|FILE    test-planning card: signature, every decision line, returns,
#                                                globals, calls, callers, existing tests
# If Python 3.10+ / Graphify cannot be set up, build/deps/tests/card fall back to the bash code map
# (codemap.sh) automatically and print "MODE: codemap". explain/path/query need the real graph.
#   graphify.sh selftest                         build a bundled fixture and check the C/C++ fixes on THIS machine
#   graphify.sh wheelhouse DIR PLATFORM PYVER    download every wheel for an OFFLINE machine,
#                                                e.g. win_amd64 3.11 | manylinux2014_x86_64 3.12 | macosx_11_0_arm64 3.12
#   graphify.sh version
#
# Paths in the graph (source_file) are relative to the repository root of the first PATH.
# Local code mode only: LLM API keys are removed from Graphify's environment on every run.
# Env: UT_PYTHON = python (>= 3.10) to create the venv with.

set -u
GRAPHIFY_VERSION=0.9.67
HERE=$(cd "$(dirname "$0")" && pwd -P)
VENDOR="$HERE/../vendor/graphify"; VENDOR=$(cd "$VENDOR" && pwd -P)
WHEEL="$VENDOR/graphifyy-$GRAPHIFY_VERSION-py3-none-any.whl"
VENV="$VENDOR/.venv"
WHEELS="$VENDOR/wheels"

die() { echo "graphify.sh: $*" >&2; exit 2; }
[ $# -ge 1 ] || { sed -n '2,30p' "$0"; exit 2; }
CMD=$1; shift

venv_py() {
  if [ -x "$VENV/bin/python" ]; then echo "$VENV/bin/python"
  elif [ -x "$VENV/Scripts/python.exe" ]; then echo "$VENV/Scripts/python.exe"
  else echo ""; fi
}

find_python() {
  local c
  for c in ${UT_PYTHON:-} python3 python "py -3"; do
    [ -n "$c" ] || continue
    if $c -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then echo "$c"; return 0; fi
  done
  return 1
}

do_setup() {
  local py vpy
  [ -f "$WHEEL" ] || die "bundled wheel missing: $WHEEL"
  vpy=$(venv_py)
  if [ -n "$vpy" ] && "$vpy" -c "import graphify, importlib.metadata as m; import sys; sys.exit(0 if m.version('graphifyy') == '$GRAPHIFY_VERSION' else 1)" 2>/dev/null; then
    echo "graphify $GRAPHIFY_VERSION already installed in $VENV"; return 0
  fi
  py=$(find_python) || die "Python 3.10+ not found. Install it, or set UT_PYTHON=/path/to/python3."
  echo "creating venv with: $py"
  $py -m venv "$VENV" || die "venv creation failed (on Debian/Ubuntu: apt install python3-venv)"
  vpy=$(venv_py); [ -n "$vpy" ] || die "venv has no python"
  if [ -d "$WHEELS" ]; then
    echo "installing from offline wheelhouse $WHEELS"
    "$vpy" -m pip install -q --disable-pip-version-check --no-index --find-links "$WHEELS" "$WHEEL" || die "offline install failed (wheelhouse built for another platform/python?)"
  else
    echo "installing dependencies from your package index (pip configuration applies)"
    "$vpy" -m pip install -q --disable-pip-version-check "$WHEEL" || die "install failed: no network/index? See resources/vendor/graphify/README.md (offline wheelhouse)"
  fi
  "$vpy" -c "import graphify" || die "graphify does not import after install"
  echo "graphify $GRAPHIFY_VERSION ready in $VENV"
}

ensure() { [ -n "$(venv_py)" ] || ( do_setup ) >&2; [ -n "$(venv_py)" ]; }   # subshell: a failed setup must not exit

# fallback: the bash code map, same commands
fallback_build() { local out=$1; shift; echo "MODE: codemap (Graphify unavailable: $FALLBACK_REASON)"; mkdir -p "$out"; echo codemap > "$out/MODE"; "$HERE/codemap.sh" build "$out/codemap" "$@"; }
mode_of() { [ -f "$1/out/graph.json" ] && echo graph || { [ -f "$1/codemap/functions.tsv" ] && echo codemap || echo none; }; }
need_graph() { case $(mode_of "$1") in graph) return 0 ;; codemap) echo "graphify.sh: '$CMD' needs the Graphify graph; this folder has the bash code map only. Use deps/tests/card." >&2; exit 1 ;; *) echo "graphify.sh: no graph in $1 (run: graphify.sh build ...)" >&2; exit 1 ;; esac; }

run_graphify() {   # code-only: strip every LLM credential / endpoint
  env -u ANTHROPIC_API_KEY -u ANTHROPIC_BASE_URL -u OPENAI_API_KEY -u OPENAI_BASE_URL \
      -u AZURE_OPENAI_API_KEY -u AZURE_OPENAI_ENDPOINT -u GEMINI_API_KEY -u GEMINI_BASE_URL \
      -u GOOGLE_API_KEY -u MOONSHOT_API_KEY -u KIMI_BASE_URL -u DEEPSEEK_API_KEY -u DEEPSEEK_BASE_URL \
      -u OPENROUTER_API_KEY -u GROQ_API_KEY -u MISTRAL_API_KEY -u GRAPHIFY_API_KEY -u GRAPHIFY_TRIAGE_BACKEND \
      -u OLLAMA_HOST -u OLLAMA_BASE_URL -u OLLAMA_MODEL \
      GRAPHIFY_NO_TIPS=1 PYTHONIOENCODING=utf-8 "$(venv_py)" -m graphify "$@"
}

do_build() {
  local cdb=""
  if [ "${1:-}" = "--cdb" ]; then
    [ -f "${2:-}" ] || die "compile DB not found: ${2:-}"; cdb=$(cd "$(dirname "$2")" && pwd -P)/$(basename "$2"); shift 2
  fi
  local out=$1; shift
  [ $# -ge 1 ] || die "usage: build [--cdb compile_commands.json] OUT_DIR PATH..."
  mkdir -p "$out" || die "cannot create $out"
  out=$(cd "$out" && pwd -P)
  # 1. mirror only the in-scope files (preprocessed with the real flags when a compile DB is given);
  #    nothing is written into the repository
  "$(venv_py)" "$HERE/graphify_ut.py" mirror "$out/scan" ${cdb:+--cdb "$cdb"} "$@" || return 1
  # 2. Graphify, local code mode. Start from an empty graph every time: `update` is incremental and would
  #    otherwise carry over nodes of the previous build (and of the previous augment step). Parse cache is kept.
  rm -f "$out/out/graph.json" "$out/out/manifest.json"
  ( cd "$out" && GRAPHIFY_OUT="$out/out" run_graphify update "$out/scan" --force ) > "$out/build.log" 2>&1
  local rc=$?
  grep -E 'warning|Rebuilt|error' "$out/build.log" | cut -c1-400
  [ $rc -eq 0 ] && [ -f "$out/out/graph.json" ] || { echo "graphify build FAILED (rc=$rc), see $out/build.log"; return 1; }
  # 3. C/C++ fixes: original lines, static flags, external callees, one node per TEST block
  if "$(venv_py)" "$HERE/graphify_ut.py" augment "$out/out/graph.json" "$out/scan"; then
    # 4. re-cluster so GRAPH_REPORT.md / graph.html reflect the fixes (local; no LLM labelling)
    local nodes viz=""
    nodes=$("$(venv_py)" -c "import json,sys; print(len(json.load(open(sys.argv[1]))['nodes']))" "$out/out/graph.json")
    [ "${nodes:-0}" -gt 5000 ] && viz="--no-viz"
    ( cd "$out" && GRAPHIFY_OUT="$out/out" run_graphify cluster-only "$out/scan" --graph "$out/out/graph.json" --no-label $viz ) >> "$out/build.log" 2>&1 \
      || echo "WARNING: report regeneration failed; GRAPH_REPORT.md is from before the fixes"
    rm -rf "$out"/out/[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]    # Graphify's dated backups: useless, we rebuild
  else
    echo "WARNING: augment step failed; graph is plain Graphify output"
  fi
  echo "graph:  $out/out/graph.json"
  echo "report: $out/out/GRAPH_REPORT.md${viz:+   (graph.html skipped: large graph)}"
}

case $CMD in
  setup)   do_setup ;;
  version) ensure || exit 2; run_graphify --version 2>/dev/null || "$(venv_py)" -c "import importlib.metadata as m; print('graphifyy', m.version('graphifyy'))" ;;
  build)   [ $# -ge 2 ] || die "usage: build [--cdb FILE] OUT_DIR PATH..."
           if ensure; then do_build "$@"; else
             FALLBACK_REASON="Python 3.10+ or package install failed"; [ "${1:-}" = "--cdb" ] && shift 2
             fallback_build "$@"; fi ;;
  query)   [ $# -ge 2 ] || die "usage: query OUT_DIR \"question\" [--budget N]"
           need_graph "$1"; ensure || exit 2; o=$1; q=$2; shift 2; run_graphify query "$q" --graph "$o/out/graph.json" "$@" ;;
  explain) [ $# -ge 2 ] || die "usage: explain OUT_DIR NAME"; need_graph "$1"; ensure || exit 2; run_graphify explain "$2" --graph "$1/out/graph.json" ;;
  path)    [ $# -ge 3 ] || die "usage: path OUT_DIR A B"; need_graph "$1"; ensure || exit 2; run_graphify path "$2" "$3" --graph "$1/out/graph.json" ;;
  deps)    [ $# -eq 2 ] || die "usage: deps OUT_DIR FILE|FUNCTION"
           case $(mode_of "$1") in graph) ensure || exit 2; "$(venv_py)" "$HERE/graphify_ut.py" deps "$1/out/graph.json" "$2" ;;
             codemap) "$HERE/codemap.sh" deps "$1/codemap" "$2" ;; *) die "no graph in $1 (run: graphify.sh build ...)" ;; esac ;;
  tests)   [ $# -ge 2 ] || die "usage: tests OUT_DIR FUNCTION [HOPS]"
           case $(mode_of "$1") in graph) ensure || exit 2; "$(venv_py)" "$HERE/graphify_ut.py" tests "$1/out/graph.json" "$2" ${3:-} ;;
             codemap) "$HERE/codemap.sh" tests "$1/codemap" "$2" ${3:-} ;; *) die "no graph in $1 (run: graphify.sh build ...)" ;; esac ;;
  card)    [ $# -eq 2 ] || die "usage: card OUT_DIR FUNCTION|FILE"
           case $(mode_of "$1") in graph) ensure || exit 2; "$(venv_py)" "$HERE/graphify_ut.py" card "$1/out/graph.json" "$1/scan" "$2" ;;
             codemap) "$HERE/codemap.sh" card "$1/codemap" "$2" ;; *) die "no graph in $1 (run: graphify.sh build ...)" ;; esac ;;
  selftest)
    ensure || exit 2
    tmp=$(mktemp -d 2>/dev/null || echo "${TMPDIR:-/tmp}/ut-selftest-$$"); mkdir -p "$tmp"
    cp -r "$HERE/selftest/." "$tmp/fx"
    if "$(venv_py)" "$HERE/graphify_ut.py" mkcdb "$tmp/fx"; then mode=""; cdbarg="--cdb $tmp/fx/compile_commands.json"
    else mode=plain; cdbarg=""; fi
    ( cd "$tmp/fx" && do_build $cdbarg "$tmp/g" src tests tests/mocks ) > "$tmp/selftest.log" 2>&1 || { cat "$tmp/selftest.log"; exit 1; }
    grep -E 'preprocessed|not preprocessed|augmented|WARNING' "$tmp/selftest.log"
    "$(venv_py)" "$HERE/graphify_ut.py" check "$tmp/g/out/graph.json" $mode; rc=$?
    rm -rf "$tmp"; exit $rc ;;
  wheelhouse)
    [ $# -eq 3 ] || die "usage: wheelhouse DIR PLATFORM PYVER   (e.g. wheels win_amd64 3.11)"
    py=$(venv_py); [ -n "$py" ] || py=$(find_python) || die "Python 3.10+ needed to download wheels"
    mkdir -p "$1" && cp "$WHEEL" "$1/"
    $py -m pip download --disable-pip-version-check --only-binary=:all: --platform "$2" --python-version "$3" -d "$1" "$WHEEL" \
      && echo "wheelhouse ready: $1 (copy it to resources/vendor/graphify/wheels on the offline machine, then run setup)" ;;
  *) die "unknown command '$CMD' (setup|build|query|explain|path|deps|tests|card|selftest|wheelhouse|version)" ;;
esac
