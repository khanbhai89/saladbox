#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════
# Saladbox — One-command setup for a new Mac
# Usage: ./setup.sh
# ══════════════════════════════════════════════════════════════
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info()  { echo -e "${BLUE}[INFO]${NC} $1"; }
ok()    { echo -e "${GREEN}[OK]${NC}   $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
fail()  { echo -e "${RED}[FAIL]${NC} $1"; }

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo ""
echo "  ╔═══════════════════════════════════╗"
echo "  ║        SALADBOX SETUP             ║"
echo "  ║  Local AI Assistant for macOS     ║"
echo "  ╚═══════════════════════════════════╝"
echo ""

# ── 1. Check macOS ──────────────────────────────────────────
if [[ "$(uname)" != "Darwin" ]]; then
  fail "This setup script is designed for macOS."
  exit 1
fi
ok "macOS detected: $(sw_vers -productVersion)"

# ── 2. Homebrew ─────────────────────────────────────────────
if ! command -v brew &>/dev/null; then
  info "Installing Homebrew..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  # Add brew to path for Apple Silicon
  if [[ -f /opt/homebrew/bin/brew ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  fi
  ok "Homebrew installed"
else
  ok "Homebrew found: $(brew --version | head -1)"
fi

# ── 3. Python 3.11+ ────────────────────────────────────────
PYTHON=""
for py in python3.12 python3.11 python3; do
  if command -v "$py" &>/dev/null; then
    version=$("$py" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
    major=$(echo "$version" | cut -d. -f1)
    minor=$(echo "$version" | cut -d. -f2)
    if [[ "$major" -ge 3 && "$minor" -ge 11 ]]; then
      PYTHON="$py"
      break
    fi
  fi
done

if [[ -z "$PYTHON" ]]; then
  info "Installing Python 3.12 via Homebrew..."
  brew install python@3.12
  PYTHON="python3.12"
  ok "Python 3.12 installed"
else
  ok "Python found: $($PYTHON --version)"
fi

# ── 4. Node.js (for Electron) ──────────────────────────────
if ! command -v node &>/dev/null; then
  info "Installing Node.js via Homebrew..."
  brew install node
  ok "Node.js installed: $(node --version)"
else
  ok "Node.js found: $(node --version)"
fi

# ── 5. Ollama ───────────────────────────────────────────────
if ! command -v ollama &>/dev/null; then
  info "Installing Ollama..."
  brew install ollama
  ok "Ollama installed"
else
  ok "Ollama found: $(ollama --version 2>&1 || echo 'installed')"
fi

# Start Ollama if not running
if ! pgrep -x ollama &>/dev/null; then
  info "Starting Ollama service..."
  ollama serve &>/dev/null &
  sleep 2
  ok "Ollama service started"
else
  ok "Ollama already running"
fi

# ── 6. Pull default model ──────────────────────────────────
DEFAULT_MODEL="qwen3:14b"
if ! ollama list 2>/dev/null | grep -q "$DEFAULT_MODEL"; then
  info "Pulling default model ($DEFAULT_MODEL)... this may take a while."
  ollama pull "$DEFAULT_MODEL"
  ok "Model $DEFAULT_MODEL pulled"
else
  ok "Model $DEFAULT_MODEL already available"
fi

# Also pull vision model
VISION_MODEL="qwen2.5vl:latest"
if ! ollama list 2>/dev/null | grep -q "qwen2.5vl"; then
  info "Pulling vision model ($VISION_MODEL)..."
  ollama pull "$VISION_MODEL"
  ok "Vision model pulled"
else
  ok "Vision model already available"
fi

# ── 7. Python virtual environment ───────────────────────────
VENV_DIR="$PROJECT_DIR/.venv"
if [[ ! -d "$VENV_DIR" ]]; then
  info "Creating Python virtual environment..."
  $PYTHON -m venv "$VENV_DIR"
  ok "Virtual environment created at $VENV_DIR"
else
  ok "Virtual environment exists"
fi

# Activate venv
source "$VENV_DIR/bin/activate"
ok "Activated venv ($($PYTHON --version))"

# ── 8. Install Python dependencies ─────────────────────────
info "Installing Python dependencies..."
pip install --upgrade pip -q
pip install -e ".[dev]" -q
ok "Python dependencies installed"

# ── 9. Install Playwright browsers ─────────────────────────
info "Installing Playwright browsers..."
playwright install chromium 2>/dev/null || python -m playwright install chromium
ok "Playwright browsers installed"

# ── 10. Install Electron dependencies ──────────────────────
info "Installing Electron dependencies..."
cd "$PROJECT_DIR/electron"
npm install --silent 2>/dev/null
cd "$PROJECT_DIR"
ok "Electron dependencies installed"

# ── 11. HuggingFace setup ──────────────────────────────────
ENV_FILE="$PROJECT_DIR/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  info "Creating .env file..."
  cat > "$ENV_FILE" <<'ENVEOF'
# Saladbox environment configuration

# HuggingFace (required for FLUX image generation)
# Get your token at: https://huggingface.co/settings/tokens
# HF_TOKEN=hf_...

# OpenRouter API (optional, for cloud models)
# OPENROUTER_API_KEY=sk-or-...

# Telegram Bot (optional)
# TELEGRAM_BOT_TOKEN=...

# Slack Bot (optional)
# SLACK_BOT_TOKEN=xoxb-...
# SLACK_APP_TOKEN=xapp-...
ENVEOF
  ok ".env template created"
else
  ok ".env file exists"
fi

# Check if HF token is set
if grep -q "^HF_TOKEN=hf_" "$ENV_FILE" 2>/dev/null; then
  ok "HuggingFace token configured"
else
  warn "HuggingFace token not set. Image generation (FLUX) needs it."
  warn "  1. Get a token at: https://huggingface.co/settings/tokens"
  warn "  2. Add it to .env: HF_TOKEN=hf_your_token_here"
  warn "  3. Or set it in Settings > General > HuggingFace in the app"
fi

# ── 12. Login to HuggingFace if token exists ────────────────
if grep -q "^HF_TOKEN=hf_" "$ENV_FILE" 2>/dev/null; then
  HF_TOKEN=$(grep "^HF_TOKEN=" "$ENV_FILE" | cut -d= -f2)
  info "Logging in to HuggingFace..."
  python -c "from huggingface_hub import login; login(token='$HF_TOKEN', add_to_git_credential=False)" 2>/dev/null && \
    ok "HuggingFace login successful" || \
    warn "HuggingFace login failed (install huggingface_hub if needed)"
fi

# ── 13. Run setup wizard if needed ──────────────────────────
if [[ ! -f "$PROJECT_DIR/config.yaml" ]]; then
  info "Running first-time setup wizard..."
  python -m saladbox --setup
fi

# ── Summary ─────────────────────────────────────────────────
echo ""
echo "  ╔═══════════════════════════════════╗"
echo "  ║      SETUP COMPLETE! 🎉          ║"
echo "  ╚═══════════════════════════════════╝"
echo ""
echo "  Quick start:"
echo "    # Terminal (CLI mode):"
echo "    source .venv/bin/activate && python -m saladbox"
echo ""
echo "    # Desktop app (Electron):"
echo "    cd electron && npm start"
echo ""
echo "    # Re-run setup wizard:"
echo "    python -m saladbox --setup"
echo ""
echo "  Settings to configure in the app:"
echo "    • General → HuggingFace token (for image generation)"
echo "    • Image Gen → Backend, model, quality"
echo "    • Connections → Telegram, Slack, MCP servers"
echo ""
