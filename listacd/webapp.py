"""Interfaz HTML (pywebview + WebView2) y su puente con Python.

La página (listacd/web) llama a los métodos de `Api` y recoge los eventos con `poll()`,
así ningún hilo de trabajo toca la ventana directamente.
"""

from __future__ import annotations

import sys
import threading
import webbrowser
from collections import deque
from pathlib import Path

from . import __version__, burner, cd, spotify
from .config import APP_NAME, Settings, cache_size, clear_cache, open_path, resource_dir
from .core import JobResult, run_job

WEB_DIR = Path(__file__).resolve().parent / "web"


def _disc_dict(d: cd.Disc, burned: bool = False) -> dict:
    return {"number": d.number, "items": [it.index for it in d.items], "seconds": round(d.seconds),
            "size": d.size, "burned": burned}


class Api:
    def __init__(self):
        self._settings = Settings.load()
        self._col: spotify.Collection | None = None
        self._result: JobResult | None = None
        self._events: deque = deque()
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._busy = False
        self._burning = False
        self._burned: set[int] = set()
        self._drives: list[burner.Drive] = []
        self._window = None

    # ---------------------------------------------------------------- utilidades
    def _emit(self, kind: str, **data):
        with self._lock:
            self._events.append({"type": kind, **data})

    def _thread(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    def poll(self):
        with self._lock:
            out = list(self._events)
            self._events.clear()
        return out

    # ------------------------------------------------------------------- estado
    def init(self):
        s = self._settings
        return {
            "version": __version__, "canBurn": burner.available(),
            "settings": {"mode": s.mode, "normalize": s.normalize, "outputDir": s.output_dir,
                         "clientId": s.client_id, "hasSecret": bool(s.client_secret),
                         "cookies": s.cookies_browser, "workers": s.workers},
        }

    def set_options(self, mode: str, normalize: bool):
        if self._busy:
            return False
        self._settings.mode = "mp3" if mode == "mp3" else "audio"
        self._settings.normalize = bool(normalize)
        self._settings.save()
        self._result = None
        return True

    def save_settings(self, data: dict):
        s = self._settings
        s.output_dir = (data.get("outputDir") or s.output_dir).strip()
        s.client_id = (data.get("clientId") or "").strip()
        if data.get("clientSecret"):
            s.client_secret = data["clientSecret"].strip()
        elif not s.client_id:
            s.client_secret = ""
        s.cookies_browser = data.get("cookies") or ""
        s.workers = int(data.get("workers") or s.workers)
        s.save()
        return self.init()

    def cache_info(self):
        return {"bytes": cache_size()}

    def clear_cache(self):
        if self._busy:
            return {"ok": False}
        clear_cache()
        return {"ok": True, "bytes": cache_size()}

    # -------------------------------------------------------------------- lista
    def load(self, url: str):
        url = (url or "").strip()
        try:
            spotify.parse_url(url)
        except ValueError:
            return {"ok": False, "error": "Ese enlace no es de Spotify. En Spotify, pulsa ⋯ en la lista, "
                                          "después Compartir y Copiar enlace."}
        s = self._settings

        def job():
            try:
                col = spotify.fetch(url, s.client_id, s.client_secret)
                self._col, self._result = col, None
                self._burned.clear()
                warn = col.warning
                if col.truncated:
                    warn = ("Spotify solo deja leer las primeras 100 canciones sin claves. "
                            "Añade tus claves gratuitas en Ajustes para leer la lista entera.")
                self._emit("loaded", collection={
                    "name": col.name, "owner": col.owner, "kind": col.kind, "cover": col.cover_url,
                    "warning": warn,
                    "tracks": [{"title": t.title, "artist": t.artist, "seconds": round(t.duration_s)}
                               for t in col.tracks]})
            except Exception as exc:
                self._emit("load_error", message=f"No se pudo leer la lista: {exc}. "
                                                 "Comprueba que es pública y que tienes internet.")

        self._thread(job)
        return {"ok": True}

    def plan(self, excluded: list[int]):
        if not self._col:
            return []
        ex = set(excluded or [])
        pairs = [(i, t.duration_s) for i, t in enumerate(self._col.tracks, 1) if i not in ex]
        return [_disc_dict(d) for d in cd.estimate(pairs, self._settings.mode)]

    # ---------------------------------------------------------------- preparar
    def start(self, excluded: list[int]):
        if self._busy or not self._col:
            return False
        self._busy = True
        self._cancel.clear()
        self._result = None
        self._burned.clear()
        col, s = self._col, self._settings
        include = {i for i in range(1, len(col.tracks) + 1) if i not in set(excluded or [])}

        def on_event(e):
            if e.kind == "track":
                self._emit("track", index=e.index, status=e.status, text=e.text)
            elif e.kind == "progress":
                self._emit("progress", done=e.done, total=e.total)

        def job():
            try:
                res = run_job(col, s, on_event, cancel=self._cancel, include=include)
                self._result = None if res.cancelled else res
                self._emit("job_done", cancelled=res.cancelled, folder=str(res.folder),
                           discs=[_disc_dict(d) for d in res.discs],
                           failed=[{"index": i, "reason": why} for i, _, why in res.failed])
            except Exception as exc:
                self._emit("job_error", message=str(exc))
            finally:
                self._busy = False

        self._thread(job)
        return True

    def cancel(self):
        self._cancel.set()

    # ---------------------------------------------------------------- grabar
    def drives(self):
        if not burner.available():
            return []
        try:
            self._drives = burner.list_drives()
        except Exception:
            self._drives = []
        return [{"id": d.unique_id, "name": str(d)} for d in self._drives]

    def _disc(self, number: int) -> cd.Disc | None:
        if not self._result:
            return None
        return next((d for d in self._result.discs if d.number == number), None)

    def _drive(self, drive_id: str) -> burner.Drive | None:
        return next((d for d in self._drives if d.unique_id == drive_id), None)

    def check_disc(self, number: int, drive_id: str):
        """Comprueba el CD-R de la grabadora. Devuelve {ok, message}."""
        disc, drive = self._disc(number), self._drive(drive_id)
        if not disc or not drive:
            return {"ok": False, "message": "Elige una grabadora."}
        try:
            info = burner.media_info(drive)
        except Exception as exc:
            return {"ok": False, "message": f"No se pudo leer la grabadora: {exc}"}
        audio = self._result.mode == "audio"
        if not info.present:
            return {"ok": False, "message": info.message or "Mete un CD-R virgen en la grabadora."}
        if not info.blank:
            return {"ok": False, "message": "El disco no está vacío. Mete un CD-R virgen."}
        if audio and not info.writable_cd:
            return {"ok": False, "message": f"Hay un {info.kind}. Los CD de audio necesitan un CD-R."}
        if audio and info.free_seconds and disc.seconds + 2 * len(disc.items) > info.free_seconds:
            return {"ok": False, "message": f"Al disco le caben {cd.fmt_time(info.free_seconds)} y este CD "
                                            f"dura {cd.fmt_time(disc.seconds)}. Usa un CD-R de 80 minutos."}
        if not audio and disc.size > info.free_bytes:
            return {"ok": False, "message": "Las canciones no caben en este disco."}
        return {"ok": True, "message": f"{info.kind} virgen en {drive}."}

    def burn(self, number: int, drive_id: str):
        disc, drive = self._disc(number), self._drive(drive_id)
        if not disc or not drive or self._busy:
            return False
        self._busy = self._burning = True
        audio = self._result.mode == "audio"
        name = self._col.name if self._col else APP_NAME

        def prog(text, frac):
            self._emit("burn_progress", disc=number, text=text, frac=frac)

        def job():
            try:
                if audio:
                    burner.burn_audio(drive, [it.path for it in disc.items], prog)
                else:
                    burner.burn_data(drive, disc.folder, name, prog)
                self._burned.add(number)
                self._emit("burn_done", disc=number, more=number < len(self._result.discs))
            except Exception as exc:
                hint = (" También puedes grabar el archivo «.cue» de la carpeta del disco con ImgBurn."
                        if audio else "")
                self._emit("burn_error", disc=number, message=f"{exc}.{hint}")
            finally:
                self._busy = self._burning = False

        self._thread(job)
        return True

    # ------------------------------------------------------------ escritorio
    def open_folder(self):
        target = self._result.folder if self._result else Path(self._settings.output_dir)
        target.mkdir(parents=True, exist_ok=True)
        open_path(target)

    def choose_folder(self):
        import webview

        res = self._window.create_file_dialog(webview.FileDialog.FOLDER, directory=self._settings.output_dir)
        return res[0] if res else None

    def paste(self):
        try:
            if sys.platform == "win32":
                import win32clipboard

                win32clipboard.OpenClipboard()
                try:
                    return win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
                finally:
                    win32clipboard.CloseClipboard()
        except Exception:
            pass
        return None

    def open_url(self, url: str):
        if url.startswith("https://"):
            webbrowser.open(url)

    def _on_closing(self):
        if self._burning:
            ok = self._window.create_confirmation_dialog(
                "Se está grabando un disco",
                "Si cierras ahora, el CD quedará inservible. ¿Cerrar de todas formas?")
            if not ok:
                return False
        elif self._busy:
            ok = self._window.create_confirmation_dialog(
                "Preparando canciones", "Se cancelará la preparación. ¿Cerrar?")
            if not ok:
                return False
        self._cancel.set()
        return True


def run_web() -> None:
    import webview

    api = Api()
    window = webview.create_window(
        APP_NAME, str(WEB_DIR / "index.html"), js_api=api, width=1200, height=800,
        min_size=(1024, 700), background_color="#DADFE3", text_select=False)
    api._window = window
    window.events.closing += api._on_closing
    icon = resource_dir() / "assets" / "listacd.ico"
    webview.start(gui="edgechromium" if sys.platform == "win32" else None,
                  icon=str(icon) if icon.exists() else None, debug=False)
