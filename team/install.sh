#!/usr/bin/env bash
# Optional: puts this skill's `mb` on PATH as ~/.local/bin/mb (a symlink, so it
# follows the skill folder). Without it, agents run `python3 <skill>/bin/mb`.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"

chmod +x "$here/bin/mb" "$here/bin/lock.sh" 2>/dev/null || true
mkdir -p "$HOME/.local/bin"
ln -sfn "$here/bin/mb" "$HOME/.local/bin/mb"

echo "linked: $HOME/.local/bin/mb -> $here/bin/mb"
command -v mb >/dev/null || echo "note: add ~/.local/bin to your PATH"
