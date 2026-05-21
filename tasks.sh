#!/usr/bin/env bash
# tasks.sh - Linux/macOS task runner equivalent to tasks.ps1
# Usage:
#   ./tasks.sh <task> [arg]
# Examples:
#   ./tasks.sh install
#   ./tasks.sh serve
#   ./tasks.sh eval 50
#   ./tasks.sh crawl PubMed

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASK="${1:-help}"
ARG="${2:-}"

cd "$ROOT"

# Dùng .venv-linux để tránh ghi đè .venv của Windows
VENV_DIR="$ROOT/.venv-linux"

info() { printf '\033[36m>> %s\033[0m\n' "$*"; }
warn() { printf '\033[33m   %s\033[0m\n' "$*"; }
ok() { printf '\033[32m>> %s\033[0m\n' "$*"; }
err() { printf '\033[31m%s\033[0m\n' "$*" >&2; }

activate_venv() {
    if [[ -f "$VENV_DIR/bin/activate" ]]; then
        # shellcheck disable=SC1091
        source "$VENV_DIR/bin/activate"
    fi
}

port_pids() {
    local port="$1"

    if command -v lsof >/dev/null 2>&1; then
        lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true
        return
    fi

    if command -v fuser >/dev/null 2>&1; then
        fuser "$port"/tcp 2>/dev/null || true
        return
    fi

    if command -v ss >/dev/null 2>&1; then
        ss -ltnp "sport = :$port" 2>/dev/null \
            | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' \
            | sort -u || true
    fi
}

kill_port() {
    local port="$1"
    local pids

    pids="$(port_pids "$port" | tr '\n' ' ')"
    if [[ -z "${pids// }" ]]; then
        return
    fi

    warn "Port $port dang bi chiem boi PID: $pids -- dang kill..."
    # shellcheck disable=SC2086
    kill $pids 2>/dev/null || true
    sleep 1

    pids="$(port_pids "$port" | tr '\n' ' ')"
    if [[ -n "${pids// }" ]]; then
        # shellcheck disable=SC2086
        kill -9 $pids 2>/dev/null || true
    fi

    ok "Port $port da giai phong."
}

start_ollama_serve() {
    local port="${1:-11434}"

    info "Checking Ollama (port $port)..."
    if curl -fsS "http://localhost:$port/api/tags" >/dev/null 2>&1; then
        ok "Ollama da san sang."
        return
    fi

    if ! command -v ollama >/dev/null 2>&1; then
        err "Khong tim thay lenh 'ollama'. Cai Ollama truoc roi chay lai task."
        exit 1
    fi

    local pids
    pids="$(port_pids "$port" | tr '\n' ' ')"
    if [[ -n "${pids// }" ]]; then
        warn "Port $port bi chiem nhung Ollama chua phan hoi. Giai phong port..."
        kill_port "$port"
    fi

    warn "Khoi dong Ollama serve (background)..."
    nohup ollama serve > "$ROOT/.ollama-serve.log" 2>&1 &

    for _ in $(seq 1 15); do
        sleep 1
        if curl -fsS "http://localhost:$port/api/tags" >/dev/null 2>&1; then
            ok "Ollama san sang."
            return
        fi
    done

    warn "[WARN] Ollama chua phan hoi sau 15s, tiep tuc task..."
}

confirm() {
    local prompt="$1"
    local answer

    read -r -p "$prompt (y/N) " answer
    [[ "$answer" == "y" || "$answer" == "Y" ]]
}

case "$TASK" in
    install)
        info "Installing dependencies..."
        python3 -m venv "$VENV_DIR"
        activate_venv
        python -m pip install --upgrade pip
        python -m pip install typer loguru pydantic pydantic-settings python-dotenv jinja2 pyyaml
        python -m pip install "fastapi>=0.115" "uvicorn[standard]" "httpx[http2]" python-multipart
        python -m pip install rank-bm25 tenacity beautifulsoup4 lxml readability-lxml trafilatura
        python -m pip install langdetect datasketch underthesea
        python -m pip install pytest pytest-asyncio tqdm numpy
        warn "Installing ML packages (co the mat 10-20 phut)..."
        python -m pip install chromadb sentence-transformers
        python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
        python -m pip install transformers
        python -m pip install -e .
        if [[ -f .env.example && ! -f .env ]]; then
            cp .env.example .env
        fi
        ok "Done. Kiem tra .env neu can chinh sua."
        ;;

    pull-models)
        info "Pulling Ollama models..."
        start_ollama_serve 11434
        ollama pull qwen3:4b
        ollama pull qwen3:1.7b
        ok "Models ready."
        ;;

    crawl)
        activate_venv
        info "Crawling sources (co the mat 1-3 gio)..."
        warn "Output: data/raw/documents.jsonl"
        if [[ -n "$ARG" ]]; then
            python -m scripts.crawl_all --source "$ARG"
        else
            python -m scripts.crawl_all
        fi
        ;;

    crawl-pubmed)
        activate_venv
        info "Crawling PubMed only..."
        python -m scripts.crawl_all --source PubMed
        ;;

    build-dataset)
        activate_venv
        info "Building fine-tuning QA dataset..."
        warn "Input : data/raw/documents.jsonl"
        warn "Output: data/finetune/qa_finetuning.jsonl"
        python -m scripts.build_qa_dataset
        ;;

    build-dataset-resume)
        activate_venv
        info "Resuming QA dataset build..."
        python -m scripts.build_qa_dataset --resume
        ;;

    build-kb)
        activate_venv
        info "Building knowledge base (embedding + index)..."
        warn "Input : data/raw/documents.jsonl"
        warn "Output: data/chroma_db/ + data/bm25_index.pkl"
        python -m scripts.build_kb
        ;;

    visualize)
        activate_venv
        info "Generating dataset visualizations..."
        warn "Output: visualize/*.png + visualize/report.html"
        (cd visualize && python run_all.py)
        ok "Done. Mo visualize/report.html de xem."
        ;;

    serve|serve-lan)
        activate_venv
        start_ollama_serve 11434
        info "Checking API port 8000..."
        kill_port 8000

        if [[ "$TASK" == "serve-lan" ]]; then
            ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
            if [[ -z "${ip:-}" ]]; then
                ip="$(ip route get 1.1.1.1 2>/dev/null | awk '{for (i=1;i<=NF;i++) if ($i=="src") print $(i+1); exit}')"
            fi
            info "Starting API server (LAN: http://${ip:-localhost}:8000)"
            warn "Web UI : http://${ip:-localhost}:8000"
            warn "OpenAPI: http://${ip:-localhost}:8000/docs"
        else
            info "Starting API server at http://localhost:8000"
            warn "Web UI : http://localhost:8000"
            warn "OpenAPI: http://localhost:8000/docs"
        fi

        uvicorn acne_llm.api.app:app --host 0.0.0.0 --port 8000 --reload
        ;;

    frontend-install)
        info "Installing frontend dependencies..."
        if ! command -v npm >/dev/null 2>&1; then
            err "Khong tim thay npm. Cai Node.js truoc roi chay lai task."
            exit 1
        fi
        (cd frontend && npm install)
        ok "Frontend dependencies ready."
        ;;

    frontend)
        info "Starting frontend at http://localhost:3000..."
        if ! command -v npm >/dev/null 2>&1; then
            err "Khong tim thay npm. Cai Node.js truoc roi chay lai task."
            exit 1
        fi
        (cd frontend && npm run dev)
        ;;

    run-all)
        info "Starting Ollama + backend + frontend..."
        bash scripts/run_all.sh
        ;;

    test)
        activate_venv
        info "Running tests..."
        python -m pytest -v
        ;;

    eval)
        activate_venv
        n="${ARG:-20}"
        info "Running eval (n=$n)..."
        start_ollama_serve 11434
        python -m scripts.run_eval --n "$n"
        ;;

    suggest-eval-labels)
        activate_venv
        info "Generating eval label suggestions..."
        python -m scripts.propose_eval_labels
        ;;

    approve-eval-labels)
        activate_venv
        info "Approving eval labels..."
        python -m scripts.approve_eval_labels
        ;;

    stats)
        activate_venv
        info "Project stats..."
        start_ollama_serve 11434
        python - <<'PY'
import sys
from pathlib import Path

sys.path.insert(0, "src")
sys.path.insert(0, ".")

from config.settings import settings
from acne_llm.di import build_container

root = Path(".")
raw_docs = root / "data" / "raw" / "documents.jsonl"
ft_data = root / "data" / "finetune" / "qa_finetuning.jsonl"
llm_data = root / "LLMData" / "acne_dataset.jsonl"

n_docs = sum(1 for _ in open(raw_docs, encoding="utf-8")) if raw_docs.exists() else 0
n_qa = sum(1 for _ in open(ft_data, encoding="utf-8")) if ft_data.exists() else 0
n_llm = sum(1 for _ in open(llm_data, encoding="utf-8")) if llm_data.exists() else 0

print()
print("=== Data ===")
print(f"  Raw docs (data/raw/documents.jsonl)          : {n_docs:,}")
print(f"  QA pairs (data/finetune/qa_finetuning.jsonl): {n_qa:,}")
print(f"  LLMData  (LLMData/acne_dataset.jsonl)        : {n_llm:,}")
print()

c = build_container(settings)
not_built = "(not built)"
print("=== KB ===")
print(f"  ChromaDB chunks : {c.store.count() if c.store else not_built}")
print(f"  BM25 chunks     : {len(c.bm25.chunk_ids) if c.bm25 else not_built}")
print(f"  RAG ready       : {c.rag_ready}")
print()
print("=== LLM ===")
print(f"  Ollama reachable: {c.llm.health()}")
print(f"  Model           : {c.llm.model}")
print(f"  Ollama URL      : {settings.ollama_url}")
print()
PY
        ;;

    chat)
        activate_venv
        read -r -p "Mo ta tinh trang mun: " desc
        start_ollama_serve 11434
        DESC="$desc" python - <<'PY'
import json
import os
import sys

sys.path.insert(0, "src")
sys.path.insert(0, ".")

from acne_llm.di import build_container
from acne_llm.schemas import UserInput
from config.settings import settings

c = build_container(settings)
out = c.llm_only.run(UserInput(description=os.environ["DESC"]))
print(json.dumps(out.model_dump(), ensure_ascii=False, indent=2))
PY
        ;;

    lint)
        activate_venv
        info "Linting + type-check..."
        python -m ruff check src/ scripts/ config/ --fix
        python -m mypy src/acne_llm --ignore-missing-imports
        ok "Lint OK."
        ;;

    docker-build)
        info "Building Docker image..."
        docker build -t acne-llm:latest .
        ok "Image built: acne-llm:latest"
        ;;

    docker-up)
        info "Starting Docker Compose (Ollama + API)..."
        docker compose up -d 2>/dev/null || docker-compose up -d
        ok "Services up. API: http://localhost:8000  Ollama: http://localhost:11434"
        ;;

    docker-down)
        info "Stopping Docker Compose..."
        docker compose down 2>/dev/null || docker-compose down
        ;;

    clean-kb)
        warn "Xoa vector index va BM25 (KHONG xoa raw crawl / finetune data)."
        if confirm "Xac nhan xoa chroma_db + bm25_index.pkl?"; then
            rm -rf data/chroma_db/*
            rm -f data/bm25_index.pkl
            ok "KB index cleared."
        fi
        ;;

    clean-raw)
        warn "Xoa raw crawl data."
        if confirm "Xac nhan xoa data/raw/* ?"; then
            rm -rf data/raw/*
            ok "Raw data cleared."
        fi
        ;;

    clean-finetune)
        warn "Xoa finetune data va checkpoint."
        if confirm "Xac nhan xoa data/finetune/* ?"; then
            rm -rf data/finetune/*
            ok "Finetune data cleared."
        fi
        ;;

    clean-logs)
        warn "Xoa log files..."
        rm -f data/logs/*.log data/logs/*.json
        ok "Logs cleared."
        ;;

    help)
        cat <<'EOF'

  AcneLLM Tasks for Linux
  =======================

  -- Setup --
  ./tasks.sh install              Install Python deps + venv
  ./tasks.sh pull-models          Pull Ollama LLM models

  -- Data Pipeline --
  ./tasks.sh crawl                Crawl tat ca nguon -> data/raw/ (~1-3h)
  ./tasks.sh crawl PubMed         Crawl source tuy chon
  ./tasks.sh crawl-pubmed         Chi crawl PubMed
  ./tasks.sh build-dataset        Sinh QA pairs cho fine-tune
  ./tasks.sh build-dataset-resume Resume build-dataset
  ./tasks.sh build-kb             Chunk + embed + index -> chroma/bm25
  ./tasks.sh visualize            Sinh bieu do phan tich dataset

  -- Serve --
  ./tasks.sh serve                Chay API server (localhost:8000)
  ./tasks.sh serve-lan            Chay + in IP LAN cho mobile
  ./tasks.sh frontend-install     Cai dependency cho Next.js frontend
  ./tasks.sh frontend             Chay frontend (localhost:3000)
  ./tasks.sh run-all              Mo Ollama + backend + frontend

  -- Docker --
  ./tasks.sh docker-build         Build Docker image
  ./tasks.sh docker-up            docker compose up -d
  ./tasks.sh docker-down          docker compose down

  -- Dev --
  ./tasks.sh test                 Chay pytest
  ./tasks.sh lint                 Ruff + mypy
  ./tasks.sh eval                 Chay eval (mac dinh 20 queries)
  ./tasks.sh eval 50              Chay eval voi 50 queries
  ./tasks.sh suggest-eval-labels  Tao goi y relevant_chunk_ids cho eval
  ./tasks.sh approve-eval-labels  Copy goi y sang relevant_chunk_ids
  ./tasks.sh stats                In thong ke data + KB + Ollama
  ./tasks.sh chat                 Chat nhanh qua terminal (llm_only)

  -- Clean --
  ./tasks.sh clean-kb             Xoa chroma_db + bm25 (giu raw/finetune)
  ./tasks.sh clean-raw            Xoa data/raw/*
  ./tasks.sh clean-finetune       Xoa data/finetune/*
  ./tasks.sh clean-logs           Xoa data/logs/*.log

EOF
        ;;

    *)
        err "Task '${TASK}' không tồn tại. Chạy './tasks.sh help' để xem danh sách."
        exit 1
        ;;
esac
