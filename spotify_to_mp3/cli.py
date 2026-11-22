"""Uso desde la terminal:

    python -m spotify_to_mp3 https://open.spotify.com/playlist/XXXX
"""

from __future__ import annotations

import argparse
import sys

from .core import download_collection


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        prog="spotify_to_mp3",
        description="Descarga una lista, álbum o canción de Spotify como una carpeta de MP3.",
    )
    p.add_argument("urls", nargs="*", help="Enlace(s) de Spotify (lista, álbum o canción)")
    p.add_argument("-o", "--salida", default=".", help="Carpeta donde crear la carpeta de la lista (por defecto, la actual)")
    p.add_argument(
        "-f", "--formato", choices=["mp3", "best"], default="mp3",
        help="mp3 (por defecto) o 'best' para guardar el audio original sin recodificar (Opus/M4A)",
    )
    p.add_argument(
        "-b", "--bitrate", default="320",
        help="Calidad del MP3: 320 (CBR, por defecto), 256, 192… o V0 (VBR de máxima calidad)",
    )
    p.add_argument("-j", "--hilos", type=int, default=4, help="Descargas simultáneas (por defecto 4)")
    p.add_argument("-n", "--numerar", action="store_true", help="Antepone el número de posición en la lista al nombre del archivo")
    p.add_argument("--gui", action="store_true", help="Abre la ventana gráfica")
    args = p.parse_args(argv)

    if args.gui or not args.urls:
        if not args.urls and sys.stdin.isatty() and not args.gui:
            url = input("Pega el enlace de la lista de Spotify: ").strip()
            if not url:
                p.print_help()
                return
            args.urls = [url]
        else:
            from .gui import run_gui

            run_gui()
            return

    for url in args.urls:
        try:
            download_collection(
                url, out_dir=args.salida, fmt=args.formato, bitrate=args.bitrate,
                workers=args.hilos, numbered=args.numerar,
            )
        except KeyboardInterrupt:
            print("\nCancelado.")
            sys.exit(130)
        except Exception as exc:
            msg = str(exc)
            if "ConnectionError" in type(exc).__name__ or "ProxyError" in type(exc).__name__:
                msg = f"No se pudo conectar con Spotify. Revisa tu conexión a internet.\n({exc})"
            print(f"Error: {msg}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
