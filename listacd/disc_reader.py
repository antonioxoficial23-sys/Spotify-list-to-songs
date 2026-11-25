"""Lectura de un CD para saber qué música tiene.

* CD de MP3 (de datos): se leen los archivos y sus etiquetas.
* CD de audio: un CD de audio no guarda los nombres de las canciones, solo las pistas y su
  duración (Windows las muestra como «Pista01.cda»). Se identifican:
    1. con el historial de discos que ha grabado ListaCD (misma cantidad y duración de pistas);
    2. si no, con MusicBrainz, la base de datos libre de CDs, a partir de esas duraciones.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field
from pathlib import Path

import requests

from . import history
from .spotify import Track

AUDIO_EXTS = {".mp3", ".wma", ".m4a", ".aac", ".ogg", ".opus", ".flac", ".wav"}
SECTORS_PER_SECOND = 75
MB_URL = "https://musicbrainz.org/ws/2/discid/-"
USER_AGENT = "ListaCD/3.5"


def default_name() -> str:
    """Nombre con fecha y hora: cada CD leído tiene su propia carpeta (no se pisan entre sí)."""
    from datetime import datetime

    return datetime.now().strftime("CD leído el %d-%m-%Y, %H.%M")


@dataclass
class DiscContents:
    kind: str  # "audio" | "mp3" | "vacio"
    name: str = ""
    tracks: list[Track] = field(default_factory=list)
    source: str = ""  # "historial" | "musicbrainz" | "etiquetas" | "sin datos"
    unknown: int = 0  # pistas de las que no se sabe qué canción son
    seconds: float = 0.0

    @property
    def summary(self) -> str:
        if self.kind == "vacio":
            return "El disco está vacío o no tiene música."
        kind = "CD de audio" if self.kind == "audio" else "CD de MP3"
        how = {
            "historial": "Lo grabó ListaCD: las canciones salen de su historial.",
            "musicbrainz": "Canciones identificadas con MusicBrainz por la duración de sus pistas.",
            "etiquetas": "Canciones leídas de los archivos del disco.",
            "sin datos": "Es un CD de audio sin nombres y no se ha podido identificar.",
        }[self.source]
        return f"{kind} con {len(self.tracks)} pistas. {how}"


# --------------------------------------------------------------------- CD de audio


def read_cda(path: Path) -> tuple[int, int, int]:
    """(número de pista, sector de inicio, longitud en sectores) de un archivo .cda de Windows."""
    data = path.read_bytes()[:44]
    if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"CDDA":
        raise ValueError(f"{path.name} no es una pista de CD de audio")
    track = struct.unpack_from("<H", data, 22)[0]
    start, length = struct.unpack_from("<II", data, 28)
    return track, start, length


def _audio_toc(root: Path) -> list[tuple[int, int, int]]:
    toc = []
    for p in root.iterdir():
        if p.suffix.lower() == ".cda":
            try:
                toc.append(read_cda(p))
            except (OSError, ValueError, struct.error):
                continue
    return sorted(toc)


def musicbrainz_lookup(toc: list[tuple[int, int, int]], timeout: float = 15) -> tuple[str, list[Track]] | None:
    """Búsqueda aproximada por duraciones (no requiere calcular el Disc ID)."""
    if not toc:
        return None
    first, last = toc[0][0], toc[-1][0]
    leadout = toc[-1][1] + toc[-1][2] + 150
    offsets = " ".join(str(start + 150) for _, start, _ in toc)
    r = requests.get(MB_URL, params={"toc": f"{first} {last} {leadout} {offsets}",
                                     "inc": "recordings artist-credits", "fmt": "json"},
                     headers={"User-Agent": USER_AGENT}, timeout=timeout)
    if r.status_code != 200:
        return None
    for release in r.json().get("releases", []):
        for medium in release.get("media", []):
            pistas = medium.get("tracks") or []
            if len(pistas) != len(toc):
                continue
            artist_rel = "".join(c.get("name", "") + c.get("joinphrase", "")
                                 for c in release.get("artist-credit", []))
            tracks = []
            for t in pistas:
                credit = t.get("artist-credit") or release.get("artist-credit") or []
                artists = [c.get("name", "") for c in credit if c.get("name")] or [artist_rel]
                tracks.append(Track(title=t.get("title", ""), artists=artists,
                                    duration_ms=int(t.get("length") or 0), album=release.get("title", ""),
                                    album_artist=artist_rel))
            return release.get("title", ""), tracks
    return None


def _read_audio(root: Path, lookup: bool) -> DiscContents:
    toc = _audio_toc(root)
    seconds = [length / SECTORS_PER_SECOND for _, _, length in toc]
    disc = DiscContents(kind="audio", seconds=sum(seconds))
    entry = history.match_audio(seconds)
    if entry:
        disc.name, disc.source = entry["name"], "historial"
        disc.tracks = [history.track_from_dict(t) for t in entry["tracks"]]
        return disc
    if lookup:
        try:
            found = musicbrainz_lookup(toc)
        except (requests.RequestException, ValueError):
            found = None
        if found:
            disc.name, disc.tracks = found
            disc.source = "musicbrainz"
            return disc
    disc.name, disc.source = default_name(), "sin datos"
    disc.tracks = [Track(title=f"Pista {n}", artists=[], duration_ms=int(s * 1000), unknown=True)
                   for (n, _, _), s in zip(toc, seconds)]
    disc.unknown = len(disc.tracks)
    return disc


# ----------------------------------------------------------------------- CD de MP3

FILENAME_RE = re.compile(r"^\s*\d{1,3}\s*[-._ ]\s*(?P<artist>.+?)\s+-\s+(?P<title>.+)$")


def _track_from_file(path: Path) -> Track:
    title = artist = ""
    seconds = 0.0
    try:
        from mutagen import File

        f = File(path, easy=True)
        if f is not None:
            title = (f.get("title") or [""])[0]
            artist = (f.get("artist") or [""])[0]
            seconds = float(getattr(f.info, "length", 0) or 0)
    except Exception:
        pass
    if not title:  # «03 - Artista - Título.mp3», como los nombra ListaCD
        m = FILENAME_RE.match(path.stem)
        title, artist = (m.group("title"), m.group("artist")) if m else (path.stem, artist)
    artists = [a.strip() for a in re.split(r",|/|;", artist) if a.strip()]
    return Track(title=title.strip(), artists=artists, duration_ms=int(seconds * 1000))


def _read_mp3(files: list[Path], label: str) -> DiscContents:
    tracks = [_track_from_file(p) for p in files]
    return DiscContents(kind="mp3", name=label or default_name(), tracks=tracks, source="etiquetas",
                        seconds=sum(t.duration_s for t in tracks))


# --------------------------------------------------------------------------- todo


def read_disc(root: Path, label: str = "", lookup: bool = True) -> DiscContents:
    """Lee el disco montado en `root` (p. ej. Path("E:/"))."""
    try:
        entries = list(root.iterdir())
    except OSError:
        return DiscContents(kind="vacio")
    if any(p.suffix.lower() == ".cda" for p in entries):
        return _read_audio(root, lookup)
    files = sorted((p for p in root.rglob("*") if p.suffix.lower() in AUDIO_EXTS and p.is_file()),
                   key=lambda p: [s.lower() for s in p.relative_to(root).parts])
    if files:
        return _read_mp3(files, label)
    return DiscContents(kind="vacio")
