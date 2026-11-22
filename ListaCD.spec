# PyInstaller: pyinstaller ListaCD.spec
# Antes, coloca ffmpeg.exe, ffprobe.exe y deno.exe en la carpeta bin/ (lo hace el workflow).
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files

datas = [("assets", "assets")]
binaries = [(str(p), "bin") for p in Path("bin").glob("*.exe")]
hiddenimports = ["pythoncom", "pywintypes", "win32com.client", "PIL._tkinter_finder"]

for pkg in ("yt_dlp_ejs", "customtkinter"):
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hiddenimports += h
datas += collect_data_files("ytmusicapi")

a = Analysis(
    ["ListaCD.py"],
    datas=datas,
    binaries=binaries,
    hiddenimports=hiddenimports,
    excludes=["matplotlib", "numpy", "pytest"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="ListaCD",
    icon="assets/listacd.ico",
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="ListaCD", upx=False)
