#!/usr/bin/env bash
# codemap.sh - zero-dependency map of C/C++ code for unit-test work (bash + awk only).
#
# Usage: codemap.sh OUT_DIR PATH...        PATH = files or directories (code under test AND test code)
#
# Writes to OUT_DIR:
#   functions.tsv  file, function, start line, end line, static(1/0), kind(func|macro-block)
#   calls.tsv      file, caller function, callee, count, where the callee is defined
#                  (file of the scanned set | "macro" | "external")
#   includes.tsv   file, included header
#   externals.tsv  callee, kind (function|macro), declared in (header in the repo or "?"), number of callers
#   summary.md     per file: functions, what they call, external dependencies = mock/stub candidates
#
# HEURISTIC, not a compiler: #if/#ifdef branches are all read, function pointers and calls hidden in
# macros are not seen, unusual syntax can confuse it. Treat the output as a map, verify in the code.
# Test macros are kept as names, e.g. "TEST(Sensor, Read_Ok)" or "TEST_F(SensorTest, Read_Ok)",
# so the map also shows which test calls which function.

set -u
[ $# -ge 2 ] || { sed -n '2,19p' "$0"; exit 2; }
OUT=$1; shift
mkdir -p "$OUT" || exit 2
REPO=$(git -C "$1" rev-parse --show-toplevel 2>/dev/null || (cd "$(dirname "$1")" && pwd -P))

LIST="$OUT/.files"
for p in "$@"; do
  if [ -d "$p" ]; then
    find "$p" -type f \( -name '*.c' -o -name '*.cc' -o -name '*.cpp' -o -name '*.cxx' -o -name '*.h' -o -name '*.hh' -o -name '*.hpp' -o -name '*.hxx' -o -name '*.inl' \) -not -path '*/.git/*'
  elif [ -f "$p" ]; then echo "$p"; fi
done | sort -u > "$LIST"
NFILES=$(wc -l < "$LIST" | tr -d ' ')
[ "$NFILES" -gt 0 ] || { echo "codemap: no C/C++ files under: $*" >&2; exit 1; }

# ---------------------------------------------------------------- 1. parse
: > "$OUT/functions.tsv"; : > "$OUT/.calls.raw"; : > "$OUT/includes.tsv"; : > "$OUT/.macros"
tr '\n' '\0' < "$LIST" | xargs -0 awk -v SQ="'" -v DOUT="$OUT/.macros" -v FOUT="$OUT/functions.tsv" -v COUT="$OUT/.calls.raw" -v IOUT="$OUT/includes.tsv" '
function reset_file() { depth=0; nst=0; infn=0; hdr=""; body=""; incmt=0; inpp=0 }
function trim(s) { gsub(/^[ \t]+|[ \t]+$/, "", s); return s }
function fname(h,    t, i, n, c, name) {
  t = h
  gsub(/__attribute__[ \t]*\(\([^)]*\)\)/, "", t)
  gsub(/__declspec[ \t]*\([^)]*\)/, "", t)
  t = trim(t)
  # macro-style test/fixture blocks: the WHOLE header is NAME(args), e.g. TEST(Group, Name) {, TEST_F(A, B) {
  if (t ~ /^[A-Z][A-Z0-9_]*[ \t]*\([^()]*\)$/) {
    name = t; gsub(/[ \t]+/, " ", name); kind = "macro-block"; return name
  }
  kind = "func"
  # drop leading macro wrappers such as CJSON_PUBLIC(void) name(...) or EXPORT_API(int) name(...)
  while (match(t, /^([A-Za-z_][A-Za-z0-9_ \t*]*[ \t])?[A-Z][A-Z0-9_]*[ \t]*\([^()]*\)[ \t]+[A-Za-z_]/))
    { pre = substr(t, 1, RLENGTH - 1); sub(/[A-Z][A-Z0-9_]*[ \t]*\([^()]*\)[ \t]+$/, "", pre); t = pre substr(t, RLENGTH) }
  i = index(t, "("); if (i == 0) return ""
  n = substr(t, 1, i - 1); sub(/[ \t]+$/, "", n)
  if (match(n, /[A-Za-z_~][A-Za-z0-9_:~]*$/)) name = substr(n, RSTART, RLENGTH); else return ""
  if (name ~ /^(if|for|while|switch|catch|return|sizeof|else|do)$/) return ""
  return name
}
function is_func_header(h) {
  if (h !~ /\(/) return 0
  if (h ~ /=[ \t]*$/) return 0
  if (h ~ /\)[ \t]*((const|override|final|noexcept|volatile|mutable|throw[ \t]*\([^)]*\))[ \t]*)*$/) return 1
  if (h ~ /\)[ \t]*:[^:]/) return 1                        # constructor initialiser list
  if (h ~ /\)[ \t]*->[ \t]*[A-Za-z_]/) return 1           # trailing return type
  return 0
}
function emit_calls(fn,    b, name, pre, cnt, k) {
  b = body; delete cnt
  while (match(b, /[A-Za-z_][A-Za-z0-9_:]*[ \t]*\(/)) {
    name = substr(b, RSTART, RLENGTH); sub(/[ \t]*\($/, "", name)
    pre = (RSTART > 1) ? substr(b, RSTART - 1, 1) : " "
    if (RSTART > 2 && substr(b, RSTART - 2, 2) == "->") pre = ">"
    b = substr(b, RSTART + RLENGTH)
    if (pre == "." || pre == ">") continue                # member calls
    if (name ~ /(^|[^:]):($|[^:])/) continue                # "case X:" / "label:" before a parenthesis
    if (name ~ /^(if|for|while|switch|return|sizeof|catch|defined|alignof|_Alignof|decltype|static_assert|_Static_assert|typeof|__typeof__|__attribute__|__asm__|asm|do|else|case|new|delete|throw|noexcept|operator|static_cast|dynamic_cast|reinterpret_cast|const_cast|volatile|const|int|char|short|long|unsigned|signed|float|double|void|bool|struct|union|enum)$/) continue
    cnt[name]++
  }
  for (k in cnt) printf "%s\t%s\t%s\t%d\n", FILENAME, fn, k, cnt[k] >> COUT
}
BEGIN { LITRE = "/[*]|//|\"|" SQ }
FNR == 1 { reset_file() }
{
  line = $0
  # preprocessor lines (and their continuations) are not code
  if (inpp) { inpp = (line ~ /\\$/); next }
  if (!incmt && line ~ /^[ \t]*#/) {
    if (match(line, /^[ \t]*#[ \t]*define[ \t]+[A-Za-z_][A-Za-z0-9_]*/)) {
      d = substr(line, RSTART, RLENGTH); sub(/^[ \t]*#[ \t]*define[ \t]+/, "", d); print d >> DOUT
    }
    if (match(line, /^[ \t]*#[ \t]*include[ \t]*[<"][^>"]+[>"]/)) {
      inc = substr(line, RSTART, RLENGTH); sub(/^[^<"]*[<"]/, "", inc); sub(/[>"]$/, "", inc)
      printf "%s\t%s\n", FILENAME, inc >> IOUT
    }
    inpp = (line ~ /\\$/); next
  }
  # strip comments, strings, char literals
  out = ""
  while (length(line) > 0) {
    if (incmt) { e = index(line, "*/"); if (e == 0) { line = ""; break } line = substr(line, e + 2); incmt = 0; out = out " "; continue }
    if (match(line, LITRE) == 0) { out = out line; break }
    out = out substr(line, 1, RSTART - 1); tok = substr(line, RSTART, RLENGTH); line = substr(line, RSTART + RLENGTH)
    if (tok == "//") break
    if (tok == "/*") { incmt = 1; continue }
    q = tok; s = 1
    while (s <= length(line)) { ch = substr(line, s, 1); if (ch == "\\") { s += 2; continue } if (ch == q) break; s++ }
    line = substr(line, s + 1); out = out q q
  }
  # walk characters: braces, statement ends, function bodies
  n = length(out)
  for (i = 1; i <= n; i++) {
    c = substr(out, i, 1)
    if (infn) {
      if (c == "{") { depth++ }
      else if (c == "}") {
        depth--
        if (depth == fdepth) {
          emit_calls(curfn)
          printf "%s\t%s\t%d\t%d\t%d\t%s\n", FILENAME, curfn, fstart, FNR, fstatic, fkind >> FOUT
          infn = 0; body = ""; hdr = ""; nst--
          continue
        }
      }
      body = body c
      continue
    }
    if (c == "{") {
      h = trim(hdr)
      if (is_func_header(h) && (nm = fname(h)) != "") {
        infn = 1; curfn = nm; fkind = kind; fstart = FNR; fdepth = depth; depth++; body = ""
        fstatic = (h ~ /(^|[^A-Za-z0-9_])(static|STATIC|PRIVATE)([^A-Za-z0-9_]|$)/) ? 1 : 0
        st[++nst] = "f"
      } else {
        # namespace / extern "C" / class / struct / union bodies stay at declaration level
        if (h ~ /(^|[^A-Za-z0-9_])(namespace|class|struct|union)([^A-Za-z0-9_]|$)/ || h ~ /extern[ \t]*""/) st[++nst] = "s"
        else st[++nst] = "o"
        depth++
      }
      hdr = ""; continue
    }
    if (c == "}") { if (nst > 0) nst--; depth--; hdr = ""; continue }
    if (c == ";") { hdr = ""; continue }
    if (nst > 0 && st[nst] == "o") continue                 # inside enum / initialiser: ignore
    hdr = hdr c
  }
  if (!infn) hdr = hdr " "; else body = body " "
}
'

# ---------------------------------------------------------------- 2. classify callees
# defined names: plain function names (strip Class:: for matching too)
awk -F'\t' '$6=="func"{print $2"\t"$1; n=$2; sub(/.*::/, "", n); if (n!=$2) print n"\t"$1}' "$OUT/functions.tsv" | sort -u -t"$(printf '\t')" -k1,1 > "$OUT/.defined"
sort -u "$OUT/.macros" -o "$OUT/.macros"
awk -F'\t' 'FILENAME==ARGV[1]{m[$1]=1; next} FILENAME==ARGV[2]{d[$1]=$2; next}
  { w = ($3 in d) ? d[$3] : (($3 in m || $3 ~ /^[A-Z][A-Z0-9_]*$/) ? "macro" : "external"); print $1"\t"$2"\t"$3"\t"$4"\t"w }' \
  "$OUT/.macros" "$OUT/.defined" "$OUT/.calls.raw" | sort > "$OUT/calls.tsv"

# external callees: find the declaring header in the repo (first match), count callers
printf 'callee\tkind\tdeclared_in\tcallers\n' > "$OUT/externals.tsv"
awk -F'\t' '$5=="external"{c[$3]++} END{for (k in c) print k"\t"c[k]}' "$OUT/calls.tsv" | sort -t"$(printf '\t')" -k2,2nr -k1,1 | head -400 |
while IFS="$(printf '\t')" read -r callee n; do
  base=${callee##*::}; kind=function
  hits=$(grep -rlE --include='*.h' --include='*.hpp' --include='*.hh' "^[[:space:]]*#[[:space:]]*define[[:space:]]+${base}([^A-Za-z0-9_]|$)" "$REPO" 2>/dev/null | grep -v '/.git/')
  if [ -n "$hits" ]; then kind=macro
  else hits=$(grep -rlE --include='*.h' --include='*.hpp' --include='*.hh' "(^|[^A-Za-z0-9_])${base}[[:space:]]*\(" "$REPO" 2>/dev/null | grep -v '/.git/'); fi
  if [ -n "$hits" ]; then
    cnt=$(printf '%s\n' "$hits" | wc -l | tr -d ' ')
    decl=$(printf '%s\n' "$hits" | awk '{print length($0)"\t"$0}' | sort -n | head -1 | cut -f2-)   # shortest path first
    decl=${decl#"$REPO"/}; [ "$cnt" -gt 1 ] && decl="$decl (+$((cnt-1)) more)"
  else decl="? not found (system/library, function pointer or generated)"; fi
  printf '%s\t%s\t%s\t%s\n' "$callee" "$kind" "$decl" "$n"
done >> "$OUT/externals.tsv"

# ---------------------------------------------------------------- 3. summary.md
{
  echo "# Code map"
  echo "Generated $(date '+%Y-%m-%d %H:%M') by codemap.sh for: $*"
  echo "Files: $NFILES. Heuristic: verify in the code before relying on a detail."
  echo
  echo "## External dependencies (mock / stub candidates)"
  echo "Called from the scanned code but not defined in it. System/library calls are usually NOT mocked."
  echo
  echo "| Function | Declared in | Callers |"
  echo "|----------|-------------|---------|"
  tail -n +2 "$OUT/externals.tsv" | awk -F'\t' '$2=="function"' | head -80 | awk -F'\t' '{print "| `"$1"` | "$3" | "$4" |"}'
  echo
  echo "## Macros used like functions (defined in repo headers)"
  echo "Usually not mocked directly: check how the test build defines them (test config header, port layer)."
  echo
  tail -n +2 "$OUT/externals.tsv" | awk -F'\t' '$2=="macro" && n<150 {printf "%s`%s`", sep, $1; sep=", "; n++} END{print (n>=150 ? " ... (see externals.tsv)" : "")}'
  echo
  echo "## Per file"
  while IFS= read -r f; do
    nf=$(awk -F'\t' -v f="$f" '$1==f' "$OUT/functions.tsv" | wc -l | tr -d ' ')
    [ "$nf" = 0 ] && ! grep -q "^$f	" "$OUT/includes.tsv" && continue
    echo
    echo "### ${f#./}"
    incs=$(awk -F'\t' -v f="$f" '$1==f{printf "%s%s", sep, $2; sep=", "}' "$OUT/includes.tsv")
    [ -n "$incs" ] && echo "Includes: $incs"
    [ "$nf" = 0 ] && continue
    echo
    echo "| Function | Lines | static | Calls to scanned code (defining file if other) | External calls |"
    echo "|----------|-------|--------|----------------------|----------------|"
    awk -F'\t' -v f="$f" '
      NR==FNR { if ($1==f) { key=$2; if ($5=="external") ext[key]=ext[key] (ext[key]?", ":"") $3; else if ($5!="macro") { d=($5==f)?"":" ("$5")"; sub(/^\.\//, "", d); inn[key]=inn[key] (inn[key]?", ":"") $3 d } } next }
      $1==f { printf "| `%s` | %d-%d | %s | %s | %s |\n", $2, $3, $4, ($5?"yes":""), inn[$2], ext[$2] }' \
      "$OUT/calls.tsv" "$OUT/functions.tsv"
  done < "$LIST"
} > "$OUT/summary.md"

rm -f "$OUT/.calls.raw" "$OUT/.defined" "$OUT/.macros" "$LIST"
echo "codemap: $NFILES files, $(wc -l < "$OUT/functions.tsv" | tr -d ' ') functions/blocks, $(awk -F'\t' '$2=="function"' "$OUT/externals.tsv" | wc -l | tr -d ' ') external functions, $(awk -F'\t' '$2=="macro"' "$OUT/externals.tsv" | wc -l | tr -d ' ') macros -> $OUT/summary.md"
