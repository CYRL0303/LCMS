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
    [string]$RcaTimeoutSeconds = $env:LEGACY_PILOT_RCA_TIMEOUT_SECONDS,
    [string]$RcaTransportRetries = $env:LEGACY_PILOT_RCA_TRANSPORT_RETRIES,
    [string]$RcaRetryBackoffSeconds = $env:LEGACY_PILOT_RCA_RETRY_BACKOFF_SECONDS,
    [string]$DockerDesktopPath = $env:DOCKER_DESKTOP_EXE,
    [int]$DockerWaitSeconds = 120,
    [int]$PostgresWaitSeconds = 60,
    [int]$BackendWaitSeconds = 60,
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173,
    [switch]$SkipDockerDaemonStart,
    [switch]$SkipPostgresStart,
    [switch]$InstallFrontendDeps,
    [switch]$StartOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
$FrontendRoot = Join-Path $RepoRoot "frontend"
$ComposeFile = Join-Path $RepoRoot "docker-compose.e2e.yml"
$PlaywrightBrowsersPath = Join-Path $RepoRoot ".playwright"
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

function Test-BackendHealth {
    param(
        [int]$Port
    )
    try {
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -Method Get -TimeoutSec 2
        return $response.service -eq "legacy-pilot-interface-contract-middleware"
    }
    catch {
        return $false
    }
}

function Test-FrontendReady {
    param(
        [int]$Port
    )
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port" -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -eq 200
    }
    catch {
        return $false
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
    $GraphStoreTable = "legacy_pilot_graph_payloads_frontend_e2e"
}
if ([string]::IsNullOrWhiteSpace($IncidentMemoryDsn)) {
    $IncidentMemoryDsn = $GraphStoreDsn
}
if ([string]::IsNullOrWhiteSpace($IncidentMemoryTable)) {
    $IncidentMemoryTable = "legacy_pilot_incident_records_frontend_e2e"
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
if ([string]::IsNullOrWhiteSpace($RcaTimeoutSeconds)) {
    $RcaTimeoutSeconds = "120"
}
if ([string]::IsNullOrWhiteSpace($RcaTransportRetries)) {
    $RcaTransportRetries = "1"
}
if ([string]::IsNullOrWhiteSpace($RcaRetryBackoffSeconds)) {
    $RcaRetryBackoffSeconds = "1"
}
if ([string]::IsNullOrWhiteSpace($DockerDesktopPath)) {
    $DockerDesktopPath = $DefaultDockerDesktopPath
}

Assert-FileExists "docker-compose.e2e.yml" $ComposeFile
Assert-FileExists "GITNEXUS_BIN" $GitNexusBin
Assert-DirectoryExists "GITNEXUS_REPO_ROOT" $GitNexusRepoRoot
Assert-DirectoryExists "frontend" $FrontendRoot

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

Assert-EnvValue "DASHSCOPE_API_KEY" $env:DASHSCOPE_API_KEY "Set it in the current shell, .env.local, or Windows User env."

$env:LEGACY_PILOT_RUN_REAL_E2E = "1"
$env:LEGACY_PILOT_RUN_REAL_FRONTEND_E2E = "1"
$env:LEGACY_PILOT_CODE_CORE_BACKEND = "gitnexus_cli"
$env:LEGACY_PILOT_GRAPH_STORE_BACKEND = "postgresql"
$env:LEGACY_PILOT_INCIDENT_CONTEXT_BACKEND = "graph_context"
$env:LEGACY_PILOT_INCIDENT_MEMORY_BACKEND = "postgresql"
$env:LEGACY_PILOT_RCA_BACKEND = "qwen_api"
$env:LEGACY_PILOT_RCA_BASE_URL = $RcaBaseUrl
$env:LEGACY_PILOT_RCA_MODEL = $RcaModel
$env:LEGACY_PILOT_RCA_CONFIDENCE_CAP = $RcaConfidenceCap
$env:LEGACY_PILOT_RCA_REPAIR_ATTEMPTS = $RcaRepairAttempts
$env:LEGACY_PILOT_RCA_TIMEOUT_SECONDS = $RcaTimeoutSeconds
$env:LEGACY_PILOT_RCA_TRANSPORT_RETRIES = $RcaTransportRetries
$env:LEGACY_PILOT_RCA_RETRY_BACKOFF_SECONDS = $RcaRetryBackoffSeconds
$env:GITNEXUS_BIN = $GitNexusBin
$env:GITNEXUS_REPO_ROOT = $GitNexusRepoRoot
$env:GITNEXUS_INDEX_TIMEOUT_SECONDS = "120"
$env:GITNEXUS_QUERY_TIMEOUT_SECONDS = "30"
$env:LEGACY_PILOT_GRAPH_STORE_DSN = $GraphStoreDsn
$env:LEGACY_PILOT_GRAPH_STORE_TABLE = $GraphStoreTable
$env:LEGACY_PILOT_INCIDENT_MEMORY_DSN = $IncidentMemoryDsn
$env:LEGACY_PILOT_INCIDENT_MEMORY_TABLE = $IncidentMemoryTable
$env:LEGACY_PILOT_FRONTEND_PORT = "$FrontendPort"
$env:VITE_LEGACY_PILOT_API_TARGET = "http://127.0.0.1:$BackendPort"
$env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath

if ($InstallFrontendDeps -or -not (Test-Path -LiteralPath (Join-Path $FrontendRoot "node_modules") -PathType Container)) {
    Push-Location $FrontendRoot
    try {
        Write-Host "Installing frontend dependencies..."
        & npm install
        if ($LASTEXITCODE -ne 0) {
            throw "npm install failed."
        }
    }
    finally {
        Pop-Location
    }
}

if (
    $InstallFrontendDeps -or
    -not (Test-Path -LiteralPath $PlaywrightBrowsersPath -PathType Container) -or
    -not (Get-ChildItem -LiteralPath $PlaywrightBrowsersPath -Directory -Filter "chromium*" -ErrorAction SilentlyContinue)
) {
    Push-Location $FrontendRoot
    try {
        Write-Host "Installing Playwright Chromium..."
        & npx playwright install chromium
        if ($LASTEXITCODE -ne 0) {
            throw "playwright install chromium failed."
        }
    }
    finally {
        Pop-Location
    }
}

$backendProcess = $null
$frontendProcess = $null
$backendOutLog = Join-Path $RepoRoot "uvicorn.frontend-e2e.$BackendPort.out.log"
$backendErrLog = Join-Path $RepoRoot "uvicorn.frontend-e2e.$BackendPort.err.log"
$frontendOutLog = Join-Path $FrontendRoot "vite.frontend-e2e.$FrontendPort.out.log"
$frontendErrLog = Join-Path $FrontendRoot "vite.frontend-e2e.$FrontendPort.err.log"

try {
    if (Test-BackendHealth -Port $BackendPort) {
        Write-Host "Using existing middleware on port $BackendPort."
    }
    else {
        Write-Host "Starting middleware on port $BackendPort..."
        if (Test-Path -LiteralPath $backendOutLog -PathType Leaf) {
            Remove-Item -LiteralPath $backendOutLog -Force
        }
        if (Test-Path -LiteralPath $backendErrLog -PathType Leaf) {
            Remove-Item -LiteralPath $backendErrLog -Force
        }
        $backendArgs = @(
            "-m",
            "uvicorn",
            "legacy_pilot.middleware.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            "$BackendPort"
        )
        $backendProcess = Start-Process `
            -FilePath "python" `
            -ArgumentList $backendArgs `
            -WorkingDirectory $RepoRoot `
            -WindowStyle Hidden `
            -RedirectStandardOutput $backendOutLog `
            -RedirectStandardError $backendErrLog `
            -PassThru

        Write-Host "Waiting for middleware health..."
        $deadline = (Get-Date).AddSeconds($BackendWaitSeconds)
        while ((Get-Date) -lt $deadline) {
            if (Test-BackendHealth -Port $BackendPort) {
                break
            }
            Start-Sleep -Seconds 2
        }
        if (-not (Test-BackendHealth -Port $BackendPort)) {
            throw "Middleware did not become healthy within $BackendWaitSeconds seconds. See $backendErrLog"
        }
    }

    if ($StartOnly) {
        if (Test-FrontendReady -Port $FrontendPort) {
            Write-Host "Using existing frontend on port $FrontendPort."
        }
        else {
            Write-Host "Starting frontend on port $FrontendPort..."
            if (Test-Path -LiteralPath $frontendOutLog -PathType Leaf) {
                Remove-Item -LiteralPath $frontendOutLog -Force
            }
            if (Test-Path -LiteralPath $frontendErrLog -PathType Leaf) {
                Remove-Item -LiteralPath $frontendErrLog -Force
            }
            $frontendArgs = @(
                "run",
                "dev",
                "--",
                "--host",
                "127.0.0.1",
                "--port",
                "$FrontendPort"
            )
            $frontendProcess = Start-Process `
                -FilePath "npm.cmd" `
                -ArgumentList $frontendArgs `
                -WorkingDirectory $FrontendRoot `
                -WindowStyle Hidden `
                -RedirectStandardOutput $frontendOutLog `
                -RedirectStandardError $frontendErrLog `
                -PassThru

            Write-Host "Waiting for frontend readiness..."
            $deadline = (Get-Date).AddSeconds(60)
            while ((Get-Date) -lt $deadline) {
                if (Test-FrontendReady -Port $FrontendPort) {
                    break
                }
                Start-Sleep -Seconds 2
            }
            if (-not (Test-FrontendReady -Port $FrontendPort)) {
                throw "Frontend did not become ready within 60 seconds. See $frontendErrLog"
            }
        }
        Write-Host "Middleware ready: http://127.0.0.1:$BackendPort"
        Write-Host "Frontend ready: http://127.0.0.1:$FrontendPort"
        exit 0
    }

    Push-Location $FrontendRoot
    try {
        Write-Host "Running real frontend Playwright E2E..."
        & npm run test:e2e -- --project=chromium tests/real-four-structures.spec.ts
        exit $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
}
finally {
    if (-not $StartOnly -and $null -ne $backendProcess -and -not $backendProcess.HasExited) {
        Write-Host "Stopping middleware process $($backendProcess.Id)..."
        Stop-Process -Id $backendProcess.Id -Force
    }
    if (-not $StartOnly -and $null -ne $frontendProcess -and -not $frontendProcess.HasExited) {
        Write-Host "Stopping frontend process $($frontendProcess.Id)..."
        Stop-Process -Id $frontendProcess.Id -Force
    }
}
