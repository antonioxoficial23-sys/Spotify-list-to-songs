"""Rutas, binarios incluidos y ajustes guardados del usuario."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path

APP_NAME = "ListaCD"


def _base_config_dir() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


def _base_cache_dir() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches"
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")


def config_dir() -> Path:
    d = _base_config_dir() / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def cache_dir() -> Path:
    d = Path(os.environ.get("LISTACD_CACHE") or _base_cache_dir() / APP_NAME / "originales")
    d.mkdir(parents=True, exist_ok=True)
    return d


def default_output_dir() -> str:
    music = Path.home() / "Music"
    return str((music if music.exists() else Path.home()) / APP_NAME)


def resource_dir() -> Path:
    """Carpeta con los recursos del programa (dentro del .exe o del código fuente)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def find_binary(name: str) -> str | None:
    """Busca primero el binario incluido con la app (bin/) y luego en el PATH."""
    exe = f"{name}.exe" if sys.platform == "win32" else name
    for d in (resource_dir() / "bin", Path(sys.executable).parent / "bin"):
        if (d / exe).exists():
            return str(d / exe)
    return shutil.which(name)


# En Windows evita que se abra una ventana negra por cada llamada a ffmpeg
NO_WINDOW = {"creationflags": 0x08000000} if sys.platform == "win32" else {}


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", **NO_WINDOW, **kw
    )


@dataclass
class Settings:
    client_id: str = ""
    client_secret: str = ""
    output_dir: str = ""
    mode: str = "audio"  # "audio" (CD de audio) | "mp3" (CD de MP3)
    normalize: bool = True
    cookies_browser: str = ""  # "", "firefox", "chrome", "edge"…
    workers: int = 4

    @classmethod
    def path(cls) -> Path:
        return config_dir() / "ajustes.json"

    @classmethod
    def load(cls) -> "Settings":
        s = cls()
        try:
            data = json.loads(cls.path().read_text(encoding="utf-8"))
            for f in fields(cls):
                if f.name in data:
                    setattr(s, f.name, data[f.name])
        except (OSError, ValueError):
            pass
        s.client_id = s.client_id or os.environ.get("SPOTIFY_CLIENT_ID", "")
        s.client_secret = s.client_secret or os.environ.get("SPOTIFY_CLIENT_SECRET", "")
        s.output_dir = s.output_dir or default_output_dir()
        return s

    def save(self) -> None:
        self.path().write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
