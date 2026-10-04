# Claude Reactions Implementation Plan

> Executed inline (superpowers:executing-plans) on branch `feature/claude-reactions`; TDD per task.

**Goal:** Buddy goes to a thinking spot while Claude Code works and celebrates (! + 3 hops) when it finishes.

**Architecture:** Claude Code hooks call `buddy event thinking|done`, which signals the running
buddy (SIGUSR1/SIGUSR2); the window forwards these to new `Brain.claude_thinking()` /
`Brain.claude_done()`; `buddy claude on|off` manages the hooks in Claude's settings.json.

**Spec:** `docs/superpowers/specs/2026-10-04-claude-reactions-design.md`

## Global Constraints

- Hook commands must always exit 0 and print nothing.
- `claude on/off` must never drop unrelated keys or hooks from Claude's settings.json.
- Logic stays GTK-free (brain, cli); window is manual-tested.
- Constants: spot = right − width − 15% of screen width; hurry speed 150 px/s; ! bubble 2.5 s;
  3 hops; thinking timeout 600 s.

## Review Focus

1. Claude settings.json with existing hooks/keys → preserved exactly (`test_claude_on_preserves_existing_settings`).
2. Corrupt settings.json → untouched, clear error (`test_claude_on_refuses_invalid_json`).
3. Claude interrupted (no Stop) → buddy doesn't think forever (`test_thinking_times_out`).
4. Hook fired while buddy not running → silent success (`test_event_without_running_buddy_is_silent`).
5. Running `claude on` twice → no duplicate hooks (`test_claude_on_is_idempotent`).

## Tasks

### Task 1: Bubble assets
Convert `.superpowers/inputs/7.png` → `buddy/assets/bubbles/exclaim.png`, `8.png` → `thinking.png`
(native 40 px wide, hard alpha). Test: `tests/test_assets.py` covers all five bubbles (width 40,
height ≤ 40, alpha only 0/255).

### Task 2: Brain reactions
`Bubble.EXCLAIM="exclaim"`, `Bubble.THINKING="thinking"`, `State.THINKING`; `Brain.claude_thinking()`,
`Brain.claude_done()`, property `Brain.moving -> bool`, `Brain.thinking_x -> float`.
Tests in `tests/test_brain.py`: walks to spot with thinking bubble; done → exclaim + 3 hops →
idle; drag while thinking returns to spot; timeout; stress while thinking; love beats thinking;
`moving` per state.

### Task 3: CLI
`buddy event thinking|done` (SIGUSR1/SIGUSR2, silent, exit 0); `buddy claude on|off`
(`claude_settings_path()`, merge/remove, backup, atomic write). Tests in `tests/test_cli.py`
named in Review Focus plus `test_claude_off_removes_only_buddy_hooks`,
`test_event_signals_running_buddy`.

### Task 4: Window, installer, guide
Window: SIGUSR1/SIGUSR2 handlers, animation from `brain.moving`, window height from the tallest
bubble. `install.sh`: detect `claude`, ask, run `buddy claude on`. Guide: Claude section and
commands (guide test extended with `claude on`, `claude off`). Manual check: send a prompt in
Claude Code → buddy goes right and thinks; reply ends → ! and three hops.
