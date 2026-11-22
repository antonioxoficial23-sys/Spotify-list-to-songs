import json
import subprocess
from pathlib import Path

import pytest

from spotify_to_mp3 import core, downloader, spotify
from spotify_to_mp3.matcher import Match, score
from spotify_to_mp3.spotify import Track


@pytest.mark.parametrize("url,kind,sid", [
    ("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=abc", "playlist", "37i9dQZF1DXcBWIGoYBM5M"),
    ("https://open.spotify.com/intl-es/album/4aawyAB9vmqN3uQ7FjRGTy", "album", "4aawyAB9vmqN3uQ7FjRGTy"),
    ("spotify:track:11dFghVXANMlKmJXsNCbNl", "track", "11dFghVXANMlKmJXsNCbNl"),
])
def test_parse_url(url, kind, sid):
    assert spotify.parse_url(url) == (kind, sid)


def test_parse_url_invalid():
    with pytest.raises(ValueError):
        spotify.parse_url("https://example.com")


def test_parse_embed():
    data = {"props": {"pageProps": {"state": {"data": {"entity": {
        "name": "Mi lista", "subtitle": "Antonio",
        "coverArt": {"sources": [{"url": "a", "width": 60}, {"url": "b", "width": 640}]},
        "trackList": [
            {"uri": "spotify:track:1", "title": "Despacito", "subtitle": "Luis Fonsi, Daddy Yankee", "duration": 229000},
            {"uri": "spotify:episode:2", "title": "Podcast", "subtitle": "X", "entityType": "episode"},
        ],
    }}}}}}
    html = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script>'
    col = spotify.parse_embed_html(html, "playlist")
    assert col.name == "Mi lista" and col.cover_url == "b"
    assert len(col.tracks) == 1
    assert col.tracks[0].artists == ["Luis Fonsi", "Daddy Yankee"]
    assert col.tracks[0].duration_ms == 229000


def test_score_prefers_original():
    t = Track(title="Bohemian Rhapsody", artists=["Queen"], duration_ms=354000)
    good = score(t, "Bohemian Rhapsody", ["Queen"], 355)
    live = score(t, "Bohemian Rhapsody (Live Aid)", ["Queen"], 360)
    karaoke = score(t, "Bohemian Rhapsody Karaoke", ["Sing King"], 354)
    other = score(t, "Another One Bites the Dust", ["Queen"], 215)
    assert good > live > other
    assert good > karaoke
    assert good >= 0.9 and other < 0.55


def test_safe_name():
    assert downloader.safe_name('AC/DC: "Back" in Black?') == "AC_DC_ _Back_ in Black_"
    assert downloader.safe_name("con") == "_con"
    assert downloader.safe_name("  ...  ") == "sin_nombre"


def _fake_audio(stem: Path, ext="mp3") -> Path:
    out = stem.with_suffix("." + ext)
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-b:a", "192k", str(out)], check=True)
    return out


def test_full_pipeline(tmp_path, monkeypatch):
    col = spotify.Collection(name="Lista: Verano/2026", kind="playlist", tracks=[
        Track(title="Canción Uno", artists=["Artista A"], duration_ms=1000, album="Álbum", cover_url="http://x/cover"),
        Track(title="Canción Dos", artists=["Artista B", "Artista C"], duration_ms=1000),
        Track(title="No Existe", artists=["Nadie"], duration_ms=1000),
    ])
    monkeypatch.setattr(spotify, "fetch", lambda url: col)

    class FakeMatcher:
        def find(self, t):
            if t.title == "No Existe":
                return None
            return Match("vid", t.title, t.artists, 1, 1.0, thumbnail="http://x/thumb")

    jpeg = b"\xff\xd8\xff\xe0" + b"0" * 100
    monkeypatch.setattr(core, "Matcher", FakeMatcher)
    monkeypatch.setattr(core, "download_audio", lambda m, stem, fmt, br: _fake_audio(stem))
    monkeypatch.setattr(core, "fetch_image", lambda url: jpeg)

    res = core.download_collection("x", out_dir=tmp_path, numbered=True, log=lambda s: None)
    folder = tmp_path / "Lista_ Verano_2026"
    assert res.folder == folder
    assert sorted(p.name for p in folder.glob("*.mp3")) == [
        "1 - Artista A - Canción Uno.mp3", "2 - Artista B, Artista C - Canción Dos.mp3"]
    assert len(res.failed) == 1 and (folder / "_canciones_fallidas.txt").exists()
    m3u = (folder / "Lista_ Verano_2026.m3u8").read_text(encoding="utf-8").splitlines()
    assert m3u == ["#EXTM3U", "1 - Artista A - Canción Uno.mp3", "2 - Artista B, Artista C - Canción Dos.mp3"]

    from mutagen.id3 import ID3
    tags = ID3(folder / "2 - Artista B, Artista C - Canción Dos.mp3")
    assert tags["TIT2"].text == ["Canción Dos"]
    assert tags["TPE1"].text == ["Artista B, Artista C"]
    assert tags.getall("APIC")[0].data == jpeg

    # Segunda ejecución: no vuelve a descargar lo que ya existe
    res2 = core.download_collection("x", out_dir=tmp_path, numbered=True, log=lambda s: None)
    assert len(res2.skipped) == 2 and not res2.ok


def test_tag_opus(tmp_path):
    p = _fake_audio(tmp_path / "a", "opus")
    downloader.tag_file(p, Track(title="T", artists=["A"]), b"\xff\xd8\xff" + b"0" * 50)
    from mutagen import File
    f = File(p)
    assert f["title"] == ["T"] and "metadata_block_picture" in f
