"""Descarga del audio original, medición de volumen, conversión y etiquetas.

Para no perder calidad:
  * Se descarga y guarda en caché el audio ORIGINAL de YouTube Music, sin recodificar.
  * Desde ese original se genera directamente el formato final (WAV de CD o MP3),
    de modo que solo hay una conversión con pérdida como mucho (nunca MP3 -> WAV).
  * El remuestreo a 44,1 kHz usa SoX (soxr, precisión 28 bits) y dither triangular al pasar a 16 bits.
  * "Igualar volumen" solo aplica una ganancia fija por canción (sin compresión ni limitador),
    y nunca sube tanto como para que un pico supere -1 dBTP.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import requests

from .config import find_binary, run
from .matcher import Match
from .spotify import Track

INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
TARGET_LUFS = -12.0
MAX_TRUE_PEAK = -1.0


class FFmpegMissing(RuntimeError):
    pass


def ffmpeg() -> str:
    path = find_binary("ffmpeg")
    if not path:
        raise FFmpegMissing("No se encontró ffmpeg (debería venir incluido con ListaCD).")
    return path


def safe_name(name: str, max_len: int = 150, ascii_cd: bool = False) -> str:
    """Nombre válido en Windows/macOS/Linux.

    ascii_cd=True deja solo caracteres representables en Windows-1252, para que la hoja
    .cue (que usan los programas de grabación) siempre encuentre el archivo.
    """
    name = INVALID_CHARS.sub("_", name)
    if ascii_cd:
        name = name.encode("cp1252", "replace").decode("cp1252").replace("?", "_")
    name = re.sub(r"\s+", " ", name).strip().rstrip(".")
    if name.upper() in {"CON", "PRN", "AUX", "NUL"} or re.fullmatch(r"(?i)(com|lpt)\d", name):
        name = f"_{name}"
    return name[:max_len].rstrip(" .") or "sin_nombre"


# ----------------------------------------------------------------------- descarga


class DownloadFailed(RuntimeError):
    """YouTube no dejó descargar el audio con ningún cliente."""


# Si YouTube responde 403 con un cliente, a menudo funciona con otro. None = los de yt-dlp.
CLIENT_ATTEMPTS: list[list[str] | None] = [
    None, ["tv"], ["web_safari"], ["android_vr"], ["mweb"], ["tv_simply"], ["ios"],
]


def _clean_partial(cache: Path, video_id: str) -> None:
    for p in cache.glob(f"{video_id}.*"):
        if p.suffix in (".part", ".ytdl") or p.name.endswith((".part", ".ytdl")) or p.stat().st_size == 0:
            p.unlink(missing_ok=True)


def explain_download_error(text: str) -> str:
    """Traduce los errores de yt-dlp a algo que el usuario pueda entender y resolver."""
    t = text.lower()
    if "403" in t or "forbidden" in t:
        return ("YouTube bloqueó la descarga (error 403). Pulsa «Reintentar»; si sigue fallando, "
                "en Ajustes elige el navegador con el que entras en YouTube.")
    if "sign in" in t or "bot" in t or "confirm" in t:
        return "YouTube pide verificar que no eres un robot. En Ajustes elige el navegador con el que entras en YouTube."
    if "age" in t and "restrict" in t:
        return "El vídeo tiene restricción de edad. En Ajustes elige el navegador con el que entras en YouTube."
    if "unavailable" in t or "private" in t or "removed" in t:
        return "El vídeo ya no está disponible en YouTube."
    if "timed out" in t or "connection" in t or "network" in t or "resolve" in t:
        return "Se cortó la conexión a internet. Pulsa «Reintentar»."
    return "No se pudo descargar de YouTube. Pulsa «Reintentar»."


def download_original(match: Match, cache: Path, cookies_browser: str = "") -> Path:
    """Descarga el mejor audio disponible tal cual (sin recodificar) a la caché.

    Si YouTube rechaza la descarga, lo vuelve a intentar con otros clientes de YouTube.
    """
    for p in cache.glob(f"{match.video_id}.*"):
        if p.suffix not in (".part", ".ytdl") and p.stat().st_size > 0:
            return p

    import yt_dlp

    base = {
        "outtmpl": str(cache / "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "retries": 5,
        "fragment_retries": 5,
        "ffmpeg_location": ffmpeg(),
    }
    deno = find_binary("deno")
    if deno:
        base["js_runtimes"] = {"deno": {"path": deno}}
    if cookies_browser:
        base["cookiesfrombrowser"] = (cookies_browser,)

    last = ""
    for n, clients in enumerate(CLIENT_ATTEMPTS):
        opts = dict(base)
        # 141 = AAC 256 kbps (solo con YouTube Premium y cookies). Si no, el mejor audio
        # (normalmente Opus ~160 kbps) evitando las versiones "drc" comprimidas.
        opts["format"] = ("141/bestaudio[format_id!*=drc]/bestaudio/best" if n == 0
                          else "bestaudio[format_id!*=drc]/bestaudio/best")
        if clients:
            opts["extractor_args"] = {"youtube": {"player_client": clients}}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(match.url, download=True)
                path = Path(ydl.prepare_filename(info))
            if path.exists() and path.stat().st_size > 0:
                return path
            found = [p for p in cache.glob(f"{match.video_id}.*")
                     if p.suffix not in (".part", ".ytdl") and p.stat().st_size > 0]
            if found:
                return found[0]
            last = "yt-dlp no generó ningún archivo de audio"
        except yt_dlp.utils.DownloadError as exc:
            last = str(exc)
            low = last.lower()
            if "unavailable" in low or "private video" in low or "removed" in low:
                break  # no se arregla cambiando de cliente
        _clean_partial(cache, match.video_id)
    raise DownloadFailed(explain_download_error(last))


# --------------------------------------------------------------------------- audio


def measure_loudness(src: Path) -> tuple[float, float] | None:
    """Devuelve (sonoridad integrada en LUFS, pico real en dBTP) o None si falla."""
    r = run([ffmpeg(), "-hide_banner", "-nostats", "-i", str(src), "-vn",
             "-af", "ebur128=peak=true", "-f", "null", "-"])
    summary = r.stderr[r.stderr.rfind("Summary:"):]
    i = re.search(r"I:\s*(-?[\d.]+|-inf) LUFS", summary)
    pk = re.search(r"Peak:\s*(-?[\d.]+|-inf) dBFS", summary)
    if not i or not pk or "inf" in i.group(1):
        return None
    return float(i.group(1)), float(pk.group(1)) if "inf" not in pk.group(1) else -99.0


def gain_for(loudness: tuple[float, float] | None) -> float:
    if loudness is None:
        return 0.0
    lufs, peak = loudness
    gain = TARGET_LUFS - lufs
    gain = min(gain, MAX_TRUE_PEAK - peak)  # no provocar saturación
    return round(gain, 2)


_SOXR_OK: bool | None = None
LAST_FILTER = ""  # cadena de filtros que funcionó (para la comprobación interna)


def _soxr() -> bool:
    global _SOXR_OK
    if _SOXR_OK is None:
        r = run([ffmpeg(), "-hide_banner", "-h", "filter=aresample"])
        _SOXR_OK = "soxr" in r.stdout
    return _SOXR_OK


def _filter_chains(gain_db: float, sample_fmt: str, dither: bool) -> list[str]:
    """Cadenas de filtros de mejor a peor; se usa la primera que acepte este ffmpeg."""
    vol = f"volume={gain_db}dB," if abs(gain_db) >= 0.05 else ""
    fmt = f"aformat=sample_fmts={sample_fmt}:channel_layouts=stereo"
    dith = ":dither_method=triangular" if dither else ""
    chains = []
    if _soxr():
        chains.append(f"{vol}aresample=44100:resampler=soxr:precision=28{dith},{fmt}")
    chains.append(f"{vol}aresample=44100{dith},{fmt}")
    chains.append(f"{vol}aresample=44100,{fmt}")
    return chains


def _convert(src: Path, dst: Path, gain_db: float, codec_args: list[str],
             sample_fmt: str, dither: bool) -> Path:
    global LAST_FILTER
    tmp = dst.with_name(dst.stem + ".tmp" + dst.suffix)
    err = ""
    for chain in _filter_chains(gain_db, sample_fmt, dither):
        cmd = [ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
               "-map", "0:a:0", "-vn", "-sn", "-map_metadata", "-1",
               "-af", chain, *codec_args, str(tmp)]
        r = run(cmd)
        if r.returncode == 0 and tmp.exists() and tmp.stat().st_size > 1000:
            LAST_FILTER = chain
            tmp.replace(dst)
            return dst
        err = r.stderr.strip()
        tmp.unlink(missing_ok=True)
    raise RuntimeError(f"ffmpeg falló: {err[-600:]}")


def to_cd_wav(src: Path, dst: Path, gain_db: float = 0.0) -> Path:
    """WAV PCM 16 bits / 44,1 kHz / estéreo: exactamente el formato de un CD de audio."""
    return _convert(src, dst, gain_db, ["-c:a", "pcm_s16le", "-f", "wav"], "s16", dither=True)


def to_mp3(src: Path, dst: Path, gain_db: float = 0.0) -> Path:
    """MP3 320 kbps CBR a 44,1 kHz con el codificador LAME en su modo más preciso.

    CBR en lugar de VBR porque algunas radios de coche antiguas no llevan bien el VBR.
    """
    return _convert(src, dst, gain_db,
                    ["-c:a", "libmp3lame", "-b:a", "320k", "-compression_level", "0",
                     "-id3v2_version", "0", "-f", "mp3"],
                    "s16p|fltp|s16", dither=False)


def wav_duration(path: Path) -> float:
    from mutagen.wave import WAVE

    return WAVE(path).info.length


# ------------------------------------------------------------------------ etiquetas


def fetch_image(url: str) -> bytes | None:
    if not url:
        return None
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        return r.content
    except Exception:
        return None


def car_friendly_cover(data: bytes | None, size: int = 500) -> bytes | None:
    """Carátula JPEG de 500x500 como máximo: algunas radios no leen imágenes grandes o PNG."""
    if not data:
        return None
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(data)).convert("RGB")
        img.thumbnail((size, size))
        out = io.BytesIO()
        img.save(out, "JPEG", quality=90, optimize=True)
        return out.getvalue()
    except Exception:
        return data if data[:3] == b"\xff\xd8\xff" else None


def tag_mp3(path: Path, t: Track, cover: bytes | None, track_no: int = 0, album: str = ""):
    from mutagen.id3 import APIC, ID3, TALB, TDRC, TIT2, TPE1, TPE2, TRCK, TSRC, ID3NoHeaderError

    try:
        ID3(path).delete(path)
    except ID3NoHeaderError:
        pass
    tags = ID3()
    tags.add(TIT2(encoding=3, text=t.title))
    tags.add(TPE1(encoding=3, text=t.artist))
    if album or t.album:
        tags.add(TALB(encoding=3, text=album or t.album))
    if t.album_artist:
        tags.add(TPE2(encoding=3, text=t.album_artist))
    if track_no:
        tags.add(TRCK(encoding=3, text=str(track_no)))
    if t.release_date:
        tags.add(TDRC(encoding=3, text=t.release_date[:4]))
    if t.isrc:
        tags.add(TSRC(encoding=3, text=t.isrc))
    if cover:
        tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover))
    # ID3v2.3 + ID3v1: lo que mejor leen las radios de coche
    tags.save(path, v2_version=3, v1=2)


def tag_wav(path: Path, t: Track, track_no: int = 0, album: str = ""):
    """Etiquetas informativas en el WAV (no se graban en el CD, pero ayudan a identificarlo)."""
    from mutagen.id3 import TALB, TIT2, TPE1, TRCK
    from mutagen.wave import WAVE

    f = WAVE(path)
    if f.tags is None:
        f.add_tags()
    f.tags.add(TIT2(encoding=3, text=t.title))
    f.tags.add(TPE1(encoding=3, text=t.artist))
    if album:
        f.tags.add(TALB(encoding=3, text=album))
    if track_no:
        f.tags.add(TRCK(encoding=3, text=str(track_no)))
    f.save()
