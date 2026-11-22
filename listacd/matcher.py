"""Busca en YouTube Music la versión que mejor coincide con cada canción de Spotify."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

from .spotify import Track

# Palabras que indican otra versión de la canción. Si aparecen en el resultado
# pero no en el título original, se penaliza.
BAD_WORDS = (
    "live", "en vivo", "directo", "karaoke", "instrumental", "cover", "remix",
    "sped up", "slowed", "reverb", "8d", "nightcore", "acoustic", "acustico",
    "acústico", "version", "edit", "mix", "reaction", "tutorial", "lyrics video",
)


@dataclass
class Match:
    video_id: str
    title: str
    artists: list[str]
    duration_s: float
    score: float
    thumbnail: str = ""

    @property
    def url(self) -> str:
        return f"https://music.youtube.com/watch?v={self.video_id}"


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"\(feat[^)]*\)|\[feat[^]]*\]|feat\..*|ft\..*", " ", text)
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _sim(a: str, b: str) -> float:
    a, b = normalize(a), normalize(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ratio = SequenceMatcher(None, a, b).ratio()
    # "Canción - Remastered 2011" contiene "Canción"
    if a in b or b in a:
        ratio = max(ratio, 0.85)
    return ratio


def score(track: Track, title: str, artists: list[str], duration_s: float) -> float:
    """Puntuación de 0 a ~1. Por debajo de ~0.55 se considera que no coincide."""
    t_score = _sim(track.title, title)
    joined = " ".join(artists)
    a_score = max([_sim(a, joined) for a in track.artists] + [_sim(track.artist, joined)])
    # El artista a veces sale en el título del vídeo ("Artista - Canción")
    if a_score < 0.6 and normalize(track.artists[0]) in normalize(title):
        a_score = 0.8

    s = 0.5 * t_score + 0.3 * a_score

    if track.duration_ms and duration_s:
        diff = abs(track.duration_s - duration_s)
        if diff <= 3:
            s += 0.2
        elif diff <= 8:
            s += 0.1
        elif diff > 30:
            s -= 0.3
        else:
            s -= 0.1 * (diff / 30)
    else:
        s += 0.05

    orig, cand = normalize(track.title), normalize(title)
    for w in BAD_WORDS:
        if re.search(rf"\b{w}\b", cand) and not re.search(rf"\b{w}\b", orig):
            s -= 0.15
    return s


def _best_thumb(thumbs) -> str:
    if not thumbs:
        return ""
    url = max(thumbs, key=lambda t: t.get("width") or 0)["url"]
    # Las miniaturas de YT Music admiten pedir más resolución cambiando el sufijo
    return re.sub(r"=w\d+-h\d+.*$", "=w1200-h1200-l90-rj", url)


class Matcher:
    MIN_SCORE = 0.55

    def __init__(self):
        from ytmusicapi import YTMusic

        self.yt = YTMusic()

    def _ytm_candidates(self, query: str, flt: str) -> list[Match]:
        try:
            results = self.yt.search(query, filter=flt, limit=10)
        except Exception:
            return []
        out = []
        for r in results:
            vid = r.get("videoId")
            if not vid:
                continue
            out.append(
                Match(
                    video_id=vid,
                    title=r.get("title", ""),
                    artists=[a["name"] for a in (r.get("artists") or []) if a.get("name")],
                    duration_s=r.get("duration_seconds") or 0,
                    score=0,
                    thumbnail=_best_thumb(r.get("thumbnails")),
                )
            )
        return out

    def ranked(self, track: Track, limit: int = 4) -> list[Match]:
        """Todas las versiones aceptables, de mejor a peor (para cuando la primera no se descarga)."""
        query = f"{track.artists[0] if track.artists else ''} {track.title}".strip()
        seen: dict[str, Match] = {}
        for flt, bonus in (("songs", 0.0), ("videos", -0.05)):
            for c in self._ytm_candidates(query, flt):
                c.score = score(track, c.title, c.artists, c.duration_s) + bonus
                if c.video_id not in seen or c.score > seen[c.video_id].score:
                    seen[c.video_id] = c
        good = [c for c in seen.values() if c.score >= self.MIN_SCORE]
        return sorted(good, key=lambda c: c.score, reverse=True)[:limit]

    def find(self, track: Track) -> Match | None:
        best: Match | None = None

        def consider(cands: list[Match], bonus: float = 0.0):
            nonlocal best
            for c in cands:
                c.score = score(track, c.title, c.artists, c.duration_s) + bonus
                if best is None or c.score > best.score:
                    best = c

        # 1) Por ISRC: si existe, suele dar la grabación exacta
        if track.isrc:
            consider(self._ytm_candidates(track.isrc, "songs")[:2], bonus=0.1)
            if best and best.score >= 0.9:
                return best

        # 2) Canciones oficiales (pistas de "Topic", la mejor fuente de audio)
        query = f"{track.artists[0] if track.artists else ''} {track.title}".strip()
        consider(self._ytm_candidates(query, "songs"))
        if best and best.score >= 0.85:
            return best

        # 3) Vídeos (para temas que no están como "song")
        consider(self._ytm_candidates(query, "videos"), bonus=-0.05)

        if best and best.score >= self.MIN_SCORE:
            return best
        return None
