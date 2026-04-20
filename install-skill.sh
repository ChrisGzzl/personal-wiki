#!/usr/bin/env bash
# install-skill.sh - Install wiki skills into openclaw agents
# Uses cp (not symlinks) because OpenClaw rejects symlink-escape (realpath outside skills root)
set -e

FORCE=false
CUSTOM_DIR=""
for arg in "$@"; do
    [ "$arg" = "--force" ] && FORCE=true
    [ -d "$arg" ] && CUSTOM_DIR="$arg"
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS=("wiki-knowledge" "wiki-capture" "wiki-ask" "wiki-promote")
OPENCLAW_DIR="${OPENCLAW_DIR:-$HOME/openclaw/orchestrator-framework}"
PARALLEL_DIR="${PARALLEL_DIR:-$HOME/openclaw/parallel-framework}"

install_skill() {
    local skills_dir="$1"
    local skill_name="$2"
    local label="$3"
    local src="$SCRIPT_DIR/skill/$skill_name"
    local dest="$skills_dir/$skill_name"

    if [ ! -d "$src" ]; then
        echo "  ✗ SKIP $skill_name: source not found at $src"
        return 1
    fi

    mkdir -p "$skills_dir"

    if [ -d "$dest" ]; then
        if [ "$FORCE" = true ]; then
            rm -rf "$dest"
        else
            read -p "  Already exists: $label/$skill_name. Overwrite? [y/N] " answer
            if [[ "$answer" =~ ^[Yy]$ ]]; then
                rm -rf "$dest"
            else
                echo "  Skipped $label/$skill_name"
                return 0
            fi
        fi
    fi

    cp -r "$src" "$dest"
    echo "  ✓ $label/$skill_name"
}

install_all_skills() {
    local skills_dir="$1"
    local label="$2"
    for skill_name in "${SKILLS[@]}"; do
        install_skill "$skills_dir" "$skill_name" "$label"
    done
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
            install_all_skills "$agent_dir/skills" "$agent_name"
        fi
    done
}

echo "Installing wiki skills: ${SKILLS[*]}..."
echo "(Use --force to skip confirmation prompts)"
echo ""

# Mode 1: explicit skills directory provided as argument
if [ -n "$CUSTOM_DIR" ]; then
    echo "[ custom: $CUSTOM_DIR ]"
    install_all_skills "$CUSTOM_DIR" "$(basename $CUSTOM_DIR)"

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
echo "Done. Restart any running agents for the skills to take effect."
