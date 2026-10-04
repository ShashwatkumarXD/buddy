import io
import urllib.error

import pytest
from PIL import Image

from buddy import sprites

ANIMATED = "https://example.test/25.gif"
STATIC = "https://example.test/25.png"


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
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def api_json(animated=ANIMATED, static=STATIC, name="pikachu"):
    return {
        "id": 25,
        "name": name,
        "sprites": {
            "front_default": static,
            "versions": {"generation-v": {"black-white": {"animated": {"front_default": animated}}}},
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


def http_404(url):
    raise urllib.error.HTTPError(url, 404, "Not Found", None, None)


def offline(url):
    raise urllib.error.URLError("no network")


def test_normalize_name():
    assert sprites.normalize_name("  Mr Mime ") == "mr-mime"


def test_cache_dir_respects_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert sprites.cache_dir() == tmp_path / "buddy" / "sprites"


def test_lookup_reads_animated_and_static_urls():
    info = sprites.lookup("pikachu", fetch_json=fetch_json_returning(api_json()))
    assert info == sprites.SpriteInfo("pikachu", 25, ANIMATED, STATIC)


def test_lookup_unknown_name():
    with pytest.raises(sprites.SpriteError, match="No Pokémon called 'pikachuu'"):
        sprites.lookup("pikachuu", fetch_json=http_404)


def test_lookup_offline():
    with pytest.raises(sprites.SpriteError, match="Could not reach PokéAPI"):
        sprites.lookup("pikachu", fetch_json=offline)


def test_download_splits_animated_gif_and_crops(tmp_path):
    name = sprites.download(
        "Pikachu",
        fetch_json=fetch_json_returning(api_json()),
        fetch_bytes=fetch_bytes_from({ANIMATED: gif_bytes()}),
        root=tmp_path,
    )
    assert name == "pikachu"
    frames = sprites.load_cached("pikachu", root=tmp_path)
    assert [ms for _, ms in frames] == [80, 120]
    assert all(Image.open(path).size == (8, 6) for path, _ in frames)


def test_download_falls_back_to_static_png(tmp_path):
    sprites.download(
        "kyurem",
        fetch_json=fetch_json_returning(api_json(animated=None, name="kyurem")),
        fetch_bytes=fetch_bytes_from({STATIC: png_bytes()}),
        root=tmp_path,
    )
    frames = sprites.load_cached("kyurem", root=tmp_path)
    assert len(frames) == 1
    assert Image.open(frames[0][0]).size == (30, 50)


def test_broken_gif_falls_back_to_static_png(tmp_path):
    sprites.download(
        "pikachu",
        fetch_json=fetch_json_returning(api_json()),
        fetch_bytes=fetch_bytes_from({ANIMATED: b"not a gif", STATIC: png_bytes()}),
        root=tmp_path,
    )
    assert len(sprites.load_cached("pikachu", root=tmp_path)) == 1


def test_failed_download_keeps_previous_cache(tmp_path):
    good = fetch_bytes_from({ANIMATED: gif_bytes()})
    sprites.download("pikachu", fetch_json=fetch_json_returning(api_json()), fetch_bytes=good, root=tmp_path)
    dropped = urllib.error.URLError("connection dropped")
    broken = fetch_bytes_from({ANIMATED: dropped, STATIC: dropped})
    with pytest.raises(sprites.SpriteError):
        sprites.download("pikachu", fetch_json=fetch_json_returning(api_json()), fetch_bytes=broken, root=tmp_path)
    assert len(sprites.load_cached("pikachu", root=tmp_path)) == 2


def test_empty_name_is_rejected(tmp_path):
    with pytest.raises(sprites.SpriteError, match="name"):
        sprites.download("   ", fetch_json=offline, fetch_bytes=offline, root=tmp_path)


def test_load_cached_missing_gives_hint(tmp_path):
    with pytest.raises(sprites.SpriteError, match="buddy choose eevee"):
        sprites.load_cached("eevee", root=tmp_path)
