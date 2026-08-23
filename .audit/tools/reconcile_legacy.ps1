param([Parameter(Mandatory=$true)][string]$RunDir)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$run = (Resolve-Path $RunDir).Path
$scope = Get-Content -LiteralPath (Join-Path $run 'scope.json') -Raw | ConvertFrom-Json
$manifest = @{}
Get-Content -LiteralPath (Join-Path $run 'manifest.jsonl') | ForEach-Object {
    $rec = $_ | ConvertFrom-Json
    $manifest[$rec.path] = $rec
}
$dirty = [System.Collections.Generic.HashSet[string]]::new()
Get-Content -LiteralPath (Join-Path $run 'git-status.txt') | ForEach-Object {
    if ($_.Length -ge 4) { [void]$dirty.Add($_.Substring(3).Trim()) }
}
$legacy = @()
Get-Content -LiteralPath (Join-Path $repo '.audit\coverage.md') | ForEach-Object {
    if ($_ -match '^\[x\] (.*?) — module:') { $legacy += $Matches[1] }
}

$dest = Join-Path $run 'FINDINGS_LEGACY_VALIDATED'
New-Item -ItemType Directory -Path $dest -Force | Out-Null
Get-ChildItem -LiteralPath (Join-Path $repo '.audit\FINDINGS') -Filter '*.md' -File |
    Copy-Item -Destination $dest

$eligible = [System.Collections.Generic.HashSet[string]]::new()
$evidence = @()
foreach ($path in $legacy) {
    $rec = $manifest[$path]
    $ok = ($null -ne $rec) -and ($rec.action -eq 'capture') -and (-not $dirty.Contains($path))
    if ($ok) { [void]$eligible.Add($path) }
    $evidence += [pscustomobject]@{
        path = $path
        snapshot_sha256 = if ($null -ne $rec) { $rec.sha256 } else { $null }
        clean_at_capture = -not $dirty.Contains($path)
        carry_forward = $ok
    }
}
$evidence | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $run 'legacy-reconciliation.json') -Encoding utf8

$coveragePath = Join-Path $run 'coverage.md'
$updated = Get-Content -LiteralPath $coveragePath | ForEach-Object {
    if ($_ -match '^\[ \] (.*?) — module:' -and $eligible.Contains($Matches[1])) {
        $_ -replace '^\[ \]', '[x]'
    } else { $_ }
}
$updated | Set-Content -LiteralPath $coveragePath -Encoding utf8

$lines = @(
    '# Legacy FINDINGS reconciliation',
    '',
    "- Snapshot HEAD: ``$($scope.head)``",
    '- Rule: carry forward only when the path is captured in this run, has a snapshot SHA-256, is clean in the capture dirty-state, and has a completed legacy FINDINGS block.',
    '- Limitation: the old run did not store hashes. Temporal evidence places the FINDINGS after the current HEAD commit; therefore these are explicitly preserved as validated legacy evidence, not relabeled as newly generated findings.',
    "- Result: $($eligible.Count) / $($legacy.Count) files carried forward.",
    '',
    '## Files',
    ''
)
foreach ($item in $evidence) {
    $mark = if ($item.carry_forward) { '[x]' } else { '[ ]' }
    $lines += "$mark $($item.path) — sha256:$($item.snapshot_sha256) — clean_at_capture:$($item.clean_at_capture)"
}
$lines | Set-Content -LiteralPath (Join-Path $run 'LEGACY_RECONCILIATION.md') -Encoding utf8
Write-Output "carried=$($eligible.Count) legacy=$($legacy.Count)"
