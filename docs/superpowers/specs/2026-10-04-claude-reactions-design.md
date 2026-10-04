# Claude Reactions — Design

Date: 2026-10-04 · Status: approved in conversation · Builds on `2026-10-04-pokemon-buddy-design.md`

## Goal

Buddy reacts to Claude Code: while Claude works on a prompt the Pokémon goes to a "thinking
spot" near the right of the screen and shows a thinking bubble; when Claude finishes it shows a
**!** bubble and hops three times on the spot, then goes back to wandering.

## Mechanism

- Claude Code hooks in `~/.claude/settings.json` (or `$CLAUDE_CONFIG_DIR/settings.json`):
  - `UserPromptSubmit` → `"<buddy>" event thinking`
  - `Stop` → `"<buddy>" event done`
  - each with `"timeout": 5`.
- `buddy event thinking|done` sends `SIGUSR1` / `SIGUSR2` to the running buddy (PID file +
  `/proc` check as for other commands). Not running → silently does nothing. Always exits 0,
  never prints, so it can never disturb Claude.

## Behaviour

| Trigger | Buddy |
|---|---|
| thinking | Walks at 150 px/s to x = `right − width − 15% of screen width`, then stands (idle animation) showing the thinking bubble |
| done | **!** bubble for 2.5 s and 3 hops in place; then normal wandering (or stressed fidget) |
| dragged while thinking | Falls, ❓ on landing as usual, then walks back to the spot |
| no `done` within 10 min | Thinking ends (Claude interrupted); next prompt starts it again |

Bubble priority: dragged → none, else ❤️ > ❓ > **!** > thinking > 💢. While stressed and thinking,
the pet thinks (stands at the spot) and the Matrix panel still shows.

## Commands and install

- `buddy claude on`: back up existing settings to `settings.json.buddy-backup`, remove any old
  buddy hooks, add the two hooks, keep everything else; written atomically. Invalid JSON →
  error, file untouched.
- `buddy claude off`: remove only buddy's hooks (and any hook lists left empty).
- `install.sh`: if `claude` is on PATH and stdin is a terminal, ask
  "Let your buddy react to Claude Code? [Y/n]" → `buddy claude on`.
- Guide gains a Claude Code section.

## Assets

User-supplied pixel art: `exclaim.png` (!) and the cloud of `thinking.png`, converted to native
pixel size (40 px wide) like the other bubbles. At the user's request the thinking bubble shows only
an open book, redrawn as pixel art by `tools/make_thinking_bubble.py`, which also writes
`thinking_1..3.png`: a page lifting, standing up and landing. Any bubble with `<name>_N.png`
frames animates: first frame held 700 ms, then 110 ms per frame, looping (`buddy/timing.py`).

## Testing

Brain: walk to spot, thinking bubble, done → ! + exactly 3 hops → wander, drag returns to spot,
10-min timeout, stress while thinking, priority. CLI: hooks added/merged/idempotent/removed,
invalid JSON untouched, backup written, `event` signals or no-ops. Window: manual.

## Out of scope

Other AI CLIs, multiple concurrent Claude sessions (last event wins), reacting to permission
prompts.
