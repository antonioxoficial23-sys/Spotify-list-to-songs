"""Historial de discos grabados con ListaCD.

Un CD de audio no guarda los nombres de las canciones. Guardando aquí qué se grabó en cada
disco (y cuánto dura cada pista), ListaCD puede reconocer sus propios CDs al leerlos.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict
from datetime import datetime

from .config import config_dir
from .spotify import Track

_LOCK = threading.Lock()
MAX_ENTRIES = 500
# En un CD grabado pista a pista, la duración que ve Windows incluye los 2 s de pausa
# que hay antes de la pista siguiente, y se redondea a sectores.
TOLERANCE_S = 4.0


def _path():
    return config_dir() / "discos_grabados.json"


def load() -> list[dict]:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def record(name: str, mode: str, disc_number: int, tracks: list[Track], seconds: list[float]) -> None:
    """Apunta un disco recién grabado. `seconds` = duración real de cada pista en el disco."""
    entry = {
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "name": name if disc_number == 1 else f"{name} (Disco {disc_number})",
        "mode": mode,
        "seconds": [round(s, 2) for s in seconds],
        "tracks": [{k: v for k, v in asdict(t).items() if k != "unknown"} for t in tracks],
    }
    with _LOCK:
        items = load()
        items.append(entry)
        try:
            _path().write_text(json.dumps(items[-MAX_ENTRIES:], ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass  # el historial es una ayuda, no debe impedir grabar


def match_audio(disc_seconds: list[float]) -> dict | None:
    """El disco grabado más reciente con las mismas pistas y duraciones (o None)."""
    if not disc_seconds:
        return None
    for entry in reversed(load()):
        burned = entry.get("seconds") or []
        if entry.get("mode") != "audio" or len(burned) != len(disc_seconds):
            continue
        if all(abs(d - b) <= TOLERANCE_S for d, b in zip(disc_seconds, burned)):
            return entry
    return None


def track_from_dict(d: dict) -> Track:
    fields = Track.__dataclass_fields__
    return Track(**{k: v for k, v in d.items() if k in fields})
