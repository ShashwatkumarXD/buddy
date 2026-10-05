import pytest

from buddy import config
from buddy.config import Config, StressConfig, TalkConfig


def test_missing_file_gives_defaults(tmp_path):
    cfg = config.load(tmp_path / "nope.toml")
    assert cfg == Config()
    assert (cfg.pokemon, cfg.style, cfg.scale, cfg.walk_speed) == ("pikachu", "hgss", 2, 20)
    assert cfg.stress == StressConfig(85, 90, 70, 85, 5)
    assert cfg.talk == TalkConfig(enabled=True, sleep_reminders=2)


def test_round_trip(tmp_path):
    cfg = Config(
        pokemon="eevee",
        style="ds",
        scale=3,
        walk_speed=35.5,
        stress=StressConfig(cpu_enter=80, ram_enter=92, cpu_exit=60, ram_exit=80, window_seconds=8),
        talk=TalkConfig(enabled=False, sleep_reminders=4),
    )
    path = tmp_path / "sub" / "config.toml"
    config.save(cfg, path)
    assert config.load(path) == cfg


def test_partial_file_fills_in_defaults(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('pokemon = " Bulbasaur "\n[stress]\ncpu_enter = 95\n')
    cfg = config.load(path)
    assert cfg.pokemon == "bulbasaur"
    assert cfg.stress.cpu_enter == 95
    assert cfg.stress.ram_enter == 90
    assert cfg.scale == 2
    assert cfg.style == "hgss"


def test_fractional_scale_is_allowed(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("scale = 1.25\n")
    assert config.load(path).scale == 1.25


def test_default_path_is_in_the_platform_config_folder():
    from buddy import paths

    assert config.config_path() == paths.config_dir() / "config.toml"


@pytest.mark.parametrize(
    "text, message",
    [
        ("pokemon = \n", "line"),
        ('scale = "big"\n', "scale"),
        ("scale = 0\n", "scale"),
        ("walk_speed = true\n", "walk_speed"),
        ('pokemon = ""\n', "pokemon"),
        ("[stress]\ncpu_exit = 90\n", "cpu_exit"),
        ("[stress]\nram_enter = 150\n", "ram_enter"),
        ("[stress]\nwindow_seconds = 0\n", "window_seconds"),
        ("stress = 3\n", "stress"),
        ('style = "snes"\n', "style"),
        ("talk = 1\n", "talk"),
        ('[talk]\nenabled = "yes"\n', "enabled"),
        ("[talk]\nsleep_reminders = -1\n", "sleep_reminders"),
        ("[talk]\nsleep_reminders = 11\n", "sleep_reminders"),
    ],
)
def test_invalid_config_raises_clear_error(tmp_path, text, message):
    path = tmp_path / "config.toml"
    path.write_text(text)
    with pytest.raises(config.ConfigError, match=message) as err:
        config.load(path)
    assert str(err.value).startswith(str(path))


def test_save_refuses_invalid_config(tmp_path):
    with pytest.raises(config.ConfigError):
        config.save(Config(scale=99), tmp_path / "c.toml")


def test_unreadable_config_is_a_config_error(tmp_path):
    path = tmp_path / "config.toml"
    path.mkdir()  # a directory where the file should be
    with pytest.raises(config.ConfigError):
        config.load(path)


def test_salvage_keeps_valid_pokemon_and_style(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('pokemon = "Eevee"\nstyle = "ds"\nscale = 10\n')
    cfg = config.salvage(path)
    assert (cfg.pokemon, cfg.style, cfg.scale) == ("eevee", "ds", Config().scale)
    path.write_text("not toml at all [")
    assert config.salvage(path) == Config()
