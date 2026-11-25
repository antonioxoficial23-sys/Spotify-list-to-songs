"""Proceso completo: buscar → descargar original → convertir → repartir en discos."""

from __future__ import annotations

import json
import os
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import cd, spotify
from .config import Settings, cache_dir
from .downloader import (
    DownloadFailed, car_friendly_cover, download_original, ffmpeg, fetch_image, gain_for, measure_loudness,
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


class FolderBusy(RuntimeError):
    """Una carpeta de disco anterior no se puede sustituir porque hay archivos abiertos."""


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
            try:
                tmp = self.path.with_suffix(".tmp")
                tmp.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
                tmp.replace(self.path)
            except OSError:
                pass  # p. ej. el antivirus tiene el archivo abierto: se sigue sin guardar la caché


def track_key(t: spotify.Track) -> str:
    return t.spotify_id or f"{t.artist}|{t.title}|{int(t.duration_s)}".lower()


MANIFEST = ".convertidas.json"


def _out_key(video_id: str, mode: str, gain: float) -> str:
    """Identifica un archivo ya convertido: misma fuente, mismo formato y mismo volumen."""
    return f"{video_id}|{mode}|{gain:.2f}"


def _load_reusable(folder: Path) -> dict[str, Path]:
    try:
        data = json.loads((folder / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    for key, rel in data.items():
        p = folder / rel
        if p.is_file() and p.stat().st_size > 0:
            out[key] = p
    return out


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
    work.mkdir(exist_ok=True)

    cache = cache_dir()
    matches = JsonCache(cache / "coincidencias.json")
    loudness = JsonCache(cache / "volumen.json")
    matcher = matcher or Matcher()
    covers: dict[int, bytes | None] = {}
    keys: dict[int, str] = {}
    reusable = _load_reusable(folder)
    claimed: set[str] = set()
    claim_lock = threading.Lock()
    # La red admite muchas descargas a la vez; ffmpeg usa un núcleo por conversión
    cpu = threading.Semaphore(max(2, os.cpu_count() or 2))
    video_locks: dict[str, threading.Lock] = {}

    def video_lock(video_id: str) -> threading.Lock:
        with claim_lock:
            return video_locks.setdefault(video_id, threading.Lock())

    def download(match: Match) -> Path:
        # Dos canciones de la lista pueden apuntar al mismo vídeo: se descarga una sola vez
        with video_lock(match.video_id):
            return download_original(match, cache, settings.cookies_browser)
    items: dict[int, cd.Item] = {}
    result = JobResult(folder=folder, mode=mode)
    selected = [(i, t) for i, t in enumerate(col.tracks, 1) if include is None or i in include]
    total = len(selected)

    def process(idx: int, t: spotify.Track) -> cd.Item:
        def step(status: str):
            if cancel.is_set():
                raise Cancelled()
            on_event(Event("track", index=idx, status=status))

        if t.unknown:
            raise LookupError("Pista de un CD sin identificar: no se sabe qué canción es.")
        if mode == "audio" and t.duration_s > cd.AUDIO_CD_SECONDS:
            raise ValueError(f"Dura {cd.fmt_time(t.duration_s)} y no cabe en un CD de audio (80 min). "
                             "Quítala o usa el modo CD MP3.")
        step(SEARCHING)
        cached = matches.get(track_key(t))
        m = Match(**cached) if cached else None
        if m is None:
            m = matcher.find(t)
            if m is None:
                raise LookupError("No está en YouTube Music. Quítala o busca otra versión en Spotify.")
            matches.put(track_key(t), m.__dict__)

        def gain_of(loud) -> float:
            return gain_for(tuple(loud) if loud else None) if settings.normalize else 0.0

        # ¿Ya se convirtió en una ejecución anterior (p. ej. antes de «Reintentar»)? Se reutiliza.
        known = loudness.get(m.video_id)
        if not settings.normalize or known is not None:
            key = _out_key(m.video_id, mode, gain_of(known))
            with claim_lock:
                old = reusable.get(key) if key not in claimed else None
                if old is not None:
                    claimed.add(key)
            if old is not None:
                keys[idx] = key
                if mode == "audio":
                    seconds = wav_duration(old)
                else:
                    covers[idx] = car_friendly_cover(fetch_image(t.cover_url or m.thumbnail))
                    seconds = t.duration_s or m.duration_s
                return cd.Item(idx, seconds, old.stat().st_size, old, t.title, t.artist)

        step(DOWNLOADING)
        try:
            original = download(m)
        except DownloadFailed as first:
            # Otra versión de la misma canción (p. ej. la del vídeo oficial) suele descargarse bien
            for alt in [c for c in matcher.ranked(t) if c.video_id != m.video_id][:3]:
                if cancel.is_set():
                    raise Cancelled()
                try:
                    original = download(alt)
                    m = alt
                    matches.put(track_key(t), m.__dict__)
                    break
                except DownloadFailed:
                    continue
            else:
                raise first

        step(CONVERTING)
        with cpu:
            if cancel.is_set():
                raise Cancelled()
            loud = loudness.get(m.video_id) if settings.normalize else None
            if settings.normalize and loud is None:
                loud = measure_loudness(original)
                if loud is not None:
                    loudness.put(m.video_id, list(loud))
            gain = gain_of(loud)
            keys[idx] = _out_key(m.video_id, mode, gain)
            if mode == "audio":
                out = to_cd_wav(original, work / f"{idx:04d}.wav", gain)
                seconds = wav_duration(out)
                if seconds > cd.AUDIO_CD_SECONDS:
                    out.unlink(missing_ok=True)
                    raise ValueError(f"La versión de YouTube dura {cd.fmt_time(seconds)} y no cabe en un CD "
                                     "de audio. Quítala o usa el modo CD MP3.")
            else:
                out = to_mp3(original, work / f"{idx:04d}.mp3", gain)
        if mode == "mp3":
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

    # ---- Reparto en discos.
    # 1) Se apartan las carpetas «Disco N» anteriores a .viejo. En Windows renombrar falla si hay
    #    algún archivo abierto: en ese caso se deshace y se avisa sin haber tocado nada.
    # Nombres nuevos en cada ejecución: si quedaron restos bloqueados de otra, no estorban.
    for stale in list(folder.glob(".viejo-*")) + list(folder.glob(".nuevo-*")):
        shutil.rmtree(stale, ignore_errors=True)
    run_id = f"{os.getpid()}-{threading.get_ident()}-{int(time.time() * 1000)}"
    old_dir = folder / f".viejo-{run_id}"
    old_dir.mkdir()
    moved: list[str] = []
    for old in sorted(p for p in folder.glob("Disco *") if p.is_dir()):
        try:
            old.rename(old_dir / old.name)
            moved.append(old.name)
        except OSError:
            for name in moved:
                try:
                    (old_dir / name).rename(folder / name)
                except OSError:
                    pass
            shutil.rmtree(work, ignore_errors=True)
            raise FolderBusy(f"No se puede actualizar «{old.name}» porque hay un archivo suyo abierto "
                             "(¿en un reproductor o en el Explorador?). Ciérralo y pulsa «Reintentar»; "
                             "las canciones ya preparadas no se pierden.")
    for it in items.values():  # los reutilizados ahora están dentro de .viejo
        try:
            rel = it.path.relative_to(folder)
        except ValueError:
            continue
        if rel.parts and rel.parts[0].startswith("Disco "):
            it.path = old_dir / rel

    # 2) Se montan los discos nuevos en .nuevo y se ponen en su sitio.
    staging = folder / f".nuevo-{run_id}"
    staging.mkdir()
    (folder / "canciones_no_encontradas.txt").unlink(missing_ok=True)

    ordered = [items[i] for i in sorted(items)]
    result.discs = cd.plan(ordered, mode)
    manifest: dict[str, str] = {}
    for disc in result.discs:
        disc.folder = staging / f"Disco {disc.number}"
        disc.folder.mkdir()
        album = col.name if len(result.discs) == 1 else f"{col.name} (Disco {disc.number})"
        for n, it in enumerate(disc.items, 1):
            t = col.tracks[it.index - 1]
            dst = disc.folder / (_file_stem(n, t, mode) + it.path.suffix)
            shutil.move(str(it.path), dst)
            it.path = dst
            if it.index in keys:
                manifest[keys[it.index]] = f"Disco {disc.number}/{dst.name}"
            if mode == "audio":
                tag_wav(dst, t, n, album)
            else:
                tag_mp3(dst, t, covers.get(it.index), n, t.album or col.name)
                it.size = dst.stat().st_size
        if mode == "audio":
            disc.cue = cd.write_cue(disc, album, disc.folder / f"Disco {disc.number}.cue")

    for disc in result.discs:
        final = folder / f"Disco {disc.number}"
        disc.folder.rename(final)
        disc.folder = final
        for it in disc.items:
            it.path = final / it.path.name
        if disc.cue:
            disc.cue = final / disc.cue.name
    shutil.rmtree(staging, ignore_errors=True)
    shutil.rmtree(work, ignore_errors=True)
    shutil.rmtree(old_dir, ignore_errors=True)  # lo que no se reutilizó
    (folder / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    if result.failed:
        (folder / "canciones_no_encontradas.txt").write_text(
            "\n".join(f"{i}. {name}  →  {why}" for i, name, why in sorted(result.failed)) + "\n",
            encoding="utf-8",
        )

    unit = "de audio" if mode == "audio" else "MP3"
    log(f"Listo: {len(items)} canciones en {len(result.discs)} CD {unit}. "
        f"{len(result.failed)} no se pudieron conseguir.")
    return result
