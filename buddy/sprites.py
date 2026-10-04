"""Find a Pokémon on PokéAPI, download its sprite frames, and cache them on disk."""
import io
import json
import os
import shutil
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageSequence

API = "https://pokeapi.co/api/v2/pokemon/{name}"
DEFAULT_FRAME_MS = 100
MIN_FRAME_MS = 20


class SpriteError(Exception):
    """A sprite could not be found, downloaded, or loaded."""


@dataclass
class SpriteInfo:
    name: str
    id: int
    animated_url: str | None
    static_url: str | None


def normalize_name(name: str) -> str:
    return "-".join(name.strip().lower().split())


def cache_dir() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "buddy" / "sprites"


def fetch_json(url: str, timeout: float = 10) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "buddy-desktop-pet"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def fetch_bytes(url: str, timeout: float = 10) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "buddy-desktop-pet"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def lookup(name: str, fetch_json=fetch_json) -> SpriteInfo:
    try:
        data = fetch_json(API.format(name=urllib.parse.quote(name)))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise SpriteError(f"No Pokémon called '{name}'.") from None
        raise SpriteError(f"PokéAPI returned an error ({e.code}).") from None
    except OSError as e:
        raise SpriteError(f"Could not reach PokéAPI ({e}). Check your internet connection.") from None
    sprites = data.get("sprites") or {}
    animated = (
        sprites.get("versions", {})
        .get("generation-v", {})
        .get("black-white", {})
        .get("animated", {})
        .get("front_default")
    )
    static = sprites.get("front_default")
    if not animated and not static:
        raise SpriteError(f"'{name}' has no sprites on PokéAPI.")
    return SpriteInfo(name=data["name"], id=data["id"], animated_url=animated, static_url=static)


def decode_frames(data: bytes) -> list[tuple[Image.Image, int]]:
    """Decode a GIF (many frames) or PNG (one frame) into RGBA frames with durations."""
    try:
        image = Image.open(io.BytesIO(data))
        return [
            (frame.convert("RGBA"), max(MIN_FRAME_MS, int(frame.info.get("duration") or DEFAULT_FRAME_MS)))
            for frame in ImageSequence.Iterator(image)
        ]
    except (OSError, ValueError, SyntaxError) as e:
        raise SpriteError(f"Unreadable sprite image ({e}).") from None


def crop_to_content(frames: list[tuple[Image.Image, int]]) -> list[tuple[Image.Image, int]]:
    """Crop every frame to the union of their opaque areas so the pet stands on the ground."""
    boxes = [box for box in (img.getchannel("A").getbbox() for img, _ in frames) if box]
    if not boxes:
        return frames
    union = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
    return [(img.crop(union), ms) for img, ms in frames]


def download(name: str, fetch_json=fetch_json, fetch_bytes=fetch_bytes, root: Path | None = None) -> str:
    name = normalize_name(name)
    if not name:
        raise SpriteError("Please give a Pokémon name.")
    info = lookup(name, fetch_json=fetch_json)
    frames = []
    if info.animated_url:
        try:
            frames = decode_frames(fetch_bytes(info.animated_url))
        except (SpriteError, OSError):
            frames = []
    if not frames:
        if not info.static_url:
            raise SpriteError(f"Could not download a sprite for '{info.name}'.")
        try:
            frames = decode_frames(fetch_bytes(info.static_url))
        except OSError as e:
            raise SpriteError(f"Could not download the sprite for '{info.name}' ({e}).") from None
    _write_atomically(root or cache_dir(), info.name, crop_to_content(frames))
    return info.name


def load_cached(name: str, root: Path | None = None) -> list[tuple[Path, int]]:
    folder = (root or cache_dir()) / normalize_name(name)
    hint = f"No sprites cached for '{name}'. Run: buddy choose {name}"
    try:
        meta = json.loads((folder / "meta.json").read_text())
        durations = [int(ms) for ms in meta["durations_ms"]]
    except (OSError, ValueError, KeyError, TypeError):
        raise SpriteError(hint) from None
    frames = [(folder / f"frame_{i:03d}.png", ms) for i, ms in enumerate(durations)]
    if not frames or not all(path.is_file() for path, _ in frames):
        raise SpriteError(hint)
    return frames


def _write_atomically(root: Path, name: str, frames: list[tuple[Image.Image, int]]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f".{name}-new-", dir=root))
    old = root / f".{name}-old"
    final = root / name
    try:
        for i, (img, _) in enumerate(frames):
            img.save(tmp / f"frame_{i:03d}.png")
        (tmp / "meta.json").write_text(json.dumps({"name": name, "durations_ms": [ms for _, ms in frames]}))
        shutil.rmtree(old, ignore_errors=True)
        if final.exists():
            final.rename(old)
        tmp.rename(final)
        shutil.rmtree(old, ignore_errors=True)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
