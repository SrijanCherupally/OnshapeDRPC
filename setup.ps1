$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath 'venv\Scripts\python.exe')) {
    python -m venv venv
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.10 or newer and add it to PATH.' }
}
& '.\venv\Scripts\python.exe' -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
New-Item -ItemType Directory -Path tools -Force | Out-Null
$taskDestination = Join-Path $PSScriptRoot 'tools\cloudflared.exe'
if (-not (Test-Path -LiteralPath $taskDestination)) {
    Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile $taskDestination
}
$taskSignature = Get-AuthenticodeSignature -LiteralPath $taskDestination
if ($taskSignature.Status -ne 'Valid' -or $taskSignature.SignerCertificate.Subject -notmatch 'Cloudflare') {
    throw 'The cloudflared executable does not have a valid Cloudflare signature.'
}
if (-not (Test-Path -LiteralPath '.env')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
}
Write-Output 'Setup complete. Set API_KEY in .env, then run .\start.ps1.'
