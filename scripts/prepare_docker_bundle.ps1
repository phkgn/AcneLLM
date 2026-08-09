[CmdletBinding()]
param(
    [string]$Destination = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
if ([string]::IsNullOrWhiteSpace($Destination)) {
    $Destination = Join-Path (Split-Path $RepoRoot -Parent) "AcneLLM-docker-bundle"
}
$Destination = [IO.Path]::GetFullPath($Destination)
$RepoPrefix = $RepoRoot.TrimEnd('\') + '\'
if ($Destination.StartsWith($RepoPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Destination must be outside the repository to avoid recursive copying."
}
if (Test-Path -LiteralPath $Destination) {
    throw "Destination already exists: $Destination. Choose another path or rename it manually."
}

$RequiredAssets = @(
    "model/V2/Q4/Modelfile",
    "model/V2/Q4/Qwen2.5-7B-Instruct.Q4_K_M.gguf",
    "model/acne_intake_release/Modelfile",
    "model/acne_intake_release/Qwen2.5-3B-Instruct.Q4_K_M.gguf",
    "data/chroma_db/chroma.sqlite3",
    "data/bm25_index.pkl",
    "data/intent_classify.train.jsonl",
    "data/intent_router_index.npz"
)
$Missing = @($RequiredAssets | Where-Object { -not (Test-Path -LiteralPath (Join-Path $RepoRoot $_)) })
if ($Missing.Count -gt 0) {
    throw "Cannot package; missing:`n  - $($Missing -join "`n  - ")"
}
if (@(Get-ChildItem -LiteralPath (Join-Path $RepoRoot "data/chroma_db") -Directory).Count -eq 0) {
    throw "Cannot package; Chroma vector segment directory is missing."
}

New-Item -ItemType Directory -Path $Destination | Out-Null

function Copy-RuntimeDirectory {
    param(
        [Parameter(Mandatory)] [string]$RelativePath,
        [string[]]$ExcludeDirectories = @(),
        [string[]]$ExcludeFiles = @("*.pyc", "*.tmp")
    )

    $Source = Join-Path $RepoRoot $RelativePath
    $Target = Join-Path $Destination $RelativePath
    New-Item -ItemType Directory -Force -Path $Target | Out-Null
    $Arguments = @($Source, $Target, "/E", "/R:1", "/W:1", "/NFL", "/NDL", "/NJH", "/NJS")
    if ($ExcludeDirectories.Count -gt 0) {
        $Arguments += "/XD"
        $Arguments += $ExcludeDirectories
    }
    if ($ExcludeFiles.Count -gt 0) {
        $Arguments += "/XF"
        $Arguments += $ExcludeFiles
    }
    & robocopy @Arguments | Out-Host
    if ($LASTEXITCODE -gt 7) {
        throw "robocopy failed for $RelativePath with exit code $LASTEXITCODE"
    }
}

# This is a self-contained runtime hand-off, not a clone of local experiments,
# reports, caches, credentials, or the Git history.
$RuntimeFiles = @(
    ".dockerignore",
    ".env.docker.example",
    ".gitattributes",
    "docker-compose.yml",
    "docker-compose.gpu.yml",
    "Dockerfile",
    "pyproject.toml",
    "README.md",
    "requirements.txt"
)
foreach ($RelativePath in $RuntimeFiles) {
    Copy-Item -LiteralPath (Join-Path $RepoRoot $RelativePath) `
        -Destination (Join-Path $Destination $RelativePath)
}

Copy-RuntimeDirectory -RelativePath "src" -ExcludeDirectories @("__pycache__")
Copy-RuntimeDirectory -RelativePath "frontend" `
    -ExcludeDirectories @("node_modules", ".next", "out", ".turbo")
Copy-RuntimeDirectory -RelativePath "config" `
    -ExcludeDirectories @("cache", "custom-covers", "logs") `
    -ExcludeFiles @("secret_key", "*.pyc", "*.tmp")
Copy-RuntimeDirectory -RelativePath "docker"

New-Item -ItemType Directory -Force -Path (Join-Path $Destination "scripts") | Out-Null
Copy-Item -LiteralPath (Join-Path $RepoRoot "scripts/check_docker_assets.ps1") `
    -Destination (Join-Path $Destination "scripts/check_docker_assets.ps1")
Copy-Item -LiteralPath $PSCommandPath `
    -Destination (Join-Path $Destination "scripts/prepare_docker_bundle.ps1")
New-Item -ItemType Directory -Force -Path (Join-Path $Destination "docs") | Out-Null
Copy-Item -LiteralPath (Join-Path $RepoRoot "docs/DOCKER_QUICKSTART.md") `
    -Destination (Join-Path $Destination "docs/DOCKER_QUICKSTART.md")

$AssetPaths = @(
    "model/V2/Q4",
    "model/acne_intake_release/Modelfile",
    "model/acne_intake_release/Qwen2.5-3B-Instruct.Q4_K_M.gguf",
    "model/acne_intake_release/README.txt",
    "data/chroma_db",
    "data/bm25_index.pkl",
    "data/bm25_index.pkl.sha256",
    "data/intent_classify.train.jsonl",
    "data/intent_router_index.npz",
    "data/seed_sources.yaml"
)
foreach ($RelativePath in $AssetPaths) {
    $Source = Join-Path $RepoRoot $RelativePath
    if (-not (Test-Path -LiteralPath $Source)) {
        continue
    }
    $Target = Join-Path $Destination $RelativePath
    $Parent = Split-Path $Target -Parent
    New-Item -ItemType Directory -Force -Path $Parent | Out-Null
    Copy-Item -LiteralPath $Source -Destination $Target -Recurse
}

New-Item -ItemType Directory -Force -Path (Join-Path $Destination "data/cache") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Destination "data/model_cache") | Out-Null
Copy-Item -LiteralPath (Join-Path $Destination ".env.docker.example") `
    -Destination (Join-Path $Destination ".env.docker")

Write-Host "Docker bundle created: $Destination" -ForegroundColor Green
Write-Host "Set API_KEY in .env.docker, then run scripts/check_docker_assets.ps1."
