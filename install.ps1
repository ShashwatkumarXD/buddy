# Install buddy on Windows:
#   powershell -ExecutionPolicy Bypass -File install.ps1 [pokemon-name]
param([string]$Pokemon = "")
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

if (Get-Command py -ErrorAction SilentlyContinue) { $python = "py"; $pyArgs = @("-3") }
elseif (Get-Command python -ErrorAction SilentlyContinue) { $python = "python"; $pyArgs = @() }
else {
    Write-Host "Python 3.11+ is required: https://www.python.org/downloads/ (tick 'Add python.exe to PATH')."
    exit 1
}
& $python @pyArgs -c "import sys; sys.exit(sys.version_info < (3, 11))"
if ($LASTEXITCODE -ne 0) { Write-Host "Python 3.11 or newer is required."; exit 1 }

Write-Host "Setting up Python environment (downloads Qt the first time, about 80 MB)..."
& $python @pyArgs -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --quiet -e .
if ($LASTEXITCODE -ne 0) { Write-Host "Installing buddy's Python packages failed."; exit 1 }

$buddy = Join-Path $PSScriptRoot ".venv\Scripts\buddy.exe"

# A small `buddy` command on PATH (a shim, so the venv's python.exe doesn't shadow yours).
$binDir = Join-Path $env:LOCALAPPDATA "buddy\bin"
New-Item -ItemType Directory -Force -Path $binDir | Out-Null
Set-Content -Path (Join-Path $binDir "buddy.cmd") -Value "@`"$buddy`" %*" -Encoding ASCII
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (-not (($userPath -split ";") -contains $binDir)) {
    $newPath = if ($userPath) { "$userPath;$binDir" } else { $binDir }
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    Write-Host "Added the 'buddy' command to your PATH (open a new terminal to use it)."
}

if ($Pokemon) { & $buddy choose $Pokemon } else { & $buddy choose }
if ($LASTEXITCODE -ne 0) { Write-Host "Couldn't get that Pokemon (see the message above). Run install.ps1 again to retry."; exit 1 }
& $buddy autostart on

$found = @()
if (Get-Command claude -ErrorAction SilentlyContinue) { $found += "Claude Code" }
if (Get-Command gemini -ErrorAction SilentlyContinue) { $found += "Gemini CLI" }
if (Get-Command codex -ErrorAction SilentlyContinue) { $found += "Codex" }
if ($found.Count -gt 0) {
    $answer = Read-Host "Found $($found -join ', '). Let your buddy react to them? [Y/n]"
    if ($answer -eq "" -or $answer -match "^[Yy]") {
        & $buddy agents on
        if ($LASTEXITCODE -ne 0) { Write-Host "Couldn't set up every agent; try later with: buddy agents on" }
    } else { Write-Host "Skipped. Turn it on later with: buddy agents on" }
}

& $buddy stop *> $null
& $buddy run
if ($LASTEXITCODE -ne 0) { Write-Host "Buddy couldn't start (see the message above)."; exit 1 }

Write-Host ""
Write-Host "Buddy is running! Commands (in a new terminal):"
Write-Host "  buddy choose <name>    switch Pokemon"
Write-Host "  buddy config           edit thresholds, size, speed"
Write-Host "  buddy autostart off    don't start at login"
Write-Host "  buddy agents on|off    react to Claude Code / Gemini CLI / Codex"
Write-Host "  buddy guide            everything else"
