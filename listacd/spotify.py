"""Lectura de metadatos de listas, álbumes y canciones de Spotify.

Formas de leer una lista:
  1. API oficial de Spotify (spotipy) si hay claves: lista completa con todos los metadatos.
  2. Página "embed" pública, sin claves: solo las primeras 100 canciones de una lista.
  3. Enlaces de canciones pegados (en Spotify: Ctrl+A y Ctrl+C dentro de la lista): sin claves
     y sin límite; se lee cada canción por separado.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import requests

URL_RE = re.compile(
    r"(?:open\.spotify\.com/(?:intl-[a-z]{2}/)?(?:embed/)?|spotify:)"
    r"(?P<kind>playlist|album|track)[/:](?P<id>[A-Za-z0-9]{22})"
)

TRACK_RE = re.compile(r"(?:open\.spotify\.com/(?:intl-[a-z]{2}/)?(?:embed/)?track/|spotify:track:)([A-Za-z0-9]{22})")
def pasted_name() -> str:
    """Nombre por defecto de una lista pegada. Con fecha y hora para que cada una tenga su carpeta."""
    from datetime import datetime

    return datetime.now().strftime("Mi lista del %d-%m-%Y, %H.%M")

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
    unknown: bool = False  # pista de un CD de audio sin identificar: no se sabe qué canción es

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
    warning: str = ""

    @property
    def duration_s(self) -> float:
        return sum(t.duration_s for t in self.tracks)


def parse_url(url: str) -> tuple[str, str]:
    m = URL_RE.search(url.strip())
    if not m:
        raise ValueError(f"No parece un enlace válido de Spotify: {url}")
    return m.group("kind"), m.group("id")


def parse_input(text: str) -> tuple[str, str | list[str]]:
    """Devuelve ("playlist"|"album"|"track", id) o ("tracks", [ids]) si se pegaron varias canciones."""
    ids = list(dict.fromkeys(TRACK_RE.findall(text or "")))  # sin repetidas, en orden
    if len(ids) > 1:
        return "tracks", ids
    return parse_url(text or "")


def fetch(url: str, client_id: str = "", client_secret: str = "", progress=None) -> Collection:
    """Lee una lista, álbum, canción o varias canciones pegadas.

    progress(hechas, total) se llama al leer canciones pegadas, que puede tardar.
    """
    kind, sid = parse_input(url)
    if kind == "tracks":
        return fetch_tracks(sid, client_id, client_secret, progress)
    if client_id and client_secret:
        try:
            return _fetch_api(kind, sid, client_id, client_secret)
        except Exception as exc:  # p.ej. listas editoriales bloqueadas por la API
            col = _fetch_embed(kind, sid)
            col.warning = f"La API de Spotify falló ({exc}); se usó la página pública."
            return col
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


def _fetch_api(kind: str, sid: str, client_id: str, client_secret: str) -> Collection:
    import spotipy
    from spotipy.cache_handler import MemoryCacheHandler
    from spotipy.oauth2 import SpotifyClientCredentials

    auth = SpotifyClientCredentials(
        client_id=client_id, client_secret=client_secret, cache_handler=MemoryCacheHandler()
    )
    sp = spotipy.Spotify(auth_manager=auth, retries=5, requests_timeout=20)

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


# ------------------------------------------------------------- canciones pegadas


def fetch_tracks(ids: list[str], client_id: str = "", client_secret: str = "", progress=None) -> Collection:
    col = Collection(name=pasted_name(), kind="tracks")
    found: dict[str, Track] = {}
    if client_id and client_secret:
        try:
            found = _tracks_api(ids, client_id, client_secret, progress)
        except Exception:
            found = {}
    missing = [i for i in ids if i not in found]
    if missing:
        found.update(_tracks_embed(missing, progress, done_before=len(ids) - len(missing), total=len(ids)))
    col.tracks = [found[i] for i in ids if i in found]
    lost = len(ids) - len(col.tracks)
    if lost:
        col.warning = (f"{lost} {'canción no se pudo' if lost == 1 else 'canciones no se pudieron'} leer de Spotify. "
                       "Vuelve a pegarlas más tarde si las echas en falta.")
    covers = [t.cover_url for t in col.tracks if t.cover_url]
    col.cover_url = covers[0] if covers else ""
    return col


def _tracks_api(ids, client_id, client_secret, progress) -> dict[str, Track]:
    import spotipy
    from spotipy.cache_handler import MemoryCacheHandler
    from spotipy.oauth2 import SpotifyClientCredentials

    sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
        client_id=client_id, client_secret=client_secret, cache_handler=MemoryCacheHandler()),
        retries=5, requests_timeout=20)
    out = {}
    for k in range(0, len(ids), 50):
        for t in sp.tracks(ids[k:k + 50]).get("tracks", []):
            if t and t.get("id"):
                out[t["id"]] = _track_from_api(t)
        if progress:
            progress(min(k + 50, len(ids)), len(ids))
    return out


def _tracks_embed(ids, progress, done_before=0, total=0, workers=6) -> dict[str, Track]:
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "es-ES,es;q=0.9"})

    def one(tid: str) -> Track | None:
        for attempt in range(4):
            try:
                r = session.get(f"https://open.spotify.com/embed/track/{tid}", timeout=20)
                if r.status_code == 429 or r.status_code >= 500:
                    time.sleep(float(r.headers.get("Retry-After") or 2 ** attempt))
                    continue
                r.raise_for_status()
                t = parse_embed_html(r.text, "track").tracks[0]
                t.spotify_id = t.spotify_id or tid
                return t
            except (requests.RequestException, RuntimeError, KeyError, IndexError, ValueError):
                time.sleep(2 ** attempt)
        return None

    out, done = {}, done_before
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(one, tid): tid for tid in ids}
        for fut in as_completed(futures):
            done += 1
            t = fut.result()
            if t:
                out[futures[fut]] = t
            if progress and (done % 5 == 0 or done == total):
                progress(done, total or len(ids))
    return out


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
