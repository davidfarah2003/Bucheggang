"""Simulator settings. The only place the team bearer key is read.

The key is read from the `.env` file at the repository root. It is never
printed, logged, or included in an error message.
"""

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[3] / ".env"
REQUEST_TIMEOUT_S = 30.0


class SettingsError(RuntimeError):
    """The runner settings could not be loaded."""


@dataclass(frozen=True)
class Settings:
    base_url: str
    api_key: str = field(repr=False)
    timeout_s: float = REQUEST_TIMEOUT_S


def _parse_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise SettingsError(f"{path} not found; copy .env.example to .env and set TEAM_API_KEY")
    values: dict[str, str] = {}
    for number, raw in enumerate(path.read_text().splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            raise SettingsError(f"{path}:{number} is not KEY=VALUE")
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[key.strip()] = value
    return values


@dataclass(frozen=True)
class OpenRouterSettings:
    api_key: str = field(repr=False)


@lru_cache(maxsize=1)
def load_openrouter() -> OpenRouterSettings:
    """Return only the provider credential; model-off startup never calls this."""
    values = _parse_env(ENV_FILE)
    if not values.get("OPENROUTER_API"):
        raise SettingsError(f"OPENROUTER_API is missing or empty in {ENV_FILE}")
    return OpenRouterSettings(api_key=values["OPENROUTER_API"])


@lru_cache(maxsize=1)
def load() -> Settings:
    values = _parse_env(ENV_FILE)
    for name in ("LEASH_BASE_URL", "TEAM_API_KEY"):
        if not values.get(name):
            raise SettingsError(f"{name} is missing or empty in {ENV_FILE}")
    return Settings(base_url=values["LEASH_BASE_URL"].rstrip("/"), api_key=values["TEAM_API_KEY"])
