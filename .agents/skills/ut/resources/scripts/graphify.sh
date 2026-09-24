#!/usr/bin/env bash
# graphify.sh - run the bundled, pinned Graphify (tree-sitter code knowledge graph) for the ut skill.
#
#   graphify.sh setup                            create the skill-local venv, install the bundled wheel
#   graphify.sh build   OUT_DIR PATH...          graph of the C/C++ files in PATH... (files or dirs)
#                                                -> OUT_DIR/out/graph.json, GRAPH_REPORT.md, graph.html
#   graphify.sh query   OUT_DIR "question" [--budget N]   local graph search (no LLM)
#   graphify.sh explain OUT_DIR "name"           one node and its neighbours (callers, callees, file)
#   graphify.sh path    OUT_DIR "A" "B"          shortest chain of calls/references from A to B
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
[ $# -ge 1 ] || { sed -n '2,19p' "$0"; exit 2; }
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

ensure() { [ -n "$(venv_py)" ] || do_setup >&2 || exit 2; }

run_graphify() {   # code-only: strip every LLM credential / endpoint
  env -u ANTHROPIC_API_KEY -u ANTHROPIC_BASE_URL -u OPENAI_API_KEY -u OPENAI_BASE_URL \
      -u AZURE_OPENAI_API_KEY -u AZURE_OPENAI_ENDPOINT -u GEMINI_API_KEY -u GEMINI_BASE_URL \
      -u GOOGLE_API_KEY -u MOONSHOT_API_KEY -u KIMI_BASE_URL -u DEEPSEEK_API_KEY -u DEEPSEEK_BASE_URL \
      -u OPENROUTER_API_KEY -u GROQ_API_KEY -u MISTRAL_API_KEY -u GRAPHIFY_API_KEY -u GRAPHIFY_TRIAGE_BACKEND \
      -u OLLAMA_HOST -u OLLAMA_BASE_URL -u OLLAMA_MODEL \
      GRAPHIFY_NO_TIPS=1 PYTHONIOENCODING=utf-8 "$(venv_py)" -m graphify "$@"
}

do_build() {
  local out=$1; shift
  [ $# -ge 1 ] || die "usage: build OUT_DIR PATH..."
  mkdir -p "$out" || die "cannot create $out"
  out=$(cd "$out" && pwd -P)
  # Mirror only the in-scope C/C++ files, keeping repo-relative paths, so the graph covers exactly
  # the requested scope and nothing is written into the repository.
  "$(venv_py)" - "$out/scan" "$@" <<'PY' || exit 1
import os, shutil, subprocess, sys
scan, paths = sys.argv[1], sys.argv[2:]
exts = {'.c', '.cc', '.cpp', '.cxx', '.h', '.hh', '.hpp', '.hxx', '.inl', '.ipp', '.tpp'}
first = os.path.abspath(paths[0])
start = first if os.path.isdir(first) else os.path.dirname(first)
try:
    root = subprocess.run(['git', '-C', start, 'rev-parse', '--show-toplevel'], capture_output=True, text=True, check=True).stdout.strip()
except Exception:
    root = os.path.commonpath([os.path.abspath(p) for p in paths]) if len(paths) > 1 else start
root = os.path.realpath(root)
if os.path.isdir(scan):
    shutil.rmtree(scan)
files = []
for p in paths:
    p = os.path.realpath(p)
    if os.path.isfile(p):
        files.append(p)
    elif os.path.isdir(p):
        for d, dirs, names in os.walk(p):
            dirs[:] = [x for x in dirs if x not in ('.git', 'graphify-out')]
            files += [os.path.join(d, n) for n in names if os.path.splitext(n)[1].lower() in exts]
    else:
        sys.exit(f"graphify.sh: no such path: {p}")
n = 0
for f in sorted(set(files)):
    rel = os.path.relpath(f, root)
    if rel.startswith('..'):
        sys.exit(f"graphify.sh: {f} is outside the repository root {root}")
    dst = os.path.join(scan, rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(f, dst); n += 1
if n == 0:
    sys.exit("graphify.sh: no C/C++ files found in: " + " ".join(paths))
with open(os.path.join(os.path.dirname(scan), 'SOURCE_ROOT'), 'w') as fh:
    fh.write(root + "\n")
print(f"scope: {n} C/C++ files (paths relative to {root})")
PY
  ( cd "$out" && GRAPHIFY_OUT="$out/out" run_graphify update "$out/scan" --force ) > "$out/build.log" 2>&1
  local rc=$?
  grep -E 'warning|Rebuilt|error' "$out/build.log" | cut -c1-400
  [ $rc -eq 0 ] && [ -f "$out/out/graph.json" ] || { echo "graphify build FAILED (rc=$rc), see $out/build.log"; return 1; }
  echo "graph:  $out/out/graph.json"
  echo "report: $out/out/GRAPH_REPORT.md   (view: $out/out/graph.html)"
}

case $CMD in
  setup)   do_setup ;;
  version) ensure; run_graphify --version 2>/dev/null || "$(venv_py)" -c "import importlib.metadata as m; print('graphifyy', m.version('graphifyy'))" ;;
  build)   [ $# -ge 2 ] || die "usage: build OUT_DIR PATH..."; ensure; do_build "$@" ;;
  query)   [ $# -ge 2 ] || die "usage: query OUT_DIR \"question\" [--budget N]"
           ensure; o=$1; q=$2; shift 2; run_graphify query "$q" --graph "$o/out/graph.json" "$@" ;;
  explain) [ $# -ge 2 ] || die "usage: explain OUT_DIR NAME"; ensure; run_graphify explain "$2" --graph "$1/out/graph.json" ;;
  path)    [ $# -ge 3 ] || die "usage: path OUT_DIR A B"; ensure; run_graphify path "$2" "$3" --graph "$1/out/graph.json" ;;
  wheelhouse)
    [ $# -eq 3 ] || die "usage: wheelhouse DIR PLATFORM PYVER   (e.g. wheels win_amd64 3.11)"
    py=$(venv_py); [ -n "$py" ] || py=$(find_python) || die "Python 3.10+ needed to download wheels"
    mkdir -p "$1" && cp "$WHEEL" "$1/"
    $py -m pip download --disable-pip-version-check --only-binary=:all: --platform "$2" --python-version "$3" -d "$1" "$WHEEL" \
      && echo "wheelhouse ready: $1 (copy it to resources/vendor/graphify/wheels on the offline machine, then run setup)" ;;
  *) die "unknown command '$CMD' (setup|build|query|explain|path|wheelhouse|version)" ;;
esac
