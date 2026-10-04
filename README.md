# Buddy

A Pokémon that lives above your windows. Click it for love, drag it around, and watch it get
stressed (with a Matrix CPU/RAM readout) when your laptop is overloaded.

Built for Ubuntu GNOME on Wayland (runs through XWayland). Personal use only — sprites come
from PokéAPI and are Nintendo's property.

## Install

```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0   # once
./install.sh            # asks which Pokémon
./install.sh charmander # or pass it directly
```

## Commands

| Command | What it does |
|---|---|
| `buddy choose <name>` | Switch Pokémon |
| `buddy config` | Edit `~/.config/buddy/config.toml` (`style`, thresholds, `scale`, `walk_speed`) |
| `buddy autostart on\|off` | Start at login or not |
| `buddy run` / `buddy stop` | Start / stop |

Logs from the installer launch: `~/.cache/buddy/buddy.log`.

## Uninstall

```bash
buddy stop; buddy autostart off
rm ~/.local/bin/buddy
rm -r ~/.config/buddy ~/.cache/buddy
```

## Sprite credits

Default `style = "gba"` uses Mystery Dungeon-style sprites from the
[PMDCollab SpriteCollab](https://github.com/PMDCollab/SpriteCollab) project (CC BY-NC 4.0,
credit to their artists). `style = "ds"` uses Black/White sprites via [PokéAPI](https://pokeapi.co).
Pokémon is © Nintendo / Creatures / GAME FREAK.
