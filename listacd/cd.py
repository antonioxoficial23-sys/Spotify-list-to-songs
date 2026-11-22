"""Reparto de canciones en discos y preparación de las carpetas para grabar."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

# CD-R de 80 minutos: 79:57 reales. Se deja margen y se cuentan los 2 s de pausa entre pistas.
AUDIO_CD_SECONDS = 79 * 60 + 30
TRACK_GAP_SECONDS = 2
MAX_AUDIO_TRACKS = 99
# CD-R de 700 MB: 359.849 sectores de 2048 bytes. Margen para la tabla de archivos.
DATA_CD_BYTES = 350_000 * 2048
SECTOR = 2048
# Algunas radios de coche no leen más de ~255 archivos por carpeta
MAX_MP3_FILES = 255


@dataclass
class Item:
    index: int  # posición en la lista original (1..N)
    seconds: float
    size: int = 0
    path: Path | None = None
    title: str = ""
    artist: str = ""


@dataclass
class Disc:
    number: int
    items: list[Item] = field(default_factory=list)
    folder: Path | None = None
    cue: Path | None = None

    @property
    def seconds(self) -> float:
        return sum(i.seconds for i in self.items)

    @property
    def size(self) -> int:
        return sum(i.size for i in self.items)


def _audio_cost(item: Item, first: bool) -> float:
    return item.seconds + (0 if first else TRACK_GAP_SECONDS)


def _data_cost(item: Item) -> int:
    return math.ceil(item.size / SECTOR) * SECTOR + SECTOR


def plan(items: list[Item], mode: str) -> list[Disc]:
    """Reparte en orden. mode = 'audio' (por duración) o 'mp3' (por tamaño)."""
    discs: list[Disc] = []
    cur = Disc(1)
    used = 0.0
    for it in items:
        if mode == "audio":
            cost = _audio_cost(it, not cur.items)
            full = used + cost > AUDIO_CD_SECONDS or len(cur.items) >= MAX_AUDIO_TRACKS
        else:
            cost = _data_cost(it)
            full = used + cost > DATA_CD_BYTES or len(cur.items) >= MAX_MP3_FILES
        if full and cur.items:
            discs.append(cur)
            cur = Disc(len(discs) + 1)
            used = 0.0
            cost = _audio_cost(it, True) if mode == "audio" else cost
        cur.items.append(it)
        used += cost
    if cur.items:
        discs.append(cur)
    return discs


def estimate(durations_s: list[float], mode: str) -> list[Disc]:
    """Estimación antes de descargar (MP3 320 kbps = 40.000 bytes/s)."""
    items = [Item(i, d, size=int(d * 40_000) + 60_000) for i, d in enumerate(durations_s, 1)]
    return plan(items, mode)


def fmt_time(seconds: float) -> str:
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _cue_text(s: str) -> str:
    s = s.replace('"', "'").replace("\n", " ").strip()
    # CD-Text: máximo 80 caracteres por campo en la práctica
    return s[:80]


def write_cue(disc: Disc, album: str, path: Path) -> Path:
    """Hoja .cue con CD-Text (títulos y artistas) para ImgBurn u otros programas."""
    lines = [
        'REM Generado por ListaCD',
        f'PERFORMER "{_cue_text("Varios artistas")}"',
        f'TITLE "{_cue_text(album)}"',
    ]
    for n, it in enumerate(disc.items, 1):
        lines += [
            f'FILE "{it.path.name}" WAVE',
            f"  TRACK {n:02d} AUDIO",
            f'    TITLE "{_cue_text(it.title)}"',
            f'    PERFORMER "{_cue_text(it.artist)}"',
        ]
        if n > 1:
            lines.append("    PREGAP 00:02:00")
        lines.append("    INDEX 01 00:00:00")
    path.write_text("\r\n".join(lines) + "\r\n", encoding="cp1252", errors="replace")
    return path
