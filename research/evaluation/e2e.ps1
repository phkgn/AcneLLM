#requires -Version 5.1


# research/ la thu muc cha cua package nay ke tu Phase 7.
$env:PYTHONPATH = "$PSScriptRoot\..;$env:PYTHONPATH"

[CmdletBinding()]
param(
    [ValidateRange(1, 128)]
    [int]$Concurrency = 32,

    [ValidateRange(1, 20)]
    [int]$MaxIntakeGenerationAttempts = 5,

    [ValidateRange(1, 5)]
    [int]$MaxGeneratorAttempts = 2,

    [string]$RunOut = "evaluation/reports/run_full_v3_2"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path

Push-Location $RepoRoot
try {
    $IntakeDataset = "evaluation/datasets/active/intake_eval.v2_1500.jsonl"
    $GeneratorDataset = "evaluation/datasets/active/generator_eval.v3_2_145.jsonl"
    $IntakeReport = "$RunOut/intake/report.json"
    $IntakePartial = "evaluation/datasets/active/intake_eval.v2_1500.partial.jsonl"
    $IntakeStdoutLog = "evaluation/reports/intake_v2_no_train_cosine.stdout.log"
    $IntakeStderrLog = "evaluation/reports/intake_v2_no_train_cosine.stderr.log"
    $E2ELog = "$RunOut/e2e.console.log"

    New-Item -ItemType Directory -Path $RunOut -Force | Out-Null
    $TranscriptStarted = $false
    try {
        Start-Transcript -Path $E2ELog -Append | Out-Null
        $TranscriptStarted = $true
        Write-Host "Log toàn bộ E2E: $E2ELog"
    }
    catch {
        Write-Warning "Không mở được transcript; console vẫn tiếp tục: $($_.Exception.Message)"
    }

    function Get-IntakeGenerator {
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.Name -match "^python(\.exe)?$" -and
                $_.CommandLine -like "*evaluation.datasets.make_intake_set_v2*" -and
                $_.CommandLine -notlike "*--smoke*"
            } |
            Select-Object -First 1
    }

    function Write-NewTextLogLines {
        param(
            [string]$Path,
            [ref]$Cursor,
            [string]$Prefix
        )

        if (-not (Test-Path -LiteralPath $Path)) {
            return
        }
        $Lines = @(Get-Content -LiteralPath $Path)
        $Start = [int]$Cursor.Value
        if ($Lines.Count -le $Start) {
            return
        }
        for ($Index = $Start; $Index -lt $Lines.Count; $Index++) {
            $Line = [string]$Lines[$Index]
            # sentence-transformers/tqdm ghi progress bar vào stderr cho MỖI
            # câu embed. Đây không phải lỗi và sẽ che lấp log nghiệp vụ.
            if (
                $Prefix -eq "[intake:err] " -and
                ($Line -match "^\s*(Batches:|Loading weights:|$)")
            ) {
                continue
            }
            Write-Host "$Prefix$Line"
        }
        $Cursor.Value = $Lines.Count
    }

    function Write-NewAcceptedRows {
        param(
            [string]$Path,
            [ref]$Cursor
        )

        if (-not (Test-Path -LiteralPath $Path)) {
            return
        }
        $Lines = @(Get-Content -LiteralPath $Path)
        $Start = [int]$Cursor.Value
        if ($Lines.Count -le $Start) {
            return
        }
        for ($Index = $Start; $Index -lt $Lines.Count; $Index++) {
            try {
                $Row = $Lines[$Index] | ConvertFrom-Json
                $Users = @($Row.messages | Where-Object { $_.role -eq "user" })
                $Text = ([string]$Users[-1].content).Replace("`r", " ").Replace("`n", " ")
                Write-Host "[intake:data][$($Index + 1)/1500][$($Row.meta.eval_case)] $Text"
            }
            catch {
                Write-Warning "Không đọc được checkpoint row $($Index + 1): $($_.Exception.Message)"
            }
        }
        $Cursor.Value = $Lines.Count
    }

    function Wait-IntakeGeneratorWithLogs {
        param([int]$ProcessId)

        # Không phát lại hàng nghìn dòng log lịch sử khi E2E vừa attach vào
        # process đang chạy. Chỉ relay dữ liệu được ghi từ thời điểm này.
        $StdoutCursor = if (Test-Path -LiteralPath $IntakeStdoutLog) {
            (Get-Content -LiteralPath $IntakeStdoutLog | Measure-Object -Line).Lines
        } else { 0 }
        $StderrCursor = if (Test-Path -LiteralPath $IntakeStderrLog) {
            (Get-Content -LiteralPath $IntakeStderrLog | Measure-Object -Line).Lines
        } else { 0 }
        $AcceptedCursor = 0
        if (Test-Path -LiteralPath $IntakePartial) {
            $AcceptedCursor = (Get-Content -LiteralPath $IntakePartial | Measure-Object -Line).Lines
        }
        Write-Host "Checkpoint hiện có: $AcceptedCursor/1500. Đang relay log PID $ProcessId..."

        while (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue) {
            Write-NewTextLogLines -Path $IntakeStdoutLog -Cursor ([ref]$StdoutCursor) -Prefix "[intake:out] "
            Write-NewTextLogLines -Path $IntakeStderrLog -Cursor ([ref]$StderrCursor) -Prefix "[intake:err] "
            Write-NewAcceptedRows -Path $IntakePartial -Cursor ([ref]$AcceptedCursor)
            Start-Sleep -Seconds 1
        }

        # Flush phần log/checkpoint được ghi ngay trước lúc process thoát.
        Write-NewTextLogLines -Path $IntakeStdoutLog -Cursor ([ref]$StdoutCursor) -Prefix "[intake:out] "
        Write-NewTextLogLines -Path $IntakeStderrLog -Cursor ([ref]$StderrCursor) -Prefix "[intake:err] "
        Write-NewAcceptedRows -Path $IntakePartial -Cursor ([ref]$AcceptedCursor)
        Write-Host "Intake generator PID $ProcessId đã kết thúc."
    }

    function Test-GeneratorDataset {
        if (-not (Test-Path -LiteralPath $GeneratorDataset)) {
            return $false
        }

        python -c "from pathlib import Path; from evaluation.datasets.registry import load_dataset; load_dataset(Path(r'$GeneratorDataset'))"
        if ($LASTEXITCODE -ne 0) {
            return $false
        }

        try {
            $Rows = @(
                Get-Content -LiteralPath $GeneratorDataset |
                    ForEach-Object { $_ | ConvertFrom-Json }
            )
        }
        catch {
            return $false
        }

        $Grounded = @(
            $Rows | Where-Object { $_.task_type -eq "answer_quality" }
        ).Count
        $Policy = @(
            $Rows | Where-Object { $_.task_type -eq "policy_safety" }
        ).Count
        $BadVersion = @(
            $Rows | Where-Object { $_.dataset_version -ne "v3.2" }
        ).Count
        $BadModel = @(
            $Rows | Where-Object {
                $_.source_provenance -eq "synthetic_deepseek" -and
                $_.generator_model -ne "deepseek-v4-pro"
            }
        ).Count

        return (
            $Grounded -eq 100 -and
            $Policy -ge 45 -and
            $BadVersion -eq 0 -and
            $BadModel -eq 0
        )
    }

    function Test-IntakeReport {
        if (-not (Test-Path -LiteralPath $IntakeReport)) {
            return $false
        }

        try {
            $Report = Get-Content -LiteralPath $IntakeReport -Raw |
                ConvertFrom-Json
        }
        catch {
            return $false
        }

        $ReportDataset = ([string]$Report.dataset).Replace("\", "/")
        return (
            $Report.rows_input -eq 1500 -and
            $Report.clean_measurement -eq $true -and
            $ReportDataset -eq $IntakeDataset
        )
    }

    function Test-OllamaModels {
        try {
            $Response = Invoke-RestMethod `
                -Uri "http://localhost:11434/api/tags" `
                -TimeoutSec 10
            $Names = @(
                $Response.models | ForEach-Object {
                    $_.name
                    ($_.name -split ":")[0]
                }
            )
            return (
                ($Names -contains "acne-generator") -and
                ($Names -contains "acne-intaker")
            )
        }
        catch {
            return $false
        }
    }

    # 1. Sinh đúng 1.500 dòng intaker. Nếu một process đang chạy thì chờ;
    # nếu process kết thúc khi quota còn thiếu thì resume từ checkpoint.
    for (
        $Attempt = 1
        $Attempt -le $MaxIntakeGenerationAttempts -and
            -not (Test-Path -LiteralPath $IntakeDataset)
        $Attempt++
    ) {
        $Running = Get-IntakeGenerator
        if ($null -ne $Running) {
            Write-Host "Đang chờ intake generator PID $($Running.ProcessId)..."
            Wait-IntakeGeneratorWithLogs -ProcessId $Running.ProcessId
        }
        else {
            Write-Host "Intake generation lượt $Attempt/$MaxIntakeGenerationAttempts..."
            python -u -m evaluation.datasets.make_intake_set_v2 `
                --yes `
                --model deepseek-v4-pro `
                --out $IntakeDataset `
                --concurrency $Concurrency `
                --dedup-cosine 0.90 `
                --attempts-factor 10
        }
    }

    if (-not (Test-Path -LiteralPath $IntakeDataset)) {
        throw "Intaker chưa tạo được file final sau $MaxIntakeGenerationAttempts lượt."
    }
    $IntakeCount = (
        Get-Content -LiteralPath $IntakeDataset | Measure-Object -Line
    ).Lines
    if ($IntakeCount -ne 1500) {
        throw "Intake dataset có $IntakeCount dòng, yêu cầu đúng 1500."
    }
    Write-Host "Intaker dataset đạt: $IntakeCount dòng."

    # 2. Sinh generator v3.2. Chỉ đi tiếp khi registry, số dòng, version và
    # provenance model đều đạt.
    for (
        $Attempt = 1
        $Attempt -le $MaxGeneratorAttempts -and -not (Test-GeneratorDataset)
        $Attempt++
    ) {
        Write-Host "Generator dataset lượt $Attempt/$MaxGeneratorAttempts..."
        python -u -m evaluation.datasets.make_eval_set `
            --generate `
            --model deepseek-v4-pro `
            --n 100 `
            --policy-n 45 `
            --out $GeneratorDataset
    }
    if (-not (Test-GeneratorDataset)) {
        throw "Generator v3.2 không đạt schema/count/model gate."
    }
    Write-Host "Generator dataset hợp lệ."

    # 3. Chờ tối đa 5 phút cho SSH tunnel/Ollama và kiểm đúng hai model.
    $OllamaReady = $false
    for ($Attempt = 1; $Attempt -le 10; $Attempt++) {
        if (Test-OllamaModels) {
            $OllamaReady = $true
            break
        }
        Write-Host "Đang chờ tunnel/Ollama và hai model ($Attempt/10)..."
        Start-Sleep -Seconds 30
    }
    if (-not $OllamaReady) {
        throw "Tunnel/Ollama không hoạt động hoặc thiếu acne-generator/acne-intaker."
    }

    # 4. run_intake không có checkpoint từng dòng. Retry tối đa hai lần và
    # không chấp nhận report có fallback hoặc đọc thiếu input.
    for (
        $Attempt = 1
        $Attempt -le 2 -and -not (Test-IntakeReport)
        $Attempt++
    ) {
        Write-Host "Intake evaluation lượt $Attempt/2..."
        python -u -m evaluation.runners.run_intake `
            --dataset $IntakeDataset `
            --train datagen/intakedata/output/intake/intake.train.jsonl `
            --output $IntakeReport
    }
    if (-not (Test-IntakeReport)) {
        throw "Intake evaluation lỗi, thiếu dòng hoặc có fallback."
    }
    Write-Host "Intake evaluation sạch và đủ 1.500 input."

    # 5. Chạy retrieval và sáu ablation arm chuẩn. full_evaluation tự retry
    # từng bước và run_ablation resume từ checkpoint trong RunOut.
    if (-not (Test-OllamaModels)) {
        throw "Tunnel/Ollama đã ngắt trước full evaluation."
    }
    python -u -m evaluation.full_evaluation `
        --yes `
        --retry 5 `
        --skip intake `
        --dataset $GeneratorDataset `
        --arms "RRR,RNR,ROR,ORR,RRO,RNO" `
        --out $RunOut
    if ($LASTEXITCODE -ne 0) {
        throw "Full evaluation thất bại. Xem $RunOut."
    }

    Write-Host ""
    Write-Host "E2E hoàn tất: $RunOut"
}
finally {
    if ($TranscriptStarted) {
        try {
            Stop-Transcript | Out-Null
        }
        catch {
            Write-Warning "Không đóng được transcript: $($_.Exception.Message)"
        }
    }
    Pop-Location
}
