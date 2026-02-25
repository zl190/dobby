#!/bin/bash
# Install Dobby -- clone to ~/.claude/skills/dobby
DEST="${HOME}/.claude/skills/dobby"
if [ -d "$DEST" ]; then
    echo "Dobby is already installed at $DEST"
    echo "To update: cd $DEST && git pull"
    exit 0
fi
mkdir -p "$(dirname "$DEST")"
git clone https://github.com/zl190/dobby.git "$DEST"
echo ""
echo "  Requirements: claude CLI, tmux, uv"
echo "Dobby installed. Use /dobby in any Claude Code session."
