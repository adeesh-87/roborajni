#!/usr/bin/env bash
# Installs `mb` into ~/.local/bin and the /team skill into ~/.claude/skills/team.
# Files are copied, so re-run this after pulling changes.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"

mkdir -p "$HOME/.local/bin" "$HOME/.claude/skills"
install -m 755 "$here/bin/mb" "$HOME/.local/bin/mb"
rm -rf "$HOME/.claude/skills/team"
cp -r "$here/skill" "$HOME/.claude/skills/team"

echo "installed: $HOME/.local/bin/mb"
echo "installed: $HOME/.claude/skills/team"
command -v mb >/dev/null || echo "note: add ~/.local/bin to your PATH"
