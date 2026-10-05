"""Render every line in buddy/assets/messages.toml as an animated GIF, plus an index.html to browse them.

Usage: .venv/bin/python tools/preview_messages.py OUT_DIR
"""
import html
import sys
import tomllib
from pathlib import Path

from PIL import Image

from buddy import pixelfont, speech

MESSAGES = Path(__file__).resolve().parent.parent / "buddy" / "assets" / "messages.toml"
ZOOM = 3
BACKDROP = (88, 108, 138, 255)
TIME_STYLES = {"morning": "wave", "afternoon": "smile", "evening": "wave", "late_night": "type", "sleep": "type"}


def sections(data: dict) -> list[tuple[str, str, list[str]]]:
    """(heading, style, lines) for each list in the file."""
    out = [(f"Greeting · {style}", style, lines) for style, lines in data["greetings"].items()]
    out.append(("Quotes", "quote", data["quotes"]["lines"]))
    out += [(f"Time · {name.replace('_', ' ')}", TIME_STYLES[name], lines) for name, lines in data["time"].items()]
    return out


def gif(style: str, text: str, path: Path) -> tuple[int, int]:
    frames = speech.frames(style, text)
    shots = []
    for im, _ in frames:
        bg = Image.new("RGBA", im.size, BACKDROP)
        bg.alpha_composite(im)
        shots.append(bg.convert("RGB").resize((im.width * ZOOM, im.height * ZOOM), Image.NEAREST))
    durations = [ms for _, ms in frames]
    durations[-1] = 2500  # linger on the finished bubble before the preview loops
    shots[0].save(path, save_all=True, append_images=shots[1:], duration=durations, loop=0, disposal=1)
    return shots[0].size


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    data = tomllib.loads(MESSAGES.read_text(encoding="utf-8"))
    parts, total = [], 0
    for heading, style, lines in sections(data):
        cards = []
        for i, text in enumerate(lines):
            if not pixelfont.supports(text):
                raise SystemExit(f"can't draw {text!r}: unsupported character")
            name = f"{heading.split(' · ')[-1].replace(' ', '_').lower()}_{i:02d}.gif"
            w, h = gif(style, text, out / name)
            cards.append(f'<figure><img src="{name}" width="{w}" height="{h}" alt=""><figcaption>{html.escape(text)}</figcaption></figure>')
        total += len(lines)
        parts.append(f"<h2>{html.escape(heading)} <small>{len(lines)} lines · style “{style}”</small></h2><div class=grid>{''.join(cards)}</div>")
    (out / "index.html").write_text(
        "<!doctype html><meta charset=utf-8><title>Buddy says…</title><style>"
        "body{font:14px system-ui;background:#1d2230;color:#e8e8f0;margin:0;padding:24px}"
        "h1{margin:0 0 4px}h2{margin:36px 0 12px;border-bottom:1px solid #3a4258;padding-bottom:6px}"
        "small{color:#9aa3bb;font-weight:normal;font-size:13px;margin-left:8px}"
        ".grid{display:flex;flex-wrap:wrap;gap:14px;align-items:flex-end}"
        "figure{margin:0;background:#586c8a;padding:6px;border-radius:6px}img{image-rendering:pixelated;display:block}"
        "figcaption{font-size:11px;color:#dfe5f2;max-width:300px;margin-top:4px}</style>"
        f"<h1>Buddy says…</h1><p>{total} lines, shown at {ZOOM}× native pixels.</p>" + "".join(parts),
        encoding="utf-8",
    )
    print(f"{total} bubbles → {out / 'index.html'}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
