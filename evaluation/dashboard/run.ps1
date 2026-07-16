param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$DashboardDir = $PSScriptRoot
$Url = "http://127.0.0.1:3100"

Set-Location -LiteralPath $DashboardDir

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Error "Không tìm thấy Node.js trong PATH. Hãy cài Node.js rồi chạy lại."
}

if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    Write-Error "Không tìm thấy npm trong PATH. Hãy cài Node.js/npm rồi chạy lại."
}

$Listener = Get-NetTCPConnection -LocalPort 3100 -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1

if ($Listener) {
    Write-Host "Port 3100 đang được sử dụng bởi PID $($Listener.OwningProcess)." -ForegroundColor Yellow
    Write-Host "Dashboard có thể đã chạy tại $Url" -ForegroundColor Cyan
    exit 1
}

if (-not $SkipInstall -and -not (Test-Path -LiteralPath (Join-Path $DashboardDir "node_modules"))) {
    Write-Host "Đang cài dependencies..." -ForegroundColor Cyan
    & npm.cmd install
    if ($LASTEXITCODE -ne 0) {
        throw "npm install thất bại với exit code $LASTEXITCODE."
    }
}

Write-Host "AcneLLM Eval Dashboard: $Url" -ForegroundColor Green
Write-Host "Nhấn Ctrl+C để dừng server." -ForegroundColor DarkGray

& npm.cmd run dev
exit $LASTEXITCODE
