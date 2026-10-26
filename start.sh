#!/usr/bin/env bash
# ==============================================================================
# AgentReliability AI — One-Command Setup & Launch
# Supports: macOS, Linux, and Windows WSL2
# ==============================================================================
set -e

# Change to the directory of this script (repository root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "================================================================================"
echo " 🤖 AgentReliability AI — Developer Self-Service Launcher"
echo "================================================================================"
echo ""

# ------------------------------------------------------------------------------
# 1. Detect Python 3 (3.9+)
# ------------------------------------------------------------------------------
PYTHON_BIN=""
if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
fi

if [ -z "$PYTHON_BIN" ]; then
    echo "❌ Error: Python 3 was not found in your PATH."
    echo ""
    echo "Quick Recovery:"
    echo "  • macOS:            brew install python@3.11"
    echo "  • Ubuntu/Debian/WSL: sudo apt update && sudo apt install -y python3 python3-venv python3-pip"
    echo "  • Official site:    https://www.python.org/downloads/"
    exit 1
fi

PY_VER_OK=$($PYTHON_BIN -c "import sys; print(1 if sys.version_info >= (3, 9) else 0)" 2>/dev/null || echo 0)
if [ "$PY_VER_OK" != "1" ]; then
    PY_VER=$($PYTHON_BIN -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "unknown")
    echo "❌ Error: Python >= 3.9 is required (found Python $PY_VER)."
    echo "   Please upgrade Python to version 3.9 or newer."
    exit 1
fi

# ------------------------------------------------------------------------------
# 2. Detect Node.js (>= 18) & npm
# ------------------------------------------------------------------------------
NODE_BIN=""
NPM_BIN=""
if command -v node >/dev/null 2>&1; then
    NODE_BIN="node"
fi
if command -v npm >/dev/null 2>&1; then
    NPM_BIN="npm"
fi

if [ -z "$NODE_BIN" ] || [ -z "$NPM_BIN" ]; then
    echo "⚠️  Warning: Node.js (>= 18) or npm was not found in your PATH."
    echo "   The Python backend and CLI will run, but the web dashboard requires Node.js."
    echo ""
    echo "Quick Recovery:"
    echo "  • Install Node.js:  https://nodejs.org (LTS version 20+ recommended)"
    echo "  • Or with NVM:      nvm install 20 && nvm use 20"
    echo ""
fi

# ------------------------------------------------------------------------------
# 3. Setup Isolated Python Virtual Environment (backend/.venv)
# ------------------------------------------------------------------------------
VENV_DIR="$SCRIPT_DIR/backend/.venv"
VENV_PY="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

if [ ! -f "$VENV_PY" ]; then
    echo "📦 [1/3] Creating isolated Python virtual environment at backend/.venv..."
    $PYTHON_BIN -m venv "$VENV_DIR"
    "$VENV_PIP" install --upgrade pip setuptools --quiet 2>/dev/null || true
    echo "✅ Virtual environment created."
fi

# Verify backend dependencies and SDK installation
NEED_PIP_INSTALL=0
if ! "$VENV_PY" -c "import fastapi, uvicorn, pydantic, sqlite3, agentreliability" >/dev/null 2>&1; then
    NEED_PIP_INSTALL=1
fi

if [ "$NEED_PIP_INSTALL" -eq 1 ]; then
    echo "📦 [2/3] Installing backend and SDK dependencies into backend/.venv..."
    if [ -f "$SCRIPT_DIR/backend/requirements.txt" ]; then
        "$VENV_PIP" install -r "$SCRIPT_DIR/backend/requirements.txt"
    fi
    # Install SDK in editable mode
    if [ -d "$SCRIPT_DIR/sdk" ]; then
        "$VENV_PIP" install -e "$SCRIPT_DIR/sdk"
    fi
    echo "✅ Backend and SDK dependencies installed."
fi

# ------------------------------------------------------------------------------
# 4. Setup Frontend Dashboard Dependencies
# ------------------------------------------------------------------------------
if [ -n "$NPM_BIN" ] && [ -d "$SCRIPT_DIR/frontend" ]; then
    if [ ! -d "$SCRIPT_DIR/frontend/node_modules" ] || [ -z "$(ls -A "$SCRIPT_DIR/frontend/node_modules" 2>/dev/null)" ]; then
        echo "📦 [3/3] Installing frontend dashboard dependencies with npm..."
        "$NPM_BIN" --prefix "$SCRIPT_DIR/frontend" install
        echo "✅ Frontend dependencies installed."
    fi
fi

# ------------------------------------------------------------------------------
# 5. Initialize Workspace Configuration & Launch Dev Server
# ------------------------------------------------------------------------------
echo ""
echo "🚀 Initializing local database and port resolution..."
"$VENV_PY" -m agentreliability.cli init

echo ""
echo "🌟 Starting AgentReliability services (Ctrl+C to stop)..."
echo "💡 Tip: To run Python agents or tests in another terminal:"
echo "   source backend/.venv/bin/activate"
echo "   python demo_agent.py success"
echo ""
exec "$VENV_PY" -m agentreliability.cli dev "$@"

