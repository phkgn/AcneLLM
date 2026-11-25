# AcneLLM - chay toan bo he thong tai may, tren Windows PowerShell.
#
#   Ollama LOCAL (:11434) + Backend (:8000) + Frontend (:3000)
#
# Muon chay model tren RunPod thay vi may minh: dung `scripts\runpod.ps1`.
param(
    [switch]$Log
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$VenvUvicorn = Join-Path $Root ".venv\Scripts\uvicorn.exe"
$BackendLog = Join-Path $env:TEMP "acne-llm-backend.log"

if (-not (Test-Path $VenvPython)) {
    throw "Windows venv not found. Create .venv with the steps in README.md (section: Clone va cai backend)."
}

try {
    & $VenvPython -V | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "bad venv"
    }
} catch {
    throw "Windows venv is broken. Recreate .venv with the steps in README.md (section: Clone va cai backend)."
}

function Stop-PortProcess {
    param([int]$Port)

    $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    if (-not $connections) {
        return
    }

    $pids = $connections | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($processId in $pids) {
        $procName = (Get-Process -Id $processId -ErrorAction SilentlyContinue).Name
        Write-Host "Stopping PID $processId on port $Port ($procName)..." -ForegroundColor Yellow
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }
}

function Wait-ForHttpOk {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Uri,
        [int]$TimeoutSeconds = 120
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) {
                return $true
            }
        } catch {}
        Start-Sleep -Seconds 1
    }

    return $false
}

function Assert-OllamaModelsAvailable {
    try {
        $tags = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 15 -ErrorAction Stop
    } catch {
        throw "Ollama is not responding on http://localhost:11434: $($_.Exception.Message)"
    }

    $availableModels = @($tags.models | ForEach-Object { $_.name -replace ":latest$", "" })
    $requiredModels = @("acne-generator-v2", "acne-intaker")
    $missingModels = @($requiredModels | Where-Object { $_ -notin $availableModels })
    if ($missingModels.Count -gt 0) {
        throw "Ollama on :11434 is missing required model(s): $($missingModels -join ', ')."
    }
}

function Ensure-LocalOllamaReady {
    $listening = Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1

    if ($listening) {
        # Cong da co nguoi giu. Neu do la SSH tunnel cua runpod.ps1 thi dung lai
        # va noi ro -- script nay chay Ollama TAI MAY, khong tu y giet tunnel cua
        # ban de gianh cong.
        $owner = Get-Process -Id $listening.OwningProcess -ErrorAction SilentlyContinue
        if ($owner -and $owner.ProcessName -eq "ssh") {
            throw "Port 11434 dang bi SSH tunnel giu (PID $($owner.Id)). Chay '.\scripts\runpod.ps1 -Stop' neu muon dung Ollama tai may, hoac dung tunnel do va bo qua canh bao nay."
        }
        Write-Host "Ollama da chay san (PID $($owner.Id)) - khong mo cua so moi." -ForegroundColor Yellow
    } else {
        if (-not (Get-Command "ollama.exe" -ErrorAction SilentlyContinue)) {
            throw "Ollama chua chay va khong tim thay ollama.exe trong PATH."
        }

        # Cua so RIENG, khong an: log cua Ollama (model nao duoc load, VRAM,
        # loi runner) la thu can nhin khi tra loi cham hoac model bi offload.
        Write-Host "Starting local Ollama on http://localhost:11434..." -ForegroundColor Green
        Start-Process powershell -ArgumentList "-NoExit", "-Command", "ollama serve"

        if (-not (Wait-ForHttpOk -Uri "http://localhost:11434/api/tags" -TimeoutSeconds 30)) {
            throw "Local Ollama did not respond on http://localhost:11434 within 30 seconds."
        }
    }

    Assert-OllamaModelsAvailable
    Write-Host "Local Ollama ready (acne-generator-v2 + acne-intaker)." -ForegroundColor Green
}

Write-Host ""
Write-Host "=== AcneLLM - Running All Services (local) ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Mo 3 cua so:" -ForegroundColor Yellow
Write-Host "  1. Ollama serve         (http://localhost:11434)"
Write-Host "  2. Backend API          (http://localhost:8000)"
Write-Host "  3. Frontend UI          (http://localhost:3000)"
Write-Host ""
Write-Host "Chay model tren RunPod thi dung scripts\runpod.ps1." -ForegroundColor Yellow
Write-Host ""
Read-Host "Press Enter to continue"

Write-Host "Checking local Ollama..." -ForegroundColor Cyan
Ensure-LocalOllamaReady

Write-Host "Starting Backend API..." -ForegroundColor Green
Stop-PortProcess -Port 8000
if ($Log) {
    $null = Remove-Item -Force $BackendLog -ErrorAction SilentlyContinue
    $null = New-Item -ItemType File -Force -Path $BackendLog
    $backendCommand = "cd `"$Root`"; & `"$VenvUvicorn`" acne_llm.api.app:app --host 0.0.0.0 --port 8000 --reload *> `"$BackendLog`""
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCommand

    $tailCommand = "Get-Content -Path `"$BackendLog`" -Wait -Tail 20"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $tailCommand
} else {
    $backendCommand = "cd `"$Root`"; & `"$VenvUvicorn`" acne_llm.api.app:app --host 0.0.0.0 --port 8000 --reload"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCommand
}

Write-Host "Waiting for backend on http://localhost:8000..." -ForegroundColor Cyan
if (-not (Wait-ForHttpOk -Uri "http://localhost:8000/docs" -TimeoutSeconds 180)) {
    if (Test-Path $BackendLog) {
        Write-Host ""
        Write-Host "Backend log tail ($BackendLog):" -ForegroundColor Yellow
        Get-Content -Path $BackendLog -Tail 80 -ErrorAction SilentlyContinue
    }
    throw "Backend did not respond on http://localhost:8000 within 180 seconds."
}

Write-Host "Backend is ready." -ForegroundColor Green

Write-Host "Starting Frontend..." -ForegroundColor Green
$frontendCommand = "cd `"$Root\frontend`"; npm run dev"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCommand

Write-Host "Waiting for frontend on http://localhost:3000..." -ForegroundColor Cyan
if (-not (Wait-ForHttpOk -Uri "http://localhost:3000" -TimeoutSeconds 180)) {
    throw "Frontend did not respond on http://localhost:3000 within 180 seconds."
}

Write-Host ""
Write-Host "Opening http://localhost:3000 now..." -ForegroundColor Cyan
Start-Process "http://localhost:3000"

Write-Host ""
Write-Host "Services started. Close the backend/frontend windows to stop them." -ForegroundColor Green
