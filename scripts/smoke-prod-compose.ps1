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

function Test-GitNexusRuntimeImage {
    param([hashtable]$EnvValues)

    $runtimeImage = Get-EnvValue $EnvValues "GITNEXUS_RUNTIME_IMAGE"
    if (-not $runtimeImage) {
        throw "GITNEXUS_RUNTIME_IMAGE is required in $EnvFile"
    }
    if ($runtimeImage -match "replace-with-version") {
        throw "GITNEXUS_RUNTIME_IMAGE must be pinned to a real runtime image tag."
    }

    Write-Host "GitNexus runtime image configured: $runtimeImage"
}

if (-not (Test-Path -LiteralPath $ComposeFile)) {
    throw "Compose file not found: $ComposeFile"
}

if (-not (Test-Path -LiteralPath $EnvFile)) {
    throw "Env file not found: $EnvFile"
}

$envValues = Read-EnvFile $EnvFile
Test-GitNexusRuntimeImage $envValues

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
