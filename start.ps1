$ErrorActionPreference = 'Stop'
$taskPython = Join-Path $PSScriptRoot 'venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Run setup.ps1 first.' }
Start-Process -FilePath $taskPython -ArgumentList ('"' + (Join-Path $PSScriptRoot 'main.py') + '"') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
