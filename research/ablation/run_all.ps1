# Chạy đoạn dài không cần trông: run -> judge -> report.
#
# KHÔNG bao gồm gen_cases. Sinh case xong phải có người đối chiếu golden_context
# ngược về guideline_docs/, và sau pilot phải đọc sigma_d để chốt N. Hai việc đó
# là cổng quyết định, không phải bước trong pipeline.
#
#   .\ablation\run_all.ps1 -Cases ablation\data\cases.dev.jsonl -Tag dev
#   .\ablation\run_all.ps1 -Cases ablation\data\cases.test.jsonl -Tag test
#   .\ablation\run_all.ps1 -Cases ... -Arms RRR,NRR,RNR      # thêm arm degrade
#
# run.py resume theo từng ô (case, arm) nên sập giữa chừng thì chạy lại là tiếp tục.

param(
  [Parameter(Mandatory = $true)][string]$Cases,
  [string]$Tag = "main",
  [string]$Arms = "",
  [int]$Limit = 0
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:PYTHONPATH = "src"

$py = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
$run = "ablation\runs\$Tag.jsonl"
$judged = "ablation\runs\$Tag.judged.jsonl"
$report = "ablation\runs\$Tag.report.md"
$log = "ablation\runs\$Tag.log"
New-Item -ItemType Directory -Force -Path "ablation\runs" | Out-Null

# ── preflight: hỏng ở đây rẻ hơn hỏng sau 3 tiếng ────────────────────────────
foreach ($k in @("OPENAI_API_KEY", "DEEPSEEK_API_KEY")) {
  if (-not (Get-Item "env:$k" -EA SilentlyContinue)) { throw "thiếu biến môi trường $k" }
}
if (-not (Test-Path $Cases)) { throw "không thấy case file: $Cases" }
& $py -c "from ablation.cases import load; c=load(r'$Cases'); print(f'{len(c)} case hợp lệ')"
if ($LASTEXITCODE -ne 0) { throw "case file không qua validate" }
& $py -c "from ablation import frontier as f; print('case=',f.CASE_MODEL,'oracle=',f.ORACLE_MODEL,'judge=',f.JUDGE_MODEL); [print('CẢNH BÁO:',w) for w in f.roles()]"
$ollama = if ($env:OLLAMA_URL) { $env:OLLAMA_URL } else { "http://localhost:11434" }
try { Invoke-WebRequest -Uri "$ollama/api/tags" -TimeoutSec 5 -UseBasicParsing | Out-Null }
catch { throw "Ollama không phản hồi tại $ollama — các arm R cần nó" }

# ── ba chặng ─────────────────────────────────────────────────────────────────
$t0 = Get-Date
"[$(Get-Date -f HH:mm:ss)] bắt đầu · $Cases -> $Tag" | Tee-Object -FilePath $log

$a = @("-m", "ablation.run", "--cases", $Cases, "--out", $run)
if ($Arms) { $a += @("--arms", $Arms) }
if ($Limit -gt 0) { $a += @("--limit", "$Limit") }
& $py @a 2>&1 | Tee-Object -FilePath $log -Append
if ($LASTEXITCODE -ne 0) { throw "run.py hỏng — chạy lại lệnh này để tiếp tục" }

& $py -m ablation.judge --run $run --cases $Cases --out $judged 2>&1 | Tee-Object -FilePath $log -Append
if ($LASTEXITCODE -ne 0) { throw "judge.py hỏng" }

& $py -m ablation.report --run $judged --out $report 2>&1 | Tee-Object -FilePath $log -Append
if ($LASTEXITCODE -ne 0) { throw "report.py hỏng" }

"[$(Get-Date -f HH:mm:ss)] xong sau $([int]((Get-Date) - $t0).TotalMinutes) phút -> $report" |
  Tee-Object -FilePath $log -Append
