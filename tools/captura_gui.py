"""Captura la interfaz con datos de ejemplo, sin red (para revisar el diseño).

Uso: DISPLAY=:99 PYTHONPATH=. python tools/captura_gui.py <vacia|cargada|progreso|lista> salida.png
"""

import io
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("HOME", tempfile.mkdtemp())
os.environ.setdefault("APPDATA", tempfile.mkdtemp())

from PIL import Image, ImageDraw, ImageGrab  # noqa: E402

from listacd import cd, core, gui, spotify  # noqa: E402
from listacd.spotify import Track  # noqa: E402

SONGS = [("Bohemian Rhapsody", "Queen", 354), ("Hotel California", "Eagles", 391),
         ("Sweet Child O' Mine", "Guns N' Roses", 356), ("Billie Jean", "Michael Jackson", 294),
         ("Despechá", "ROSALÍA", 157), ("Tití Me Preguntó", "Bad Bunny", 243),
         ("La Bachata", "Manuel Turizo", 162), ("Wonderwall", "Oasis", 258),
         ("Smells Like Teen Spirit", "Nirvana", 301), ("Mr. Brightside", "The Killers", 222),
         ("Africa", "TOTO", 295), ("Take On Me", "a-ha", 225), ("Livin' On A Prayer", "Bon Jovi", 249),
         ("Don't Stop Me Now", "Queen", 209), ("Back In Black", "AC/DC", 255)] * 3


def main(state: str, out: str, w: int = 1366, h: int = 768):
    app = gui.App()
    app.drive_menu = None if not app.drive_menu else app.drive_menu
    if state != "vacia":
        col = spotify.Collection(name="Viaje en coche", kind="playlist", owner="antonio",
                                 tracks=[Track(title=t, artists=[a], duration_ms=d * 1000) for t, a, d in SONGS])
        img = Image.new("RGB", (300, 300))
        dr = ImageDraw.Draw(img)
        for y in range(300):
            dr.line([(0, y), (300, y)], fill=(40 + y // 4, 40 + y // 6, 60))
        b = io.BytesIO()
        img.save(b, "PNG")
        app._on_loaded(col, b.getvalue())
        for i in (5, 6, 7):
            app.excluded.add(i)
            app._retag(i)
        app._update_plan()
    if state == "progreso":
        app.busy = True
        app.t0 = time.time() - 60
        for i in range(1, 12):
            if i not in app.excluded:
                app._on_event(core.Event("track", index=i, status=core.DONE))
        app._on_event(core.Event("track", index=12, status=core.CONVERTING))
        app._on_event(core.Event("track", index=13, status=core.DOWNLOADING))
        app._on_event(core.Event("track", index=4, status=core.FAILED, text="No se encontró en YouTube Music"))
        app._on_event(core.Event("progress", done=12, total=42))
        app._set_go(False, "Preparando…")
        app._show_progress()
        app.cancel_btn.grid(row=10, padx=16, pady=(6, 0), sticky="ew")
    elif state == "lista":
        pairs = [(i, t.duration_s) for i, t in enumerate(app.collection.tracks, 1) if i not in app.excluded]
        discs = cd.estimate(pairs, "audio")
        for d in discs:
            d.folder = Path(tempfile.gettempdir())
        for d in discs:
            for it in d.items:
                app._on_event(core.Event("track", index=it.index, status=core.DONE))
        app.burned.add(1)
        app._on_job_done(core.JobResult(folder=Path(tempfile.gettempdir()), mode="audio", discs=discs))
    app.geometry(f"{w}x{h}+0+0")

    def snap():
        app.update()
        ImageGrab.grab(bbox=(0, 0, w, h), xdisplay=os.environ.get("DISPLAY")).save(out)
        app.destroy()

    app.after(1500, snap)
    app.mainloop()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
