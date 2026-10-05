#!/usr/bin/env bash
# Install or update buddy on Linux or macOS. Needs nothing but curl (no Git, no Python):
#   curl -fsSL https://raw.githubusercontent.com/ShashwatkumarXD/buddy/main/install.sh | bash
#   curl -fsSL https://raw.githubusercontent.com/ShashwatkumarXD/buddy/main/install.sh | bash -s eevee
# From a clone (for development): ./install.sh [pokemon-name]
# Windows: see install.ps1. Optional: BUDDY_REF=<branch|tag|commit> (default main).
# Everything runs from main() on the last line, so a half-downloaded script does nothing.
set -euo pipefail

GITHUB_REPO="ShashwatkumarXD/buddy"
PYTHON_VERSION="3.12"
TMP_SRC=""

say() { printf '%s\n' "$*"; }
fail() { printf 'buddy: %s\n' "$*" >&2; exit 1; }
# `curl | bash` feeds this script on stdin, so questions go to the terminal itself.
can_ask() { { : </dev/tty; } 2>/dev/null; }

clone_dir() {  # the repo folder when run as ./install.sh, empty when piped in
    local self="${BASH_SOURCE[0]:-}" dir
    if [ -n "$self" ] && [ -f "$self" ]; then
        dir="$(cd "$(dirname "$self")" && pwd)"
        if [ -f "$dir/pyproject.toml" ] && [ -d "$dir/buddy" ]; then say "$dir"; fi
    fi
}

find_uv() {
    local f
    for f in "$1/uv" "$1/bin/uv"; do
        if [ -x "$f" ]; then say "$f"; return 0; fi
    done
    return 1
}

main() {
    local data cache
    case "$(uname -s)" in
        Darwin) data="$HOME/Library/Application Support/buddy"; cache="$HOME/Library/Caches/buddy" ;;
        Linux) data="${XDG_DATA_HOME:-$HOME/.local/share}/buddy"; cache="${XDG_CACHE_HOME:-$HOME/.cache}/buddy" ;;
        *) fail "this installer is for Linux and macOS; on Windows use install.ps1" ;;
    esac
    command -v curl >/dev/null || fail "curl is needed (Ubuntu/Debian: sudo apt install curl)"
    local pokemon="${1:-}" repo venv src uv answer
    repo="$(clone_dir)"
    if [ -n "$repo" ]; then venv="$repo/.venv"; else venv="$data/venv"; fi
    local buddy="$venv/bin/buddy"

    if [ -n "$repo" ]; then
        src="$repo"
    else
        local ref="${BUDDY_REF:-main}"
        local archive="${BUDDY_ARCHIVE:-https://github.com/$GITHUB_REPO/archive/$ref.tar.gz}"
        TMP_SRC="$(mktemp -d)"
        trap 'rm -rf "$TMP_SRC"' EXIT
        say "Downloading buddy ($ref)…"
        curl -fsSL "$archive" | tar -xz -C "$TMP_SRC" --strip-components=1 || fail "couldn't download $archive"
        src="$TMP_SRC"
    fi

    mkdir -p "$data" "$cache" "$HOME/.local/bin"
    if ! uv="$(find_uv "$data/uv")"; then
        say "Downloading uv (it fetches a private copy of Python just for buddy)…"
        curl -fsSL https://astral.sh/uv/install.sh | env UV_UNMANAGED_INSTALL="$data/uv" sh >/dev/null \
            || fail "couldn't install uv from astral.sh"
        uv="$(find_uv "$data/uv")" || fail "uv was installed but isn't in $data/uv"
    fi
    # Python and uv's downloads live in buddy's folders; any Python already installed is left alone.
    export UV_PYTHON_INSTALL_DIR="$data/python" UV_PYTHON_PREFERENCE=only-managed UV_CACHE_DIR="$cache/uv"

    if [ -x "$buddy" ]; then "$buddy" stop >/dev/null 2>&1 || true; fi  # updating: replace the running one
    say "Setting up Python $PYTHON_VERSION and Qt (about 120 MB the first time)…"
    rm -rf "$venv"
    "$uv" venv --quiet --python "$PYTHON_VERSION" "$venv"
    if [ -n "$repo" ]; then
        "$uv" pip install --quiet --python "$venv/bin/python" -e "$repo[dev]"
    else
        "$uv" pip install --quiet --python "$venv/bin/python" "$src"
    fi

    if [ "$(uname -s)" = "Linux" ]; then
        local missing
        missing="$("$venv/bin/python" -c 'from buddy.window import missing_x11_libraries as m; print(" ".join(m()))')"
        if [ -n "$missing" ]; then
            say "Qt needs a few system libraries: $missing"
            if can_ask && command -v apt >/dev/null; then
                read -r -p "Install them now with sudo apt? [Y/n] " answer </dev/tty || answer=n
                case "${answer:-y}" in
                    [Yy]*) sudo apt install -y $missing </dev/tty ;;
                    *) say "Buddy can't start until you run: sudo apt install $missing" ;;
                esac
            else
                say "Install them with your package manager (Ubuntu/Debian: sudo apt install $missing)."
            fi
        fi
    fi

    ln -sf "$buddy" "$HOME/.local/bin/buddy"
    if can_ask; then
        "$buddy" choose ${pokemon:+"$pokemon"} </dev/tty
    else
        "$buddy" choose ${pokemon:+"$pokemon"} </dev/null
    fi
    "$buddy" autostart on

    local found=""
    command -v claude >/dev/null && found="$found, Claude Code"
    command -v gemini >/dev/null && found="$found, Gemini CLI"
    command -v codex >/dev/null && found="$found, Codex"
    found="${found#, }"
    if [ -n "$found" ]; then
        if can_ask; then
            read -r -p "Found $found. Let your buddy react to them? [Y/n] " answer </dev/tty || answer=n
            case "${answer:-y}" in
                [Yy]*) "$buddy" agents on || say "Couldn't set up every agent; try later with: buddy agents on" ;;
                *) say "Skipped. Turn it on later with: buddy agents on" ;;
            esac
        else
            say "Found $found. To let your buddy react to them, run: buddy agents on"
        fi
    fi

    "$buddy" run >/dev/null || fail "buddy couldn't start (see the message above)"

    say ""
    say "Buddy is running! Commands:"
    say "  buddy choose <name>    switch Pokémon"
    say "  buddy config           edit thresholds, size, speed"
    say "  buddy autostart off    don't start at login"
    say "  buddy agents on|off    react to Claude Code / Gemini CLI / Codex"
    say "  buddy guide            everything else"
    case ":$PATH:" in
        *":$HOME/.local/bin:"*) ;;
        *) say "Note: add ~/.local/bin to your PATH to use the 'buddy' command." ;;
    esac
}

main "$@"
