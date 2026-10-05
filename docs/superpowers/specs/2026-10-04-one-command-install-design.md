# One-command install

## Problem
Installing needed Git and Python 3.11+ first. Plenty of machines have neither: Windows has only the
Microsoft Store `python` stub, macOS ships Python 3.9, Ubuntu 22.04 ships 3.10.

## Goal
One line installs (and later updates) buddy, starting from nothing but the OS:

    Windows:      irm https://raw.githubusercontent.com/ShashwatkumarXD/buddy/main/install.ps1 | iex
    macOS/Linux:  curl -fsSL https://raw.githubusercontent.com/ShashwatkumarXD/buddy/main/install.sh | bash

## Design
- **Python comes from uv.** The installer downloads uv (astral.sh) into buddy's own folder
  (`UV_INSTALL_DIR`, `UV_NO_MODIFY_PATH=1`); uv downloads a private CPython 3.12
  (`UV_PYTHON_INSTALL_DIR`, `UV_PYTHON_PREFERENCE=only-managed`) and builds the venv. No admin
  rights, no PATH or shell-profile edits, any Python already on the machine is left alone.
- **No Git.** Piped in, the installer downloads the GitHub archive of `BUDDY_REF` (default `main`,
  any branch/tag/commit works) to a temp folder and does a normal install from it into the venv.
  Run from a clone (`./install.sh`, `install.ps1`) it does an editable install with the dev extras
  into the clone's `.venv`, as before.
- **Where things go** (one folder per OS, deleting it uninstalls):

  | OS      | Folder                                  | Holds                     |
  |---------|-----------------------------------------|---------------------------|
  | Linux   | `${XDG_DATA_HOME:-~/.local/share}/buddy` | `uv/`, `python/`, `venv/` |
  | macOS   | `~/Library/Application Support/buddy`   | same (next to config)     |
  | Windows | `%LOCALAPPDATA%\buddy`                  | same, plus `bin\` shim    |

  uv's download cache goes in buddy's cache folder.
- **Re-running updates.** It stops a running buddy first (Windows locks files in use), rebuilds the
  venv from scratch, and keeps settings, sprites and agent hooks.
- **Piped scripts can still ask questions.** `curl | bash` feeds the script on stdin, so prompts
  read `/dev/tty` and are skipped when there is no terminal. `irm | iex` runs inside the user's own
  PowerShell, so the script never calls `exit` (that would close their window) and keeps its
  settings in function scope. Arguments: `bash -s eevee`, or `$env:BUDDY_POKEMON`.
- The whole bash script sits in a `main` function called on the last line, so a cut-off download
  runs nothing.

## Verification
- CI job `install` on Linux, macOS and Windows runs the real one-liner against the pushed commit
  (`BUDDY_REF=<sha>`), with `BUDDY_QT_PLATFORM=offscreen` so buddy starts without a screen, then
  `buddy stop` must succeed (proves it was running).
- Locally on Linux: clone mode and download mode (from a `git archive` via `BUDDY_ARCHIVE`) in a
  throwaway HOME.
