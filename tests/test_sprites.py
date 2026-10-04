import io
import tarfile
import urllib.error

import pytest
from PIL import Image

from buddy import sprites

ANIMATED = "https://example.test/25.gif"
STATIC = "https://example.test/25.png"
GEN3 = "https://example.test/gen3/25.png"
PMD = "https://raw.githubusercontent.com/PMDCollab/SpriteCollab/master/sprite/0025/"

ANIM_XML = """<?xml version="1.0"?>
<AnimData><Anims>
  <Anim><Name>Walk</Name><FrameWidth>10</FrameWidth><FrameHeight>12</FrameHeight>
    <Durations><Duration>6</Duration><Duration>12</Duration></Durations></Anim>
  <Anim><Name>Idle</Name><FrameWidth>14</FrameWidth><FrameHeight>16</FrameHeight>
    <Durations><Duration>30</Duration><Duration>30</Duration><Duration>30</Duration></Durations></Anim>
  <Anim><Name>Sleep</Name><CopyOf>Idle</CopyOf></Anim>
</Anims></AnimData>"""


def png(im):
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def gif_bytes():
    """Two 20x20 frames with an opaque 4x4 square in different places."""
    frames = []
    for x, y in [(4, 10), (8, 12)]:
        im = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
        im.paste((255, 0, 0, 255), (x, y, x + 4, y + 4))
        frames.append(im)
    buf = io.BytesIO()
    frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:], duration=[80, 120], loop=0, disposal=2)
    return buf.getvalue()


def png_bytes():
    im = Image.new("RGBA", (96, 96), (0, 0, 0, 0))
    im.paste((0, 0, 255, 255), (30, 40, 60, 90))
    return png(im)


def pmd_sheet(fw, fh, cols, rows=8, right_row=2):
    """A 2x2 marker at every frame's centre; green on the right-facing row, red elsewhere."""
    im = Image.new("RGBA", (fw * cols, fh * rows), (0, 0, 0, 0))
    for r in range(rows):
        color = (0, 255, 0, 255) if r == right_row else (255, 0, 0, 255)
        for c in range(cols):
            cx, cy = c * fw + fw // 2, r * fh + fh // 2
            im.paste(color, (cx - 1, cy - 1, cx + 1, cy + 1))
    return png(im)


def api_json(animated=ANIMATED, static=STATIC, gen3=None, name="pikachu", id=25):
    return {
        "id": id,
        "name": name,
        "sprites": {
            "front_default": static,
            "versions": {
                "generation-iii": {"emerald": {"front_default": gen3}},
                "generation-v": {"black-white": {"animated": {"front_default": animated}}},
            },
        },
    }


def fetch_json_returning(payload):
    return lambda url: payload


def fetch_bytes_from(mapping):
    def fetch(url):
        value = mapping[url]
        if isinstance(value, Exception):
            raise value
        return value

    return fetch


def gba_fetch(base=PMD, **overrides):
    mapping = {
        base + "AnimData.xml": ANIM_XML.encode(),
        base + "Walk-Anim.png": pmd_sheet(10, 12, 2),
        base + "Idle-Anim.png": pmd_sheet(14, 16, 3),
        GEN3: png_bytes(),
    }
    mapping.update(overrides)
    return fetch_bytes_from(mapping)


def http_404(url):
    raise urllib.error.HTTPError(url, 404, "Not Found", None, None)


def offline(url):
    raise urllib.error.URLError("no network")


def test_normalize_name():
    assert sprites.normalize_name("  Mr Mime ") == "mr-mime"


def test_cache_dir_respects_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert sprites.cache_dir() == tmp_path / "buddy" / "sprites"


def test_lookup_reads_sprite_urls():
    info = sprites.lookup("pikachu", fetch_json=fetch_json_returning(api_json(gen3=GEN3)))
    assert info == sprites.SpriteInfo("pikachu", 25, ANIMATED, STATIC, GEN3)


def test_lookup_unknown_name():
    with pytest.raises(sprites.SpriteError, match="No Pokémon called 'pikachuu'"):
        sprites.lookup("pikachuu", fetch_json=http_404)


def test_lookup_offline():
    with pytest.raises(sprites.SpriteError, match="Could not reach PokéAPI"):
        sprites.lookup("pikachu", fetch_json=offline)


def test_parse_anim_data_resolves_copies_and_converts_to_ms():
    anims = sprites.parse_anim_data(ANIM_XML)
    assert anims["Walk"] == sprites.PmdAnim("Walk", 10, 12, [100, 200])
    assert anims["Sleep"] == sprites.PmdAnim("Idle", 14, 16, [500, 500, 500])


def test_parse_anim_data_rejects_garbage():
    with pytest.raises(sprites.SpriteError):
        sprites.parse_anim_data("<AnimData><oops>")


def test_gba_uses_mystery_dungeon_walk_and_idle(tmp_path):
    name = sprites.download(
        "Pikachu", style="gba", fetch_json=fetch_json_returning(api_json()), fetch_bytes=gba_fetch(), root=tmp_path
    )
    assert name == "pikachu"
    cached = sprites.load_cached("pikachu", style="gba", root=tmp_path)
    assert cached.faces == 1
    assert [ms for _, ms in cached.anims["walk"]] == [100, 200]
    assert [ms for _, ms in cached.anims["idle"]] == [500, 500, 500]
    sizes = {Image.open(path).size for frames in cached.anims.values() for path, _ in frames}
    assert sizes == {(2, 2)}  # walk and idle frames share one centre anchor
    walk = Image.open(cached.anims["walk"][0][0]).convert("RGBA")
    assert walk.getpixel((0, 0)) == (0, 255, 0, 255)  # taken from the right-facing row


def test_gba_without_idle_animation_reuses_walk(tmp_path):
    xml = ANIM_XML.replace("<Name>Idle</Name>", "<Name>Hop</Name>").replace("<CopyOf>Idle</CopyOf>", "<CopyOf>Hop</CopyOf>")
    sprites.download(
        "pikachu",
        style="gba",
        fetch_json=fetch_json_returning(api_json()),
        fetch_bytes=gba_fetch(**{PMD + "AnimData.xml": xml.encode()}),
        root=tmp_path,
    )
    cached = sprites.load_cached("pikachu", style="gba", root=tmp_path)
    assert cached.anims["idle"] == cached.anims["walk"]


def test_gba_falls_back_to_emerald_sprite(tmp_path):
    notes = []
    missing = urllib.error.HTTPError(PMD, 404, "Not Found", None, None)
    sprites.download(
        "pikachu",
        style="gba",
        fetch_json=fetch_json_returning(api_json(gen3=GEN3)),
        fetch_bytes=gba_fetch(**{PMD + "AnimData.xml": missing}),
        root=tmp_path,
        notes=notes,
    )
    cached = sprites.load_cached("pikachu", style="gba", root=tmp_path)
    assert cached.faces == -1
    assert len(cached.anims["walk"]) == 1
    assert cached.anims["idle"] == cached.anims["walk"]
    assert "Emerald" in notes[0]


def test_ds_splits_animated_gif_and_crops(tmp_path):
    sprites.download(
        "pikachu",
        style="ds",
        fetch_json=fetch_json_returning(api_json()),
        fetch_bytes=fetch_bytes_from({ANIMATED: gif_bytes()}),
        root=tmp_path,
    )
    cached = sprites.load_cached("pikachu", style="ds", root=tmp_path)
    assert cached.faces == -1
    assert [ms for _, ms in cached.anims["walk"]] == [80, 120]
    assert all(Image.open(path).size == (8, 6) for path, _ in cached.anims["walk"])


def test_ds_falls_back_to_static_png(tmp_path):
    sprites.download(
        "kyurem",
        style="ds",
        fetch_json=fetch_json_returning(api_json(animated=None, name="kyurem")),
        fetch_bytes=fetch_bytes_from({STATIC: png_bytes()}),
        root=tmp_path,
    )
    frames = sprites.load_cached("kyurem", style="ds", root=tmp_path).anims["walk"]
    assert len(frames) == 1
    assert Image.open(frames[0][0]).size == (30, 50)


def test_ds_broken_gif_falls_back_to_static_png(tmp_path):
    sprites.download(
        "pikachu",
        style="ds",
        fetch_json=fetch_json_returning(api_json()),
        fetch_bytes=fetch_bytes_from({ANIMATED: b"not a gif", STATIC: png_bytes()}),
        root=tmp_path,
    )
    assert len(sprites.load_cached("pikachu", style="ds", root=tmp_path).anims["walk"]) == 1


def test_styles_are_cached_separately(tmp_path):
    sprites.download("pikachu", style="gba", fetch_json=fetch_json_returning(api_json()), fetch_bytes=gba_fetch(), root=tmp_path)
    with pytest.raises(sprites.SpriteError):
        sprites.load_cached("pikachu", style="ds", root=tmp_path)
    assert sprites.load_cached("pikachu", style="gba", root=tmp_path).faces == 1


def test_unknown_style_is_rejected(tmp_path):
    with pytest.raises(sprites.SpriteError, match="style"):
        sprites.download("pikachu", style="snes", fetch_json=offline, fetch_bytes=offline, root=tmp_path)


def test_failed_download_keeps_previous_cache(tmp_path):
    good = fetch_bytes_from({ANIMATED: gif_bytes()})
    sprites.download("pikachu", style="ds", fetch_json=fetch_json_returning(api_json()), fetch_bytes=good, root=tmp_path)
    dropped = urllib.error.URLError("connection dropped")
    broken = fetch_bytes_from({ANIMATED: dropped, STATIC: dropped})
    with pytest.raises(sprites.SpriteError):
        sprites.download("pikachu", style="ds", fetch_json=fetch_json_returning(api_json()), fetch_bytes=broken, root=tmp_path)
    assert len(sprites.load_cached("pikachu", style="ds", root=tmp_path).anims["walk"]) == 2


def test_empty_name_is_rejected(tmp_path):
    with pytest.raises(sprites.SpriteError, match="name"):
        sprites.download("   ", fetch_json=offline, fetch_bytes=offline, root=tmp_path)


def test_load_cached_missing_gives_hint(tmp_path):
    with pytest.raises(sprites.SpriteError, match="buddy choose eevee"):
        sprites.load_cached("eevee", root=tmp_path)


def test_parse_anim_data_refuses_entity_declarations():
    bomb = '<?xml version="1.0"?><!DOCTYPE a [<!ENTITY x "xxxxxxxx"><!ENTITY y "&x;&x;&x;&x;">]><AnimData>&y;</AnimData>'
    with pytest.raises(sprites.SpriteError, match="DTD"):
        sprites.parse_anim_data(bomb)


def hgss_pack(ids=(25,)):
    """A tiny stand-in for veekun's overworld.tar.gz: 32x32 frames, one coloured dot per pose."""
    colors = {"right": (0, 0, 255), "right/frame2": (0, 0, 200), "down": (0, 255, 0), "down/frame2": (0, 200, 0)}
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for id in ids:
            for pose, rgb in colors.items():
                im = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
                im.paste(rgb + (255,), (10, 12, 22, 30))
                data = png(im)
                info = tarfile.TarInfo(f"pokemon/overworld/{pose}/{id}.png")
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class CountingFetch:
    def __init__(self, mapping):
        self.mapping = mapping
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        value = self.mapping[url]
        if isinstance(value, Exception):
            raise value
        return value


def test_hgss_walks_with_follower_step_and_faces_you_when_idle(tmp_path):
    fetch = CountingFetch({sprites.HGSS_PACK_URL: hgss_pack()})
    sprites.download("pikachu", style="hgss", fetch_json=fetch_json_returning(api_json()), fetch_bytes=fetch, root=tmp_path)
    cached = sprites.load_cached("pikachu", style="hgss", root=tmp_path)
    assert cached.faces == 1
    assert [ms for _, ms in cached.anims["walk"]] == [sprites.HGSS_STEP_MS] * 2
    assert [ms for _, ms in cached.anims["idle"]] == [sprites.HGSS_IDLE_MS] * 2
    walk = Image.open(cached.anims["walk"][0][0]).convert("RGBA")
    idle = Image.open(cached.anims["idle"][0][0]).convert("RGBA")
    assert walk.size == idle.size == (12, 18)
    assert walk.getpixel((0, 0)) == (0, 0, 255, 255)  # side view, facing right
    assert idle.getpixel((0, 0)) == (0, 255, 0, 255)  # front view


def test_hgss_pack_is_downloaded_once(tmp_path):
    fetch = CountingFetch({sprites.HGSS_PACK_URL: hgss_pack(ids=(25, 133))})
    sprites.download("pikachu", style="hgss", fetch_json=fetch_json_returning(api_json()), fetch_bytes=fetch, root=tmp_path)
    sprites.download(
        "eevee", style="hgss", fetch_json=fetch_json_returning(api_json(name="eevee", id=133)), fetch_bytes=fetch, root=tmp_path
    )
    assert fetch.calls.count(sprites.HGSS_PACK_URL) == 1
    assert sprites.load_cached("eevee", style="hgss", root=tmp_path).faces == 1


def test_corrupt_hgss_pack_is_downloaded_again(tmp_path):
    (tmp_path / sprites.HGSS_PACK_FILE).write_bytes(b"half a download")
    fetch = CountingFetch({sprites.HGSS_PACK_URL: hgss_pack()})
    sprites.download("pikachu", style="hgss", fetch_json=fetch_json_returning(api_json()), fetch_bytes=fetch, root=tmp_path)
    assert fetch.calls.count(sprites.HGSS_PACK_URL) == 1
    assert len(sprites.load_cached("pikachu", style="hgss", root=tmp_path).anims["walk"]) == 2


def test_hgss_after_gen4_falls_back_to_mystery_dungeon(tmp_path):
    notes = []
    base = sprites.PMD_BASE.format(id=494)
    fetch = gba_fetch(base=base, **{sprites.HGSS_PACK_URL: hgss_pack()})
    sprites.download(
        "victini",
        style="hgss",
        fetch_json=fetch_json_returning(api_json(name="victini", id=494)),
        fetch_bytes=fetch,
        root=tmp_path,
        notes=notes,
    )
    cached = sprites.load_cached("victini", style="hgss", root=tmp_path)
    assert [ms for _, ms in cached.anims["walk"]] == [100, 200]  # the Mystery Dungeon walk
    assert "Mystery Dungeon" in notes[0]


def test_hgss_pokemon_missing_from_pack_falls_back_to_mystery_dungeon(tmp_path):
    notes = []
    fetch = gba_fetch(**{sprites.HGSS_PACK_URL: hgss_pack(ids=(1,))})
    sprites.download(
        "pikachu", style="hgss", fetch_json=fetch_json_returning(api_json()), fetch_bytes=fetch, root=tmp_path, notes=notes
    )
    assert [ms for _, ms in sprites.load_cached("pikachu", style="hgss", root=tmp_path).anims["walk"]] == [100, 200]
    assert "Mystery Dungeon" in notes[0]
