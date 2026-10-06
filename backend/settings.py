import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class ConfigurationError(RuntimeError):
    pass


def required_setting(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigurationError(f"Falta configurar la variable de entorno {name}.")
    return value


def optional_setting(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()
