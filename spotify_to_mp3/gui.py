"""Ventana sencilla (tkinter, incluido con Python) para no tener que usar la terminal."""

from __future__ import annotations

import queue
import threading
from pathlib import Path


def run_gui() -> None:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    from tkinter.scrolledtext import ScrolledText

    from .core import download_collection

    root = tk.Tk()
    root.title("Spotify → MP3")
    root.geometry("720x520")
    root.minsize(520, 380)

    msgs: queue.Queue[str] = queue.Queue()
    url_var = tk.StringVar()
    out_var = tk.StringVar(value=str(Path.home() / "Music"))
    fmt_var = tk.StringVar(value="MP3 320 kbps")
    num_var = tk.BooleanVar(value=False)

    frm = ttk.Frame(root, padding=12)
    frm.pack(fill="both", expand=True)
    frm.columnconfigure(1, weight=1)

    ttk.Label(frm, text="Enlace de Spotify:").grid(row=0, column=0, sticky="w")
    ttk.Entry(frm, textvariable=url_var).grid(row=0, column=1, columnspan=2, sticky="ew", pady=4)

    ttk.Label(frm, text="Guardar en:").grid(row=1, column=0, sticky="w")
    ttk.Entry(frm, textvariable=out_var).grid(row=1, column=1, sticky="ew", pady=4)
    ttk.Button(
        frm, text="Elegir…",
        command=lambda: out_var.set(filedialog.askdirectory() or out_var.get()),
    ).grid(row=1, column=2, padx=(6, 0))

    ttk.Label(frm, text="Calidad:").grid(row=2, column=0, sticky="w")
    ttk.Combobox(
        frm, textvariable=fmt_var, state="readonly",
        values=["MP3 320 kbps", "MP3 V0 (VBR)", "Original sin recodificar (Opus/M4A)"],
    ).grid(row=2, column=1, sticky="w", pady=4)
    ttk.Checkbutton(frm, text="Numerar canciones", variable=num_var).grid(row=2, column=2, sticky="w")

    btn = ttk.Button(frm, text="Descargar")
    btn.grid(row=3, column=0, columnspan=3, pady=8, sticky="ew")

    log_box = ScrolledText(frm, height=16, state="disabled", font=("Consolas", 10))
    log_box.grid(row=4, column=0, columnspan=3, sticky="nsew")
    frm.rowconfigure(4, weight=1)

    def pump():
        while not msgs.empty():
            line = msgs.get()
            if line == "\x00done":
                btn.config(state="normal")
                continue
            log_box.config(state="normal")
            log_box.insert("end", line + "\n")
            log_box.see("end")
            log_box.config(state="disabled")
        root.after(100, pump)

    def start():
        url = url_var.get().strip()
        if not url:
            messagebox.showwarning("Falta el enlace", "Pega el enlace de una lista de Spotify.")
            return
        choice = fmt_var.get()
        fmt = "best" if choice.startswith("Original") else "mp3"
        bitrate = "V0" if "V0" in choice else "320"
        btn.config(state="disabled")

        def job():
            try:
                download_collection(
                    url, out_dir=out_var.get(), fmt=fmt, bitrate=bitrate,
                    numbered=num_var.get(), log=msgs.put,
                )
            except BaseException as exc:  # SystemExit incluido (p.ej. falta ffmpeg)
                msgs.put(f"Error: {exc}")
            finally:
                msgs.put("\x00done")

        threading.Thread(target=job, daemon=True).start()

    btn.config(command=start)
    pump()
    root.mainloop()
