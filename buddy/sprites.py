"""Find a Pokémon on PokéAPI, download its sprite frames, and cache them on disk.

Three styles:
- "hgss": HeartGold/SoulSilver follower sprites from veekun's overworld pack (#1–493, 2-frame
  step facing right, front view when idle), falling back to "gba" for later Pokémon.
- "gba": Mystery Dungeon-style walk/idle sheets from PMDCollab SpriteCollab (side view,
  facing right), falling back to the still Emerald battle sprite.
- "ds": Black/White animated battle sprite (facing left), falling back to the still sprite.
"""
import http.client
import io
import json
import os
import shutil
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zlib
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageSequence

API = "https://pokeapi.co/api/v2/pokemon/{name}"
PMD_BASE = "https://raw.githubusercontent.com/PMDCollab/SpriteCollab/master/sprite/{id:04d}/"
PMD_FRAME_MS = 1000 / 60  # AnimData durations are in 60 fps game frames
PMD_RIGHT_ROW = 2  # sheet rows: down, down-right, right, up-right, up, up-left, left, down-left
STYLES = ("hgss", "gba", "ds")
HGSS_PACK_URL = "https://veekun.com/static/pokedex/downloads/overworld.tar.gz"
HGSS_PACK_FILE = "hgss-overworld.tar.gz"
HGSS_MAX_ID = 493
HGSS_STEP_MS = 250
HGSS_IDLE_MS = 600
DEFAULT_FRAME_MS = 100
MIN_FRAME_MS = 20

Frames = list[tuple[Image.Image, int]]


class SpriteError(Exception):
    """A sprite could not be found, downloaded, or loaded."""


@dataclass
class SpriteInfo:
    name: str
    id: int
    animated_url: str | None
    static_url: str | None
    gen3_url: str | None = None


@dataclass
class PmdAnim:
    sheet: str  # base name of the "<sheet>-Anim.png" file holding the frames
    width: int
    height: int
    durations_ms: list[int]


@dataclass
class CachedSprite:
    anims: dict[str, list[tuple[Path, int]]]  # "walk" and "idle" -> (frame png, duration ms)
    faces: int  # direction the source art faces: 1 right, -1 left


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
    versions = sprites.get("versions", {})
    animated = versions.get("generation-v", {}).get("black-white", {}).get("animated", {}).get("front_default")
    gen3 = versions.get("generation-iii", {})
    gen3_url = gen3.get("emerald", {}).get("front_default") or gen3.get("firered-leafgreen", {}).get("front_default")
    static = sprites.get("front_default")
    return SpriteInfo(name=data["name"], id=data["id"], animated_url=animated, static_url=static, gen3_url=gen3_url)


def decode_frames(data: bytes) -> Frames:
    """Decode a GIF (many frames) or PNG (one frame) into RGBA frames with durations."""
    try:
        image = Image.open(io.BytesIO(data))
        return [
            (frame.convert("RGBA"), max(MIN_FRAME_MS, int(frame.info.get("duration") or DEFAULT_FRAME_MS)))
            for frame in ImageSequence.Iterator(image)
        ]
    except (OSError, ValueError, SyntaxError) as e:
        raise SpriteError(f"Unreadable sprite image ({e}).") from None


def parse_anim_data(xml_text: str) -> dict[str, PmdAnim]:
    """Parse a SpriteCollab AnimData.xml into animations by name, following CopyOf links."""
    if "<!DOCTYPE" in xml_text or "<!ENTITY" in xml_text:  # real files never have one; blocks entity bombs
        raise SpriteError("Refusing animation data that contains a DTD.")
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise SpriteError(f"Unreadable Mystery Dungeon animation data ({e}).") from None
    nodes = {node.findtext("Name"): node for node in root.iter("Anim") if node.findtext("Name")}

    def resolve(name: str, seen: tuple[str, ...] = ()) -> PmdAnim:
        node = nodes[name]
        copy_of = node.findtext("CopyOf")
        if copy_of:
            if copy_of in seen or copy_of not in nodes:
                raise SpriteError(f"Broken CopyOf for animation {name}.")
            return resolve(copy_of, seen + (name,))
        try:
            return PmdAnim(
                sheet=name,
                width=int(node.findtext("FrameWidth")),
                height=int(node.findtext("FrameHeight")),
                durations_ms=[max(MIN_FRAME_MS, round(int(d.text) * PMD_FRAME_MS)) for d in node.iter("Duration")],
            )
        except (TypeError, ValueError):
            raise SpriteError(f"Bad animation data for {name}.") from None

    return {name: resolve(name) for name in nodes}


def slice_right_facing(sheet: Image.Image, anim: PmdAnim) -> Frames:
    rows = sheet.height // anim.height
    top = (PMD_RIGHT_ROW if rows > PMD_RIGHT_ROW else 0) * anim.height
    return [
        (sheet.crop((i * anim.width, top, (i + 1) * anim.width, top + anim.height)), ms)
        for i, ms in enumerate(anim.durations_ms)
    ]


def center_frames(anims: dict[str, Frames]) -> dict[str, Frames]:
    """Pad every frame onto one canvas with frame centres aligned (SpriteCollab anchors frames at their centre)."""
    width = max(img.width for frames in anims.values() for img, _ in frames)
    height = max(img.height for frames in anims.values() for img, _ in frames)
    out = {}
    for key, frames in anims.items():
        out[key] = []
        for img, ms in frames:
            canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            canvas.paste(img, ((width - img.width) // 2, (height - img.height) // 2))
            out[key].append((canvas, ms))
    return out


def crop_to_content(frames: Frames) -> Frames:
    """Crop every frame to the union of their opaque areas so the pet stands on the ground."""
    boxes = [box for box in (img.getchannel("A").getbbox() for img, _ in frames) if box]
    if not boxes:
        return frames
    union = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
    return [(img.crop(union), ms) for img, ms in frames]


def crop_anims(anims: dict[str, Frames]) -> dict[str, Frames]:
    """crop_to_content with one shared box across all animations."""
    keys = list(anims)
    cropped = crop_to_content([frame for key in keys for frame in anims[key]])
    out, start = {}, 0
    for key in keys:
        out[key] = cropped[start : start + len(anims[key])]
        start += len(anims[key])
    return out


def download(
    name: str,
    style: str = "gba",
    fetch_json=fetch_json,
    fetch_bytes=fetch_bytes,
    root: Path | None = None,
    notes: list[str] | None = None,
) -> str:
    """Download and cache a Pokémon's sprite; returns its canonical name. Fallback notes go into `notes`."""
    if style not in STYLES:
        raise SpriteError(f"Unknown sprite style '{style}' (use hgss, gba or ds).")
    name = normalize_name(name)
    if not name:
        raise SpriteError("Please give a Pokémon name.")
    info = lookup(name, fetch_json=fetch_json)
    root = root or cache_dir()
    if style == "hgss":
        anims, faces = _hgss_anims(info, fetch_bytes, root, notes)
    elif style == "gba":
        anims, faces = _gba_anims(info, fetch_bytes, notes)
    else:
        anims, faces = {"walk": _ds_frames(info, fetch_bytes)}, -1
    _write_atomically(root / style, info.name, crop_anims(anims), faces)
    return info.name


def load_cached(name: str, style: str = "gba", root: Path | None = None) -> CachedSprite:
    folder = (root or cache_dir()) / style / normalize_name(name)
    hint = f"No sprites cached for '{name}'. Run: buddy choose {name}"
    try:
        meta = json.loads((folder / "meta.json").read_text())
        faces = 1 if meta["faces"] == 1 else -1
        anims = {key: [(folder / file, int(ms)) for file, ms in entries] for key, entries in meta["anims"].items()}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise SpriteError(hint) from None
    if not anims.get("walk") or not all(path.is_file() for frames in anims.values() for path, _ in frames):
        raise SpriteError(hint)
    anims.setdefault("idle", anims["walk"])
    return CachedSprite(anims=anims, faces=faces)


def _open_image(data: bytes) -> Image.Image:
    try:
        return Image.open(io.BytesIO(data)).convert("RGBA")
    except (OSError, ValueError, SyntaxError) as e:
        raise SpriteError(f"Unreadable sprite sheet ({e}).") from None


def _hgss_anims(info: SpriteInfo, fetch_bytes, root: Path, notes: list[str] | None) -> tuple[dict[str, Frames], int]:
    if info.id <= HGSS_MAX_ID:
        poses = {"walk": ("right", "right/frame2"), "idle": ("down", "down/frame2")}
        timing = {"walk": HGSS_STEP_MS, "idle": HGSS_IDLE_MS}
        pack_path = _hgss_pack(fetch_bytes, root)
        try:
            with tarfile.open(pack_path) as pack:
                anims = {
                    key: [(_read_pack_image(pack, f"pokemon/overworld/{pose}/{info.id}.png"), timing[key]) for pose in pair]
                    for key, pair in poses.items()
                }
            return anims, 1
        except KeyError:
            pass
        except _PACK_ERRORS as e:
            raise SpriteError(f"The HeartGold/SoulSilver sprite pack is unreadable ({e}). Run the command again.") from None
    if notes is not None:
        notes.append(f"No HeartGold/SoulSilver follower sprite for {info.name}; using Mystery Dungeon style instead.")
    return _gba_anims(info, fetch_bytes, notes)


def _hgss_pack(fetch_bytes, root: Path) -> Path:
    """Path to veekun's overworld pack, downloading it once (again if the cached copy is unreadable)."""
    pack = root / HGSS_PACK_FILE
    if pack.exists():
        if _readable_pack(pack):
            return pack
        pack.unlink()
    try:
        data = fetch_bytes(HGSS_PACK_URL)
    except (OSError, http.client.HTTPException) as e:
        raise SpriteError(f"Could not download the HeartGold/SoulSilver sprite pack ({e}).") from None
    root.mkdir(parents=True, exist_ok=True)
    tmp = pack.with_suffix(".part")
    tmp.write_bytes(data)
    if not _readable_pack(tmp):
        tmp.unlink(missing_ok=True)
        raise SpriteError("The HeartGold/SoulSilver sprite pack didn't download correctly. Run the command again.")
    tmp.rename(pack)
    return pack


_PACK_ERRORS = (tarfile.TarError, EOFError, zlib.error, OSError)


def _readable_pack(path: Path) -> bool:
    try:
        with tarfile.open(path) as tar:
            tar.getmembers()
        return True
    except _PACK_ERRORS:
        return False


def _read_pack_image(pack: tarfile.TarFile, member: str) -> Image.Image:
    """Read one PNG straight out of the pack (nothing is extracted to disk). Missing member -> KeyError."""
    file = pack.extractfile(member)
    if file is None:
        raise KeyError(member)
    return _open_image(file.read())


def _gba_anims(info: SpriteInfo, fetch_bytes, notes: list[str] | None) -> tuple[dict[str, Frames], int]:
    base = PMD_BASE.format(id=info.id)
    try:
        data = parse_anim_data(fetch_bytes(base + "AnimData.xml").decode("utf-8"))
        walk, idle = data["Walk"], data.get("Idle")
        wanted = [("walk", walk)] + ([("idle", idle)] if idle and idle != walk else [])
        sheets: dict[str, Image.Image] = {}
        anims = {}
        for key, anim in wanted:
            if anim.sheet not in sheets:
                sheets[anim.sheet] = _open_image(fetch_bytes(base + f"{anim.sheet}-Anim.png"))
            anims[key] = slice_right_facing(sheets[anim.sheet], anim)
        return center_frames(anims), 1
    except (SpriteError, OSError, KeyError, UnicodeDecodeError):
        pass
    url, label = (info.gen3_url, "Emerald") if info.gen3_url else (info.static_url, "still")
    if not url:
        raise SpriteError(f"No sprite available for '{info.name}'.")
    try:
        frames = decode_frames(fetch_bytes(url))
    except OSError as e:
        raise SpriteError(f"Could not download the sprite for '{info.name}' ({e}).") from None
    if notes is not None:
        notes.append(f"No Mystery Dungeon sprite for {info.name}; using its {label} sprite instead.")
    return {"walk": frames[:1]}, -1


def _ds_frames(info: SpriteInfo, fetch_bytes) -> Frames:
    if info.animated_url:
        try:
            return decode_frames(fetch_bytes(info.animated_url))
        except (SpriteError, OSError):
            pass
    if not info.static_url:
        raise SpriteError(f"Could not download a sprite for '{info.name}'.")
    try:
        return decode_frames(fetch_bytes(info.static_url))
    except OSError as e:
        raise SpriteError(f"Could not download the sprite for '{info.name}' ({e}).") from None


def _write_atomically(root: Path, name: str, anims: dict[str, Frames], faces: int) -> None:
    root.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f".{name}-new-", dir=root))
    old = root / f".{name}-old"
    final = root / name
    try:
        meta = {"name": name, "faces": faces, "anims": {}}
        for key, frames in anims.items():
            entries = []
            for i, (img, ms) in enumerate(frames):
                file = f"{key}_{i:03d}.png"
                img.save(tmp / file)
                entries.append([file, ms])
            meta["anims"][key] = entries
        (tmp / "meta.json").write_text(json.dumps(meta))
        shutil.rmtree(old, ignore_errors=True)
        if final.exists():
            final.rename(old)
        tmp.rename(final)
        shutil.rmtree(old, ignore_errors=True)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
