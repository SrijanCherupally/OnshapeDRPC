$ErrorActionPreference = 'Stop'
$taskPython = Join-Path $PSScriptRoot 'venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Run setup.ps1 first.' }
$taskShell = New-Object -ComObject WScript.Shell
$taskShortcutPath = Join-Path ([Environment]::GetFolderPath('Startup')) 'OnshapeDRPC.lnk'
$taskShortcut = $taskShell.CreateShortcut($taskShortcutPath)
$taskShortcut.TargetPath = $taskPython
$taskShortcut.Arguments = '"' + (Join-Path $PSScriptRoot 'main.py') + '"'
$taskShortcut.WorkingDirectory = $PSScriptRoot
$taskShortcut.Description = 'Onshape Discord Rich Presence'
$taskShortcut.Save()
Write-Output 'OnshapeDRPC will start silently when you sign into Windows.'
