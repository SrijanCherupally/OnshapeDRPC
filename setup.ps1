$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath 'venv\Scripts\python.exe')) {
    python -m venv venv
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.10 or newer and add it to PATH.' }
}
& '.\venv\Scripts\python.exe' -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
if (-not (Test-Path -LiteralPath '.env')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
}
Write-Output 'Setup complete. Set API_KEY in .env, then run .\start.ps1.'
