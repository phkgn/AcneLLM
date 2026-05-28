# AcneLLM - run all services on Windows PowerShell
param(
    [switch]$Log
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$VenvUvicorn = Join-Path $Root ".venv\Scripts\uvicorn.exe"
$BackendLog = Join-Path $env:TEMP "acne-llm-backend.log"

if (-not (Test-Path $VenvPython)) {
    throw "Windows venv not found. Run '.\tasks.ps1 install' from the repo root to create .venv."
}

try {
    & $VenvPython -V | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "bad venv"
    }
} catch {
    throw "Windows venv is broken. Run '.\tasks.ps1 install' from the repo root to rebuild .venv."
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

Write-Host ""
Write-Host "=== AcneLLM - Running All Services ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "This script will open 3 windows:" -ForegroundColor Yellow
Write-Host "  1. Ollama Server  (http://localhost:11434)"
Write-Host "  2. Backend API    (http://localhost:8000)"
Write-Host "  3. Frontend UI    (http://localhost:3000)"
Write-Host ""
Read-Host "Press Enter to continue"

Write-Host "Starting Ollama server..." -ForegroundColor Green
Stop-PortProcess -Port 11434
Start-Process powershell -ArgumentList "-NoExit", "-Command", "ollama serve"
Start-Sleep -Seconds 2

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
Write-Host "Services started. Close any service window to stop it." -ForegroundColor Green
