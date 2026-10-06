"""Settings stored in ~/.config/buddy/config.toml."""
import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from buddy import paths


STYLES = ("hgss", "gba", "ds")
GREETINGS = ("wave", "sparkle", "smile", "hand")  # the random hellos buddy knows (smile and hand have no words)


class ConfigError(ValueError):
    """The config file is unreadable or holds invalid values."""


@dataclass
class StressConfig:
    cpu_enter: float = 85.0
    ram_enter: float = 90.0
    cpu_exit: float = 70.0
    ram_exit: float = 85.0
    window_seconds: int = 5


@dataclass
class TalkConfig:
    enabled: bool = True  # time-of-day hellos, random greetings, late-night nudges
    sleep_reminders: int = 2  # bedtime nudges after "are you still building something?"
    greetings: list[str] = field(default_factory=lambda: list(GREETINGS))  # random hellos to use
    greeting_minutes: list[int] = field(default_factory=lambda: [10, 20])  # gap between hellos with words: low, high
    quick_minutes: list[int] = field(default_factory=lambda: [3, 6])  # gap between wordless ones: low, high


@dataclass
class Config:
    pokemon: str = "pikachu"
    style: str = "hgss"
    scale: float = 2.0
    walk_speed: float = 20.0
    stress: StressConfig = field(default_factory=StressConfig)
    talk: TalkConfig = field(default_factory=TalkConfig)


def config_path() -> Path:
    return paths.config_dir() / "config.toml"


def load(path: Path | None = None) -> Config:
    path = Path(path) if path else config_path()
    if not path.exists():
        return Config()
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        stress, talk = data.get("stress", {}), data.get("talk", {})
        for name, table in (("stress", stress), ("talk", talk)):
            if not isinstance(table, dict):
                raise ConfigError(f"[{name}] must be a table")
        d, t = StressConfig(), TalkConfig()
        cfg = Config(
            pokemon=_string(data, "pokemon", Config.pokemon),
            style=_string(data, "style", Config.style),
            scale=_float(data, "scale", Config.scale),
            walk_speed=_float(data, "walk_speed", Config.walk_speed),
            stress=StressConfig(
                cpu_enter=_float(stress, "cpu_enter", d.cpu_enter),
                ram_enter=_float(stress, "ram_enter", d.ram_enter),
                cpu_exit=_float(stress, "cpu_exit", d.cpu_exit),
                ram_exit=_float(stress, "ram_exit", d.ram_exit),
                window_seconds=_int(stress, "window_seconds", d.window_seconds),
            ),
            talk=TalkConfig(
                enabled=_bool(talk, "enabled", t.enabled),
                sleep_reminders=_int(talk, "sleep_reminders", t.sleep_reminders),
                greetings=_names(talk, "greetings", t.greetings),
                greeting_minutes=_ints(talk, "greeting_minutes", t.greeting_minutes),
                quick_minutes=_ints(talk, "quick_minutes", t.quick_minutes),
            ),
        )
        validate(cfg)
    except (tomllib.TOMLDecodeError, UnicodeDecodeError, OSError, ConfigError) as e:
        raise ConfigError(f"{path}: {e}") from None
    return cfg


def salvage(path: Path | None = None) -> Config:
    """Defaults for a broken config file, keeping its pokemon and style when those are valid."""
    cfg = Config()
    path = Path(path) if path else config_path()
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError, OSError):
        return cfg
    pokemon, style = data.get("pokemon"), data.get("style")
    if isinstance(pokemon, str) and pokemon.strip():
        cfg.pokemon = pokemon.strip().lower()
    if isinstance(style, str) and style.strip().lower() in STYLES:
        cfg.style = style.strip().lower()
    return cfg


def save(cfg: Config, path: Path | None = None) -> None:
    validate(cfg)
    path = Path(path) if path else config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    s = cfg.stress
    path.write_text(
        f"pokemon = {json.dumps(cfg.pokemon)}\n"
        f"style = {json.dumps(cfg.style)}  # hgss (HeartGold followers), gba (Mystery Dungeon) or ds (Black/White)\n"
        f"scale = {cfg.scale!r}\n"
        f"walk_speed = {cfg.walk_speed!r}\n"
        "\n[stress]\n"
        f"cpu_enter = {s.cpu_enter!r}\n"
        f"ram_enter = {s.ram_enter!r}\n"
        f"cpu_exit = {s.cpu_exit!r}\n"
        f"ram_exit = {s.ram_exit!r}\n"
        f"window_seconds = {s.window_seconds}\n"
        "\n[talk]\n"
        f"enabled = {'true' if cfg.talk.enabled else 'false'}\n"
        f"sleep_reminders = {cfg.talk.sleep_reminders}  # bedtime nudges after 11 PM\n"
        f"greetings = {json.dumps(cfg.talk.greetings)}  # random hellos: wave, sparkle, smile, hand ([] for none)\n"
        f"greeting_minutes = {json.dumps(cfg.talk.greeting_minutes)}  # minutes between wave/sparkle hellos: low, high\n"
        f"quick_minutes = {json.dumps(cfg.talk.quick_minutes)}  # minutes between the wordless smile/hand: low, high\n",
        encoding="utf-8",
    )


def validate(cfg: Config) -> None:
    if not cfg.pokemon:
        raise ConfigError("pokemon must not be empty")
    if cfg.style not in STYLES:
        raise ConfigError('style must be "hgss", "gba" or "ds"')
    if not 0.5 <= cfg.scale <= 6:
        raise ConfigError("scale must be between 0.5 and 6")
    if not 1 <= cfg.walk_speed <= 500:
        raise ConfigError("walk_speed must be between 1 and 500")
    s = cfg.stress
    for name, enter, exit_ in (("cpu", s.cpu_enter, s.cpu_exit), ("ram", s.ram_enter, s.ram_exit)):
        if not 0 < enter <= 100:
            raise ConfigError(f"{name}_enter must be between 1 and 100")
        if not 0 <= exit_ < enter:
            raise ConfigError(f"{name}_exit must be lower than {name}_enter")
    if not 1 <= s.window_seconds <= 60:
        raise ConfigError("window_seconds must be between 1 and 60")
    if not 0 <= cfg.talk.sleep_reminders <= 10:
        raise ConfigError("sleep_reminders must be between 0 and 10")
    for name in cfg.talk.greetings:
        if name not in GREETINGS:
            raise ConfigError(f"greetings: unknown {name!r} (choose from {', '.join(GREETINGS)})")
    for key in ("greeting_minutes", "quick_minutes"):
        minutes = getattr(cfg.talk, key)
        if len(minutes) != 2 or not 1 <= minutes[0] <= minutes[1] <= 1440:
            raise ConfigError(f"{key} must be [low, high] minutes, 1–1440, low no more than high")


def _string(table: dict, key: str, default: str) -> str:
    value = table.get(key, default)
    if not isinstance(value, str):
        raise ConfigError(f"{key} must be text, got {value!r}")
    return value.strip().lower()


def _bool(table: dict, key: str, default: bool) -> bool:
    value = table.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"{key} must be true or false, got {value!r}")
    return value


def _names(table: dict, key: str, default: list[str]) -> list[str]:
    value = table.get(key, default)
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ConfigError(f"{key} must be a list of names, got {value!r}")
    return [v.strip().lower() for v in value]


def _ints(table: dict, key: str, default: list[int]) -> list[int]:
    value = table.get(key, default)
    if not isinstance(value, list) or not all(isinstance(v, int) and not isinstance(v, bool) for v in value):
        raise ConfigError(f"{key} must be two whole numbers like [20, 40], got {value!r}")
    return list(value)


def _int(table: dict, key: str, default: int) -> int:
    value = table.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{key} must be a whole number, got {value!r}")
    return value


def _float(table: dict, key: str, default: float) -> float:
    value = table.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{key} must be a number, got {value!r}")
    return float(value)
