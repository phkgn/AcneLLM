# AcneLLM - run all services on Windows PowerShell
param(
    [switch]$Log,
    [string]$RunpodIp = "213.173.107.79",
    [int]$RunpodSshPort = 40463,
    [string]$RunpodSshKey = "$env:USERPROFILE\.ssh\runpod_acnellm_ed25519"
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

function Ensure-RemoteOllamaReady {
    $listener = Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1

    if (-not $listener) {
        if (-not (Test-Path $RunpodSshKey)) {
            throw "RunPod SSH key not found: $RunpodSshKey"
        }

        Write-Host "Starting RunPod SSH tunnel on http://localhost:11434..." -ForegroundColor Green
        $tunnelArguments = @(
            "-N",
            "-L", "127.0.0.1:11434:127.0.0.1:11434",
            "-p", "$RunpodSshPort",
            "-i", $RunpodSshKey,
            "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ExitOnForwardFailure=yes",
            "-o", "ServerAliveInterval=30",
            "-o", "ServerAliveCountMax=3",
            "root@$RunpodIp"
        )
        $tunnelProcess = Start-Process -FilePath "ssh.exe" -ArgumentList $tunnelArguments -WindowStyle Hidden -PassThru

        if (-not (Wait-ForHttpOk -Uri "http://localhost:11434/api/tags" -TimeoutSeconds 30)) {
            if (-not $tunnelProcess.HasExited) {
                Stop-Process -Id $tunnelProcess.Id -ErrorAction SilentlyContinue
            }
            throw "Could not connect to RunPod Ollama through SSH ($RunpodIp`:$RunpodSshPort). Check the current SSH over exposed TCP port in RunPod."
        }

        $listener = Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue |
            Select-Object -First 1
    }

    $owner = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
    if (-not $owner -or $owner.ProcessName -ne "ssh") {
        $ownerName = if ($owner) { $owner.ProcessName } else { "unknown" }
        throw "Port 11434 is owned by '$ownerName', not the RunPod SSH tunnel. Close local Ollama and start the SSH tunnel first."
    }

    try {
        $tags = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 15 -ErrorAction Stop
    } catch {
        throw "The SSH tunnel is listening on port 11434, but remote Ollama is not responding: $($_.Exception.Message)"
    }

    $availableModels = @($tags.models | ForEach-Object { $_.name -replace ":latest$", "" })
    $requiredModels = @("acne-generator", "acne-intaker")
    $missingModels = @($requiredModels | Where-Object { $_ -notin $availableModels })
    if ($missingModels.Count -gt 0) {
        throw "Remote Ollama is missing required model(s): $($missingModels -join ', ')."
    }

    Write-Host "RunPod Ollama tunnel is ready (acne-generator + acne-intaker)." -ForegroundColor Green
}

Write-Host ""
Write-Host "=== AcneLLM - Running All Services ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "This script ensures the RunPod Ollama tunnel and opens 2 windows:" -ForegroundColor Yellow
Write-Host "  Automatic: RunPod Ollama (http://localhost:11434)"
Write-Host "  1. Backend API          (http://localhost:8000)"
Write-Host "  2. Frontend UI          (http://localhost:3000)"
Write-Host ""
Read-Host "Press Enter to continue"

Write-Host "Checking RunPod Ollama tunnel..." -ForegroundColor Cyan
Ensure-RemoteOllamaReady

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
