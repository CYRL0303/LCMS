[CmdletBinding()]
param(
    [string]$GitNexusBin = $env:GITNEXUS_BIN,
    [string]$GitNexusRepoRoot = $env:GITNEXUS_REPO_ROOT,
    [string]$GraphStoreDsn = $env:LEGACY_PILOT_GRAPH_STORE_DSN,
    [string]$GraphStoreTable = $env:LEGACY_PILOT_GRAPH_STORE_TABLE,
    [string]$IncidentMemoryDsn = $env:LEGACY_PILOT_INCIDENT_MEMORY_DSN,
    [string]$IncidentMemoryTable = $env:LEGACY_PILOT_INCIDENT_MEMORY_TABLE,
    [string]$RcaBaseUrl = $env:LEGACY_PILOT_RCA_BASE_URL,
    [string]$RcaModel = $env:LEGACY_PILOT_RCA_MODEL,
    [string]$RcaConfidenceCap = $env:LEGACY_PILOT_RCA_CONFIDENCE_CAP,
    [string]$RcaRepairAttempts = $env:LEGACY_PILOT_RCA_REPAIR_ATTEMPTS,
    [string]$DockerDesktopPath = $env:DOCKER_DESKTOP_EXE,
    [int]$DockerWaitSeconds = 120,
    [int]$PostgresWaitSeconds = 60,
    [switch]$SkipDockerDaemonStart,
    [switch]$SkipPostgresStart,
    [switch]$StartOnly,
    [string[]]$PytestArgs = @("tests/test_real_structure1_structure2_e2e.py", "-q", "-s")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
$ComposeFile = Join-Path $RepoRoot "docker-compose.e2e.yml"
$DefaultGitNexusBin = "Q:\tmp\gitnexus-local.cmd"
$DefaultGitNexusRepoRoot = "Q:\Hackathons\GitNexus-main\GitNexus-main\gitnexus"
$DefaultDockerDesktopPath = "C:\Program Files\Docker\Docker\Docker Desktop.exe"

function Import-LocalEnvFile {
    param(
        [string]$Path
    )
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return
    }
    foreach ($rawLine in Get-Content -LiteralPath $Path) {
        $line = $rawLine.Trim()
        if ([string]::IsNullOrWhiteSpace($line) -or $line.StartsWith("#") -or -not $line.Contains("=")) {
            continue
        }
        $parts = $line.Split("=", 2)
        $name = $parts[0].Trim()
        $value = $parts[1].Trim().Trim("'`"")
        if ([string]::IsNullOrWhiteSpace($name) -or [Environment]::GetEnvironmentVariable($name, "Process")) {
            continue
        }
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

Import-LocalEnvFile (Join-Path $RepoRoot ".env.local")

if ([string]::IsNullOrWhiteSpace($env:DASHSCOPE_API_KEY)) {
    $userDashScopeApiKey = [Environment]::GetEnvironmentVariable("DASHSCOPE_API_KEY", "User")
    if (-not [string]::IsNullOrWhiteSpace($userDashScopeApiKey)) {
        $env:DASHSCOPE_API_KEY = $userDashScopeApiKey
    }
}

if ([string]::IsNullOrWhiteSpace($GitNexusBin)) {
    $GitNexusBin = $DefaultGitNexusBin
}
if ([string]::IsNullOrWhiteSpace($GitNexusRepoRoot)) {
    $GitNexusRepoRoot = $DefaultGitNexusRepoRoot
}
if ([string]::IsNullOrWhiteSpace($GraphStoreDsn)) {
    $GraphStoreDsn = "postgresql://legacy_pilot:legacy_pilot@127.0.0.1:55432/legacy_pilot?connect_timeout=5"
}
if ([string]::IsNullOrWhiteSpace($GraphStoreTable)) {
    $GraphStoreTable = "legacy_pilot_graph_payloads_structure3_e2e"
}
if ([string]::IsNullOrWhiteSpace($IncidentMemoryDsn)) {
    $IncidentMemoryDsn = $GraphStoreDsn
}
if ([string]::IsNullOrWhiteSpace($IncidentMemoryTable)) {
    $IncidentMemoryTable = "legacy_pilot_incident_records_structure4_e2e"
}
if ([string]::IsNullOrWhiteSpace($RcaBaseUrl)) {
    $RcaBaseUrl = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
}
if ([string]::IsNullOrWhiteSpace($RcaModel)) {
    $RcaModel = "qwen-plus"
}
if ([string]::IsNullOrWhiteSpace($RcaConfidenceCap)) {
    $RcaConfidenceCap = "0.75"
}
if ([string]::IsNullOrWhiteSpace($RcaRepairAttempts)) {
    $RcaRepairAttempts = "2"
}
if ([string]::IsNullOrWhiteSpace($DockerDesktopPath)) {
    $DockerDesktopPath = $DefaultDockerDesktopPath
}

function Assert-FileExists {
    param(
        [string]$Name,
        [string]$Path
    )
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Name not found: $Path"
    }
}

function Assert-DirectoryExists {
    param(
        [string]$Name,
        [string]$Path
    )
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        throw "$Name not found: $Path"
    }
}

function Assert-EnvValue {
    param(
        [string]$Name,
        [string]$Value,
        [string]$Hint
    )
    if ([string]::IsNullOrWhiteSpace($Value)) {
        throw "$Name is required. $Hint"
    }
}

Assert-FileExists "docker-compose.e2e.yml" $ComposeFile
Assert-FileExists "GITNEXUS_BIN" $GitNexusBin
Assert-DirectoryExists "GITNEXUS_REPO_ROOT" $GitNexusRepoRoot

function Test-DockerDaemonReady {
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & docker info 1>$null 2>$null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
}

function Ensure-DockerDaemon {
    if (Test-DockerDaemonReady) {
        Write-Host "Docker daemon is ready."
        return
    }
    if ($SkipDockerDaemonStart) {
        throw "Docker daemon is not ready and -SkipDockerDaemonStart was set."
    }
    Assert-FileExists "Docker Desktop.exe" $DockerDesktopPath
    Write-Host "Starting Docker Desktop..."
    Start-Process -FilePath $DockerDesktopPath -WindowStyle Hidden

    Write-Host "Waiting for Docker daemon readiness..."
    $deadline = (Get-Date).AddSeconds($DockerWaitSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-DockerDaemonReady) {
            Write-Host "Docker daemon is ready."
            return
        }
        Start-Sleep -Seconds 3
    }
    throw "Docker daemon did not become ready within $DockerWaitSeconds seconds."
}

Ensure-DockerDaemon

if (-not $SkipPostgresStart) {
    Write-Host "Starting E2E PostgreSQL with docker compose..."
    & docker compose -f $ComposeFile up -d postgres
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose failed to start postgres."
    }
}

Write-Host "Waiting for PostgreSQL readiness..."
$deadline = (Get-Date).AddSeconds($PostgresWaitSeconds)
$ready = $false
while ((Get-Date) -lt $deadline) {
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & docker exec legacy-pilot-pg-e2e pg_isready -U legacy_pilot -d legacy_pilot 1>$null 2>$null
        if ($LASTEXITCODE -eq 0) {
            $ready = $true
            break
        }
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    Start-Sleep -Seconds 2
}
if (-not $ready) {
    throw "PostgreSQL did not become ready within $PostgresWaitSeconds seconds."
}

if ($StartOnly) {
    Write-Host "Docker daemon and PostgreSQL are ready."
    exit 0
}

Assert-EnvValue "DASHSCOPE_API_KEY" $env:DASHSCOPE_API_KEY "Set it in the current shell; do not commit it."

$env:LEGACY_PILOT_RUN_REAL_E2E = "1"
$env:LEGACY_PILOT_CODE_CORE_BACKEND = "gitnexus_cli"
$env:LEGACY_PILOT_GRAPH_STORE_BACKEND = "postgresql"
$env:LEGACY_PILOT_INCIDENT_CONTEXT_BACKEND = "graph_context"
$env:LEGACY_PILOT_INCIDENT_MEMORY_BACKEND = "postgresql"
$env:LEGACY_PILOT_RCA_BACKEND = "qwen_api"
$env:LEGACY_PILOT_RCA_BASE_URL = $RcaBaseUrl
$env:LEGACY_PILOT_RCA_MODEL = $RcaModel
$env:LEGACY_PILOT_RCA_CONFIDENCE_CAP = $RcaConfidenceCap
$env:LEGACY_PILOT_RCA_REPAIR_ATTEMPTS = $RcaRepairAttempts
$env:GITNEXUS_BIN = $GitNexusBin
$env:GITNEXUS_REPO_ROOT = $GitNexusRepoRoot
$env:GITNEXUS_INDEX_TIMEOUT_SECONDS = "120"
$env:GITNEXUS_QUERY_TIMEOUT_SECONDS = "30"
$env:LEGACY_PILOT_GRAPH_STORE_DSN = $GraphStoreDsn
$env:LEGACY_PILOT_GRAPH_STORE_TABLE = $GraphStoreTable
$env:LEGACY_PILOT_INCIDENT_MEMORY_DSN = $IncidentMemoryDsn
$env:LEGACY_PILOT_INCIDENT_MEMORY_TABLE = $IncidentMemoryTable

Push-Location $RepoRoot
try {
    Write-Host "Running real Structure1/PostgreSQL/Structure2/Structure3/Structure4 E2E..."
    & python -m pytest @PytestArgs
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
