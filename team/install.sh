#!/usr/bin/env bash
# Optional: puts this skill's `mb` and `crew` on PATH in ~/.local/bin (symlinks, so they
# follow the skill folder). Without it, agents run `python3 <skill>/bin/mb`.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"

chmod +x "$here/bin/mb" "$here/bin/crew" "$here/bin/lock.sh" 2>/dev/null || true
mkdir -p "$HOME/.local/bin"
for tool in mb crew; do
  ln -sfn "$here/bin/$tool" "$HOME/.local/bin/$tool"
  echo "linked: $HOME/.local/bin/$tool -> $here/bin/$tool"
done
command -v mb >/dev/null || echo "note: add ~/.local/bin to your PATH"
