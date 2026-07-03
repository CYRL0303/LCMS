param(
    [string]$GitNexusPackageDir = $env:GITNEXUS_PACKAGE_DIR,
    [string]$RuntimeImage = $env:GITNEXUS_RUNTIME_IMAGE,
    [switch]$Push
)

$ErrorActionPreference = "Stop"

function Assert-Value {
    param(
        [string]$Name,
        [string]$Value
    )

    if ([string]::IsNullOrWhiteSpace($Value)) {
        throw "$Name is required."
    }
}

if ([string]::IsNullOrWhiteSpace($GitNexusPackageDir)) {
    $GitNexusPackageDir = "gitnexus"
}

Assert-Value "GITNEXUS_RUNTIME_IMAGE" $RuntimeImage

$root = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
$dockerfile = Join-Path $root "Dockerfile.gitnexus-runtime"
if (-not (Test-Path -LiteralPath $dockerfile -PathType Leaf)) {
    throw "Dockerfile.gitnexus-runtime not found: $dockerfile"
}
$vendorPackageJson = Join-Path $root "vendor\gitnexus-source\$GitNexusPackageDir\package.json"
if (-not (Test-Path -LiteralPath $vendorPackageJson -PathType Leaf)) {
    throw "Vendored GitNexus package.json not found: $vendorPackageJson"
}

$buildArgs = @(
    "build",
    "-f", $dockerfile,
    "--build-arg", "GITNEXUS_PACKAGE_DIR=$GitNexusPackageDir",
    "-t", $RuntimeImage,
    $root
)

& docker @buildArgs
if ($LASTEXITCODE -ne 0) {
    throw "docker build failed with exit code $LASTEXITCODE"
}

if ($Push) {
    & docker push $RuntimeImage
    if ($LASTEXITCODE -ne 0) {
        throw "docker push failed with exit code $LASTEXITCODE"
    }
}
