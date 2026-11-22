"""Proceso completo: buscar → descargar original → convertir → repartir en discos."""

from __future__ import annotations

import json
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import cd, spotify
from .config import Settings, cache_dir
from .downloader import (
    car_friendly_cover, download_original, ffmpeg, fetch_image, gain_for, measure_loudness,
    safe_name, tag_mp3, tag_wav, to_cd_wav, to_mp3, wav_duration,
)
from .matcher import Match, Matcher

# Estados que se envían a la interfaz para cada canción
SEARCHING, DOWNLOADING, CONVERTING, DONE, FAILED = (
    "Buscando", "Descargando", "Convirtiendo", "Lista", "Error")


@dataclass
class Event:
    kind: str  # "track" | "log" | "progress"
    index: int = 0
    status: str = ""
    text: str = ""
    done: int = 0
    total: int = 0


@dataclass
class JobResult:
    folder: Path
    mode: str
    discs: list[cd.Disc] = field(default_factory=list)
    failed: list[tuple[int, str, str]] = field(default_factory=list)
    cancelled: bool = False


class Cancelled(Exception):
    pass


class JsonCache:
    """Pequeña caché persistente en JSON, segura entre hilos."""

    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        try:
            self.data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.data = {}

    def get(self, key: str):
        return self.data.get(key)

    def put(self, key: str, value) -> None:
        with self.lock:
            self.data[key] = value
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.path)


def track_key(t: spotify.Track) -> str:
    return t.spotify_id or f"{t.artist}|{t.title}|{int(t.duration_s)}".lower()


def output_folder(col: spotify.Collection, settings: Settings) -> Path:
    sub = "CD Audio" if settings.mode == "audio" else "CD MP3"
    return Path(settings.output_dir).expanduser() / safe_name(col.name, 80) / sub


def _file_stem(n: int, t: spotify.Track, mode: str) -> str:
    stem = f"{n:02d} - {t.artist} - {t.title}"
    if mode == "audio":
        return safe_name(stem, 120, ascii_cd=True)
    # Joliet (el sistema de archivos de los CD de datos) admite 64 caracteres por nombre
    return safe_name(stem, 59)


def run_job(
    col: spotify.Collection,
    settings: Settings,
    on_event: Callable[[Event], None] = lambda e: None,
    cancel: threading.Event | None = None,
    matcher: Matcher | None = None,
    include: set[int] | None = None,
) -> JobResult:
    """Procesa la lista. `include` = posiciones (1..N) a incluir; None = todas."""
    cancel = cancel or threading.Event()
    mode = settings.mode
    ffmpeg()  # falla pronto si no está

    def log(text: str):
        on_event(Event("log", text=text))

    folder = output_folder(col, settings)
    folder.mkdir(parents=True, exist_ok=True)
    work = folder / ".trabajo"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()

    cache = cache_dir()
    matches = JsonCache(cache / "coincidencias.json")
    loudness = JsonCache(cache / "volumen.json")
    matcher = matcher or Matcher()
    covers: dict[int, bytes | None] = {}
    items: dict[int, cd.Item] = {}
    result = JobResult(folder=folder, mode=mode)
    selected = [(i, t) for i, t in enumerate(col.tracks, 1) if include is None or i in include]
    total = len(selected)

    def process(idx: int, t: spotify.Track) -> cd.Item:
        def step(status: str):
            if cancel.is_set():
                raise Cancelled()
            on_event(Event("track", index=idx, status=status))

        step(SEARCHING)
        cached = matches.get(track_key(t))
        m = Match(**cached) if cached else None
        if m is None:
            m = matcher.find(t)
            if m is None:
                raise LookupError("No se encontró en YouTube Music")
            matches.put(track_key(t), m.__dict__)

        step(DOWNLOADING)
        original = download_original(m, cache, settings.cookies_browser)

        step(CONVERTING)
        gain = 0.0
        if settings.normalize:
            loud = loudness.get(m.video_id)
            if loud is None:
                loud = measure_loudness(original)
                if loud is not None:
                    loudness.put(m.video_id, list(loud))
            gain = gain_for(tuple(loud) if loud else None)
        if mode == "audio":
            out = to_cd_wav(original, work / f"{idx:04d}.wav", gain)
            seconds = wav_duration(out)
        else:
            out = to_mp3(original, work / f"{idx:04d}.mp3", gain)
            covers[idx] = car_friendly_cover(fetch_image(t.cover_url or m.thumbnail))
            seconds = t.duration_s or m.duration_s
        return cd.Item(idx, seconds, out.stat().st_size, out, t.title, t.artist)

    log(f"Preparando «{col.name}» ({total} canciones) en {folder}")
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, settings.workers)) as pool:
        futures = {pool.submit(process, i, t): (i, t) for i, t in selected}
        try:
            for fut in as_completed(futures):
                i, t = futures[fut]
                done += 1
                try:
                    items[i] = fut.result()
                    on_event(Event("track", index=i, status=DONE))
                except Cancelled:
                    pass
                except Exception as exc:
                    msg = str(exc).strip().splitlines()[0][:200] if str(exc).strip() else type(exc).__name__
                    result.failed.append((i, f"{t.artist} - {t.title}", msg))
                    on_event(Event("track", index=i, status=FAILED, text=msg))
                    log(f"✗ {t.artist} - {t.title}: {msg}")
                on_event(Event("progress", done=done, total=total))
        finally:
            if cancel.is_set():
                pool.shutdown(cancel_futures=True)

    if cancel.is_set():
        result.cancelled = True
        shutil.rmtree(work, ignore_errors=True)
        log("Cancelado.")
        return result

    # ---- Reparto en discos y carpetas finales
    for old in folder.glob("Disco *"):
        if old.is_dir():
            shutil.rmtree(old, ignore_errors=True)
    (folder / "canciones_no_encontradas.txt").unlink(missing_ok=True)

    ordered = [items[i] for i in sorted(items)]
    result.discs = cd.plan(ordered, mode)
    for disc in result.discs:
        disc.folder = folder / f"Disco {disc.number}"
        disc.folder.mkdir()
        album = col.name if len(result.discs) == 1 else f"{col.name} (Disco {disc.number})"
        for n, it in enumerate(disc.items, 1):
            t = col.tracks[it.index - 1]
            dst = disc.folder / (_file_stem(n, t, mode) + it.path.suffix)
            shutil.move(str(it.path), dst)
            it.path = dst
            if mode == "audio":
                tag_wav(dst, t, n, album)
            else:
                tag_mp3(dst, t, covers.get(it.index), n, t.album or col.name)
                it.size = dst.stat().st_size
        if mode == "audio":
            disc.cue = cd.write_cue(disc, album, disc.folder / f"Disco {disc.number}.cue")
    shutil.rmtree(work, ignore_errors=True)

    if result.failed:
        (folder / "canciones_no_encontradas.txt").write_text(
            "\n".join(f"{i}. {name}  →  {why}" for i, name, why in sorted(result.failed)) + "\n",
            encoding="utf-8",
        )

    unit = "de audio" if mode == "audio" else "MP3"
    log(f"Listo: {len(items)} canciones en {len(result.discs)} CD {unit}. "
        f"{len(result.failed)} no se pudieron conseguir.")
    return result
