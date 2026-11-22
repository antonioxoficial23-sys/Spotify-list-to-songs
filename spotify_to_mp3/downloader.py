"""Descarga el audio con yt-dlp, lo convierte con ffmpeg y escribe las etiquetas."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import requests

from .matcher import Match
from .spotify import Track

INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_name(name: str, max_len: int = 150) -> str:
    """Nombre válido para archivos/carpetas en Windows, macOS y Linux."""
    name = INVALID_CHARS.sub("_", name).strip().rstrip(".")
    name = re.sub(r"\s+", " ", name)
    if name.upper() in {"CON", "PRN", "AUX", "NUL"} or re.fullmatch(r"(?i)(com|lpt)\d", name):
        name = f"_{name}"
    return name[:max_len].rstrip() or "sin_nombre"


def check_ffmpeg() -> None:
    if not shutil.which("ffmpeg"):
        raise SystemExit(
            "No se encontró ffmpeg. Instálalo y vuelve a intentarlo:\n"
            "  Windows: winget install ffmpeg\n"
            "  macOS:   brew install ffmpeg\n"
            "  Linux:   sudo apt install ffmpeg"
        )


def download_audio(match: Match, dest_stem: Path, fmt: str, bitrate: str) -> Path:
    """Descarga la mejor pista de audio disponible y la deja en dest_stem.<ext>.

    fmt = "mp3"  -> recodifica a MP3 (bitrate "320" CBR o "V0" VBR máxima calidad)
    fmt = "best" -> guarda el audio original sin recodificar (opus/m4a), sin pérdida extra
    """
    import yt_dlp

    postprocessors = []
    if fmt == "mp3":
        quality = "0" if bitrate.upper() == "V0" else bitrate.rstrip("kK")
        postprocessors.append(
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": quality}
        )
    else:
        postprocessors.append({"key": "FFmpegExtractAudio", "preferredcodec": "best"})

    opts = {
        # Prioriza la mejor pista de solo audio (normalmente Opus ~160 kbps o AAC 256 kbps
        # con YouTube Premium/cookies); si no hay, cualquier formato con audio.
        "format": "bestaudio[acodec!=none]/bestaudio/best",
        "outtmpl": str(dest_stem) + ".%(ext)s",
        "postprocessors": postprocessors,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "retries": 5,
        "fragment_retries": 5,
        "overwrites": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([match.url])

    for ext in ("mp3", "opus", "m4a", "ogg", "webm", "aac", "flac"):
        p = dest_stem.with_suffix(f".{ext}")
        if p.exists():
            return p
    raise RuntimeError("yt-dlp no generó ningún archivo de audio")


def fetch_image(url: str) -> bytes | None:
    if not url:
        return None
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        return r.content
    except Exception:
        return None


def tag_file(path: Path, track: Track, cover: bytes | None):
    ext = path.suffix.lower()
    if ext == ".mp3":
        _tag_mp3(path, track, cover)
    elif ext in (".m4a", ".aac"):
        _tag_m4a(path, track, cover)
    elif ext in (".opus", ".ogg"):
        _tag_ogg(path, track, cover)


def _tag_mp3(path: Path, t: Track, cover: bytes | None):
    from mutagen.id3 import APIC, ID3, TALB, TDRC, TIT2, TPE1, TPE2, TPOS, TRCK, TSRC, ID3NoHeaderError

    try:
        ID3(path).delete(path)  # quita las etiquetas que deja yt-dlp/ffmpeg
    except ID3NoHeaderError:
        pass
    tags = ID3()
    tags.add(TIT2(encoding=3, text=t.title))
    tags.add(TPE1(encoding=3, text=t.artist))
    if t.album:
        tags.add(TALB(encoding=3, text=t.album))
    if t.album_artist:
        tags.add(TPE2(encoding=3, text=t.album_artist))
    if t.track_number:
        tags.add(TRCK(encoding=3, text=str(t.track_number)))
    if t.disc_number:
        tags.add(TPOS(encoding=3, text=str(t.disc_number)))
    if t.release_date:
        tags.add(TDRC(encoding=3, text=t.release_date))
    if t.isrc:
        tags.add(TSRC(encoding=3, text=t.isrc))
    if cover:
        mime = "image/png" if cover[:4] == b"\x89PNG" else "image/jpeg"
        tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=cover))
    tags.save(path, v2_version=3)  # v2.3: máxima compatibilidad (Windows, coches, móviles)


def _tag_m4a(path: Path, t: Track, cover: bytes | None):
    from mutagen.mp4 import MP4, MP4Cover

    f = MP4(path)
    f["\xa9nam"] = t.title
    f["\xa9ART"] = t.artist
    if t.album:
        f["\xa9alb"] = t.album
    if t.album_artist:
        f["aART"] = t.album_artist
    if t.release_date:
        f["\xa9day"] = t.release_date
    if t.track_number:
        f["trkn"] = [(t.track_number, 0)]
    if cover:
        kind = MP4Cover.FORMAT_PNG if cover[:4] == b"\x89PNG" else MP4Cover.FORMAT_JPEG
        f["covr"] = [MP4Cover(cover, imageformat=kind)]
    f.save()


def _tag_ogg(path: Path, t: Track, cover: bytes | None):
    import base64

    from mutagen import File
    from mutagen.flac import Picture

    f = File(path)
    if f is None:
        return
    f["title"] = t.title
    f["artist"] = t.artists
    if t.album:
        f["album"] = t.album
    if t.album_artist:
        f["albumartist"] = t.album_artist
    if t.release_date:
        f["date"] = t.release_date
    if t.track_number:
        f["tracknumber"] = str(t.track_number)
    if t.isrc:
        f["isrc"] = t.isrc
    if cover:
        pic = Picture()
        pic.type = 3
        pic.mime = "image/png" if cover[:4] == b"\x89PNG" else "image/jpeg"
        pic.data = cover
        f["metadata_block_picture"] = [base64.b64encode(pic.write()).decode()]
    f.save()
