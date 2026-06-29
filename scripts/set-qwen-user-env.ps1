[CmdletBinding()]
param(
    [securestring]$DashScopeApiKey,
    [switch]$WriteDotEnvLocal
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($null -eq $DashScopeApiKey) {
    $DashScopeApiKey = Read-Host -Prompt "DASHSCOPE_API_KEY" -AsSecureString
}

$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($DashScopeApiKey)
try {
    $plainKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
}
finally {
    if ($bstr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}

if ([string]::IsNullOrWhiteSpace($plainKey)) {
    throw "DASHSCOPE_API_KEY is required."
}

[Environment]::SetEnvironmentVariable("DASHSCOPE_API_KEY", $plainKey, "User")
$env:DASHSCOPE_API_KEY = $plainKey

if ($WriteDotEnvLocal) {
    $repoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
    $envPath = Join-Path $repoRoot ".env.local"
    $lines = @(
        "# Local secrets and machine-specific defaults. This file is gitignored.",
        "DASHSCOPE_API_KEY=$plainKey"
    )
    Set-Content -LiteralPath $envPath -Encoding ASCII -Value $lines
}

Write-Host "DASHSCOPE_API_KEY saved to the current process and Windows User environment."
if ($WriteDotEnvLocal) {
    Write-Host ".env.local updated."
}
