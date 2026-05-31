#!/usr/bin/env bash
# init.sh — Armory project environment setup script
# Run this to install dependencies and prepare the development environment.

set -e

echo "=== Armory — Interactive Pentest Payload Dictionary ==="
echo ""

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 11 ]; }; then
  echo "ERROR: Python 3.11+ is required. Found: Python $PYTHON_VERSION"
  echo "Please install Python 3.11 or higher and re-run this script."
  exit 1
fi
echo "[OK] Python $PYTHON_VERSION detected"

# Create and activate virtual environment if not already in one
if [ -z "$VIRTUAL_ENV" ]; then
  if [ ! -d ".venv" ]; then
    echo "[*] Creating virtual environment in .venv..."
    python3 -m venv .venv
  fi
  echo "[*] Activating virtual environment..."
  # shellcheck disable=SC1091
  source .venv/bin/activate
  echo "[OK] Virtual environment active: $VIRTUAL_ENV"
else
  echo "[OK] Already in virtual environment: $VIRTUAL_ENV"
fi

# Install the package with all dependencies
echo ""
echo "[*] Installing Armory and dependencies..."
pip install --upgrade pip --quiet
pip install -e ".[dev]" 2>/dev/null || pip install -e .

echo ""
echo "[OK] Installation complete."

# Verify the console script is available
if command -v armory > /dev/null 2>&1; then
  echo "[OK] 'armory' command is available in PATH"
else
  echo "[WARN] 'armory' command not found in PATH. You may need to activate the venv:"
  echo "       source .venv/bin/activate"
fi

# Initialize the SQLite database by running a no-op command
echo ""
echo "[*] Initializing SQLite database..."
armory info xss > /dev/null 2>&1 && echo "[OK] Database initialized at ~/.armory/armory.db" || echo "[WARN] Could not initialize database. Run 'armory info xss' manually."

# Print optional AI setup info
echo ""
echo "=== Optional: Claude AI Integration ==="
if [ -n "$ARMORY_CLAUDE_API_KEY" ]; then
  echo "[OK] ARMORY_CLAUDE_API_KEY is set. AI features are enabled."
else
  echo "[INFO] ARMORY_CLAUDE_API_KEY is not set. AI features are disabled."
  echo "       To enable: export ARMORY_CLAUDE_API_KEY='your-anthropic-api-key'"
fi

# Print optional DB path info
echo ""
echo "=== Database Location ==="
if [ -n "$ARMORY_DB_PATH" ]; then
  echo "[INFO] ARMORY_DB_PATH is set to: $ARMORY_DB_PATH"
else
  DB_PATH="${HOME}/.armory/armory.db"
  echo "[INFO] SQLite database will be stored at: $DB_PATH"
fi

# Print quick-start info
echo ""
echo "=== Quick Start ==="
echo "  armory                         # Launch interactive TUI"
echo "  armory info xss                # Show XSS class overview"
echo "  armory info --list-all         # List all vulnerability classes"
echo "  armory search 'alert'          # Search payloads for 'alert'"
echo "  armory export --class xss --format burp   # Export XSS payloads for Burp"
echo "  armory cheatsheet --class xss  # Print compact XSS cheat sheet"
echo "  armory --help                  # Full command reference"
echo ""
echo "=== Key Bindings (in TUI) ==="
echo "  / → search overlay     ? → help modal"
echo "  B → bookmark           N → note editor"
echo "  Y → copy to clipboard  E → AI explain (requires API key)"
echo "  V → AI variants        C → AI chain suggestion"
echo "  H → history panel      q → quit"
echo ""
echo "[READY] Armory is ready to use. Run 'armory' to launch the TUI."
