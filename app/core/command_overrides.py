"""Permite sobrescrever, sem precisar mexer em código nem gerar um .exe novo, os
comandos GPIB do UCS 500N — já que o dicionário de comandos real do fabricante
não é público. O operador descobre os comandos certos testando no Terminal GPIB
(Configurações) e salva aqui; o driver passa a usar esses valores de verdade."""

import json

from app.config import DATA_DIR

OVERRIDES_PATH = DATA_DIR / "ucs500n_commands_override.json"


def load_overrides() -> dict:
    if not OVERRIDES_PATH.exists():
        return {}
    try:
        with open(OVERRIDES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_overrides(overrides: dict) -> None:
    with open(OVERRIDES_PATH, "w", encoding="utf-8") as f:
        json.dump(overrides, f, indent=2, ensure_ascii=False)
