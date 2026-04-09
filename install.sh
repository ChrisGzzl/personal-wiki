#!/usr/bin/env bash
# install.sh - One-step install for personal-wiki
# Usage: bash install.sh [wiki-root-path]
set -e

WIKI_ROOT="${1:-$HOME/wiki}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==============================="
echo "  personal-wiki installer"
echo "==============================="
echo ""

# ── 1. Install base Python package ──────────────────────────────────────────
echo "[1/5] Installing wiki-cli..."
pip install -e "$SCRIPT_DIR" --quiet 2>/dev/null || \
pip install -e "$SCRIPT_DIR" --break-system-packages --quiet 2>/dev/null || {
    echo "  ✗ pip install failed. Make sure pip is available."
    exit 1
}

if ! command -v wiki &> /dev/null; then
    echo "  ✗ 'wiki' command not found. Add pip's bin dir to PATH:"
    echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
    exit 1
fi
echo "  ✓ wiki command ready"

# ── 2. Initialize wiki data directory ───────────────────────────────────────
echo ""
echo "[2/5] Initializing wiki at $WIKI_ROOT..."
wiki init "$WIKI_ROOT"

# ── 3. LLM provider setup wizard ────────────────────────────────────────────
echo ""
echo "[3/5] LLM configuration"
echo "  Choose your LLM provider:"
echo "  1) Anthropic  (claude-3-5-sonnet-latest)"
echo "  2) OpenAI     (gpt-4o)"
echo "  3) Compatible (Stepfun, Qianfan, Ollama, etc.)"
echo ""
read -p "  Provider [1/2/3, default=1]: " provider_choice
provider_choice="${provider_choice:-1}"

case "$provider_choice" in
    2)
        PROVIDER="openai"
        DEFAULT_MODEL="gpt-4o"
        DEFAULT_BASE_URL="https://api.openai.com/v1"
        SDK_EXTRA="openai"
        ;;
    3)
        PROVIDER="openai"
        SDK_EXTRA="openai"
        echo ""
        read -p "  Base URL (e.g. https://api.stepfun.com/v1): " DEFAULT_BASE_URL
        DEFAULT_BASE_URL="${DEFAULT_BASE_URL:-https://api.openai.com/v1}"
        read -p "  Model name (e.g. gpt-4o): " MODEL
        MODEL="${MODEL:-gpt-4o}"
        ;;
    *)
        PROVIDER="anthropic"
        DEFAULT_MODEL="claude-3-5-sonnet-latest"
        DEFAULT_BASE_URL=""
        SDK_EXTRA="anthropic"
        ;;
esac

echo ""
if [ -z "$MODEL" ]; then
    read -p "  Model [default: $DEFAULT_MODEL]: " MODEL
    MODEL="${MODEL:-$DEFAULT_MODEL}"
fi

echo ""
echo "  Enter your API key."
echo "  (input is hidden, stored in $WIKI_ROOT/config.yaml)"
read -s -p "  API key: " API_KEY
echo ""

if [ -z "$API_KEY" ]; then
    echo "  ⚠ No API key entered. You can add it later to $WIKI_ROOT/config.yaml"
fi

# Install SDK
echo ""
echo "  Installing $SDK_EXTRA SDK..."
pip install -e "$SCRIPT_DIR[$SDK_EXTRA]" --quiet 2>/dev/null || \
pip install -e "$SCRIPT_DIR[$SDK_EXTRA]" --break-system-packages --quiet 2>/dev/null || \
echo "  ⚠ SDK install failed, you may need to install it manually: pip install $SDK_EXTRA"

# Write config.yaml
CONFIG_FILE="$WIKI_ROOT/config.yaml"

if [ "$PROVIDER" = "anthropic" ]; then
    cat > "$CONFIG_FILE" << YAML
llm:
  provider: "anthropic"
  model: "$MODEL"
  api_key: "$API_KEY"
  max_tokens: 16000
  temperature: 0.3

# 可选：为不同操作指定不同模型（不填则都使用 llm.model）
# models:
#   ingest: "claude-3-5-sonnet-latest"
#   query:  "claude-haiku-3-5"
#   lint:   "claude-haiku-3-5"

paths:
  wiki_root: "$WIKI_ROOT"
  raw_dir: "raw"
  wiki_dir: "wiki"
  outputs_dir: "outputs"
  schema_file: "schema.md"
  state_file: ".wiki_state.json"

behavior:
  lint_stale_days: 30
  max_raw_batch: 10
  language: "zh-CN"
YAML
else
    cat > "$CONFIG_FILE" << YAML
llm:
  provider: "openai"
  base_url: "$DEFAULT_BASE_URL"
  model: "$MODEL"
  api_key: "$API_KEY"
  max_tokens: 8000
  temperature: 0.3

# 可选：为不同操作指定不同模型（不填则都使用 llm.model）
# models:
#   ingest: "$MODEL"
#   query:  "$MODEL"
#   lint:   "$MODEL"

paths:
  wiki_root: "$WIKI_ROOT"
  raw_dir: "raw"
  wiki_dir: "wiki"
  outputs_dir: "outputs"
  schema_file: "schema.md"
  state_file: ".wiki_state.json"

behavior:
  lint_stale_days: 30
  max_raw_batch: 10
  language: "zh-CN"
YAML
fi

echo "  ✓ config.yaml configured (provider: $PROVIDER, model: $MODEL)"

# ── 4. Add WIKI_ROOT to shell profile ───────────────────────────────────────
echo ""
echo "[4/5] Shell environment setup..."

SHELL_RC="$HOME/.bashrc"
[ -f "$HOME/.zshrc" ] && SHELL_RC="$HOME/.zshrc"

EXPORT_LINE="export WIKI_ROOT=$WIKI_ROOT"
if grep -q "WIKI_ROOT" "$SHELL_RC" 2>/dev/null; then
    echo "  ✓ WIKI_ROOT already in $SHELL_RC"
else
    echo "" >> "$SHELL_RC"
    echo "# personal-wiki" >> "$SHELL_RC"
    echo "$EXPORT_LINE" >> "$SHELL_RC"
    echo "  ✓ Added WIKI_ROOT to $SHELL_RC"
fi
export WIKI_ROOT="$WIKI_ROOT"

# ── 5. Schema reminder + optional openclaw skill ────────────────────────────
echo ""
echo "[5/5] Final setup..."

echo ""
echo "  ┌─ Next: edit your schema.md ──────────────────────────────────┐"
echo "  │  $WIKI_ROOT/schema.md                                         "
echo "  │  Fill in your focus areas, background, and thinking style.   "
echo "  │  This directly affects how the LLM compiles your knowledge.  "
echo "  └──────────────────────────────────────────────────────────────┘"

# Optional openclaw skill
OPENCLAW_DIR="${OPENCLAW_DIR:-$HOME/openclaw/orchestrator-framework}"
PARALLEL_DIR="${PARALLEL_DIR:-$HOME/openclaw/parallel-framework}"

if [ -d "$OPENCLAW_DIR" ] || [ -d "$PARALLEL_DIR" ]; then
    echo ""
    read -p "  openclaw detected. Install wiki-knowledge skill into agents? [y/N] " answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        bash "$SCRIPT_DIR/install-skill.sh"
    fi
fi

# ── Done ────────────────────────────────────────────────────────────────────
echo ""
echo "==============================="
echo "  Installation complete!"
echo "==============================="
echo ""
echo "Run 'source $SHELL_RC' or open a new terminal, then:"
echo ""
echo "  wiki status                           # check everything is working"
echo "  wiki ingest --url 'https://...'       # ingest your first article"
echo "  wiki query 'What do I know about X?'  # query your knowledge base"
echo ""
