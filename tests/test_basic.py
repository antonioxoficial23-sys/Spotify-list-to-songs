import json
import subprocess
from pathlib import Path

import pytest

from listacd import cd, core, downloader, spotify
from listacd.config import Settings
from listacd.matcher import Match, score
from listacd.spotify import Track


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
    assert col.duration_s == 229


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
    assert downloader.safe_name("Beyoncé – 東京", ascii_cd=True) == "Beyoncé – __"


def test_plan_audio_splits_by_time():
    items = [cd.Item(i, 240) for i in range(1, 51)]  # 50 canciones de 4 min = 200 min
    discs = cd.plan(items, "audio")
    assert len(discs) == 3
    for d in discs:
        assert d.seconds + cd.TRACK_GAP_SECONDS * (len(d.items) - 1) <= cd.AUDIO_CD_SECONDS
    assert [it.index for d in discs for it in d.items] == list(range(1, 51))


def test_plan_mp3_and_limits():
    discs = cd.estimate([240.0] * 100, "mp3")  # ~9,7 MB cada una
    assert len(discs) == 2 and len(discs[0].items) > 60
    many = cd.plan([cd.Item(i, 1, size=1000) for i in range(1, 301)], "mp3")
    assert [len(d.items) for d in many] == [255, 45]
    assert len(cd.plan([cd.Item(i, 10) for i in range(1, 121)], "audio")[0].items) == 99


def test_gain_never_clips():
    assert downloader.gain_for((-20.0, -10.0)) == 8.0   # sube hasta -12 LUFS
    assert downloader.gain_for((-20.0, -3.0)) == 2.0    # limitado por el pico (-1 dBTP)
    assert downloader.gain_for((-7.0, 0.5)) == -5.0     # baja las canciones muy fuertes
    assert downloader.gain_for(None) == 0.0


def _fake_original(cache: Path, vid: str, freq: int) -> Path:
    out = cache / f"{vid}.opus"
    if not out.exists():
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
             f"sine=frequency={freq}:duration=2:sample_rate=48000", "-c:a", "libopus", "-b:a", "160k", str(out)],
            check=True)
    return out


@pytest.fixture
def fake_env(tmp_path, monkeypatch):
    monkeypatch.setenv("LISTACD_CACHE", str(tmp_path / "cache"))
    col = spotify.Collection(name="Lista: Verano/2026", kind="playlist", tracks=[
        Track(title="Canción Uno", artists=["Artista A"], duration_ms=2000, album="Álbum", cover_url="http://x/c",
              spotify_id="a1"),
        Track(title="Canción Dos", artists=["Artista B", "Artista C"], duration_ms=2000, spotify_id="a2"),
        Track(title="No Existe", artists=["Nadie"], duration_ms=2000, spotify_id="a3"),
    ])

    class FakeMatcher:
        calls = 0

        def find(self, t):
            FakeMatcher.calls += 1
            if t.title == "No Existe":
                return None
            return Match(f"vid{t.spotify_id}", t.title, t.artists, 2, 1.0, thumbnail="http://x/t")

    from PIL import Image
    import io
    buf = io.BytesIO()
    Image.new("RGB", (1200, 1200), "red").save(buf, "PNG")
    monkeypatch.setattr(core, "download_original",
                        lambda m, cache, cookies: _fake_original(cache, m.video_id, 440 if m.video_id.endswith("1") else 880))
    monkeypatch.setattr(core, "fetch_image", lambda url: buf.getvalue())
    s = Settings(output_dir=str(tmp_path / "out"), workers=2)
    return col, s, FakeMatcher


def test_pipeline_audio_cd(fake_env, tmp_path):
    col, s, FakeMatcher = fake_env
    s.mode = "audio"
    events = []
    res = core.run_job(col, s, events.append, matcher=FakeMatcher())
    folder = tmp_path / "out" / "Lista_ Verano_2026" / "CD Audio"
    assert res.folder == folder and len(res.discs) == 1 and len(res.failed) == 1
    disc = folder / "Disco 1"
    wavs = sorted(p.name for p in disc.glob("*.wav"))
    assert wavs == ["01 - Artista A - Canción Uno.wav", "02 - Artista B, Artista C - Canción Dos.wav"]
    import wave
    with wave.open(str(disc / wavs[0])) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (2, 2, 44100)
        assert abs(w.getnframes() / 44100 - 2) < 0.05
    cue = (disc / "Disco 1.cue").read_text(encoding="cp1252")
    assert 'FILE "01 - Artista A - Canción Uno.wav" WAVE' in cue
    assert 'TITLE "Canción Dos"' in cue and "PREGAP 00:02:00" in cue
    assert (folder / "canciones_no_encontradas.txt").exists()
    assert not (folder / ".trabajo").exists()
    assert any(e.kind == "track" and e.status == core.DONE for e in events)

    # Segunda vez: usa la caché de coincidencias (no vuelve a buscar las encontradas)
    before = FakeMatcher.calls
    core.run_job(col, s, matcher=FakeMatcher())
    assert FakeMatcher.calls - before == 1


def test_pipeline_mp3_cd(fake_env, tmp_path):
    col, s, FakeMatcher = fake_env
    s.mode = "mp3"
    res = core.run_job(col, s, matcher=FakeMatcher())
    disc = res.discs[0].folder
    files = sorted(p.name for p in disc.glob("*.mp3"))
    assert files == ["01 - Artista A - Canción Uno.mp3", "02 - Artista B, Artista C - Canción Dos.mp3"]
    from mutagen.id3 import ID3
    from mutagen.mp3 import MP3
    f = MP3(disc / files[1])
    assert f.info.bitrate == 320000 and f.info.sample_rate == 44100
    tags = ID3(disc / files[1])
    assert tags["TPE1"].text == ["Artista B, Artista C"] and tags["TRCK"].text == ["2"]
    from PIL import Image
    import io
    img = Image.open(io.BytesIO(tags.getall("APIC")[0].data))
    assert img.format == "JPEG" and img.size == (500, 500)


def test_cancel(fake_env):
    import threading
    col, s, FakeMatcher = fake_env
    ev = threading.Event()
    ev.set()
    res = core.run_job(col, s, cancel=ev, matcher=FakeMatcher())
    assert res.cancelled and not res.discs


def test_include_and_loudness_cache(fake_env, monkeypatch):
    col, s, FakeMatcher = fake_env
    s.mode = "audio"
    calls = []
    real = core.measure_loudness
    monkeypatch.setattr(core, "measure_loudness", lambda p: calls.append(p) or real(p))
    res = core.run_job(col, s, matcher=FakeMatcher(), include={2})
    assert [it.index for d in res.discs for it in d.items] == [2] and not res.failed
    assert len(calls) == 1
    core.run_job(col, s, matcher=FakeMatcher(), include={2})
    assert len(calls) == 1  # el volumen medido sale de la caché


def test_estimate_with_pairs():
    discs = cd.estimate([(3, 100.0), (7, 200.0)], "audio")
    assert [it.index for it in discs[0].items] == [3, 7]


def test_clear_cache(tmp_path, monkeypatch):
    from listacd import config
    monkeypatch.setenv("LISTACD_CACHE", str(tmp_path))
    (tmp_path / "a.opus").write_bytes(b"x" * 10)
    (tmp_path / "coincidencias.json").write_text("{}")
    assert config.cache_size() == 12
    config.clear_cache()
    assert [p.name for p in tmp_path.iterdir()] == ["coincidencias.json"]


def test_webapp_bridge(fake_env, monkeypatch):
    """El puente que usa la interfaz HTML: plan, preparar y eventos."""
    import time
    from listacd import webapp
    col, s, FakeMatcher = fake_env
    s.mode = "audio"
    monkeypatch.setattr(webapp.Settings, "load", classmethod(lambda cls: s))
    monkeypatch.setattr(core, "Matcher", FakeMatcher)
    api = webapp.Api()
    assert api.plan([]) == []
    assert api.load("https://example.com")["ok"] is False
    api._col = col
    assert [d["items"] for d in api.plan([2])] == [[1, 3]]
    assert api.start([3]) is True
    events = []
    for _ in range(200):
        events += api.poll()
        if any(e["type"] == "job_done" for e in events):
            break
        time.sleep(0.05)
    done = next(e for e in events if e["type"] == "job_done")
    assert done["discs"][0]["items"] == [1, 2] and not done["failed"]
    assert any(e["type"] == "progress" for e in events)
    assert api.init()["settings"]["mode"] == "audio"
    # Los atributos internos no se exponen a JavaScript (pywebview publica los públicos)
    assert all(k.startswith("_") for k in vars(api))
