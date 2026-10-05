# Buddy

**A tiny Pokémon that lives on top of your windows.** It walks along the bottom of your screen
while you work. You can pet it, pick it up and drop it, and it acts as your laptop's "soul": when
your computer is overloaded, it gets stressed and shows you why. It can also keep you company
while Claude Code, Gemini CLI or Codex is working.

<p align="center"><img src="docs/images/reactions.png" alt="Buddy's reaction bubbles: love when clicked, confused when dropped, stressed under load, a book while an AI agent works, and an exclamation mark when it finishes" width="760"></p>

---

## What it does

- **Wanders around.** Your Pokémon strolls along the bottom of the screen in little steps, over
  VS Code, your terminal, the desktop or any other window, and on every workspace.
- **Loves attention.** Click it and it hops with a ❤️.
- **Can be picked up.** Click, hold and drag it anywhere. When you let go it falls back down and
  looks around, a bit confused ❓.
- **Gets dizzy.** Shake it back and forth while you hold it and little stars ⭐ start circling
  its head, and keep circling for a little while after it lands.
- **Takes naps.** Leave it alone for a few minutes and now and then it dozes off where it stands,
  with little 💤 drifting up. Step away from your computer for 5 minutes and it sleeps until you're
  back. Clicking or picking it up wakes it.
- **Feels your laptop's stress.** If CPU or RAM stays high long enough to make your laptop lag,
  it gets angry 💢 and shows a little Matrix-style CPU/RAM readout. When things calm down, the
  readout disappears.
- **Keeps your AI agent company.** When you send a prompt to Claude Code, Gemini CLI or Codex,
  it hurries to the right side of the screen and reads a book while the agent works. When the
  agent finishes, it jumps up and down with a ❗.
- **Stays out of your way.** Clicks right next to it go through to the window underneath.

<p align="center">
  <img src="docs/images/thinking.gif" alt="Thinking bubble: an open book flipping its pages" width="168">
  &nbsp;&nbsp;&nbsp;
  <img src="docs/images/stress-panel.png" alt="Stress panel: green Matrix rain with CPU 94% and RAM 88%" width="240">
</p>

## What you need

- **Windows 10/11, macOS, or Linux.** It's built and tested on Ubuntu 26.04 (GNOME, Wayland).
  Windows and macOS are covered by automated tests on every change, and confirmation on real
  screens is welcome.
- **An internet connection** the first time: the installer downloads Buddy, its own private copy
  of Python and Qt (about 120 MB), and your Pokémon's sprite. After that it works offline.

You don't need Python or Git: the installer uses [uv](https://docs.astral.sh/uv/) to fetch a
private Python just for Buddy, and leaves any Python you already have alone. No admin rights needed.

## Install

**Windows:** open PowerShell and run

```powershell
irm https://raw.githubusercontent.com/ShashwatkumarXD/buddy/main/install.ps1 | iex
```

**macOS or Linux:** open a terminal and run

```bash
curl -fsSL https://raw.githubusercontent.com/ShashwatkumarXD/buddy/main/install.sh | bash
```

Run the same line again any time to update Buddy. Your settings and Pokémon are kept.

> **Linux only:** Qt needs a few system libraries. The installer checks for them and offers to
> install them with `sudo apt`. On Ubuntu the line is
> `sudo apt install libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-render-util0 libxcb-xkb1`.

The installer will:

1. set up everything Buddy needs inside the `buddy` folder
2. ask which Pokémon you want (just press Enter for Pikachu)
3. make Buddy start automatically when you log in
4. offer to connect it to Claude Code, Gemini CLI or Codex if you have them installed
5. start your Buddy right away

You can also name your Pokémon straight away: add `-s charmander` after `bash`, or on Windows run
`$env:BUDDY_POKEMON = "charmander"` first.

> **Tip:** on Windows the `buddy` command works straight away in the window you installed from.
> In terminals that were already open, or if macOS/Linux says `buddy: command not found`, open a
> new terminal. On macOS or Linux, if it still happens, add `~/.local/bin` to your `PATH`.

## Everyday use

| You want to… | Run |
|---|---|
| Switch to another Pokémon | `buddy choose eevee` |
| Hide Buddy | `buddy stop` |
| Bring Buddy back | `buddy run` |
| Change its size, speed or stress levels | `buddy config` |
| Stop it starting at login | `buddy autostart off` |
| Start it at login again | `buddy autostart on` |
| Connect it to your AI agents | `buddy agents on` |
| Disconnect it from your AI agents | `buddy agents off` |
| See the full guide in your terminal | `buddy guide` |

**Choosing a Pokémon:** use its English name, in any capitalisation. Spaces are fine (`buddy choose mr mime`).
If Buddy is running, it switches instantly.

## Working with AI agents

Buddy can react to **Claude Code**, **Gemini CLI** and **Codex**:

```bash
buddy agents on            # connect every agent installed on your computer
buddy agents on gemini     # or just one: claude, gemini or codex
```

Then **restart your agent** (open sessions don't see the change until they restart).

- **Codex only:** it asks you to approve new hooks once. Type `/hooks` inside Codex.
- **What gets changed:** Buddy adds two small hooks to the agent's settings file and leaves
  everything else as it was. It saves a backup next to the file first.
- **Turning it off:** `buddy agents off` removes only Buddy's hooks.

| When… | Buddy… |
|---|---|
| you send a prompt | hurries to a spot near the right edge of the screen and reads its book |
| the agent finishes | shows ❗ and jumps three times, then goes back to wandering |
| you stop the agent early | keeps reading until your next prompt, or for up to 10 minutes |

## Settings

Run `buddy config` to open the settings file. When you save and close the editor, Buddy checks
your changes and reloads.

| Setting | Default | What it means |
|---|---|---|
| `pokemon` | `"pikachu"` | Your Pokémon. Change it with `buddy choose`, which also downloads the sprite. |
| `style` | `"hgss"` | The look of the sprites (see below). Run `buddy choose <name>` again after changing it. |
| `scale` | `2` | Size. `2` is about 64 px, `3` about 96 px. Whole numbers keep the pixel art sharp. |
| `walk_speed` | `20` | Walking speed in pixels per second. |
| `cpu_enter` / `ram_enter` | `85` / `90` | Buddy gets stressed when average CPU or RAM use (%) reaches these. |
| `cpu_exit` / `ram_exit` | `70` / `85` | It calms down only when usage stays below these. |
| `window_seconds` | `5` | How many seconds usage has to stay high (or low) before Buddy reacts. |

### Sprite styles

| Style | Looks like | Pokémon |
|---|---|---|
| `hgss` (default) | The Pokémon that follows you around in HeartGold/SoulSilver | #1–493 (later ones use `gba`) |
| `gba` | Pokémon Mystery Dungeon style | Almost all of them |
| `ds` | Black/White battle sprites | All of them |

**Want to see the stressed look?** This keeps every CPU core busy for 25 seconds:

```bash
for i in $(seq $(nproc)); do timeout 25 sh -c 'while :; do :; done' & done
```

## Troubleshooting

| Problem | Fix |
|---|---|
| Buddy doesn't appear | Run `buddy run --foreground` in a terminal and read the message it prints. |
| `buddy` is not recognized (Windows) | Open a new PowerShell window, or run `$env:Path += ";$env:LOCALAPPDATA\buddy\bin"` |
| "Qt needs some system libraries" (Linux) | Run the `sudo apt install …` line it prints. |
| "could not connect to display" (Linux) | `sudo apt install xwayland` |
| "No sprites cached for …" | `buddy choose <name>` (needs internet once) |
| "Buddy is already running" | `buddy stop`, then `buddy run` |
| Buddy doesn't react to my agent | `buddy agents on`, then restart the agent. For Codex, also approve via `/hooks`. |
| Settings error | `buddy config` points at the problem line. Fix it and save. |
| Not there after logging in (Linux) | Check `journalctl --user -b \| grep -i buddy` |
| Windows: only on one desktop | Buddy stays on the virtual desktop where it started. Windows doesn't let apps pin themselves to every desktop. |

Logs are in `~/.cache/buddy/buddy.log` (Linux), `~/Library/Caches/buddy/buddy.log` (macOS) or `%LOCALAPPDATA%\buddy\Cache\buddy.log` (Windows).

## Uninstall

```bash
buddy agents off
buddy stop
buddy autostart off
```

Then delete Buddy's files (this includes its private Python):

| System | Files to delete |
|---|---|
| Linux | `~/.local/bin/buddy`, `~/.local/share/buddy`, `~/.config/buddy`, `~/.cache/buddy` |
| macOS | `~/.local/bin/buddy`, `~/Library/Application Support/buddy`, `~/Library/Caches/buddy` |
| Windows | `%APPDATA%\buddy`, `%LOCALAPPDATA%\buddy` (and remove `%LOCALAPPDATA%\buddy\bin` from your user PATH) |

## For developers

Clone the repo and run `./install.sh` (Windows: `powershell -ExecutionPolicy Bypass -File install.ps1`).
From a clone, the installer makes an editable install with the test tools in `.venv`.
`BUDDY_REF=<branch>` makes the one-line installer fetch a branch instead of `main`.

```bash
.venv/bin/pytest -q                            # run the tests
.venv/bin/python tools/make_thinking_bubble.py # rebuild the thinking-bubble frames
```

The design notes live in [`docs/superpowers/specs/`](docs/superpowers/specs/).

## Credits

- HeartGold/SoulSilver follower sprites (`hgss`): [veekun](https://veekun.com/dex/downloads)
- Mystery Dungeon-style sprites (`gba`): [PMDCollab SpriteCollab](https://github.com/PMDCollab/SpriteCollab)
  (CC BY-NC 4.0, credit to their artists)
- Black/White sprites (`ds`) and Pokémon data: [PokéAPI](https://pokeapi.co)
- Pokémon is © Nintendo / Creatures / GAME FREAK. This is a fan project for personal use; no sprites
  are included in this repository. Each one is downloaded on your own computer when you choose it.
