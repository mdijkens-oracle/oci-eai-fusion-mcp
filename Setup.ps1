#Requires -Version 7.2
<#
Purpose: set up the named fusionmcp Conda environment and check local configuration.
Prerequisites: Conda on PATH; internet/package-cache access for missing dependencies.
Inputs: optional -Dev to install development requirements. No credentials in arguments.
Side effects: creates the named environment if absent; installs pinned runtime packages.
Usage: .\Setup.ps1; then conda activate fusionmcp
Expected result: offline configuration check passes (weekly Fusion password optional).
Cleanup: environment removal is a separate explicit action; this script deletes nothing.
#>
[CmdletBinding()]
param([switch]$Dev)
$ErrorActionPreference = 'Stop'
Push-Location -LiteralPath $PSScriptRoot
try {
    $environments = (& conda env list --json | ConvertFrom-Json).envs
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect Conda environments.' }
    $existing = @($environments | Where-Object { (Split-Path $_ -Leaf) -eq 'fusionmcp' })
    if ($existing.Count -gt 1) { throw 'Multiple fusionmcp environments found; select one before continuing.' }
    if ($existing.Count -eq 0) {
        & conda create --name fusionmcp python=3.11 pip --yes
        if ($LASTEXITCODE -ne 0) { throw 'Conda environment creation failed.' }
    }
    & conda run --no-capture-output -n fusionmcp python -c 'import sys; assert sys.version_info[:2] == (3, 11), "Python 3.11 required"; print("Using named environment fusionmcp, Python", sys.version.split()[0])'
    if ($LASTEXITCODE -ne 0) { throw 'Existing named environment does not have Python 3.11.' }
    $requirementsFile = if ($Dev) { 'requirements-dev.txt' } else { 'requirements.txt' }
    & conda run --no-capture-output -n fusionmcp python -m pip install -r $requirementsFile
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    if (-not (Test-Path -LiteralPath '.env')) {
        Copy-Item -LiteralPath '.env.example' -Destination '.env'
        Write-Host 'Created .env from the safe template; fill its placeholders locally.'
    }
    & conda run --no-capture-output -n fusionmcp python check_config.py
    if ($LASTEXITCODE -ne 0) { throw 'Configuration needs attention; see key names above.' }
} finally { Pop-Location }
