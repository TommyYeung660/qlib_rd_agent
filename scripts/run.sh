#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
#  Run script for qlib_rd_agent
#  Runs the full pipeline: sync → RD-Agent → upload
#
#  Usage:
#    chmod +x scripts/run.sh
#    ./scripts/run.sh [OPTIONS]
#
#  Options are passed through to `python -m src.main full`:
#    --max-iterations N    Override max RD-Agent iterations
#    --skip-sync           Skip Dropbox sync step
#
#  Examples:
#    ./scripts/run.sh
#    ./scripts/run.sh --max-iterations 5
#    ./scripts/run.sh --skip-sync
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# ---------------------------------------------------------------------------
# Activate virtual environment
# ---------------------------------------------------------------------------
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
    echo "[run.sh] Activated .venv"
elif [ -f ".venv/Scripts/activate" ]; then
    source .venv/Scripts/activate
    echo "[run.sh] Activated .venv (Windows)"
else
    echo "[run.sh] ERROR: No .venv found. Run scripts/setup_wsl.sh first."
    exit 1
fi

# ---------------------------------------------------------------------------
# Run the full pipeline (pass through any CLI arguments)
# ---------------------------------------------------------------------------
echo "[run.sh] Starting qlib_rd_agent pipeline..."
echo "[run.sh] Args: $*"
python -m src.main full "$@"

echo "[run.sh] Pipeline complete"
