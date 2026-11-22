"""Lectura de metadatos de listas, álbumes y canciones de Spotify.

Dos métodos:
  1. API oficial de Spotify (spotipy) si hay SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET.
     Devuelve la lista completa con todos los metadatos (álbum, número de pista, año...).
  2. Página "embed" pública de Spotify, sin credenciales. Sirve para salir del paso,
     pero solo trae título, artistas y duración, y Spotify la limita a ~100 canciones.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

import requests

URL_RE = re.compile(
    r"(?:open\.spotify\.com/(?:intl-[a-z]{2}/)?(?:embed/)?|spotify:)"
    r"(?P<kind>playlist|album|track)[/:](?P<id>[A-Za-z0-9]{22})"
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)


@dataclass
class Track:
    title: str
    artists: list[str]
    duration_ms: int = 0
    album: str = ""
    album_artist: str = ""
    track_number: int = 0
    disc_number: int = 1
    release_date: str = ""
    isrc: str = ""
    cover_url: str = ""
    spotify_id: str = ""

    @property
    def artist(self) -> str:
        return ", ".join(self.artists)

    @property
    def duration_s(self) -> float:
        return self.duration_ms / 1000


@dataclass
class Collection:
    name: str
    kind: str
    owner: str = ""
    cover_url: str = ""
    tracks: list[Track] = field(default_factory=list)
    truncated: bool = False  # True si se usó el embed y puede faltar algo


def parse_url(url: str) -> tuple[str, str]:
    m = URL_RE.search(url.strip())
    if not m:
        raise ValueError(f"No parece un enlace válido de Spotify: {url}")
    return m.group("kind"), m.group("id")


def _load_dotenv(path: str = ".env") -> None:
    """Carga KEY=VALOR de un archivo .env (si existe) sin pisar variables ya definidas."""
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except FileNotFoundError:
        pass


def fetch(url: str) -> Collection:
    kind, sid = parse_url(url)
    _load_dotenv()
    if os.environ.get("SPOTIFY_CLIENT_ID") and os.environ.get("SPOTIFY_CLIENT_SECRET"):
        try:
            return _fetch_api(kind, sid)
        except Exception as exc:  # p.ej. listas editoriales bloqueadas por la API
            print(f"[aviso] La API de Spotify falló ({exc}); uso la página pública.")
    return _fetch_embed(kind, sid)


# --------------------------------------------------------------------------- API


def _best_image(images) -> str:
    if not images:
        return ""
    return max(images, key=lambda i: (i.get("width") or 0))["url"]


def _track_from_api(t: dict, album: dict | None = None) -> Track:
    album = album or t.get("album") or {}
    return Track(
        title=t["name"],
        artists=[a["name"] for a in t.get("artists", [])],
        duration_ms=t.get("duration_ms", 0),
        album=album.get("name", ""),
        album_artist=", ".join(a["name"] for a in album.get("artists", [])),
        track_number=t.get("track_number", 0),
        disc_number=t.get("disc_number", 1),
        release_date=album.get("release_date", ""),
        isrc=(t.get("external_ids") or {}).get("isrc", ""),
        cover_url=_best_image(album.get("images")),
        spotify_id=t.get("id") or "",
    )


def _fetch_api(kind: str, sid: str) -> Collection:
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials

    sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(), retries=5)

    if kind == "track":
        t = sp.track(sid)
        tr = _track_from_api(t)
        return Collection(name=f"{tr.artist} - {tr.title}", kind=kind, tracks=[tr])

    if kind == "album":
        alb = sp.album(sid)
        col = Collection(
            name=alb["name"],
            kind=kind,
            owner=", ".join(a["name"] for a in alb["artists"]),
            cover_url=_best_image(alb.get("images")),
        )
        page = alb["tracks"]
        while page:
            for t in page["items"]:
                col.tracks.append(_track_from_api(t, alb))
            page = sp.next(page) if page.get("next") else None
        return col

    pl = sp.playlist(sid)
    col = Collection(
        name=pl["name"],
        kind=kind,
        owner=(pl.get("owner") or {}).get("display_name", ""),
        cover_url=_best_image(pl.get("images")),
    )
    page = pl["tracks"]
    while page:
        for item in page["items"]:
            t = item.get("track")
            # Se saltan episodios de podcast, archivos locales y huecos
            if not t or t.get("type") != "track" or t.get("is_local"):
                continue
            col.tracks.append(_track_from_api(t))
        page = sp.next(page) if page.get("next") else None
    return col


# ------------------------------------------------------------------------- embed


def _fetch_embed(kind: str, sid: str) -> Collection:
    r = requests.get(
        f"https://open.spotify.com/embed/{kind}/{sid}",
        headers={"User-Agent": USER_AGENT, "Accept-Language": "es-ES,es;q=0.9"},
        timeout=30,
    )
    r.raise_for_status()
    return parse_embed_html(r.text, kind)


def parse_embed_html(html: str, kind: str) -> Collection:
    m = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S
    )
    if not m:
        raise RuntimeError("No se pudo leer la página de Spotify (¿la lista es privada?).")
    data = json.loads(m.group(1))
    entity = data["props"]["pageProps"]["state"]["data"]["entity"]

    cover = ""
    sources = ((entity.get("coverArt") or {}).get("sources")) or []
    if sources:
        cover = max(sources, key=lambda s: s.get("width") or 0)["url"]

    name = entity.get("name") or entity.get("title") or "Spotify"
    col = Collection(name=name, kind=kind, owner=entity.get("subtitle", ""), cover_url=cover)

    if kind == "track":
        artists = [a["name"] for a in entity.get("artists", [])] or [entity.get("subtitle", "")]
        col.tracks.append(
            Track(title=name, artists=artists, duration_ms=entity.get("duration", 0),
                  cover_url=cover, spotify_id=entity.get("id", ""))
        )
        col.name = f"{', '.join(artists)} - {name}"
        return col

    for i, t in enumerate(entity.get("trackList", []), 1):
        if t.get("entityType", "track") != "track":
            continue
        artists = [a.strip() for a in t.get("subtitle", "").replace(" ", " ").split(",")]
        col.tracks.append(
            Track(
                title=t.get("title", ""),
                artists=[a for a in artists if a],
                duration_ms=t.get("duration", 0),
                album=name if kind == "album" else "",
                album_artist=col.owner if kind == "album" else "",
                track_number=i if kind == "album" else 0,
                cover_url=cover if kind == "album" else "",
                spotify_id=(t.get("uri") or "").rsplit(":", 1)[-1],
            )
        )
    col.truncated = len(col.tracks) >= 100
    return col
