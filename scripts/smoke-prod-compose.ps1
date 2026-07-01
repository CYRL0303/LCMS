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

function Invoke-CheckedCommand {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$FilePath failed with exit code $LASTEXITCODE"
    }
}

function Test-GitNexusBuildSource {
    param([hashtable]$EnvValues)

    $gitnexusSourceRoot = Get-EnvValue $EnvValues "GITNEXUS_SOURCE_ROOT"
    if (-not $gitnexusSourceRoot) {
        throw "GITNEXUS_SOURCE_ROOT is required in $EnvFile"
    }

    $packageDir = Get-EnvValue $EnvValues "GITNEXUS_PACKAGE_DIR"
    if (-not $packageDir) {
        $packageDir = "gitnexus"
    }

    $resolvedRoot = Resolve-EnvPath $gitnexusSourceRoot
    $packageRoot = Join-Path $resolvedRoot $packageDir
    $packageJson = Join-Path $packageRoot "package.json"
    $packageLock = Join-Path $packageRoot "package-lock.json"
    if (-not (Test-Path -LiteralPath $packageJson -PathType Leaf)) {
        throw "GitNexus package.json not found: $packageJson"
    }
    if (-not (Test-Path -LiteralPath $packageLock -PathType Leaf)) {
        throw "GitNexus package-lock.json not found for npm ci: $packageLock"
    }

    Write-Host "GitNexus build source preflight passed: $packageJson"
}

if (-not (Test-Path -LiteralPath $ComposeFile)) {
    throw "Compose file not found: $ComposeFile"
}

if (-not (Test-Path -LiteralPath $EnvFile)) {
    throw "Env file not found: $EnvFile"
}

$envValues = Read-EnvFile $EnvFile
Test-GitNexusBuildSource $envValues

$composeArgs = @("compose", "--env-file", $EnvFile, "-f", $ComposeFile)

Invoke-CheckedCommand "docker" ($composeArgs + @("up", "-d", "--build"))

Invoke-CheckedCommand "docker" ($composeArgs + @("exec", "-T", "api", "test", "-f", "/opt/gitnexus/dist/cli/index.js"))
$nativeCheckScript = 'from pathlib import Path; root=Path(''/opt/gitnexus/node_modules/@ladybugdb/core''); native=next(root.rglob(''lbugjs.node''), None); assert native is not None, ''LadybugDB native module not found''; assert native.read_bytes()[:4] == b''\x7fELF'', ''GitNexus native module is not a Linux ELF binary'''
Invoke-CheckedCommand "docker" ($composeArgs + @("exec", "-T", "api", "python", "-c", $nativeCheckScript))
Invoke-CheckedCommand "docker" ($composeArgs + @("exec", "-T", "api", "sh", "-lc", "rm -rf /tmp/gitnexus-smoke-repo && mkdir -p /tmp/gitnexus-smoke-repo && printf 'class Smoke {}\n' > /tmp/gitnexus-smoke-repo/Smoke.java && gitnexus analyze /tmp/gitnexus-smoke-repo --skip-git --index-only --name docker-smoke"))

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

docker @composeArgs ps
docker @composeArgs logs --tail 120 web
docker @composeArgs logs --tail 120 api
docker @composeArgs logs --tail 120 postgres

throw "Production Compose smoke failed: $healthUrl"
