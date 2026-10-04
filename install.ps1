# Install or update buddy on Windows. Needs nothing preinstalled (no Git, no Python):
#   irm https://raw.githubusercontent.com/ShashwatkumarXD/buddy/main/install.ps1 | iex
#   $env:BUDDY_POKEMON = "eevee"; irm https://raw.githubusercontent.com/ShashwatkumarXD/buddy/main/install.ps1 | iex
# From a clone (for development): powershell -ExecutionPolicy Bypass -File install.ps1 [pokemon-name]
# Optional: $env:BUDDY_REF = "<branch|tag|commit>" (default main).
# `irm | iex` runs inside your own PowerShell window, so this never calls `exit` (that would close
# the window) and keeps its settings inside the function.

function Install-Buddy {
    param([string]$Pokemon = "", [string]$CloneDir = "")
    $ErrorActionPreference = "Stop"
    $ProgressPreference = "SilentlyContinue"  # Windows PowerShell downloads crawl with the progress bar
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $githubRepo = "ShashwatkumarXD/buddy"
    $pythonVersion = "3.12"

    $data = Join-Path $env:LOCALAPPDATA "buddy"
    $cache = Join-Path $data "Cache"
    if ($CloneDir) { $venv = Join-Path $CloneDir ".venv" } else { $venv = Join-Path $data "venv" }
    $buddy = Join-Path $venv "Scripts\buddy.exe"
    New-Item -ItemType Directory -Force -Path $data, $cache | Out-Null

    $tmp = $null
    try {
        if ($CloneDir) {
            $src = $CloneDir
        } else {
            $ref = if ($env:BUDDY_REF) { $env:BUDDY_REF } else { "main" }
            $archive = if ($env:BUDDY_ARCHIVE) { $env:BUDDY_ARCHIVE } else { "https://github.com/$githubRepo/archive/$ref.zip" }
            $tmp = Join-Path ([IO.Path]::GetTempPath()) ("buddy-" + [guid]::NewGuid())
            New-Item -ItemType Directory -Path $tmp | Out-Null
            Write-Host "Downloading buddy ($ref)..."
            $zip = Join-Path $tmp "buddy.zip"
            Invoke-WebRequest -UseBasicParsing -Uri $archive -OutFile $zip
            Expand-Archive -Path $zip -DestinationPath $tmp
            $src = (Get-ChildItem -Path $tmp -Directory | Select-Object -First 1).FullName
        }

        $uvDir = Join-Path $data "uv"
        $uv = @("$uvDir\uv.exe", "$uvDir\bin\uv.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
        if (-not $uv) {
            Write-Host "Downloading uv (it fetches a private copy of Python just for buddy)..."
            $env:UV_UNMANAGED_INSTALL = $uvDir
            try {
                powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex" | Out-Null
            } finally {
                Remove-Item Env:UV_UNMANAGED_INSTALL -ErrorAction SilentlyContinue
            }
            $uv = @("$uvDir\uv.exe", "$uvDir\bin\uv.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
            if (-not $uv) { Write-Host "Couldn't install uv from astral.sh."; return }
        }
        # Python and uv's downloads live in buddy's folders; any Python already installed is left alone.
        $env:UV_PYTHON_INSTALL_DIR = Join-Path $data "python"
        $env:UV_PYTHON_PREFERENCE = "only-managed"
        $env:UV_CACHE_DIR = Join-Path $cache "uv"

        if (Test-Path $buddy) { try { & $buddy stop *> $null } catch {} }  # updating: Windows can't replace files in use
        Write-Host "Setting up Python $pythonVersion and Qt (about 120 MB the first time)..."
        for ($i = 0; Test-Path $venv; $i++) {  # the old buddy may take a moment to let go of its files
            try { Remove-Item -Recurse -Force $venv }
            catch { if ($i -ge 20) { throw }; Start-Sleep -Milliseconds 250 }
        }
        & $uv venv --quiet --python $pythonVersion $venv
        if ($LASTEXITCODE -ne 0) { Write-Host "Couldn't set up Python (see the message above)."; return }
        $python = Join-Path $venv "Scripts\python.exe"
        if ($CloneDir) { & $uv pip install --quiet --python $python -e "$CloneDir[dev]" }
        else { & $uv pip install --quiet --python $python $src }
        if ($LASTEXITCODE -ne 0) { Write-Host "Installing buddy's Python packages failed."; return }
    } finally {
        foreach ($name in "UV_PYTHON_INSTALL_DIR", "UV_PYTHON_PREFERENCE", "UV_CACHE_DIR") {
            Remove-Item "Env:$name" -ErrorAction SilentlyContinue
        }
        if ($tmp) { Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue }
    }

    # A small `buddy` command on PATH (a shim, so the venv's python.exe doesn't shadow yours).
    $binDir = Join-Path $data "bin"
    New-Item -ItemType Directory -Force -Path $binDir | Out-Null
    Set-Content -Path (Join-Path $binDir "buddy.cmd") -Value "@`"$buddy`" %*" -Encoding ASCII
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if (-not (($userPath -split ";") -contains $binDir)) {
        $newPath = if ($userPath) { "$userPath;$binDir" } else { $binDir }
        [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
        Write-Host "Added the 'buddy' command to your PATH."
    }
    # The user PATH only reaches newly opened terminals. `irm | iex` runs in your own window,
    # so add it here too and `buddy` works right away.
    if (-not (($env:Path -split ";") -contains $binDir)) { $env:Path = "$env:Path;$binDir" }

    if ($Pokemon) { & $buddy choose $Pokemon } else { & $buddy choose }
    if ($LASTEXITCODE -ne 0) { Write-Host "Couldn't get that Pokemon (see the message above). Run the installer again to retry."; return }
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

    & $buddy run
    if ($LASTEXITCODE -ne 0) { Write-Host "Buddy couldn't start (see the message above)."; return }

    Write-Host ""
    Write-Host "Buddy is running! Commands (terminals that were already open need reopening first):"
    Write-Host "  buddy choose <name>    switch Pokemon"
    Write-Host "  buddy config           edit thresholds, size, speed"
    Write-Host "  buddy autostart off    don't start at login"
    Write-Host "  buddy agents on|off    react to Claude Code / Gemini CLI / Codex"
    Write-Host "  buddy guide            everything else"
}

# Run from a clone, $PSScriptRoot is the repo; piped into iex it is empty.
$cloneDir = if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot "pyproject.toml"))) { $PSScriptRoot } else { "" }
$pokemonName = if ($args.Count -gt 0) { [string]$args[0] } elseif ($env:BUDDY_POKEMON) { $env:BUDDY_POKEMON } else { "" }
Install-Buddy -Pokemon $pokemonName -CloneDir $cloneDir
