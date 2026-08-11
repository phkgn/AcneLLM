# AcneLLM - SSH tunnel toi Ollama chay tren RunPod.
#
# Lam DUNG mot viec: forward 127.0.0.1:11434 sang Ollama cua pod, roi doi API
# tra loi. Khong dong backend, khong dong frontend -- chay `scripts\RUN.ps1`
# sau do, no thay :11434 da co nguoi phuc vu va dung luon.
#
#   .\scripts\runpod.ps1                 # mo tunnel (dung IP/port mac dinh)
#   .\scripts\runpod.ps1 -Ip 1.2.3.4 -SshPort 40001
#   .\scripts\runpod.ps1 -Status         # xem tunnel co dang chay khong
#   .\scripts\runpod.ps1 -Stop           # dong tunnel
#
# IP va port cua RunPod DOI moi lan tao pod. Lay o muc "SSH over exposed TCP".
param(
    [string]$Ip = "213.173.107.79",
    [int]$SshPort = 40463,
    [string]$SshKey = "$env:USERPROFILE\.ssh\runpod_acnellm_ed25519",
    [switch]$Stop,
    [switch]$Status
)

$ErrorActionPreference = "Stop"

function Get-TunnelProcess {
    $listener = Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $listener) {
        return $null
    }
    $owner = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
    if ($owner -and $owner.ProcessName -eq "ssh") {
        return $owner
    }
    return $null
}

function Get-PortOwnerName {
    $listener = Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $listener) {
        return $null
    }
    $owner = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
    if ($owner) { return $owner.ProcessName } else { return "unknown" }
}

function Wait-ForHttpOk {
    param([string]$Uri, [int]$TimeoutSeconds = 30)

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

# ── -Status ──────────────────────────────────────────────────────────────────
if ($Status) {
    $tunnel = Get-TunnelProcess
    if ($tunnel) {
        Write-Host "Tunnel dang chay (PID $($tunnel.Id))." -ForegroundColor Green
        $models = try {
            (Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 10).models |
                ForEach-Object { $_.name }
        } catch { @() }
        if ($models) {
            Write-Host "Model tren pod: $($models -join ', ')"
        } else {
            Write-Host "Tunnel mo nhung /api/tags khong tra loi." -ForegroundColor Yellow
        }
    } else {
        $ownerName = Get-PortOwnerName
        if ($ownerName) {
            Write-Host "Khong co tunnel. Port 11434 dang thuoc ve '$ownerName'." -ForegroundColor Yellow
        } else {
            Write-Host "Khong co tunnel, port 11434 dang trong." -ForegroundColor Yellow
        }
    }
    return
}

# ── -Stop ────────────────────────────────────────────────────────────────────
if ($Stop) {
    $tunnel = Get-TunnelProcess
    if (-not $tunnel) {
        Write-Host "Khong co tunnel nao de dong." -ForegroundColor Yellow
        return
    }
    Write-Host "Dong tunnel (PID $($tunnel.Id))..." -ForegroundColor Yellow
    Stop-Process -Id $tunnel.Id -Force -ErrorAction SilentlyContinue

    $deadline = (Get-Date).AddSeconds(10)
    while ((Get-TunnelProcess) -and (Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 250
    }
    if (Get-TunnelProcess) {
        throw "Khong dong duoc tunnel tren port 11434."
    }
    Write-Host "Da dong." -ForegroundColor Green
    return
}

# ── Mo tunnel ────────────────────────────────────────────────────────────────
$existing = Get-TunnelProcess
if ($existing) {
    Write-Host "Tunnel da chay san (PID $($existing.Id)). Chay .\scripts\RUN.ps1 duoc roi." -ForegroundColor Green
    return
}

$ownerName = Get-PortOwnerName
if ($ownerName) {
    throw "Port 11434 dang thuoc ve '$ownerName' (co the la ollama chay tai may). Tat no truoc, hoac cu dung luon Ollama do va bo qua script nay."
}

if (-not (Test-Path $SshKey)) {
    throw "Khong tim thay SSH key: $SshKey"
}

Write-Host "Mo tunnel toi RunPod $Ip`:$SshPort ..." -ForegroundColor Green
$tunnelArguments = @(
    "-N",
    "-L", "127.0.0.1:11434:127.0.0.1:11434",
    "-p", "$SshPort",
    "-i", $SshKey,
    "-o", "BatchMode=yes",
    "-o", "StrictHostKeyChecking=accept-new",
    "-o", "ExitOnForwardFailure=yes",
    "-o", "ServerAliveInterval=30",
    "-o", "ServerAliveCountMax=3",
    "root@$Ip"
)
$tunnelProcess = Start-Process -FilePath "ssh.exe" -ArgumentList $tunnelArguments -WindowStyle Hidden -PassThru

if (-not (Wait-ForHttpOk -Uri "http://localhost:11434/api/tags" -TimeoutSeconds 30)) {
    if (-not $tunnelProcess.HasExited) {
        Stop-Process -Id $tunnelProcess.Id -Force -ErrorAction SilentlyContinue
    }
    throw "Khong ket noi duoc Ollama qua SSH ($Ip`:$SshPort). Kiem tra lai IP/port o muc 'SSH over exposed TCP' trong RunPod -- hai gia tri nay doi moi lan tao pod."
}

$models = @(
    (Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 15).models |
        ForEach-Object { $_.name -replace ":latest$", "" }
)
$missing = @(@("acne-generator", "acne-intaker") | Where-Object { $_ -notin $models })

Write-Host ""
Write-Host "Tunnel san sang tren http://localhost:11434 (PID $($tunnelProcess.Id))." -ForegroundColor Green
if ($missing.Count -gt 0) {
    Write-Host "CANH BAO: pod thieu model: $($missing -join ', ')" -ForegroundColor Yellow
    Write-Host "Model co san: $($models -join ', ')"
} else {
    Write-Host "Pod co du acne-generator + acne-intaker." -ForegroundColor Green
}
Write-Host ""
Write-Host "Chay tiep:  .\scripts\RUN.ps1" -ForegroundColor Cyan
Write-Host "Dong sau:   .\scripts\runpod.ps1 -Stop" -ForegroundColor Cyan
