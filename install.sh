#!/usr/bin/env bash
# Install buddy: ./install.sh [pokemon-name]
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
REPO="$PWD"
BUDDY="$REPO/.venv/bin/buddy"
LOG_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/buddy"

command -v python3 >/dev/null || { echo "python3 is required"; exit 1; }
if ! python3 -c "import gi; gi.require_foreign('cairo'); gi.require_version('Gtk', '3.0'); from gi.repository import Gtk" 2>/dev/null; then
    echo "GTK bindings are missing. Install them with: sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0"
    exit 1
fi
command -v Xwayland >/dev/null || echo "warning: Xwayland not found; on Wayland buddy needs it (sudo apt install xwayland)"

echo "Setting up Python environment…"
python3 -m venv --system-site-packages .venv
.venv/bin/pip install --quiet -e .

mkdir -p "$HOME/.local/bin" "$LOG_DIR"
ln -sf "$BUDDY" "$HOME/.local/bin/buddy"

if [ $# -ge 1 ]; then "$BUDDY" choose "$1"; else "$BUDDY" choose; fi
"$BUDDY" autostart on

if command -v claude >/dev/null; then
    if [ -t 0 ]; then
        read -r -p "Found Claude Code. Let your buddy react to it? [Y/n] " answer
        case "${answer:-y}" in
            [Yy]*) "$BUDDY" claude on ;;
            *) echo "Skipped. Turn it on later with: buddy claude on" ;;
        esac
    else
        echo "Found Claude Code. To let your buddy react to it, run: buddy claude on"
    fi
fi
"$BUDDY" stop >/dev/null 2>&1 || true
setsid -f "$BUDDY" run >"$LOG_DIR/buddy.log" 2>&1 </dev/null

echo
echo "Buddy is running! Commands:"
echo "  buddy choose <name>    switch Pokémon"
echo "  buddy config           edit thresholds, size, speed"
echo "  buddy autostart off    don't start at login"
echo "  buddy claude on|off    react to Claude Code"
echo "  buddy guide            everything else"
echo "  buddy stop / buddy run"
case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) echo "Note: add ~/.local/bin to your PATH to use the 'buddy' command." ;;
esac
