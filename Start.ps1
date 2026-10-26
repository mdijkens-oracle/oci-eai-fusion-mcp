# Start in the foreground. Ctrl+C stops only this application.
# No browser auto-open; no global processes are stopped.
#Requires -Version 7.2
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try { conda run --no-capture-output -n fusionmcp python server.py }
finally { Pop-Location }

