#!/bin/bash
# Super Pick — one-time setup
# Symlinks the skill source from this repo into ~/.claude/skills/ so Claude Code
# can find it. Idempotent: safe to run multiple times.

set -euo pipefail

REPO_SKILL="$(cd "$(dirname "$0")/skill" && pwd)"
TARGET="$HOME/.claude/skills/super-pick"

mkdir -p "$HOME/.claude/skills"

if [ -L "$TARGET" ]; then
  echo "Removing existing symlink at $TARGET"
  rm "$TARGET"
elif [ -e "$TARGET" ]; then
  echo "ERROR: $TARGET exists and is not a symlink. Move it aside before re-running."
  exit 1
fi

ln -s "$REPO_SKILL" "$TARGET"
echo "Symlinked: $TARGET -> $REPO_SKILL"

echo ""
echo "Setup complete. Test by running:"
echo "  cd \"$(dirname "$REPO_SKILL")/.."
echo "  claude"
echo "  > find me a navy linen shirt under 2000"
