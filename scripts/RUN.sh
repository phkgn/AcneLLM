#!/usr/bin/env bash
# AcneLLM - Khởi động toàn bộ services trên Linux
# Tương đương scripts/RUN.ps1 trên Windows
#
# Usage:
#   ./scripts/RUN.sh           # chạy bình thường
#   ./scripts/RUN.sh --log     # ghi log backend ra /tmp/acne-llm-backend.log
#
# Mở 3 terminal riêng biệt:
#   1. Ollama Server  (http://localhost:11434)
#   2. Backend API    (http://localhost:8000)
#   3. Frontend UI    (http://localhost:3000)

set -euo pipefail

# ── Flags ────────────────────────────────────────────────────
LOG=false
for arg in "$@"; do
    [[ "$arg" == "--log" || "$arg" == "-l" ]] && LOG=true
done

# ── Paths ────────────────────────────────────────────────────
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Dùng .venv-linux để không ghi đè .venv của Windows
VENV_DIR="$ROOT/.venv-linux"
VENV_PYTHON="$VENV_DIR/bin/python"
VENV_UVICORN="$VENV_DIR/bin/uvicorn"
BACKEND_LOG="/tmp/acne-llm-backend.log"

# ── Colors ───────────────────────────────────────────────────
RED='\033[0;31m'; YELLOW='\033[0;33m'; GREEN='\033[0;32m'
CYAN='\033[0;36m'; RESET='\033[0m'

info()  { printf "${CYAN}>> %s${RESET}\n" "$*"; }
warn()  { printf "${YELLOW}   %s${RESET}\n" "$*"; }
ok()    { printf "${GREEN}>> %s${RESET}\n" "$*"; }
err()   { printf "${RED}%s${RESET}\n" "$*" >&2; }

# ── Sanity checks ────────────────────────────────────────────
if [[ ! -f "$VENV_PYTHON" ]]; then
    err "Không tìm thấy venv tại $VENV_DIR"
    err "Chạy './tasks.sh install' từ thư mục gốc trước."
    exit 1
fi

if ! "$VENV_PYTHON" -c "import sys; sys.exit(0)" 2>/dev/null; then
    err "venv bị lỗi. Chạy './tasks.sh install' để tạo lại."
    exit 1
fi

if ! command -v ollama >/dev/null 2>&1; then
    err "Không tìm thấy lệnh 'ollama'."
    err "Cài Ollama: curl -fsSL https://ollama.com/install.sh | sh"
    exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
    err "Không tìm thấy npm. Cài Node.js 18+ trước."
    exit 1
fi

# ── Kill port helper ─────────────────────────────────────────
kill_port() {
    local port="$1"
    local pids=""

    if command -v lsof >/dev/null 2>&1; then
        pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
    elif command -v fuser >/dev/null 2>&1; then
        pids="$(fuser "$port"/tcp 2>/dev/null || true)"
    elif command -v ss >/dev/null 2>&1; then
        pids="$(ss -ltnp "sport = :$port" 2>/dev/null \
            | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' | sort -u || true)"
    fi

    if [[ -z "${pids// }" ]]; then
        return
    fi

    warn "Port $port đang bị chiếm (PID: $pids) — đang kill..."
    # shellcheck disable=SC2086
    kill $pids 2>/dev/null || true
    sleep 1

    # Force kill nếu vẫn còn
    pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
    if [[ -n "${pids// }" ]]; then
        # shellcheck disable=SC2086
        kill -9 $pids 2>/dev/null || true
    fi

    ok "Port $port đã giải phóng."
}

# ── Wait for HTTP ─────────────────────────────────────────────
wait_for_http() {
    local url="$1"
    local timeout="${2:-120}"
    local elapsed=0

    while (( elapsed < timeout )); do
        if curl -fsS --max-time 3 "$url" >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
        (( elapsed++ ))
    done

    return 1
}

# ── Open terminal ─────────────────────────────────────────────
# Hỗ trợ: gnome-terminal, konsole, xfce4-terminal, xterm
# Nếu không có GUI → chạy nền (background) và in log path
open_terminal() {
    local title="$1"
    local cmd="$2"

    # Ưu tiên terminal env variable nếu user tự set
    if [[ -n "${TERMINAL:-}" ]] && command -v "$TERMINAL" >/dev/null 2>&1; then
        "$TERMINAL" -e bash -lc "$cmd; exec bash" >/dev/null 2>&1 &
        return 0
    fi

    if command -v gnome-terminal >/dev/null 2>&1; then
        gnome-terminal --title="$title" -- bash -lc "$cmd; exec bash" >/dev/null 2>&1 &
        return 0
    fi

    if command -v konsole >/dev/null 2>&1; then
        konsole --new-tab -p tabtitle="$title" -e bash -lc "$cmd; exec bash" >/dev/null 2>&1 &
        return 0
    fi

    if command -v xfce4-terminal >/dev/null 2>&1; then
        xfce4-terminal --title="$title" --command "bash -lc \"$cmd; exec bash\"" >/dev/null 2>&1 &
        return 0
    fi

    if command -v xterm >/dev/null 2>&1; then
        xterm -title "$title" -e bash -lc "$cmd; exec bash" >/dev/null 2>&1 &
        return 0
    fi

    if command -v tilix >/dev/null 2>&1; then
        tilix -t "$title" -e bash -lc "$cmd; exec bash" >/dev/null 2>&1 &
        return 0
    fi

    # Fallback: chạy nền, không mở terminal GUI
    return 1
}

# ── Open browser ──────────────────────────────────────────────
open_browser() {
    local url="$1"
    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$url" >/dev/null 2>&1 &
    elif command -v sensible-browser >/dev/null 2>&1; then
        sensible-browser "$url" >/dev/null 2>&1 &
    else
        warn "Không mở được browser tự động. Mở thủ công: $url"
    fi
}

# ═══════════════════════════════════════════════════════════════
echo
echo "=== AcneLLM — Khởi động toàn bộ Services ==="
echo
echo "Script sẽ mở 3 terminal riêng biệt:"
warn "  1. Ollama Server  (http://localhost:11434)"
warn "  2. Backend API    (http://localhost:8000)"
warn "  3. Frontend UI    (http://localhost:3000)"
echo
read -r -p "Nhấn Enter để tiếp tục (Ctrl+C để huỷ)..."

# ── 1. Ollama ─────────────────────────────────────────────────
info "Kiểm tra Ollama..."

if curl -fsS --max-time 3 "http://localhost:11434/api/tags" >/dev/null 2>&1; then
    ok "Ollama đang chạy sẵn."
else
    kill_port 11434
    info "Khởi động Ollama..."

    OLLAMA_CMD="ollama serve"
    if ! open_terminal "AcneLLM — Ollama" "$OLLAMA_CMD"; then
        warn "Không tìm thấy terminal GUI — chạy Ollama nền..."
        nohup ollama serve > /tmp/acne-llm-ollama.log 2>&1 &
        warn "Log Ollama: /tmp/acne-llm-ollama.log"
    fi

    info "Đợi Ollama sẵn sàng (tối đa 30s)..."
    if ! wait_for_http "http://localhost:11434/api/tags" 30; then
        err "Ollama không phản hồi sau 30 giây."
        err "Kiểm tra: curl http://localhost:11434/api/tags"
        exit 1
    fi
    ok "Ollama sẵn sàng."
fi

# ── 2. Backend ────────────────────────────────────────────────
info "Kiểm tra port 8000..."
kill_port 8000

if [[ "$LOG" == true ]]; then
    : > "$BACKEND_LOG"
    BACKEND_CMD="cd '$ROOT' && source .venv-linux/bin/activate && uvicorn acne_llm.api.app:app --host 0.0.0.0 --port 8000 --reload 2>&1 | tee '$BACKEND_LOG'"
    warn "Backend log: $BACKEND_LOG"
else
    BACKEND_CMD="cd '$ROOT' && source .venv-linux/bin/activate && uvicorn acne_llm.api.app:app --host 0.0.0.0 --port 8000 --reload"
fi

info "Khởi động Backend API..."
if ! open_terminal "AcneLLM — Backend" "$BACKEND_CMD"; then
    warn "Không tìm thấy terminal GUI — chạy backend nền..."
    if [[ "$LOG" == true ]]; then
        bash -lc "cd '$ROOT' && source .venv-linux/bin/activate && uvicorn acne_llm.api.app:app --host 0.0.0.0 --port 8000 --reload" > "$BACKEND_LOG" 2>&1 &
    else
        bash -lc "cd '$ROOT' && source .venv-linux/bin/activate && uvicorn acne_llm.api.app:app --host 0.0.0.0 --port 8000 --reload" > /tmp/acne-llm-backend.log 2>&1 &
        warn "Log backend: /tmp/acne-llm-backend.log"
    fi
fi

info "Đợi Backend sẵn sàng (tối đa 180s — lần đầu tải model embedding có thể lâu)..."
if ! wait_for_http "http://localhost:8000/api/v1/health" 180; then
    err "Backend không phản hồi sau 180 giây."
    err "Kiểm tra log: tail -f /tmp/acne-llm-backend.log"
    exit 1
fi
ok "Backend sẵn sàng."

# ── 3. Frontend ───────────────────────────────────────────────
info "Kiểm tra port 3000..."
kill_port 3000

FRONTEND_CMD="cd '$ROOT/frontend' && npm run dev"

info "Khởi động Frontend..."
if ! open_terminal "AcneLLM — Frontend" "$FRONTEND_CMD"; then
    warn "Không tìm thấy terminal GUI — chạy frontend nền..."
    bash -lc "$FRONTEND_CMD" > /tmp/acne-llm-frontend.log 2>&1 &
    warn "Log frontend: /tmp/acne-llm-frontend.log"
fi

info "Đợi Frontend sẵn sàng (tối đa 180s)..."
if ! wait_for_http "http://localhost:3000" 180; then
    err "Frontend không phản hồi sau 180 giây."
    err "Kiểm tra log: tail -f /tmp/acne-llm-frontend.log"
    exit 1
fi
ok "Frontend sẵn sàng."

# ── Done ──────────────────────────────────────────────────────
echo
ok "Tất cả services đã chạy!"
warn "  Ollama  : http://localhost:11434"
warn "  Backend : http://localhost:8000"
warn "  Docs    : http://localhost:8000/docs"
warn "  Chat UI : http://localhost:3000"
echo

info "Mở trình duyệt http://localhost:3000..."
open_browser "http://localhost:3000"

echo
warn "Đóng cửa sổ terminal tương ứng để dừng từng service."
warn "Dừng tất cả: kill \$(lsof -tiTCP:8000,3000,11434 -sTCP:LISTEN)"
ng để dừng từng service."
warn "Dừng tất cả: kill \$(lsof -tiTCP:8000,3000,11434 -sTCP:LISTEN)"
