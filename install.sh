#!/usr/bin/env bash
# Install buddy on Linux or macOS: ./install.sh [pokemon-name]
# (Windows: powershell -ExecutionPolicy Bypass -File install.ps1)
set -euo pipefail
cd "$(cd "$(dirname "$0")" && pwd)"
REPO="$PWD"
BUDDY="$REPO/.venv/bin/buddy"
OS="$(uname -s)"

command -v python3 >/dev/null || { echo "Python 3.11+ is required (https://www.python.org/downloads/)."; exit 1; }
python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' || { echo "Python 3.11 or newer is required."; exit 1; }

echo "Setting up Python environment (downloads Qt the first time, about 80 MB)…"
python3 -m venv .venv
.venv/bin/pip install --quiet -e .

if [ "$OS" = "Linux" ]; then
    missing="$(.venv/bin/python -c 'from buddy.window import missing_x11_libraries as m; print(" ".join(m()))')"
    if [ -n "$missing" ]; then
        echo "Qt needs a few system libraries: $missing"
        if [ -t 0 ] && command -v apt >/dev/null; then
            read -r -p "Install them now with sudo apt? [Y/n] " answer || answer=n
            case "${answer:-y}" in
                [Yy]*) sudo apt install -y $missing ;;
                *) echo "Buddy can't start until you run: sudo apt install $missing" ;;
            esac
        else
            echo "Install them with your package manager (Ubuntu/Debian: sudo apt install $missing)."
        fi
    fi
fi

mkdir -p "$HOME/.local/bin"
ln -sf "$BUDDY" "$HOME/.local/bin/buddy"

if [ $# -ge 1 ]; then "$BUDDY" choose "$1"; else "$BUDDY" choose; fi
"$BUDDY" autostart on

found=""
command -v claude >/dev/null && found="$found, Claude Code"
command -v gemini >/dev/null && found="$found, Gemini CLI"
command -v codex >/dev/null && found="$found, Codex"
found="${found#, }"
if [ -n "$found" ]; then
    if [ -t 0 ]; then
        read -r -p "Found $found. Let your buddy react to them? [Y/n] " answer || answer=n
        case "${answer:-y}" in
            [Yy]*) "$BUDDY" agents on || echo "Couldn't set up every agent; try later with: buddy agents on" ;;
            *) echo "Skipped. Turn it on later with: buddy agents on" ;;
        esac
    else
        echo "Found $found. To let your buddy react to them, run: buddy agents on"
    fi
fi

"$BUDDY" stop >/dev/null 2>&1 || true
"$BUDDY" run >/dev/null || { echo "Buddy couldn't start (see the message above)."; exit 1; }

echo
echo "Buddy is running! Commands:"
echo "  buddy choose <name>    switch Pokémon"
echo "  buddy config           edit thresholds, size, speed"
echo "  buddy autostart off    don't start at login"
echo "  buddy agents on|off    react to Claude Code / Gemini CLI / Codex"
echo "  buddy guide            everything else"
case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) echo "Note: add ~/.local/bin to your PATH to use the 'buddy' command." ;;
esac
