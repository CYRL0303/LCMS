param(
    [string]$ComposeFile = "docker-compose.prod.yml",
    [string]$EnvFile = ".env.prod",
    [int]$TimeoutSeconds = 180
)

$ErrorActionPreference = "Stop"

function Read-EnvFile {
    param([string]$Path)

    $values = @{}
    foreach ($rawLine in Get-Content -LiteralPath $Path) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
            continue
        }
        $key, $value = $line.Split("=", 2)
        $values[$key.Trim()] = $value.Trim().Trim("'").Trim('"')
    }
    return $values
}

function Resolve-EnvPath {
    param([string]$PathValue)

    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        return $PathValue
    }
    return [System.IO.Path]::GetFullPath((Join-Path (Get-Location).Path $PathValue))
}

function Get-EnvValue {
    param(
        [hashtable]$EnvValues,
        [string]$Key
    )

    $processValue = [Environment]::GetEnvironmentVariable($Key, "Process")
    if ($processValue) {
        return $processValue
    }
    return $EnvValues[$Key]
}

function Test-GitNexusRuntime {
    param([hashtable]$EnvValues)

    $gitnexusRoot = Get-EnvValue $EnvValues "GITNEXUS_REPO_ROOT"
    if (-not $gitnexusRoot) {
        throw "GITNEXUS_REPO_ROOT is required in $EnvFile"
    }

    $resolvedRoot = Resolve-EnvPath $gitnexusRoot
    $cliPath = Join-Path $resolvedRoot "dist/cli/index.js"
    if (-not (Test-Path -LiteralPath $cliPath -PathType Leaf)) {
        throw "GitNexus CLI not found: $cliPath"
    }

    Write-Host "GitNexus runtime preflight passed: $cliPath"
}

if (-not (Test-Path -LiteralPath $ComposeFile)) {
    throw "Compose file not found: $ComposeFile"
}

if (-not (Test-Path -LiteralPath $EnvFile)) {
    throw "Env file not found: $EnvFile"
}

$envValues = Read-EnvFile $EnvFile
Test-GitNexusRuntime $envValues

docker compose --env-file $EnvFile -f $ComposeFile up -d --build

docker compose --env-file $EnvFile -f $ComposeFile exec -T api test -f /opt/gitnexus/dist/cli/index.js
docker compose --env-file $EnvFile -f $ComposeFile exec -T api node /opt/gitnexus/dist/cli/index.js --help

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$healthUrl = "http://127.0.0.1:8080/api/health"

while ((Get-Date) -lt $deadline) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $healthUrl -TimeoutSec 5
        if ($response.StatusCode -eq 200 -and $response.Content -match "legacy-pilot-interface-contract-middleware") {
            Write-Host "Production Compose smoke passed: $healthUrl"
            exit 0
        }
    } catch {
        Start-Sleep -Seconds 3
    }
}

docker compose --env-file $EnvFile -f $ComposeFile ps
docker compose --env-file $EnvFile -f $ComposeFile logs --tail 120 web
docker compose --env-file $EnvFile -f $ComposeFile logs --tail 120 api
docker compose --env-file $EnvFile -f $ComposeFile logs --tail 120 postgres

throw "Production Compose smoke failed: $healthUrl"
