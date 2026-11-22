"""Punto de entrada. Sin argumentos abre la ventana; con un enlace funciona en la terminal.

    ListaCD                                   → interfaz gráfica
    ListaCD <enlace> [--modo audio|mp3]       → prepara los discos desde la terminal
    ListaCD --selftest salida.txt             → comprobación interna (compilación)
"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path


def selftest(out: str) -> int:
    lines, ok = [], True

    def check(name, fn):
        nonlocal ok
        try:
            lines.append(f"[OK] {name}: {fn()}")
        except Exception:
            ok = False
            lines.append(f"[FALLO] {name}:\n{traceback.format_exc()}")

    import tempfile

    from . import __version__, burner
    from .config import find_binary, run

    def ffmpeg_test():
        from .downloader import to_cd_wav, to_mp3, measure_loudness, gain_for, wav_duration

        exe = find_binary("ffmpeg")
        assert exe, "ffmpeg no encontrado"
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "src.opus"
            r = run([exe, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=3:sample_rate=48000",
                     "-c:a", "libopus", "-b:a", "160k", str(src)])
            assert r.returncode == 0, r.stderr
            g = gain_for(measure_loudness(src))
            w = to_cd_wav(src, Path(d) / "a.wav", g)
            from . import downloader as dl0
            wav_chain = dl0.LAST_FILTER
            m = to_mp3(src, Path(d) / "a.mp3", g)
            from . import downloader as dl

            return (f"{exe} · wav {wav_duration(w):.2f}s · mp3 {m.stat().st_size} B · "
                    f"ganancia {g} dB · WAV: {wav_chain} · MP3: {dl.LAST_FILTER}")

    check("Versión", lambda: __version__)
    check("ffmpeg", ffmpeg_test)
    check("deno", lambda: find_binary("deno") or "no incluido")
    check("yt-dlp", lambda: __import__("yt_dlp.version", fromlist=["x"]).__version__)
    check("yt-dlp-ejs", lambda: __import__("yt_dlp_ejs").__name__)
    check("ytmusicapi", lambda: __import__("ytmusicapi").__name__)
    check("spotipy", lambda: __import__("spotipy").__name__)
    check("customtkinter", lambda: __import__("customtkinter").__version__)
    check("interfaz web", lambda: all((Path(__file__).parent / "web" / f).exists()
                                      for f in ("index.html", "app.css", "app.js")) and "archivos OK")
    if sys.platform == "win32":
        def webview_check():
            import webview
            from webview.platforms import winforms  # noqa: F401  (carga pythonnet y WebView2)

            return f"pywebview {webview.__version__ if hasattr(webview, '__version__') else ''} + WebView2"
        check("pywebview", webview_check)
    if sys.platform == "win32":
        check("IMAPI2", burner.self_test)
    Path(out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if ok else 1


def launch_gui() -> int:
    """Interfaz HTML (WebView2); si no está disponible, la ventana clásica."""
    try:
        from .webapp import run_web

        run_web()
    except Exception:
        from .config import config_dir

        (config_dir() / "error_interfaz.log").write_text(traceback.format_exc(), encoding="utf-8")
        from .gui import run_gui

        run_gui()
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ListaCD", description="Listas de Spotify a CD para el coche.")
    p.add_argument("url", nargs="?", help="Enlace de Spotify (lista, álbum o canción)")
    p.add_argument("--modo", choices=["audio", "mp3"], help="audio = CD de audio (por defecto), mp3 = CD de MP3")
    p.add_argument("-o", "--salida", help="Carpeta de destino")
    p.add_argument("--sin-normalizar", action="store_true", help="No igualar el volumen")
    p.add_argument("--selftest", metavar="ARCHIVO", help=argparse.SUPPRESS)
    args = p.parse_args(argv)

    if args.selftest:
        return selftest(args.selftest)
    if not args.url:
        return launch_gui()

    from . import spotify
    from .config import Settings
    from .core import run_job

    s = Settings.load()
    if args.modo:
        s.mode = args.modo
    if args.salida:
        s.output_dir = args.salida
    if args.sin_normalizar:
        s.normalize = False

    try:
        col = spotify.fetch(args.url, s.client_id, s.client_secret)
        if col.truncated:
            print("[aviso] Solo se leyeron las primeras 100 canciones (faltan claves de Spotify).")
        total = len(col.tracks)

        def on_event(e):
            if e.kind == "log":
                print(e.text)
            elif e.kind == "progress":
                print(f"\r{e.done}/{total}", end="", flush=True)

        res = run_job(col, s, on_event)
    except KeyboardInterrupt:
        print("\nCancelado.")
        return 130
    except Exception as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        return 1
    for d in res.discs:
        print(f"Disco {d.number}: {len(d.items)} canciones → {d.folder}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
