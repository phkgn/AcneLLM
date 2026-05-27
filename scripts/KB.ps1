# AcneLLM - Build Knowledge Base pipeline (Windows PowerShell)
# Usage:
#   .\scripts\KB.ps1              # full pipeline
#   .\scripts\KB.ps1 -SkipChunk  # skip chunk step
#   .\scripts\KB.ps1 -SkipEval   # skip eval step
#   .\scripts\KB.ps1 -N 200      # generate 200 queries thay vi 1000

param(
    [switch]$SkipChunk,
    [switch]$SkipEval,
    [int]$N = 1000
)

$ErrorActionPreference = "Stop"

$Root   = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$LogDir = Join-Path $Root "logs"

if (-not (Test-Path $Python)) {
    throw "venv not found at $Python"
}

$null = New-Item -ItemType Directory -Force -Path $LogDir

function Banner([string]$msg, [string]$color = "Cyan") {
    Write-Host ""
    Write-Host ("=" * 60) -ForegroundColor $color
    Write-Host "  $msg" -ForegroundColor $color
    Write-Host ("=" * 60) -ForegroundColor $color
}

function RunStep([string]$label, [string[]]$pyArgs) {
    Banner $label
    & $Python @pyArgs
    if ($LASTEXITCODE -ne 0) {
        throw "FAILED: $label (exit $LASTEXITCODE)"
    }
    Write-Host "  -> OK" -ForegroundColor Green
}

function RunParallel([string]$label1, [string[]]$args1,
                     [string]$label2, [string[]]$args2) {
    Banner "PARALLEL: $label1  +  $label2"

    $log1    = Join-Path $LogDir "embed.log"
    $log2    = Join-Path $LogDir "gen_queries.log"
    $errLog1 = Join-Path $LogDir "embed.err.log"
    $errLog2 = Join-Path $LogDir "gen_queries.err.log"

    # Xoa log cu
    foreach ($f in @($log1,$log2,$errLog1,$errLog2)) {
        if (Test-Path $f) { Remove-Item $f -Force }
    }

    # Mo 2 cua so PowerShell rieng — output hien thuc trong window do
    $cmd1 = "Set-Location '$Root'; & '$Python' $($args1 -join ' ') 2>&1 | Tee-Object -FilePath '$log1'; Write-Host '[embed] EXIT: ' + `$LASTEXITCODE; Read-Host 'Press Enter to close'"
    $cmd2 = "Set-Location '$Root'; & '$Python' $($args2 -join ' ') 2>&1 | Tee-Object -FilePath '$log2'; Write-Host '[gen] EXIT: ' + `$LASTEXITCODE; Read-Host 'Press Enter to close'"

    $p1 = Start-Process powershell -ArgumentList "-NoExit", "-Command", $cmd1 -PassThru
    $p2 = Start-Process powershell -ArgumentList "-NoExit", "-Command", $cmd2 -PassThru

    Write-Host "  Opened 2 windows: embed (PID $($p1.Id)) + gen-queries (PID $($p2.Id))" -ForegroundColor Gray
    Write-Host "  Waiting for both to finish..." -ForegroundColor Gray

    # Doi ca 2 ket thuc, hien tail log moi 10s
    $tail1 = 0; $tail2 = 0
    while (-not $p1.HasExited -or -not $p2.HasExited) {
        Start-Sleep -Seconds 10

        if (Test-Path $log1) {
            $lines = @(Get-Content $log1 -ErrorAction SilentlyContinue)
            if ($lines.Count -gt $tail1) {
                $lines[$tail1..($lines.Count - 1)] | ForEach-Object {
                    Write-Host "  [embed] $_" -ForegroundColor DarkCyan
                }
                $tail1 = $lines.Count
            }
        }
        if (Test-Path $log2) {
            $lines = @(Get-Content $log2 -ErrorAction SilentlyContinue)
            if ($lines.Count -gt $tail2) {
                $lines[$tail2..($lines.Count - 1)] | ForEach-Object {
                    Write-Host "  [gen]   $_" -ForegroundColor DarkYellow
                }
                $tail2 = $lines.Count
            }
        }
    }

    # Flush phan con lai
    if (Test-Path $log1) {
        $lines = @(Get-Content $log1 -ErrorAction SilentlyContinue)
        if ($lines.Count -gt $tail1) {
            $lines[$tail1..($lines.Count - 1)] | ForEach-Object {
                Write-Host "  [embed] $_" -ForegroundColor DarkCyan
            }
        }
    }
    if (Test-Path $log2) {
        $lines = @(Get-Content $log2 -ErrorAction SilentlyContinue)
        if ($lines.Count -gt $tail2) {
            $lines[$tail2..($lines.Count - 1)] | ForEach-Object {
                Write-Host "  [gen]   $_" -ForegroundColor DarkYellow
            }
        }
    }

    # Check exit code qua log file (cua so van mo nen khong lay duoc ExitCode truc tiep)
    $embedOk = Test-Path $log1
    $genOk   = Test-Path $log2

    # Doc dong cuoi de check exit
    if ($embedOk) {
        $last = (Get-Content $log1 -ErrorAction SilentlyContinue) | Select-Object -Last 5
        if ($last -match "Error|Traceback|FAILED|exit 1") {
            throw "Embed job FAILED. Check $log1"
        }
    }
    if ($genOk) {
        $last = (Get-Content $log2 -ErrorAction SilentlyContinue) | Select-Object -Last 5
        if ($last -match "Error|Traceback|FAILED|exit 1") {
            throw "Gen-queries job FAILED. Check $log2"
        }
    }

    Write-Host "  -> Both parallel steps OK" -ForegroundColor Green
    Write-Host "  (Ban co the dong 2 cua so embed/gen neu chua tu dong dong)" -ForegroundColor Gray
}

# ============================================================
$t0 = Get-Date
Banner "AcneLLM -- Build KB Pipeline" "Green"
Write-Host "  Root  : $Root"
Write-Host "  Logs  : $LogDir"

# [1] Chunk
if (-not $SkipChunk) {
    RunStep "[1/4] Chunk -> chunks.jsonl" @("scripts/build_kb.py", "--step", "chunk", "--force")
} else {
    Write-Host "  [1/4] Chunk — SKIPPED" -ForegroundColor Yellow
}

# [2] Embed + Gen queries — song song trong 2 cua so rieng
RunParallel `
    "embed"       @("scripts/build_kb.py", "--step", "embed") `
    "gen-queries" @("scripts/eval_rag.py", "--skip-eval", "--n", "$N")

# [3] BM25
RunStep "[3/4] BM25 index" @("scripts/build_kb.py", "--step", "bm25")

# [4] Eval RAG
if (-not $SkipEval) {
    RunStep "[4/4] Eval RAG (hybrid)" @("scripts/eval_rag.py", "--skip-gen", "--mode", "hybrid")
} else {
    Write-Host "  [4/4] Eval RAG — SKIPPED" -ForegroundColor Yellow
}

$elapsed = [math]::Round(((Get-Date) - $t0).TotalMinutes, 1)
Banner "Done! Total: $elapsed minutes" "Green"
