# tasks.ps1 — thay thế Makefile cho Windows
# Dùng: .\tasks.ps1 <task>
# VD:   .\tasks.ps1 install
#        .\tasks.ps1 serve
#        .\tasks.ps1 eval 20
#        .\tasks.ps1 build-dataset
#        .\tasks.ps1 visualize

param(
    [string]$Task = "help",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RemainingArgs
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot

$N = 20
$Source = ""
$Log = $false

for ($i = 0; $i -lt ($RemainingArgs | Measure-Object).Count; $i++) {
    $arg = $RemainingArgs[$i]
    switch -Regex ($arg) {
        '^(--log|-log|-Log)$' {
            $Log = $true
            continue
        }
        '^(--n|-n)=(\d+)$' {
            $N = [int]$Matches[2]
            continue
        }
        '^(--source|-source)=(.+)$' {
            $Source = $Matches[2]
            continue
        }
        '^(--n|-n)$' {
            if ($i + 1 -lt $RemainingArgs.Count) {
                $N = [int]$RemainingArgs[$i + 1]
                $i++
            }
            continue
        }
        '^(--source|-source)$' {
            if ($i + 1 -lt $RemainingArgs.Count) {
                $Source = $RemainingArgs[$i + 1]
                $i++
            }
            continue
        }
        '^\d+$' {
            if ($Task -eq "eval") {
                $N = [int]$arg
            } elseif (($Task -like "crawl*" -or $Task -eq "overnight-kb") -and -not $Source) {
                $Source = $arg
            }
            continue
        }
        default {
            if (($Task -like "crawl*" -or $Task -eq "overnight-kb") -and -not $arg.StartsWith("-") -and -not $Source) {
                $Source = $arg
            }
        }
    }
}

function Ensure-Venv {
    $venvRoot = Join-Path $Root ".venv"
    $pythonExe = Join-Path $venvRoot "Scripts\python.exe"
    $venvReady = $false

    if (Test-Path $pythonExe) {
        try {
            & $pythonExe -V | Out-Null
            $venvReady = ($LASTEXITCODE -eq 0)
        } catch {
            $venvReady = $false
        }
    }

    if (-not $venvReady) {
        Write-Host ">> Recreating Windows virtual environment..." -ForegroundColor Yellow
        if (Test-Path $venvRoot) {
            Remove-Item -Recurse -Force $venvRoot
        }
        & py -3 -m venv $venvRoot
        if ($LASTEXITCODE -ne 0) {
            throw "Could not create .venv with py -3"
        }
        & $pythonExe -V | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Could not verify new .venv Python at $pythonExe"
        }
    }

    $script:PythonExe = Join-Path $venvRoot "Scripts\python.exe"
    $script:UvicornExe = Join-Path $venvRoot "Scripts\uvicorn.exe"
    $script:PytestExe = Join-Path $venvRoot "Scripts\pytest.exe"
    $script:RuffExe = Join-Path $venvRoot "Scripts\ruff.exe"
    $script:MypyExe = Join-Path $venvRoot "Scripts\mypy.exe"
}

function Invoke-Executable {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Arguments
    )

    & $Path @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: $Path $($Arguments -join ' ') (exit $LASTEXITCODE)"
    }
}

function python { param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments) Invoke-Executable $script:PythonExe @Arguments }
function uvicorn { param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments) Invoke-Executable $script:UvicornExe @Arguments }
function pytest { param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments) Invoke-Executable $script:PytestExe @Arguments }
function ruff { param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments) Invoke-Executable $script:RuffExe @Arguments }
function mypy { param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments) Invoke-Executable $script:MypyExe @Arguments }

function Start-OllamaServe {
    param([int]$Port = 11434)

    Write-Host ">> Checking Ollama (port $Port)..." -ForegroundColor Cyan
    $ollamaProc = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    if ($ollamaProc) {
        $pids = $ollamaProc | Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($procId in $pids) {
            $procName = (Get-Process -Id $procId -ErrorAction SilentlyContinue).Name
            Write-Host "   Port $Port bi chiem boi PID $procId ($procName) -- dang kill..." -ForegroundColor Yellow
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        }
        Start-Sleep -Seconds 1
        Write-Host "   Port $Port da giai phong." -ForegroundColor Green
    }

    Write-Host "   Khoi dong Ollama serve (background)..." -ForegroundColor Cyan
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden

    $ready = $false
    for ($i = 0; $i -lt 15; $i++) {
        Start-Sleep -Seconds 1
        try {
            $r = Invoke-WebRequest -Uri "http://localhost:$Port/api/tags" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
            if ($r.StatusCode -eq 200) { $ready = $true; break }
        } catch {}
    }

    if ($ready) {
        Write-Host "   Ollama san sang." -ForegroundColor Green
    } else {
        Write-Host "   [WARN] Ollama chua phan hoi sau 15s, tiep tuc task..." -ForegroundColor Yellow
    }
}

Ensure-Venv

switch ($Task) {

    "install" {
        Write-Host ">> Installing dependencies..." -ForegroundColor Cyan
        Write-Host ">> Using .venv at $Root\.venv" -ForegroundColor DarkGray
        python -m pip install --upgrade pip
        # Install core deps truoc (khong co ML models nang)
        python -m pip install typer loguru pydantic pydantic-settings python-dotenv jinja2 pyyaml
        python -m pip install "fastapi>=0.115" "uvicorn[standard]" "httpx[http2]" python-multipart
        python -m pip install rank-bm25 tenacity beautifulsoup4 lxml readability-lxml trafilatura
        python -m pip install langdetect datasketch underthesea
        python -m pip install pytest pytest-asyncio tqdm numpy
        # ML packages (lon, mat nhieu thoi gian)
        Write-Host ">> Installing ML packages (co the mat 10-20 phut)..." -ForegroundColor Yellow
        python -m pip install chromadb sentence-transformers
        python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
        python -m pip install transformers
        # Install package nay cuoi cung
        python -m pip install -e .
        Write-Host ">> Done. Copy .env.example -> .env va chinh sua." -ForegroundColor Green
    }

    "pull-models" {
        Write-Host ">> Pulling Ollama models..." -ForegroundColor Cyan
        Start-OllamaServe -Port 11434
        ollama pull qwen2.5:7b
        ollama pull qwen2.5:3b
        Write-Host ">> Models ready." -ForegroundColor Green
    }

    "crawl" {
        Write-Host ">> Crawling sources..." -ForegroundColor Cyan
        Write-Host "   Output: data/raw/documents.jsonl" -ForegroundColor Yellow
        Write-Host "   NOTE  : GHI DE file cu. De giu lai, chay overnight-kb thay." -ForegroundColor DarkGray
        if ($Source) {
            python -m scripts.crawl_all --source $Source --source-concurrency 1 --pw-concurrency 5
        } else {
            python -m scripts.crawl_all --source-concurrency 1 --pw-concurrency 5
        }
    }

    "crawl-pubmed" {
        Write-Host ">> Crawling PubMed only..." -ForegroundColor Cyan
        python -m scripts.crawl_all --source PubMed
    }

    "build-dataset" {
        Write-Host ">> Building fine-tuning QA dataset..." -ForegroundColor Cyan
        Write-Host "   Input : data/raw/documents.jsonl" -ForegroundColor Yellow
        Write-Host "   Output: data/finetune/qa_finetuning.jsonl" -ForegroundColor Yellow
        Write-Host "   (can --resume de tiep tuc neu bi ngat)" -ForegroundColor DarkGray
        python -m scripts.build_qa_dataset
    }

    "build-dataset-resume" {
        Write-Host ">> Resuming QA dataset build (bo qua doc da xu ly)..." -ForegroundColor Cyan
        python -m scripts.build_qa_dataset --resume
    }

    "build-kb" {
        Write-Host ">> Building knowledge base (embedding + index)..." -ForegroundColor Cyan
        Write-Host "   Input : data/raw/documents.jsonl" -ForegroundColor Yellow
        Write-Host "   Output: data/chroma_db/ + data/bm25_index.pkl" -ForegroundColor Yellow
        python -m scripts.build_kb
    }

    "build-kb-force" {
        Write-Host ">> FORCE rebuilding knowledge base (xoa cu, build lai)..." -ForegroundColor Cyan
        Write-Host "   WARNING: Se xoa chroma_db/ va bm25_index.pkl cu" -ForegroundColor Yellow
        Write-Host "   Input : data/raw/documents.jsonl" -ForegroundColor Yellow
        Write-Host "   Output: data/chroma_db/ + data/bm25_index.pkl" -ForegroundColor Yellow
        python -m scripts.build_kb --force
    }

    "overnight-kb" {
        Write-Host ">> Overnight KB pipeline: crawl -> build-kb -> verify" -ForegroundColor Cyan
        Write-Host "   Step 1: Crawl ALL sources -> data/raw/documents.jsonl" -ForegroundColor Yellow
        Write-Host "   Step 2: Build KB (chunk + embed + bm25) with --force" -ForegroundColor Yellow
        Write-Host "   Step 3: Verify RAG ready" -ForegroundColor Yellow
        Write-Host "   NOTE  : De tranh timeout, PW concurrency = 5, source concurrency = 1" -ForegroundColor DarkGray

        $logDir = Join-Path $Root "data\logs"
        New-Item -ItemType Directory -Force $logDir | Out-Null
        $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
        $logPath = Join-Path $logDir "overnight_kb_$stamp.log"
        Write-Host "   Log   : $logPath" -ForegroundColor DarkGray

        $transcriptStarted = $false
        $success = $false

        try {
            try {
                Start-Transcript -Path $logPath -Append | Out-Null
                $transcriptStarted = $true
            } catch {
                Write-Host "   [WARN] Khong tao duoc transcript log: $($_.Exception.Message)" -ForegroundColor Yellow
            }

            # Step 0: Backup existing documents.jsonl
            $docsPath = Join-Path $Root "data\raw\documents.jsonl"
            if (Test-Path $docsPath) {
                $backupPath = "$docsPath.bak.$(Get-Date -Format 'yyyyMMddHHmmss')"
                Copy-Item $docsPath $backupPath -Force
                Write-Host ">> [$(Get-Date -Format 'u')] Backup documents.jsonl -> $backupPath" -ForegroundColor Green
            }

            # Step 1: Crawl
            Write-Host ">> [$(Get-Date -Format 'u')] Step 1/3: crawl (source_concurrency=1, pw-concurrency=5)" -ForegroundColor Cyan
            if ($Source) {
                Write-Host "   Source: $Source" -ForegroundColor DarkGray
                python -m scripts.crawl_all --source $Source --source-concurrency 1 --pw-concurrency 5
            } else {
                python -m scripts.crawl_all --source-concurrency 1 --pw-concurrency 5
            }

            # Step 2: Build KB with --force
            Write-Host ">> [$(Get-Date -Format 'u')] Step 2/3: build-kb --force" -ForegroundColor Cyan
            python -m scripts.build_kb --force

            # Step 3: Verify
            Write-Host ">> [$(Get-Date -Format 'u')] Step 3/3: verify RAG readiness" -ForegroundColor Cyan
            python -c "
import sys; sys.path.insert(0,'src'); sys.path.insert(0,'.')
from pathlib import Path
from config.settings import settings
from acne_llm.di import build_container
docs_path = Path(settings.docs_jsonl)
c = build_container(settings)
doc_count = sum(1 for line in docs_path.open(encoding='utf-8') if line.strip()) if docs_path.exists() else 0
chroma_count = c.store.count() if c.store else 0
bm25_count = len(c.bm25.chunk_ids) if c.bm25 else 0
print()
print('=== Overnight Verification ===')
print(f'  Documents.jsonl exists: {docs_path.exists()}')
print(f'  Documents count       : {doc_count}')
print(f'  ChromaDB ready         : {c.store is not None}')
print(f'  ChromaDB chunks        : {chroma_count}')
print(f'  BM25 ready             : {c.bm25 is not None}')
print(f'  BM25 chunks            : {bm25_count}')
print(f'  RAG ready              : {c.rag_ready}')
print()
if c.rag_ready and doc_count > 0 and chroma_count > 0 and bm25_count > 0:
    print('  OVERNIGHT SUCCESS: RAG pipeline is ready.')
else:
    print('  OVERNIGHT FAILED: RAG not ready. Check logs.')
    raise SystemExit(1)
"
            $success = $true
            Write-Host ">> Overnight KB pipeline DONE." -ForegroundColor Green
        } catch {
            Write-Host ">> Overnight FAILED: $($_.Exception.Message)" -ForegroundColor Red
            throw
        } finally {
            if ($transcriptStarted) {
                Stop-Transcript | Out-Null
                Write-Host ">> Log saved: $logPath" -ForegroundColor Green
            }
            if ($success) {
                Write-Host ">> SUCCESS. De chay API: .\tasks.ps1 serve" -ForegroundColor Cyan
            }
        }
    }

    "visualize" {
        Write-Host ">> Generating dataset visualizations..." -ForegroundColor Cyan
        Write-Host "   Output: visualize/*.png + visualize/report.html" -ForegroundColor Yellow
        Set-Location "$Root\visualize"
        python run_all.py
        Set-Location $Root
        Write-Host ">> Done. Mo visualize/report.html de xem." -ForegroundColor Green
    }

    "serve" {
        & "$Root\scripts\RUN.ps1" -Log:$Log
    }

    "serve-lan" {
        Start-OllamaServe -Port 11434

        # --- FastAPI: kill port 8000 nếu bị chiếm ---
        Write-Host ">> Checking API port 8000..." -ForegroundColor Cyan
        $apiProc = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
        if ($apiProc) {
            $pids = $apiProc | Select-Object -ExpandProperty OwningProcess -Unique
            foreach ($pid in $pids) {
                $procName = (Get-Process -Id $pid -ErrorAction SilentlyContinue).Name
                Write-Host "   Port 8000 bi chiem boi PID $pid ($procName) -- dang kill..." -ForegroundColor Yellow
                Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
            }
            Start-Sleep -Seconds 1
            Write-Host "   Port 8000 da giai phong." -ForegroundColor Green
        }

        $ip = (Get-NetIPAddress -AddressFamily IPv4 |
            Where-Object { $_.InterfaceAlias -notlike "*Loopback*" } |
            Select-Object -First 1).IPAddress
        Write-Host ">> Starting API server (LAN: http://${ip}:8000)" -ForegroundColor Cyan
        Write-Host "   API UI  : http://${ip}:8000" -ForegroundColor Yellow
        Write-Host "   OpenAPI: http://${ip}:8000/docs" -ForegroundColor Yellow
        uvicorn acne_llm.api.app:app --host 0.0.0.0 --port 8000 --reload
    }

    "test" {
        Write-Host ">> Running tests..." -ForegroundColor Cyan
        python -m pytest -v
    }

    "eval" {
        Write-Host ">> Running eval (n=$N)..." -ForegroundColor Cyan
        Start-OllamaServe -Port 11434
        python -m scripts.run_eval --n $N
    }

    "suggest-eval-labels" {
        Write-Host ">> Generating eval label suggestions..." -ForegroundColor Cyan
        python -m scripts.propose_eval_labels
    }

    "approve-eval-labels" {
        Write-Host ">> Approving eval labels..." -ForegroundColor Cyan
        python -m scripts.approve_eval_labels
    }

    "stats" {
        Write-Host ">> Project stats..." -ForegroundColor Cyan
        Start-OllamaServe -Port 11434
        python -c "
import sys, json
from pathlib import Path
sys.path.insert(0,'src'); sys.path.insert(0,'.')
from config.settings import settings
from acne_llm.di import build_container

root = Path('.')

# Data stats
raw_docs = root / 'data' / 'raw' / 'documents.jsonl'
ft_data  = root / 'data' / 'finetune' / 'qa_finetuning.jsonl'
llm_data = root / 'LLMData' / 'acne_dataset.jsonl'

n_docs = sum(1 for _ in open(raw_docs, encoding='utf-8')) if raw_docs.exists() else 0
n_qa   = sum(1 for _ in open(ft_data,  encoding='utf-8')) if ft_data.exists()  else 0
n_llm  = sum(1 for _ in open(llm_data, encoding='utf-8')) if llm_data.exists() else 0

print()
print('=== Data ===')
print(f'  Raw docs (data/raw/documents.jsonl)       : {n_docs:,}')
print(f'  QA pairs (data/finetune/qa_finetuning.jsonl): {n_qa:,}')
print(f'  LLMData  (LLMData/acne_dataset.jsonl)     : {n_llm:,}')
print()

# Container / KB stats
c = build_container(settings)
not_built = '(not built)'
print('=== KB ===')
print(f'  ChromaDB chunks : {c.store.count() if c.store else not_built}')
print(f'  BM25 chunks     : {len(c.bm25.chunk_ids) if c.bm25 else not_built}')
print(f'  RAG ready       : {c.rag_ready}')
print()
print('=== LLM ===')
print(f'  Ollama reachable: {c.llm.health()}')
print(f'  Model           : {c.llm.model}')
print(f'  Ollama URL      : {settings.ollama_url}')
print()
"
    }

    "chat" {
        $desc = Read-Host "Mo ta tinh trang mun"
        Start-OllamaServe -Port 11434
        python -c "
import sys; sys.path.insert(0,'src'); sys.path.insert(0,'.')
from config.settings import settings
from acne_llm.di import build_container
from acne_llm.schemas import UserInput
import json
c = build_container(settings)
out = c.llm_only.run(UserInput(description='$desc'))
print(json.dumps(out.model_dump(), ensure_ascii=False, indent=2))
"
    }

    "lint" {
        Write-Host ">> Linting + type-check..." -ForegroundColor Cyan
        python -m ruff check src/ scripts/ config/ --fix
        python -m mypy src/acne_llm --ignore-missing-imports
        Write-Host ">> Lint OK." -ForegroundColor Green
    }

    "docker-build" {
        Write-Host ">> Building Docker image..." -ForegroundColor Cyan
        docker build -t acne-llm:latest .
        Write-Host ">> Image built: acne-llm:latest" -ForegroundColor Green
    }

    "docker-up" {
        Write-Host ">> Starting Docker Compose (Ollama + API)..." -ForegroundColor Cyan
        docker-compose up -d
        Write-Host ">> Services up. API: http://localhost:8000  Ollama: http://localhost:11434" -ForegroundColor Green
    }

    "docker-down" {
        Write-Host ">> Stopping Docker Compose..." -ForegroundColor Cyan
        docker-compose down
    }

    "clean-kb" {
        Write-Host ">> Xoa vector index va BM25 (KHONG xoa raw crawl / finetune data)..." -ForegroundColor Yellow
        $confirm = Read-Host "Xac nhan xoa chroma_db + bm25_index.pkl? (y/N)"
        if ($confirm -eq "y") {
            Remove-Item -Recurse -Force data\chroma_db\* -ErrorAction SilentlyContinue
            Remove-Item -Force data\bm25_index.pkl -ErrorAction SilentlyContinue
            Write-Host ">> KB index cleared. (data/raw va data/finetune giu nguyen)" -ForegroundColor Green
        }
    }

    "clean-raw" {
        Write-Host ">> Xoa raw crawl data..." -ForegroundColor Yellow
        $confirm = Read-Host "Xac nhan xoa data/raw/* ? (y/N)"
        if ($confirm -eq "y") {
            Remove-Item -Recurse -Force data\raw\* -ErrorAction SilentlyContinue
            Write-Host ">> Raw data cleared." -ForegroundColor Green
        }
    }

    "clean-finetune" {
        Write-Host ">> Xoa finetune data va checkpoint..." -ForegroundColor Yellow
        $confirm = Read-Host "Xac nhan xoa data/finetune/* ? (y/N)"
        if ($confirm -eq "y") {
            Remove-Item -Recurse -Force data\finetune\* -ErrorAction SilentlyContinue
            Write-Host ">> Finetune data cleared." -ForegroundColor Green
        }
    }

    "clean-logs" {
        Write-Host ">> Xoa log files..." -ForegroundColor Yellow
        Remove-Item -Force data\logs\*.log -ErrorAction SilentlyContinue
        Remove-Item -Force data\logs\*.json -ErrorAction SilentlyContinue
        Write-Host ">> Logs cleared." -ForegroundColor Green
    }

    "help" {
        Write-Host ""
        Write-Host "  AcneLLM Tasks" -ForegroundColor Cyan
        Write-Host "  ==============" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  -- Setup --" -ForegroundColor DarkGray
        Write-Host "  .\tasks.ps1 install              Install Python deps + venv"
        Write-Host "  .\tasks.ps1 pull-models          Pull Ollama LLM models"
        Write-Host ""
        Write-Host "  -- Data Pipeline --" -ForegroundColor DarkGray
        Write-Host "  .\tasks.ps1 crawl [source]        Crawl 1 source hoac tat ca (GHI DE file cu) (~4-8h)"
        Write-Host "  .\tasks.ps1 crawl-pubmed         Chi crawl PubMed (nhanh)"
        Write-Host "  .\tasks.ps1 build-dataset        Sinh QA pairs cho fine-tune (can API key)"
        Write-Host "  .\tasks.ps1 build-dataset-resume Resume build-dataset (bo qua da xong)"
        Write-Host "  .\tasks.ps1 build-kb             Chunk + embed + index -> chroma/bm25"
        Write-Host "  .\tasks.ps1 build-kb-force       Rebuild KB tu dau (xoa cu)"
        Write-Host "  .\tasks.ps1 overnight-kb         Crawl -> build-kb -> verify (run overnight)"
        Write-Host "  .\tasks.ps1 visualize            Sinh bieu do phan tich dataset"
        Write-Host ""
        Write-Host "  -- Serve --" -ForegroundColor DarkGray
        Write-Host "  .\tasks.ps1 serve                Chay web moi (frontend + backend)"
        Write-Host "  .\tasks.ps1 serve --log          Mo them terminal tail backend log"
        Write-Host "  .\tasks.ps1 serve-lan            Chay backend LAN cho mobile"
        Write-Host ""
        Write-Host "  -- Docker --" -ForegroundColor DarkGray
        Write-Host "  .\tasks.ps1 docker-build         Build Docker image"
        Write-Host "  .\tasks.ps1 docker-up            docker-compose up -d"
        Write-Host "  .\tasks.ps1 docker-down          docker-compose down"
        Write-Host ""
        Write-Host "  -- Dev --" -ForegroundColor DarkGray
        Write-Host "  .\tasks.ps1 test                 Chay pytest"
        Write-Host "  .\tasks.ps1 lint                 Ruff + mypy"
        Write-Host "  .\tasks.ps1 eval                 Chay eval (mac dinh 20 queries)"
        Write-Host "  .\tasks.ps1 suggest-eval-labels  Tao goi y relevant_chunk_ids cho eval"
        Write-Host "  .\tasks.ps1 approve-eval-labels  Copy goi y sang relevant_chunk_ids"
        Write-Host "  .\tasks.ps1 eval 50              Chay eval voi 50 queries"
        Write-Host "  .\tasks.ps1 stats                In thong ke data + KB + Ollama"
        Write-Host "  .\tasks.ps1 chat                 Chat nhanh qua terminal (llm_only)"
        Write-Host ""
        Write-Host "  -- Clean --" -ForegroundColor DarkGray
        Write-Host "  .\tasks.ps1 clean-kb             Xoa chroma_db + bm25 (giu raw/finetune)"
        Write-Host "  .\tasks.ps1 clean-raw            Xoa data/raw/*"
        Write-Host "  .\tasks.ps1 clean-finetune       Xoa data/finetune/*"
        Write-Host "  .\tasks.ps1 clean-logs           Xoa data/logs/*.log"
        Write-Host ""
    }

    default {
        Write-Host "Task '$Task' khong ton tai. Chay '.\tasks.ps1 help' de xem danh sach." -ForegroundColor Red
        exit 1
    }
}
