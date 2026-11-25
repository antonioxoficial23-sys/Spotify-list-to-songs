"""Grabación de CDs en Windows con IMAPI2 (el motor de grabación integrado en Windows).

* CD de audio: Track-At-Once, una pista por canción, PCM 16 bits / 44,1 kHz.
* CD de MP3: disco de datos ISO 9660 + Joliet (lo que leen las radios de coche).

Todas las funciones deben llamarse desde un mismo hilo; cada una inicializa COM.
"""

from __future__ import annotations

import sys
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

SECTOR_AUDIO = 2352
FS_ISO9660, FS_JOLIET = 1, 2

# IMAPI_MEDIA_PHYSICAL_TYPE
MEDIA_NAMES = {
    0: "Desconocido", 1: "CD-ROM", 2: "CD-R", 3: "CD-RW", 4: "DVD-ROM", 5: "DVD-RAM",
    6: "DVD+R", 7: "DVD+RW", 8: "DVD+R DL", 9: "DVD-R", 10: "DVD-RW", 11: "DVD-R DL",
    12: "Disco", 13: "DVD+RW DL", 14: "HD DVD-ROM", 15: "HD DVD-R", 16: "HD DVD-RAM",
    17: "BD-ROM", 18: "BD-R", 19: "BD-RE",
}
CD_WRITABLE = {2, 3}
REWRITABLE = {3, 5, 7, 10, 13, 19}  # CD-RW, DVD-RAM, DVD+RW, DVD-RW, DVD+RW DL, BD-RE


class BurnError(RuntimeError):
    pass


@dataclass
class Drive:
    unique_id: str
    letter: str
    name: str

    def __str__(self) -> str:
        return f"{self.letter} {self.name}".strip()


@dataclass
class MediaInfo:
    present: bool
    kind: str = ""
    blank: bool = False
    writable_cd: bool = False
    free_seconds: float = 0.0
    free_bytes: int = 0
    message: str = ""
    rewritable: bool = False  # CD-RW: se puede borrar y volver a grabar


def available() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import pythoncom  # noqa: F401
        import win32com.client  # noqa: F401

        return True
    except ImportError:
        return False


def _com():
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    return pythoncom, win32com.client


def _recorder(client, unique_id: str):
    rec = client.Dispatch("IMAPI2.MsftDiscRecorder2")
    rec.InitializeDiscRecorder(unique_id)
    return rec


def list_drives() -> list[Drive]:
    if not available():
        return []
    _, client = _com()
    master = client.Dispatch("IMAPI2.MsftDiscMaster2")
    drives = []
    for i in range(master.Count):
        uid = master.Item(i)
        try:
            rec = _recorder(client, uid)
            paths = list(rec.VolumePathNames or [])
            letter = paths[0].rstrip("\\") if paths else ""
            name = f"{(rec.VendorId or '').strip()} {(rec.ProductId or '').strip()}".strip()
            drives.append(Drive(uid, letter, name or "Grabadora"))
        except Exception:
            continue
    return drives


def media_info(drive: Drive) -> MediaInfo:
    pythoncom, client = _com()
    rec = _recorder(client, drive.unique_id)
    data = client.Dispatch("IMAPI2.MsftDiscFormat2Data")
    try:
        if not data.IsRecorderSupported(rec):
            return MediaInfo(False, message="Esta unidad no puede grabar.")
        data.Recorder = rec
        if not data.IsCurrentMediaSupported(rec):
            # Un CD-RW ya grabado y cerrado no admite más datos, pero sí borrarse
            try:
                er = client.Dispatch("IMAPI2.MsftDiscFormat2Erase")
                er.Recorder = rec
                if er.IsCurrentMediaSupported(rec):
                    return MediaInfo(True, kind="CD-RW", blank=False, writable_cd=True, rewritable=True,
                                     message="El CD-RW ya tiene música.")
            except pythoncom.com_error:
                pass
            return MediaInfo(False, message="No hay disco, o el que hay ya está grabado y cerrado. "
                                            "Mete un CD-R virgen.")
        kind = int(data.CurrentPhysicalMediaType)
        blank = bool(data.MediaHeuristicallyBlank)
        free_sectors = int(data.FreeSectorsOnMedia)
    except pythoncom.com_error:
        return MediaInfo(False, message="Introduce un CD-R virgen.")
    info = MediaInfo(
        present=True, kind=MEDIA_NAMES.get(kind, "Disco"), blank=blank,
        writable_cd=kind in CD_WRITABLE, free_bytes=free_sectors * 2048,
        free_seconds=free_sectors / 75.0, rewritable=kind in REWRITABLE,
    )
    if not blank:
        info.message = "El disco no está vacío."
    elif kind not in CD_WRITABLE:
        info.message = f"Hay un {info.kind}; para el coche usa un CD-R."
    return info


def erase(drive: Drive, progress: Callable[[str, float], None] = lambda text, frac: None) -> None:
    """Borrado rápido de un CD-RW (deja el disco virgen para volver a grabarlo)."""
    pythoncom, client = _com()
    rec = _recorder(client, drive.unique_id)
    er = client.Dispatch("IMAPI2.MsftDiscFormat2Erase")
    er.Recorder = rec
    er.ClientName = "ListaCD"
    er.FullErase = False
    progress("Borrando el CD-RW…", 0.02)
    try:
        er.EraseMedia()
    except pythoncom.com_error as exc:
        raise BurnError(f"No se pudo borrar el CD-RW: {_com_msg(exc)}") from exc


def _hglobal_stream(pythoncom, wav_path: Path):
    """Crea un IStream con el PCM del WAV, rellenado hasta un múltiplo de 2352 bytes."""
    with wave.open(str(wav_path), "rb") as w:
        if (w.getnchannels(), w.getsampwidth(), w.getframerate()) != (2, 2, 44100):
            raise BurnError(f"{wav_path.name} no es audio de CD (16 bits, 44,1 kHz, estéreo).")
        stream = pythoncom.CreateStreamOnHGlobal(None, True)
        written = 0
        while chunk := w.readframes(44100 * 10):
            stream.Write(chunk)
            written += len(chunk)
    pad = (-written) % SECTOR_AUDIO
    if pad:
        stream.Write(b"\x00" * pad)
    stream.Seek(0, 0)
    return stream


def burn_audio(
    drive: Drive,
    wavs: list[Path],
    progress: Callable[[str, float], None] = lambda text, frac: None,
    eject: bool = True,
) -> None:
    pythoncom, client = _com()
    rec = _recorder(client, drive.unique_id)
    tao = client.Dispatch("IMAPI2.MsftDiscFormat2TrackAtOnce")
    if not tao.IsRecorderSupported(rec):
        raise BurnError("Esta grabadora no admite CD de audio.")
    tao.Recorder = rec
    tao.ClientName = "ListaCD"
    tao.DoNotFinalizeMedia = False  # cerrar el disco: imprescindible para el coche
    try:
        tao.PrepareMedia()
    except pythoncom.com_error as exc:
        raise BurnError(f"No se pudo preparar el disco: {_com_msg(exc)}") from exc
    try:
        for n, wav in enumerate(wavs, 1):
            progress(f"Grabando pista {n} de {len(wavs)}…", (n - 1) / len(wavs))
            stream = _hglobal_stream(pythoncom, wav)
            tao.AddAudioTrack(stream)
            del stream
        progress("Cerrando el disco…", 0.99)
    except pythoncom.com_error as exc:
        raise BurnError(f"Error al grabar: {_com_msg(exc)}") from exc
    finally:
        try:
            tao.ReleaseMedia()
        except Exception:
            pass
    progress("¡Disco grabado!", 1.0)
    if eject:
        _eject(rec)


def iso_volume_name(name: str) -> str:
    """Nombre de volumen válido para IMAPI2: máx. 15 caracteres; en ISO 9660 solo A–Z, 0–9 y _."""
    import re
    import unicodedata

    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().upper()
    plain = re.sub(r"[^A-Z0-9]+", "_", plain).strip("_")
    return plain[:15].rstrip("_") or "LISTACD"


def build_data_image(client, folder: Path, volume_name: str, rec=None):
    fsi = client.Dispatch("IMAPI2FS.MsftFileSystemImage")
    if rec is not None:
        fsi.ChooseImageDefaults(rec)
    else:
        fsi.ChooseImageDefaultsForMediaType(2)  # CD-R
    fsi.FileSystemsToCreate = FS_ISO9660 | FS_JOLIET
    fsi.VolumeName = iso_volume_name(volume_name)
    fsi.Root.AddTree(str(folder), False)
    return fsi.CreateResultImage()


def burn_data(
    drive: Drive,
    folder: Path,
    volume_name: str,
    progress: Callable[[str, float], None] = lambda text, frac: None,
    eject: bool = True,
) -> None:
    pythoncom, client = _com()
    rec = _recorder(client, drive.unique_id)
    data = client.Dispatch("IMAPI2.MsftDiscFormat2Data")
    data.Recorder = rec
    data.ClientName = "ListaCD"
    data.ForceMediaToBeClosed = True  # disco cerrado: lo lee cualquier radio
    progress("Preparando la imagen del disco…", 0.02)
    try:
        image = build_data_image(client, folder, volume_name, rec)
        progress("Grabando…", 0.05)
        data.Write(image.ImageStream)
    except pythoncom.com_error as exc:
        raise BurnError(f"Error al grabar: {_com_msg(exc)}") from exc
    progress("¡Disco grabado!", 1.0)
    if eject:
        _eject(rec)


def _eject(rec) -> None:
    try:
        time.sleep(1)
        rec.EjectMedia()
    except Exception:
        pass


def _com_msg(exc) -> str:
    try:
        hr, msg, details, _ = exc.args
        if details and details[2]:
            return str(details[2]).strip()
        return f"{msg} (0x{hr & 0xFFFFFFFF:08X})"
    except Exception:
        return str(exc)


def self_test() -> str:
    """Comprobación sin grabadora (usada en la compilación automática en Windows)."""
    import tempfile

    pythoncom, client = _com()
    master = client.Dispatch("IMAPI2.MsftDiscMaster2")
    out = [f"IMAPI2 OK, grabadoras: {master.Count}"]
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "datos").mkdir()
        (d / "datos" / "01 - Prueba - Canción.mp3").write_bytes(b"\x00" * 5000)
        img = build_data_image(client, d / "datos", "Viaje a la playa (Disco 1) ñ")
        out.append(f"Imagen ISO/Joliet OK: {img.TotalBlocks} bloques")
        wav = d / "t.wav"
        with wave.open(str(wav), "wb") as w:
            w.setnchannels(2), w.setsampwidth(2), w.setframerate(44100)
            w.writeframes(b"\x01\x00" * 2 * 44100)
        stream = _hglobal_stream(pythoncom, wav)
        size = stream.Stat()[2]
        assert size % SECTOR_AUDIO == 0, size
        out.append(f"Stream de audio OK: {size} bytes")
    client.Dispatch("IMAPI2.MsftDiscFormat2Erase")
    out.append("Borrado de CD-RW disponible")
    return "\n".join(out)
