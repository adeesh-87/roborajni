#!/usr/bin/env bash
# kb-id.sh [REPO_DIR] - identify a codebase so its knowledge base can be found again.
# Prints:  id=<folder name under resources/kb/>   root=<repo root>   remote=<origin url or none>
# The id comes from the git "origin" URL, so every clone and every machine maps to the same KB.
# Without a remote it falls back to the folder name plus a hash of the path (local only).
set -u
dir=${1:-.}
root=$(git -C "$dir" rev-parse --show-toplevel 2>/dev/null) || root=$(cd "$dir" 2>/dev/null && pwd -P) || { echo "kb-id: no such dir $dir" >&2; exit 2; }
url=$(git -C "$root" remote get-url origin 2>/dev/null || true)
if [ -n "$url" ]; then
  # https://user@host/a/b.git | git@host:a/b.git | ssh://git@host:22/a/b -> host-a-b (proxy/local prefixes dropped)
  id=$(printf '%s' "$url" | sed -E 's#^[a-zA-Z+]+://##; s#^[^@/]*@##; s#\.git/?$##; s#/+$##; s#:[0-9]+/#/#; s#^(127\.0\.0\.1|localhost)[^/]*/(git/)?#local/#; s#[:/]+#-#g; s#[^A-Za-z0-9._-]#_#g' | tr 'A-Z' 'a-z')
else
  h=$(printf '%s' "$root" | cksum | cut -d' ' -f1)
  id="local-$(basename "$root" | tr -d '\n' | tr -c 'A-Za-z0-9._-' '_' | tr 'A-Z' 'a-z')-$h"
fi
echo "id=$id"
echo "root=$root"
echo "remote=${url:-none}"
