#!/usr/bin/env bash
# ============================================================================
# ONE-COMMAND SETUP for the darkfactory on a MacBook.
#
#   ./scripts/setup_macos.sh
#
# Safe to run multiple times (it skips what's already done). It will:
#   1. check you're on macOS and have the basics (installs Homebrew/Python/
#      Ollama if missing — it asks before installing anything)
#   2. create the Python environment and install the factory
#   3. run the 13-test verification suite (proves everything works)
#   4. do a free offline dry-run (no AI tokens used)
#   5. help you sign in to Ollama and pick your models
#   6. install the 24/7 background service (auto-start, auto-restart)
#   7. optionally keep the Mac awake on power so the factory never sleeps
# ============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"

say()  { printf "\n\033[1;36m▶ %s\033[0m\n" "$*"; }
ok()   { printf "\033[1;32m  ✓ %s\033[0m\n" "$*"; }
warn() { printf "\033[1;33m  ! %s\033[0m\n" "$*"; }
ask()  { read -r -p "  $1 [y/N] " a; [[ "${a:-n}" =~ ^[Yy] ]]; }

# ---------------------------------------------------------------- 0. macOS?
if [[ "$(uname -s)" != "Darwin" ]]; then
  warn "This script is for macOS. On other systems, follow README manual steps."
  exit 1
fi

# ------------------------------------------------------------- 1. basics
say "Step 1/7 — checking the basics"

if ! command -v brew >/dev/null 2>&1; then
  warn "Homebrew (the Mac app installer for developers) is not installed."
  if ask "Install Homebrew now? (opens the official installer)"; then
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    eval "$([ -x /opt/homebrew/bin/brew ] && /opt/homebrew/bin/brew shellenv || /usr/local/bin/brew shellenv)"
  else
    warn "Cannot continue without Homebrew. Re-run when ready."; exit 1
  fi
fi
ok "Homebrew present"

if ! command -v python3 >/dev/null 2>&1; then
  say "Installing Python…"; brew install python
fi
ok "Python $(python3 --version | cut -d' ' -f2) present"

if ! command -v ollama >/dev/null 2>&1; then
  warn "Ollama (runs the AI models) is not installed."
  if ask "Install Ollama now?"; then brew install ollama; else
    warn "Cannot continue without Ollama."; exit 1
  fi
fi
ok "Ollama present"

# make sure the Ollama daemon is running (the app or brew service)
if ! curl -s --max-time 3 http://localhost:11434/api/version >/dev/null 2>&1; then
  say "Starting the Ollama background service…"
  brew services start ollama >/dev/null 2>&1 || (nohup ollama serve >/dev/null 2>&1 &)
  sleep 3
fi
if curl -s --max-time 3 http://localhost:11434/api/version >/dev/null 2>&1; then
  ok "Ollama daemon is running"
else
  warn "Could not reach Ollama at localhost:11434 — open the Ollama app once, then re-run this script."
  exit 1
fi

# ------------------------------------------------- 2. python environment
say "Step 2/7 — installing the factory"
if [ ! -x .venv/bin/python ]; then python3 -m venv .venv; fi
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -e .
ok "Installed into $REPO_DIR/.venv"

# ------------------------------------------------------ 3. verification
say "Step 3/7 — running the 13-test verification suite"
.venv/bin/python -m unittest tests.test_contracts 2>&1 | tail -3
ok "All contracts verified on THIS machine"

# ---------------------------------------------------------- 4. dry run
say "Step 4/7 — free offline dry-run (no AI tokens, sample data)"
DARKFACTORY_LLM=mock .venv/bin/python -m darkfactory once product_research
DARKFACTORY_LLM=mock .venv/bin/python -m darkfactory once digest
ok "Pipeline works end-to-end. See workspace/reports/ and workspace/artifacts/"

# ------------------------------------------------------- 5. AI models
say "Step 5/7 — AI models"
echo "  The factory uses Ollama Cloud models: the heavy AI runs in Ollama's"
echo "  cloud, your MacBook only orchestrates. One-time sign-in required."
if ask "Sign in to Ollama now? (opens a browser)"; then
  ollama signin || warn "Sign-in did not complete — you can run 'ollama signin' later."
fi
if ! ollama list 2>/dev/null | grep -q "qwen3:8b"; then
  if ask "Download the small local fallback model qwen3:8b (~5 GB, one time)?"; then
    ollama pull qwen3:8b
  fi
fi
echo
echo "  Your models right now:"
ollama list 2>/dev/null | sed 's/^/    /' || true
warn "IMPORTANT: open config/harness.yaml and set planner_model / worker_model"
warn "to names from the list above (cloud models end in -cloud)."

# ------------------------------------------------- 6. 24/7 service
say "Step 6/7 — install the 24/7 background service"
echo "  This makes the factory start at login and restart if it ever crashes."
if ask "Install and start the 24/7 service now?"; then
  PYTHON_BIN="$REPO_DIR/.venv/bin/python" ./scripts/install_macos.sh
else
  warn "Skipped. Run ./scripts/install_macos.sh whenever you're ready."
fi

# ------------------------------------------------ 7. keep-awake option
say "Step 7/7 — keep the Mac awake on power (optional)"
echo "  A MacBook sleeps when idle or when the lid closes — the factory then"
echo "  pauses and catches up on wake (nothing is lost, runs just happen later)."
echo "  For true 24/7, keep it plugged in and prevent sleep while on power."
if ask "Prevent sleep while plugged in? (asks for your password; undo: sudo pmset -c sleep 10)"; then
  sudo pmset -c sleep 0 && ok "Mac will stay awake while on the charger (lid open)."
fi

say "DONE — your dark factory is set up"
cat <<'EOF'
  Daily driver (from this folder):
    ./df status        # is everything healthy?
    ./df approvals     # what is waiting for YOUR signature?
    ./df approve 3     # sign off action #3
    ./df candidates    # the product funnel
    open workspace/reports/    # your daily digest lives here

  Next moves (in order of impact):
    1. Edit config/objectives.yaml — YOUR categories, budget, margin floor
    2. Set your model names in config/harness.yaml (from `ollama list`)
    3. Read the "Owner's Manual" section of README.md
EOF
