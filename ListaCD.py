"""Lanzador de ListaCD (usado también por PyInstaller para crear el .exe)."""

import sys

from listacd.cli import main

if __name__ == "__main__":
    sys.exit(main())
