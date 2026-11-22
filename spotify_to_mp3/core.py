"""Orquesta todo: lee la lista, busca cada canción, la descarga y la etiqueta."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import spotify
from .downloader import check_ffmpeg, download_audio, fetch_image, safe_name, tag_file
from .matcher import Matcher

AUDIO_EXTS = (".mp3", ".opus", ".m4a", ".ogg")


@dataclass
class Result:
    folder: Path
    ok: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)


def _existing(stem: Path) -> Path | None:
    for ext in AUDIO_EXTS:
        p = stem.with_suffix(ext)
        if p.exists() and p.stat().st_size > 0:
            return p
    return None


def download_collection(
    url: str,
    out_dir: str | Path = ".",
    fmt: str = "mp3",
    bitrate: str = "320",
    workers: int = 4,
    numbered: bool = False,
    log: Callable[[str], None] = print,
) -> Result:
    check_ffmpeg()

    log("Leyendo la lista de Spotify…")
    col = spotify.fetch(url)
    if not col.tracks:
        raise SystemExit("La lista está vacía o no se pudo leer.")
    if col.truncated:
        log(
            "[aviso] Sin credenciales de Spotify solo se pueden leer las primeras 100 "
            "canciones. Configura SPOTIFY_CLIENT_ID y SPOTIFY_CLIENT_SECRET (ver README)."
        )

    folder = Path(out_dir).expanduser() / safe_name(col.name)
    folder.mkdir(parents=True, exist_ok=True)
    total = len(col.tracks)
    log(f"«{col.name}»: {total} canciones → {folder}")

    matcher = Matcher()
    cover_cache: dict[str, bytes | None] = {}
    cache_lock = threading.Lock()
    result = Result(folder=folder)
    width = len(str(total))
    file_order: list[str | None] = [None] * total

    def cover_for(url: str) -> bytes | None:
        with cache_lock:
            if url in cover_cache:
                return cover_cache[url]
        data = fetch_image(url)
        with cache_lock:
            cover_cache[url] = data
        return data

    def work(idx: int, track: spotify.Track):
        label = f"{track.artist} - {track.title}"
        base = safe_name(label)
        if numbered:
            base = f"{idx:0{width}d} - {base}"
        stem = folder / base

        if (existing := _existing(stem)) is not None:
            return idx, "skip", label, existing.name

        match = matcher.find(track)
        if match is None:
            return idx, "fail", label, "no se encontró en YouTube Music"

        path = download_audio(match, stem, fmt, bitrate)
        cover = cover_for(track.cover_url or match.thumbnail)
        tag_file(path, track, cover)
        return idx, "ok", label, path.name

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(work, i, t): (i, t) for i, t in enumerate(col.tracks, 1)}
        done = 0
        for fut in as_completed(futures):
            done += 1
            i, t = futures[fut]
            prefix = f"[{done:>{width}}/{total}]"
            try:
                idx, status, label, info = fut.result()
            except Exception as exc:  # error de red, vídeo bloqueado, etc.
                label = f"{t.artist} - {t.title}"
                result.failed.append((label, str(exc).splitlines()[0][:200]))
                log(f"{prefix} ✗ {label}  ({exc.__class__.__name__})")
                continue
            if status == "ok":
                result.ok.append(label)
                file_order[idx - 1] = info
                log(f"{prefix} ✓ {label}")
            elif status == "skip":
                result.skipped.append(label)
                file_order[idx - 1] = info
                log(f"{prefix} = {label} (ya existía)")
            else:
                result.failed.append((label, info))
                log(f"{prefix} ✗ {label}  ({info})")

    # Lista .m3u8 con el orden original para abrirla en cualquier reproductor
    m3u = folder / f"{safe_name(col.name)}.m3u8"
    m3u.write_text(
        "#EXTM3U\n" + "\n".join(f for f in file_order if f) + "\n", encoding="utf-8"
    )

    failed_file = folder / "_canciones_fallidas.txt"
    if result.failed:
        failed_file.write_text(
            "\n".join(f"{name}\t{why}" for name, why in result.failed) + "\n", encoding="utf-8"
        )
    elif failed_file.exists():
        failed_file.unlink()

    log(
        f"\nListo: {len(result.ok)} descargadas, {len(result.skipped)} ya existían, "
        f"{len(result.failed)} fallidas.\nCarpeta: {folder}"
    )
    if result.failed:
        log(f"Las fallidas están en {failed_file.name}. Vuelve a ejecutar para reintentarlas.")
    return result
