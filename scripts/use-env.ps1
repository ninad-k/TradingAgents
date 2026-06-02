# Switch the active .env between profiles.
#
# Usage:
#   pwsh scripts/use-env.ps1 demo         # small Ollama models, fast (for demos)
#   pwsh scripts/use-env.ps1 production   # gemma4:latest, full quality (for server)
#   pwsh scripts/use-env.ps1 status       # show which profile is currently active

param(
    [Parameter(Position = 0)]
    [ValidateSet('demo', 'production', 'status')]
    [string]$Profile = 'status'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $root '.env'
$demoPath = Join-Path $root '.env.demo'
$prodPath = Join-Path $root '.env.production'

function Get-FirstLlm([string]$path) {
    if (-not (Test-Path $path)) { return '(missing)' }
    $line = Select-String -Path $path -Pattern '^DEEP_THINK_LLM=' -SimpleMatch:$false | Select-Object -First 1
    if ($line) { return ($line.Line -replace '^DEEP_THINK_LLM=', '') }
    return '(not set)'
}

if ($Profile -eq 'status') {
    Write-Host "Current .env DEEP_THINK_LLM : $(Get-FirstLlm $envPath)"
    Write-Host "  .env.demo                 : $(Get-FirstLlm $demoPath)"
    Write-Host "  .env.production           : $(Get-FirstLlm $prodPath)"
    return
}

$source = if ($Profile -eq 'demo') { $demoPath } else { $prodPath }
if (-not (Test-Path $source)) {
    throw "Source profile not found: $source"
}

Copy-Item -Path $source -Destination $envPath -Force
Write-Host "Activated '$Profile' profile -> .env now matches $(Split-Path -Leaf $source)"
Write-Host "DEEP_THINK_LLM = $(Get-FirstLlm $envPath)"

if ($Profile -eq 'demo') {
    Write-Host ""
    Write-Host "Pre-warm Ollama before the demo:"
    Write-Host "  ollama run qwen2.5:1.5b 'warm'"
    Write-Host "  ollama run qwen2.5:3b   'warm'"
}
