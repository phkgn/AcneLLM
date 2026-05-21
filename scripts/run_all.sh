#!/usr/bin/env bash
# AcneLLM - run Ollama, backend, and frontend in separate Linux terminal windows.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

OLLAMA_CMD='ollama serve'
BACKEND_CMD="cd '$ROOT' && source .venv/bin/activate && uvicorn acne_llm.api.app:app --host 0.0.0.0 --port 8000 --reload"
FRONTEND_CMD="cd '$ROOT/frontend' && npm run dev"

open_terminal() {
    local title="$1"
    local command="$2"

    if [[ -n "${TERMINAL:-}" ]] && command -v "$TERMINAL" >/dev/null 2>&1; then
        "$TERMINAL" -e bash -lc "$command; exec bash" >/dev/null 2>&1 &
        return 0
    fi
    if command -v gnome-terminal >/dev/null 2>&1; then
        gnome-terminal --title="$title" -- bash -lc "$command; exec bash" >/dev/null 2>&1 &
        return 0
    fi
    if command -v konsole >/dev/null 2>&1; then
        konsole --new-tab -p tabtitle="$title" -e bash -lc "$command; exec bash" >/dev/null 2>&1 &
        return 0
    fi
    if command -v xfce4-terminal >/dev/null 2>&1; then
        xfce4-terminal --title="$title" --command "bash -lc \"$command; exec bash\"" >/dev/null 2>&1 &
        return 0
    fi
    return 1
}

echo
echo "=== AcneLLM - Running All Services ==="
echo
echo "This script opens 3 terminals when your desktop terminal supports it:"
echo "  1. Ollama Server  (http://localhost:11434)"
echo "  2. Backend API    (http://localhost:8000)"
echo "  3. Frontend UI    (http://localhost:3000)"
echo

if open_terminal "AcneLLM Ollama" "$OLLAMA_CMD" \
    && open_terminal "AcneLLM Backend" "$BACKEND_CMD" \
    && open_terminal "AcneLLM Frontend" "$FRONTEND_CMD"; then
    echo "Services are starting. Open http://localhost:3000"
else
    echo "Could not detect a supported terminal launcher."
    echo
    echo "Run these manually in 3 terminals:"
    echo "  Terminal 1: $OLLAMA_CMD"
    echo "  Terminal 2: $BACKEND_CMD"
    echo "  Terminal 3: $FRONTEND_CMD"
fi
