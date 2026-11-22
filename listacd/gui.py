"""Interfaz gráfica de ListaCD (CustomTkinter)."""

from __future__ import annotations

import io
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from . import __version__, burner, cd, spotify
from .config import APP_NAME, Settings, cache_size, clear_cache, open_path, resource_dir
from .core import CONVERTING, DONE, DOWNLOADING, FAILED, SEARCHING, Event, JobResult, run_job

# Paleta «salpicadero de noche»: grafito con luz ámbar.
ACCENT = "#D97706"
ACCENT_HOVER = "#B45309"
ACCENT_SOFT = "#F59E0B"
OK_GREEN = "#4ADE80"
WARN = "#FBBF24"
ERR = "#F87171"
BG = "#121212"
CARD = "#1C1C1E"
CARD_2 = "#2A2A2D"
HOVER = "#36363A"
MUTED = "#A1A1AA"
DIM = "#6B6B73"
TEXT = "#F4F4F5"
FAMILY = "Segoe UI" if sys.platform == "win32" else None

MODE_LABELS = {"audio": "CD de audio", "mp3": "CD MP3"}
MODE_HELP = {
    "audio": "Calidad CD, sin pasar por MP3. Suena en\ncualquier radio. ~18–20 canciones por disco.",
    "mp3": "MP3 320 kbps, ~60–80 canciones por disco.\nSolo si tu radio pone «MP3» en el frontal.",
}
# Símbolos tipográficos: los emojis de color no se ven bien en Tk/Windows
STATUS_ICONS = {SEARCHING: "● Buscando", DOWNLOADING: "● Descargando",
                CONVERTING: "● Convirtiendo", DONE: "✓ Lista", FAILED: "✕ Error"}
CHECK_ON, CHECK_OFF = "☑", "☐"


def font(size: int = 13, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=FAMILY, size=size, weight=weight) if FAMILY else ctk.CTkFont(size=size, weight=weight)


class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, master: "App"):
        super().__init__(master)
        self.app = master
        s = master.settings
        self.title("Ajustes")
        self.resizable(False, False)
        self.configure(fg_color=BG)
        self.transient(master)
        self.after(100, self.grab_set)

        pad = {"padx": 20, "sticky": "ew"}
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="Carpeta de destino", font=master.f_bold).grid(row=0, pady=(20, 4), **pad)
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.grid(row=1, **pad)
        row.grid_columnconfigure(0, weight=1)
        self.out = ctk.CTkEntry(row)
        self.out.insert(0, s.output_dir)
        self.out.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(row, text="Elegir…", width=90, fg_color=CARD_2, hover_color=HOVER,
                      command=self._pick).grid(row=0, column=1, padx=(8, 0))

        ctk.CTkLabel(self, text="Claves de Spotify (para listas de más de 100 canciones)",
                     font=master.f_bold).grid(row=2, pady=(18, 4), **pad)
        help_txt = ("Gratis: entra en developer.spotify.com/dashboard, pulsa «Create app»,\n"
                    "marca «Web API», guarda y copia aquí el Client ID y el Client secret.")
        ctk.CTkLabel(self, text=help_txt, text_color=MUTED, justify="left").grid(row=3, **pad)
        ctk.CTkButton(self, text="Abrir el panel de desarrolladores de Spotify", fg_color=CARD_2,
                      hover_color=HOVER,
                      command=lambda: webbrowser.open("https://developer.spotify.com/dashboard")
                      ).grid(row=4, pady=6, **pad)
        self.cid = ctk.CTkEntry(self, placeholder_text="Client ID")
        self.cid.insert(0, s.client_id)
        self.cid.grid(row=5, pady=4, **pad)
        self.csec = ctk.CTkEntry(self, placeholder_text="Client secret", show="•")
        self.csec.insert(0, s.client_secret)
        self.csec.grid(row=6, pady=4, **pad)

        ctk.CTkLabel(self, text="Avanzado", font=master.f_bold).grid(row=7, pady=(18, 4), **pad)
        adv = ctk.CTkFrame(self, fg_color="transparent")
        adv.grid(row=8, **pad)
        ctk.CTkLabel(adv, text="Cookies del navegador (si YouTube pide verificación\n"
                               "o tienes YouTube Premium para audio AAC 256 kbps):",
                     justify="left", text_color=MUTED).grid(row=0, column=0, sticky="w")
        self.cookies = ctk.CTkOptionMenu(adv, values=["Ninguno", "firefox", "chrome", "edge", "brave", "opera"],
                                         fg_color=CARD_2, button_color=CARD_2, width=120)
        self.cookies.set(s.cookies_browser or "Ninguno")
        self.cookies.grid(row=0, column=1, padx=(12, 0))
        ctk.CTkLabel(adv, text="Descargas simultáneas:", text_color=MUTED).grid(row=1, column=0, sticky="w", pady=8)
        self.workers = ctk.CTkOptionMenu(adv, values=["1", "2", "3", "4", "6", "8"],
                                         fg_color=CARD_2, button_color=CARD_2, width=120)
        self.workers.set(str(s.workers))
        self.workers.grid(row=1, column=1, padx=(12, 0))

        cache_row = ctk.CTkFrame(self, fg_color="transparent")
        cache_row.grid(row=9, pady=(8, 0), **pad)
        cache_row.grid_columnconfigure(0, weight=1)
        self.cache_lbl = ctk.CTkLabel(cache_row, text="", text_color=MUTED, anchor="w")
        self.cache_lbl.grid(row=0, column=0, sticky="w")
        ctk.CTkButton(cache_row, text="Vaciar caché", width=120, fg_color=CARD_2, hover_color=HOVER,
                      command=self._clear_cache).grid(row=0, column=1, padx=(12, 0))
        self._show_cache()

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.grid(row=10, pady=20, **pad)
        btns.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(btns, text="Cancelar", fg_color=CARD_2, hover_color=HOVER, width=110,
                      command=self.destroy).grid(row=0, column=1, padx=6)
        ctk.CTkButton(btns, text="Guardar", fg_color=ACCENT, hover_color=ACCENT_HOVER, width=110,
                      command=self._save).grid(row=0, column=2)

    def _show_cache(self):
        mb = cache_size() / 1e6
        self.cache_lbl.configure(text=f"Audios originales guardados: {mb:,.0f} MB\n"
                                      "(aceleran volver a preparar una lista)".replace(",", "."))

    def _clear_cache(self):
        if self.app.busy:
            messagebox.showinfo(APP_NAME, "Espera a que termine el trabajo en curso.", parent=self)
            return
        clear_cache()
        self._show_cache()

    def _pick(self):
        d = filedialog.askdirectory(parent=self, initialdir=self.out.get())
        if d:
            self.out.delete(0, "end")
            self.out.insert(0, d)

    def _save(self):
        s = self.app.settings
        s.output_dir = self.out.get().strip() or s.output_dir
        s.client_id = self.cid.get().strip()
        s.client_secret = self.csec.get().strip()
        c = self.cookies.get()
        s.cookies_browser = "" if c == "Ninguno" else c
        s.workers = int(self.workers.get())
        s.save()
        self.destroy()


class App(ctk.CTk):
    def __init__(self):
        ctk.set_appearance_mode("dark")
        super().__init__()
        self.settings = Settings.load()
        self.collection: spotify.Collection | None = None
        self.result: JobResult | None = None
        self.events: queue.Queue = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.drives: list[burner.Drive] = []
        self.track_status: dict[int, str] = {}
        self.track_errors: dict[int, str] = {}
        self.excluded: set[int] = set()
        self.burned: set[int] = set()
        self.burning = False

        self.title(f"{APP_NAME} {__version__} — Listas de Spotify a CD")
        self.geometry("1180x760")
        self.minsize(980, 640)
        self.configure(fg_color=BG)
        self._set_icon()

        self.f_title = font(24, "bold")
        self.f_h2 = font(18, "bold")
        self.f_bold = font(14, "bold")
        self.f_small = font(12)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self._build_header()
        self._build_input()
        self._build_body()
        self._style_tree()
        self._set_mode(self.settings.mode)
        self.after(80, self._pump)
        if burner.available():
            self.after(400, self._refresh_drives)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        if self.burning:
            if not messagebox.askyesno(
                    APP_NAME, "Se está grabando un disco. Si cierras ahora, el CD quedará inservible.\n\n"
                              "¿Cerrar de todas formas?", icon="warning"):
                return
        elif self.busy and not messagebox.askyesno(
                APP_NAME, "Todavía se están preparando canciones. ¿Cerrar y cancelar?"):
            return
        self.cancel.set()
        self.destroy()

    # ------------------------------------------------------------------ layout

    def _set_icon(self):
        ico = resource_dir() / "assets" / "listacd.ico"
        png = resource_dir() / "assets" / "listacd.png"
        try:
            if sys.platform == "win32" and ico.exists():
                self.iconbitmap(str(ico))
            elif png.exists():
                self._icon_img = tk.PhotoImage(file=str(png))
                self.iconphoto(True, self._icon_img)
        except tk.TclError:
            pass

    def _build_header(self):
        h = ctk.CTkFrame(self, fg_color="transparent")
        h.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 6))
        h.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(h, text="◉", font=font(30), text_color=ACCENT_SOFT).grid(row=0, column=0, rowspan=2, padx=(0, 12))
        ctk.CTkLabel(h, text=APP_NAME, font=self.f_title).grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(h, text="De tu lista de Spotify a un CD para el coche, con la mejor calidad posible",
                     text_color=MUTED).grid(row=1, column=1, sticky="w")
        ctk.CTkButton(h, text="Ajustes", width=110, fg_color=CARD_2, hover_color=HOVER,
                      command=lambda: SettingsDialog(self)).grid(row=0, column=2, rowspan=2)

    def _build_input(self):
        f = ctk.CTkFrame(self, fg_color=CARD, corner_radius=14)
        f.grid(row=1, column=0, sticky="ew", padx=24, pady=8)
        f.grid_columnconfigure(0, weight=1)
        self.url = ctk.CTkEntry(f, height=44, font=font(14), border_width=0, fg_color=CARD_2,
                                placeholder_text="Pega aquí el enlace de la lista de Spotify  (Compartir → Copiar enlace)")
        self.url.grid(row=0, column=0, sticky="ew", padx=(14, 8), pady=14)
        self.url.bind("<Return>", lambda e: self._load())
        self.paste_btn = ctk.CTkButton(f, text="Pegar", width=80, height=44, fg_color=CARD_2,
                                       hover_color=HOVER, command=self._paste)
        self.paste_btn.grid(row=0, column=1, pady=14)
        self.load_btn = ctk.CTkButton(f, text="Cargar lista", width=140, height=44, font=self.f_bold,
                                      fg_color=ACCENT, hover_color=ACCENT_HOVER, command=self._load)
        self.load_btn.grid(row=0, column=2, padx=14, pady=14)

    def _build_body(self):
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=2, column=0, sticky="nsew", padx=24, pady=(8, 18))
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)

        # ---- izquierda: lista
        left = ctk.CTkFrame(body, fg_color=CARD, corner_radius=14)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        left.grid_columnconfigure(1, weight=1)
        left.grid_rowconfigure(1, weight=1)

        self.cover_lbl = ctk.CTkLabel(left, text="♪", width=110, height=110, fg_color=CARD_2,
                                      corner_radius=10, font=font(40), text_color=MUTED)
        self.cover_lbl.grid(row=0, column=0, padx=16, pady=16)
        info = ctk.CTkFrame(left, fg_color="transparent")
        info.grid(row=0, column=1, sticky="w")
        self.pl_kind = ctk.CTkLabel(info, text="LISTA", text_color=MUTED, font=self.f_small)
        self.pl_kind.grid(row=0, column=0, sticky="w")
        self.pl_name = ctk.CTkLabel(info, text="Ninguna lista cargada", font=self.f_h2, anchor="w", justify="left")
        self.pl_name.grid(row=1, column=0, sticky="w")
        self.pl_meta = ctk.CTkLabel(info, text="Pega un enlace arriba para empezar", text_color=MUTED)
        self.pl_meta.grid(row=2, column=0, sticky="w")
        self.pl_warn = ctk.CTkLabel(info, text="", text_color=WARN, justify="left", wraplength=560)
        self.pl_warn.grid(row=3, column=0, sticky="w")

        tree_frame = tk.Frame(left, bg=CARD)
        tree_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=12, pady=(0, 12))
        tree_frame.grid_columnconfigure(0, weight=1)
        tree_frame.grid_rowconfigure(0, weight=1)
        cols = ("sel", "n", "title", "artist", "dur", "disc", "status")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", style="LCD.Treeview")
        for c, label, w, anchor, stretch in (
            ("sel", CHECK_ON, 34, "center", False),
            ("n", "#", 40, "e", False), ("title", "Canción", 280, "w", True),
            ("artist", "Artista", 200, "w", True), ("dur", "Duración", 76, "e", False),
            ("disc", "CD", 44, "center", False), ("status", "Estado", 130, "w", False),
        ):
            self.tree.heading(c, text=label, anchor=anchor)
            self.tree.column(c, width=w, anchor=anchor, stretch=stretch, minwidth=40)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb = ctk.CTkScrollbar(tree_frame, command=self.tree.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=sb.set)
        for tag, color in ((DONE, "#CDEBD5"), (FAILED, ERR), (DOWNLOADING, ACCENT_SOFT),
                           (CONVERTING, ACCENT_SOFT), (SEARCHING, MUTED), ("off", DIM)):
            self.tree.tag_configure(tag, foreground=color)
        self.tree.tag_configure("odd", background="#202022")
        self.tree.bind("<Button-1>", self._on_tree_click, add=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.sel_hint = ctk.CTkLabel(left, text="Pulsa ☑ para quitar o volver a poner una canción.",
                                     text_color=DIM, font=self.f_small, anchor="w")
        self.sel_hint.grid(row=2, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 10))

        # ---- derecha: opciones y acciones
        right = self.right = ctk.CTkScrollableFrame(body, fg_color=CARD, corner_radius=14, width=340)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        p = {"padx": 16, "sticky": "ew"}

        ctk.CTkLabel(right, text="1. Tipo de CD", font=self.f_bold, anchor="w").grid(row=0, pady=(16, 6), **p)
        self.mode_btn = ctk.CTkSegmentedButton(
            right, values=list(MODE_LABELS.values()), height=36, font=self.f_bold,
            fg_color=CARD_2, unselected_color=CARD_2, unselected_hover_color=HOVER,
            selected_color=ACCENT, selected_hover_color=ACCENT_HOVER,
            command=lambda v: self._set_mode("audio" if v == MODE_LABELS["audio"] else "mp3"))
        self.mode_btn.grid(row=1, **p)
        self.mode_help = ctk.CTkLabel(right, text="", text_color=MUTED, justify="left", anchor="w")
        self.mode_help.grid(row=2, pady=(6, 4), **p)
        self.norm_var = tk.BooleanVar(value=self.settings.normalize)
        ctk.CTkSwitch(right, text="Igualar volumen entre canciones", variable=self.norm_var,
                      progress_color=ACCENT, command=self._save_opts).grid(row=3, pady=(6, 0), **p)
        ctk.CTkLabel(right, text="Solo ajusta la ganancia, sin comprimir el sonido.",
                     text_color=MUTED, font=self.f_small, anchor="w").grid(row=4, **p)

        self.plan_card = ctk.CTkFrame(right, fg_color=CARD_2, corner_radius=10)
        self.plan_card.grid(row=5, pady=14, **p)
        self.plan_card.grid_columnconfigure(0, weight=1)
        self.plan_title = ctk.CTkLabel(self.plan_card, text="Discos necesarios: —", font=self.f_bold, anchor="w")
        self.plan_title.grid(row=0, padx=12, pady=(10, 2), sticky="ew")
        self.plan_lbl = ctk.CTkLabel(self.plan_card, text="", text_color=MUTED, justify="left", anchor="w")
        self.plan_lbl.grid(row=1, padx=12, pady=(0, 10), sticky="ew")

        ctk.CTkLabel(right, text="2. Preparar canciones", font=self.f_bold, anchor="w").grid(row=6, pady=(4, 6), **p)
        self.go_btn = ctk.CTkButton(right, text="Descargar y preparar", height=44, font=self.f_bold,
                                    fg_color=ACCENT, hover_color=ACCENT_HOVER, command=self._start,
                                    text_color_disabled="#FDE7C2",
                                    state="disabled")
        self.go_btn.configure(fg_color=CARD_2, text_color_disabled=DIM)
        self.go_btn.grid(row=7, **p)
        self.progress = ctk.CTkProgressBar(right, progress_color=ACCENT, height=10)
        self.progress.set(0)
        self._progress_grid = dict(row=8, pady=(10, 2), **p)  # se muestra al empezar
        self.status_lbl = ctk.CTkLabel(right, text="", text_color=MUTED, anchor="w", justify="left",
                                       wraplength=300)
        self.status_lbl.grid(row=9, **p)
        self.cancel_btn = ctk.CTkButton(right, text="Cancelar", fg_color=CARD_2, hover_color=HOVER,
                                        command=self._cancel)

        ctk.CTkLabel(right, text="3. Grabar", font=self.f_bold, anchor="w").grid(row=11, pady=(16, 6), **p)
        burn = ctk.CTkFrame(right, fg_color="transparent")
        burn.grid(row=12, **p)
        burn.grid_columnconfigure(0, weight=1)
        if burner.available():
            self.drive_menu = ctk.CTkOptionMenu(burn, values=["Buscando grabadoras…"], fg_color=CARD_2,
                                                button_color=CARD_2, dynamic_resizing=False)
            self.drive_menu.grid(row=0, column=0, sticky="ew")
            ctk.CTkButton(burn, text="↻", width=36, fg_color=CARD_2, hover_color=HOVER,
                          command=self._refresh_drives).grid(row=0, column=1, padx=(6, 0))
        else:
            self.drive_menu = None
            ctk.CTkLabel(burn, text="La grabación integrada solo funciona en Windows.\n"
                                    "Usa la carpeta o el archivo .cue con tu programa\nde grabación.",
                         text_color=MUTED, justify="left").grid(row=0, column=0, sticky="w")
        self.discs_frame = ctk.CTkFrame(right, fg_color="transparent")
        self.discs_frame.grid(row=13, pady=(10, 0), **p)
        self.discs_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self.discs_frame, text="Aparecerán aquí cuando las canciones estén listas.",
                     text_color=MUTED, anchor="w").grid(row=0, sticky="ew")
        self.open_btn = ctk.CTkButton(right, text="Abrir carpeta", fg_color=CARD_2, hover_color=HOVER,
                                      command=self._open_folder, state="disabled")
        self.open_btn.grid(row=14, pady=(10, 16), **p)

    def _style_tree(self):
        st = ttk.Style(self)
        st.theme_use("default")
        st.configure("LCD.Treeview", background=CARD, fieldbackground=CARD, foreground=TEXT,
                     rowheight=28, borderwidth=0, font=(FAMILY or "TkDefaultFont", 10))
        st.configure("LCD.Treeview.Heading", background=CARD_2, foreground=MUTED, relief="flat",
                     font=(FAMILY or "TkDefaultFont", 10, "bold"), padding=(6, 6))
        st.map("LCD.Treeview", background=[("selected", "#3A2A12")], foreground=[("selected", TEXT)])
        st.map("LCD.Treeview.Heading", background=[("active", CARD_2)])
        st.layout("LCD.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])

    # ------------------------------------------------------------- acciones UI

    def _paste(self):
        try:
            text = self.clipboard_get().strip()
        except tk.TclError:
            return
        self.url.delete(0, "end")
        self.url.insert(0, text)
        self._load()

    def _save_opts(self):
        self.settings.normalize = bool(self.norm_var.get())
        self.settings.save()

    def _set_mode(self, mode: str):
        if self.busy:
            self.mode_btn.set(MODE_LABELS[self.settings.mode])
            return
        self.settings.mode = mode
        self.settings.save()
        self.mode_btn.set(MODE_LABELS[mode])
        self.mode_help.configure(text=MODE_HELP[mode])
        self.result = None
        self._show_discs()
        self._update_plan()

    def _update_plan(self):
        col = self.collection
        if not col:
            return
        pairs = [(i, t.duration_s) for i, t in enumerate(col.tracks, 1) if i not in self.excluded]
        discs = cd.estimate(pairs, self.settings.mode)
        for iid in self.tree.get_children():
            self.tree.set(iid, "disc", "")
        self._apply_plan(discs, estimate=True)
        if not self.busy:
            self._set_go(bool(pairs))

    def _apply_plan(self, discs: list[cd.Disc], estimate: bool):
        n = len(discs)
        kind = "de 80 min" if self.settings.mode == "audio" else "de 700 MB"
        pre = "≈ " if estimate else ""
        if n == 0:
            self.plan_title.configure(text="Ninguna canción seleccionada")
            self.plan_lbl.configure(text="")
            return
        self.plan_title.configure(text=f"{pre}{n} CD-R {kind}")
        lines = []
        for d in discs:
            size = (f"{cd.fmt_time(d.seconds)}" if self.settings.mode == "audio"
                    else f"{d.size / 1e6:.0f} MB · {cd.fmt_time(d.seconds)}")
            lines.append(f"Disco {d.number}: {len(d.items)} canciones · {size}")
        self.plan_lbl.configure(text="\n".join(lines[:12]) + ("\n…" if len(lines) > 12 else ""))
        for d in discs:
            for it in d.items:
                iid = str(it.index)
                if self.tree.exists(iid):
                    self.tree.set(iid, "disc", d.number)

    def _load(self):
        if self.busy:
            return
        url = self.url.get().strip()
        if not url:
            return
        try:
            spotify.parse_url(url)
        except ValueError:
            messagebox.showwarning(APP_NAME, "Ese enlace no parece de Spotify.\n\n"
                                   "En Spotify: «…» de la lista → Compartir → Copiar enlace.")
            return
        self.load_btn.configure(state="disabled", text="Cargando…")
        s = self.settings

        def job():
            try:
                col = spotify.fetch(url, s.client_id, s.client_secret)
                cover = None
                if col.cover_url:
                    from .downloader import fetch_image
                    cover = fetch_image(col.cover_url)
                self.events.put(("loaded", col, cover))
            except Exception as exc:
                self.events.put(("load_error", exc))

        threading.Thread(target=job, daemon=True).start()

    def _on_loaded(self, col: spotify.Collection, cover: bytes | None):
        self.load_btn.configure(state="normal", text="Cargar lista")
        self.collection = col
        self.result = None
        kinds = {"playlist": "LISTA", "album": "ÁLBUM", "track": "CANCIÓN"}
        self.pl_kind.configure(text=kinds.get(col.kind, ""))
        name = col.name if len(col.name) < 50 else col.name[:48] + "…"
        self.pl_name.configure(text=name)
        meta = f"{len(col.tracks)} canciones · {cd.fmt_time(col.duration_s)}"
        if col.owner:
            meta = f"{col.owner} · {meta}"
        self.pl_meta.configure(text=meta)
        warn = col.warning
        if col.truncated:
            warn = ("Solo se han podido leer las primeras 100 canciones. Para listas más largas "
                    "añade tus claves de Spotify en ⚙ Ajustes (es gratis).")
        self.pl_warn.configure(text=warn)
        if cover:
            try:
                from PIL import Image

                img = Image.open(io.BytesIO(cover))
                self._cover = ctk.CTkImage(img, size=(110, 110))
                self.cover_lbl.configure(image=self._cover, text="")
            except Exception:
                pass
        else:
            self.cover_lbl.configure(image=None, text="♪")

        self.tree.delete(*self.tree.get_children())
        self.track_status.clear()
        self.track_errors.clear()
        self.excluded.clear()
        self.burned.clear()
        for i, t in enumerate(col.tracks, 1):
            self.tree.insert("", "end", iid=str(i),
                             values=(CHECK_ON, i, t.title, t.artist, cd.fmt_time(t.duration_s), "", ""),
                             tags=("odd",) if i % 2 else ())
        self._update_plan()
        self._show_discs()
        self.status_lbl.configure(text="")
        self.progress.set(0)

    def _start(self):
        if not self.collection or self.busy:
            return
        self.busy = True
        self.cancel.clear()
        self.result = None
        self._show_discs()
        self._set_go(False, "Preparando…")
        self._show_progress()
        self.load_btn.configure(state="disabled")
        self.cancel_btn.grid(row=10, padx=16, pady=(6, 0), sticky="ew")
        self.progress.set(0)
        self.status_lbl.configure(text="Empezando…")
        self.track_errors.clear()
        self.burned.clear()
        for iid in self.tree.get_children():
            self.tree.set(iid, "status", "")
            self._retag(int(iid))
        self.t0 = time.time()
        col, s = self.collection, self.settings
        include = {i for i in range(1, len(col.tracks) + 1) if i not in self.excluded}

        def job():
            try:
                res = run_job(col, s, on_event=lambda e: self.events.put(("event", e)),
                              cancel=self.cancel, include=include)
                self.events.put(("job_done", res))
            except Exception as exc:
                self.events.put(("job_error", exc))

        threading.Thread(target=job, daemon=True).start()

    def _cancel(self):
        self.cancel.set()
        self.status_lbl.configure(text="Cancelando… (termina las canciones en curso)")

    def _on_event(self, e: Event):
        if e.kind == "track":
            iid = str(e.index)
            if self.tree.exists(iid):
                self.tree.set(iid, "status", STATUS_ICONS.get(e.status, e.status))
                self.track_status[e.index] = e.status
                if e.status == FAILED:
                    self.track_errors[e.index] = e.text
                self._retag(e.index)
        elif e.kind == "progress":
            self.progress.set(e.done / max(1, e.total))
            elapsed = time.time() - self.t0
            eta = elapsed / e.done * (e.total - e.done) if e.done else 0
            self.status_lbl.configure(text=f"{e.done} de {e.total} canciones · quedan ~{cd.fmt_time(eta)}")
        elif e.kind == "log":
            pass

    def _on_job_done(self, res: JobResult):
        self.busy = False
        self.cancel_btn.grid_forget()
        self._set_go(True, "Descargar y preparar")
        self.load_btn.configure(state="normal")
        if res.cancelled:
            self.status_lbl.configure(text="Cancelado.")
            return
        self.result = res
        self._apply_plan(res.discs, estimate=False)
        ok = sum(len(d.items) for d in res.discs)
        msg = f"✓ {ok} canciones listas en {len(res.discs)} disco(s)."
        if res.failed:
            msg += f"\n✕ {len(res.failed)} no se encontraron (ver lista)."
        self.status_lbl.configure(text=msg)
        self.progress.set(1)
        self.open_btn.configure(state="normal")
        self._show_discs()
        try:  # baja el panel derecho hasta los botones de grabar
            self.after(150, lambda: self.right._parent_canvas.yview_moveto(1.0))
        except Exception:
            pass

    def _show_discs(self):
        for w in self.discs_frame.winfo_children():
            w.destroy()
        res = self.result
        if not res or not res.discs:
            self.open_btn.configure(state="disabled")
            ctk.CTkLabel(self.discs_frame, text="Aparecerán aquí cuando las canciones estén listas.",
                         text_color=MUTED, anchor="w").grid(row=0, sticky="ew")
            return
        for r, d in enumerate(res.discs):
            dur = cd.fmt_time(d.seconds)
            done = d.number in self.burned
            label = (f"✓ Disco {d.number} grabado · grabar otra copia" if done
                     else f"Grabar disco {d.number}   ·   {len(d.items)} canciones · {dur}")
            ctk.CTkButton(
                self.discs_frame, text=label, height=38, anchor="w",
                fg_color="#1F3A28" if done else CARD_2, hover_color=ACCENT_HOVER,
                state="normal" if self.drive_menu else "disabled",
                command=lambda d=d: self._burn(d),
            ).grid(row=r, pady=3, sticky="ew")

    def _set_go(self, enabled: bool, text: str | None = None):
        """Botón principal: gris cuando no se puede pulsar, ámbar cuando sí."""
        kw = {"text": text} if text else {}
        busy_look = not enabled and text is not None
        self.go_btn.configure(state="normal" if enabled else "disabled",
                              fg_color=ACCENT if enabled or busy_look else CARD_2,
                              text_color_disabled="#FDE7C2" if busy_look else DIM, **kw)

    def _show_progress(self):
        if not self.progress.winfo_ismapped():
            self.progress.grid(**self._progress_grid)

    def _retag(self, index: int):
        iid = str(index)
        if not self.tree.exists(iid):
            return
        off = index in self.excluded
        tags = ["off"] if off else ([self.track_status[index]] if index in self.track_status else [])
        if index % 2:
            tags.append("odd")
        self.tree.item(iid, tags=tags)
        self.tree.set(iid, "sel", CHECK_OFF if off else CHECK_ON)

    def _on_tree_click(self, event):
        if self.tree.identify_region(event.x, event.y) == "heading":
            if self.tree.identify_column(event.x) == "#1" and self.collection and not self.busy:
                # Cabecera ☑: poner o quitar todas
                n = len(self.collection.tracks)
                self.excluded = set() if self.excluded else set(range(1, n + 1))
                for i in range(1, n + 1):
                    self._retag(i)
                self._invalidate()
            return
        if self.tree.identify_column(event.x) != "#1" or self.busy:
            return
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        i = int(iid)
        self.excluded.symmetric_difference_update({i})
        self._retag(i)
        self._invalidate()
        return "break"

    def _invalidate(self):
        """La selección cambió: el resultado anterior ya no corresponde."""
        if self.result:
            self.result = None
            self._show_discs()
        self._update_plan()

    def _on_tree_select(self, _event=None):
        sel = self.tree.selection()
        if sel and int(sel[0]) in self.track_errors and not self.busy:
            t = self.collection.tracks[int(sel[0]) - 1]
            self.status_lbl.configure(text=f"✕ {t.title}: {self.track_errors[int(sel[0])]}")

    def _open_folder(self):
        if self.result:
            open_path(self.result.folder)

    # ---------------------------------------------------------------- grabación

    def _refresh_drives(self):
        if not self.drive_menu:
            return

        def job():
            try:
                self.events.put(("drives", burner.list_drives()))
            except Exception as exc:
                self.events.put(("drives_error", exc))

        threading.Thread(target=job, daemon=True).start()

    def _on_drives(self, drives: list[burner.Drive]):
        self.drives = drives
        if drives:
            names = [str(d) for d in drives]
            self.drive_menu.configure(values=names)
            self.drive_menu.set(names[0])
        else:
            self.drive_menu.configure(values=["No se encontró grabadora"])
            self.drive_menu.set("No se encontró grabadora")

    def _selected_drive(self) -> burner.Drive | None:
        name = self.drive_menu.get() if self.drive_menu else ""
        return next((d for d in self.drives if str(d) == name), None)

    def _burn(self, disc: cd.Disc):
        if self.busy:
            return
        drive = self._selected_drive()
        if not drive:
            messagebox.showwarning(APP_NAME, "No se encontró ninguna grabadora de CD.\n"
                                   "Conéctala y pulsa ↻.")
            return
        self.busy = True
        self.status_lbl.configure(text="Comprobando el disco…")
        res = self.result

        def job():
            try:
                info = burner.media_info(drive)
                self.events.put(("media", disc, drive, info, res))
            except Exception as exc:
                self.events.put(("burn_error", exc))

        threading.Thread(target=job, daemon=True).start()

    def _on_media(self, disc: cd.Disc, drive: burner.Drive, info: burner.MediaInfo, res: JobResult):
        audio = res.mode == "audio"
        problem = info.message if not info.present else ""
        if info.present and not info.blank:
            problem = "El disco no está vacío. Introduce un CD-R virgen."
        elif info.present and audio and not info.writable_cd:
            problem = f"Hay un {info.kind} en la grabadora. Los CD de audio necesitan un CD-R."
        elif info.present and audio and info.free_seconds and disc.seconds + 2 * len(disc.items) > info.free_seconds:
            problem = (f"El disco solo tiene {cd.fmt_time(info.free_seconds)} libres y este CD "
                       f"necesita {cd.fmt_time(disc.seconds)}. Usa un CD-R de 80 minutos.")
        elif info.present and not audio and disc.size > info.free_bytes:
            problem = "No caben las canciones en este disco."
        if problem:
            self.busy = False
            self.status_lbl.configure(text=problem)
            messagebox.showwarning(APP_NAME, f"{problem}\n\nCuando lo tengas, vuelve a pulsar «Grabar disco {disc.number}».")
            return
        if not messagebox.askokcancel(
            APP_NAME,
            f"Se va a grabar el disco {disc.number} ({len(disc.items)} canciones, {cd.fmt_time(disc.seconds)}) "
            f"en {drive}.\n\nNo uses el ordenador para tareas pesadas mientras graba. ¿Continuar?"):
            self.busy = False
            self.status_lbl.configure(text="")
            return

        self.progress.set(0)
        self._show_progress()
        self.burning = True
        name = self.collection.name if self.collection else APP_NAME

        def prog(text, frac):
            self.events.put(("burn_progress", text, frac))

        def job():
            try:
                if audio:
                    burner.burn_audio(drive, [it.path for it in disc.items], prog)
                else:
                    burner.burn_data(drive, disc.folder, name, prog)
                self.events.put(("burn_done", disc))
            except Exception as exc:
                self.events.put(("burn_error", exc))

        threading.Thread(target=job, daemon=True).start()

    def _on_burn_done(self, disc: cd.Disc):
        self.busy = False
        self.burning = False
        self.burned.add(disc.number)
        self._show_discs()
        self.progress.set(1)
        self.status_lbl.configure(text=f"✓ Disco {disc.number} grabado.")
        nxt = disc.number + 1
        extra = (f"\n\nMete otro CD-R virgen y pulsa «Grabar disco {nxt}»."
                 if self.result and nxt <= len(self.result.discs) else "")
        messagebox.showinfo(APP_NAME, f"¡Disco {disc.number} grabado!{extra}")

    def _on_burn_error(self, exc: Exception):
        self.busy = False
        self.burning = False
        self.status_lbl.configure(text=f"Error al grabar: {exc}")
        cue_hint = ""
        if self.result and self.result.mode == "audio":
            cue_hint = ("\n\nAlternativa: graba el archivo «.cue» de la carpeta del disco con "
                        "ImgBurn (gratis): «Write image file to disc». Además incluye los títulos (CD-Text).")
        messagebox.showerror(APP_NAME, f"No se pudo grabar el disco:\n{exc}{cue_hint}")

    # --------------------------------------------------------------- bucle de eventos

    def _pump(self):
        try:
            for _ in range(200):
                msg = self.events.get_nowait()
                kind = msg[0]
                if kind == "event":
                    self._on_event(msg[1])
                elif kind == "loaded":
                    self._on_loaded(msg[1], msg[2])
                elif kind == "load_error":
                    self.load_btn.configure(state="normal", text="Cargar lista")
                    messagebox.showerror(APP_NAME, f"No se pudo leer la lista:\n{msg[1]}\n\n"
                                         "Comprueba que es pública y que tienes internet.")
                elif kind == "job_done":
                    self._on_job_done(msg[1])
                elif kind == "job_error":
                    self._on_job_done(JobResult(folder=Path("."), mode=self.settings.mode, cancelled=True))
                    self.status_lbl.configure(text=f"Error: {msg[1]}")
                    messagebox.showerror(APP_NAME, f"Ha ocurrido un error:\n{msg[1]}")
                elif kind == "drives":
                    self._on_drives(msg[1])
                elif kind == "drives_error":
                    self._on_drives([])
                elif kind == "media":
                    self._on_media(*msg[1:])
                elif kind == "burn_progress":
                    self.status_lbl.configure(text=msg[1])
                    self.progress.set(msg[2])
                elif kind == "burn_done":
                    self._on_burn_done(msg[1])
                elif kind == "burn_error":
                    self._on_burn_error(msg[1])
        except queue.Empty:
            pass
        self.after(80, self._pump)


def run_gui() -> None:
    app = App()
    app.mainloop()
