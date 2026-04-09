#!/usr/bin/env bash
# install-skill.sh - Install wiki-knowledge skill into openclaw agents
#
# Symlink behavior:
#   - If target symlink already exists: prompt for confirmation (or use --force to overwrite)
#   - If target is a real directory (not a symlink): refuse to overwrite, show error
#   - --force: overwrite existing symlinks without prompting
#
# Usage:
#   bash install-skill.sh [skills-dir]   # install into a specific directory
#   bash install-skill.sh --force        # overwrite existing symlinks silently
#
# Default behavior (no args): searches for openclaw agent frameworks at
#   $OPENCLAW_DIR (default: ~/openclaw/orchestrator-framework)
#   $PARALLEL_DIR (default: ~/openclaw/parallel-framework)
set -e

FORCE=false
CUSTOM_DIR=""
for arg in "$@"; do
    [ "$arg" = "--force" ] && FORCE=true
    [ -d "$arg" ] && CUSTOM_DIR="$arg"
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_SRC="$SCRIPT_DIR/skill/wiki-knowledge"
OPENCLAW_DIR="${OPENCLAW_DIR:-$HOME/openclaw/orchestrator-framework}"
PARALLEL_DIR="${PARALLEL_DIR:-$HOME/openclaw/parallel-framework}"

install_skill_to_dir() {
    local skills_dir="$1"
    local label="$2"
    local link="$skills_dir/wiki-knowledge"

    mkdir -p "$skills_dir"

    if [ -e "$link" ] && [ ! -L "$link" ]; then
        echo "  ✗ SKIP $label: $link exists and is not a symlink (manual entry?)"
        echo "    Remove it manually if you want to replace it."
        return
    fi

    if [ -L "$link" ]; then
        if [ "$FORCE" = true ]; then
            rm "$link"
            echo "  [overwrite] $label"
        else
            read -p "  Symlink already exists in '$label'. Overwrite? [y/N] " answer
            if [[ "$answer" =~ ^[Yy]$ ]]; then
                rm "$link"
            else
                echo "  Skipped $label"
                return
            fi
        fi
    fi

    ln -s "$SKILL_SRC" "$link"
    echo "  ✓ Linked into $label"
}

install_to_framework() {
    local target_dir="$1"
    local agents_dir="$target_dir/agents"

    if [ ! -d "$agents_dir" ]; then
        echo "  Skipping $(basename $target_dir) (no agents/ directory found)"
        return
    fi

    for agent_dir in "$agents_dir"/*/; do
        if [ -d "$agent_dir" ]; then
            local agent_name
            agent_name="$(basename "$agent_dir")"
            install_skill_to_dir "$agent_dir/skills/knowledge" "$agent_name"
        fi
    done
}

echo "Installing wiki-knowledge skill..."
echo "(Use --force to skip confirmation prompts)"
echo ""

# Mode 1: explicit skills directory provided as argument
if [ -n "$CUSTOM_DIR" ]; then
    echo "[ custom: $CUSTOM_DIR ]"
    install_skill_to_dir "$CUSTOM_DIR" "$(basename $CUSTOM_DIR)"

# Mode 2: scan openclaw framework directories
else
    if [ -d "$OPENCLAW_DIR" ]; then
        echo "[ orchestrator-framework ]"
        install_to_framework "$OPENCLAW_DIR"
    else
        echo "orchestrator-framework not found at $OPENCLAW_DIR, skipping"
    fi

    echo ""

    if [ -d "$PARALLEL_DIR" ]; then
        echo "[ parallel-framework ]"
        install_to_framework "$PARALLEL_DIR"
    else
        echo "parallel-framework not found at $PARALLEL_DIR, skipping"
    fi
fi

echo ""
echo "Done. Restart any running agents for the skill to take effect."
