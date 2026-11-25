import json
import subprocess
from pathlib import Path

import pytest

from listacd import burner, cd, core, downloader, spotify
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

        def ranked(self, t):
            return [Match(f"alt{t.spotify_id}", t.title, t.artists, 2, 0.9)]

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


def test_pasted_tracks(monkeypatch):
    """Canciones copiadas de Spotify (Ctrl+A, Ctrl+C): sin claves y sin límite de 100."""
    ids = [f"{i:022d}" for i in range(150)]
    # Al pegar en un campo de una línea los saltos desaparecen: también debe funcionar
    text = "".join(f"https://open.spotify.com/track/{i}" for i in ids) + "\nspotify:track:" + ids[0]
    kind, got = spotify.parse_input(text)
    assert kind == "tracks" and got == ids
    assert spotify.parse_input("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M")[0] == "playlist"

    def fake_embed(missing, progress, done_before=0, total=0, workers=6):
        if progress:
            progress(total, total)
        return {i: Track(title=f"T{i[-3:]}", artists=["A"], duration_ms=1000, spotify_id=i)
                for i in missing if i != ids[7]}
    monkeypatch.setattr(spotify, "_tracks_embed", fake_embed)
    seen = []
    col = spotify.fetch(text, progress=lambda d, t: seen.append((d, t)))
    assert col.kind == "tracks" and len(col.tracks) == 149
    assert [t.spotify_id for t in col.tracks[:3]] == ids[:3]
    assert "1 canción no se pudo" in col.warning and seen[-1] == (150, 150)


def test_download_retries_other_clients(tmp_path, monkeypatch):
    """Un 403 con el cliente por defecto se resuelve probando otros clientes de YouTube."""
    import yt_dlp
    tried = []

    class FakeYDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download):
            clients = self.opts.get("extractor_args", {}).get("youtube", {}).get("player_client")
            tried.append(clients)
            if len(tried) < 3:
                (tmp_path / "abc.webm.part").write_bytes(b"x")
                raise yt_dlp.utils.DownloadError("ERROR: unable to download video data: HTTP Error 403: Forbidden")
            (tmp_path / "abc.webm").write_bytes(b"audio")
            return {"id": "abc", "ext": "webm"}

        def prepare_filename(self, info):
            return str(tmp_path / "abc.webm")

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)
    p = downloader.download_original(Match("abc", "T", ["A"], 1, 1), tmp_path)
    assert p.name == "abc.webm" and tried == [None, ["tv"], ["web_safari"]]
    assert not list(tmp_path.glob("*.part"))


def test_download_403_message(tmp_path, monkeypatch):
    import yt_dlp

    class AlwaysFail:
        def __init__(self, opts): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def extract_info(self, url, download):
            raise yt_dlp.utils.DownloadError("ERROR: unable to download video data: HTTP Error 403: Forbidden")

    monkeypatch.setattr(yt_dlp, "YoutubeDL", AlwaysFail)
    with pytest.raises(downloader.DownloadFailed, match="403"):
        downloader.download_original(Match("zzz", "T", ["A"], 1, 1), tmp_path)


def test_pipeline_uses_alternative_when_download_fails(fake_env, monkeypatch):
    col, s, FakeMatcher = fake_env
    real = core.download_original

    def flaky(m, cache, cookies):
        if m.video_id == "vida1":  # la primera versión de «Canción Uno» está bloqueada
            raise downloader.DownloadFailed("YouTube bloqueó la descarga (error 403).")
        return real(m, cache, cookies)
    monkeypatch.setattr(core, "download_original", flaky)
    res = core.run_job(col, s, matcher=FakeMatcher(), include={1})
    assert not res.failed and len(res.discs[0].items) == 1
    from listacd.config import cache_dir
    import json
    saved = json.loads((cache_dir() / "coincidencias.json").read_text())
    assert saved["a1"]["video_id"] == "alta1"  # la próxima vez va directa a la que funciona


def test_retry_reuses_converted_songs(fake_env, monkeypatch):
    """«Reintentar» solo procesa las que faltaban: las ya convertidas se reutilizan."""
    col, s, FakeMatcher = fake_env
    for mode in ("audio", "mp3"):
        s.mode = mode
        first = core.run_job(col, s, matcher=FakeMatcher(), include={1, 2})
        names = sorted(p.name for p in first.discs[0].folder.iterdir())
        conversions = []
        real_wav, real_mp3 = core.to_cd_wav, core.to_mp3
        monkeypatch.setattr(core, "to_cd_wav", lambda *a: conversions.append(a) or real_wav(*a))
        monkeypatch.setattr(core, "to_mp3", lambda *a: conversions.append(a) or real_mp3(*a))
        downloads = []
        real_dl = core.download_original
        monkeypatch.setattr(core, "download_original", lambda *a: downloads.append(a) or real_dl(*a))
        second = core.run_job(col, s, matcher=FakeMatcher(), include={1, 2})
        assert conversions == [] and downloads == []
        assert sorted(p.name for p in second.discs[0].folder.iterdir()) == names
        assert not list(first.folder.glob(".nuevo*")) and not (first.folder / ".trabajo").exists()
        # Quitar una canción y volver a preparar: la otra sigue sin convertirse de nuevo
        third = core.run_job(col, s, matcher=FakeMatcher(), include={2})
        assert conversions == [] and [it.index for it in third.discs[0].items] == [2]
        assert third.discs[0].items[0].path.name.startswith("01 - ")
        monkeypatch.undo()
        monkeypatch.setenv("LISTACD_CACHE", str(Path(first.folder).parents[2] / "cache"))
        monkeypatch.setattr(core, "download_original",
                            lambda m, cache, cookies: _fake_original(cache, m.video_id, 440))
        monkeypatch.setattr(core, "fetch_image", lambda url: None)


def test_iso_volume_name():
    """IMAPI2: como mucho 15 caracteres y, en ISO 9660, solo A–Z, 0–9 y _."""
    import re
    from listacd.burner import iso_volume_name
    for name, want in [("Viaje a la playa", "VIAJE_A_LA_PLAY"), ("ASTROWORLD", "ASTROWORLD"),
                       ("Canción de verano ñ", "CANCION_DE_VERA"), ("🚗🎶", "LISTACD"), ("a-b", "A_B")]:
        got = iso_volume_name(name)
        assert got == want and len(got) <= 15 and re.fullmatch(r"[A-Z0-9_]+", got)


def test_open_file_in_old_disc_is_reported_without_losing_work(fake_env, monkeypatch):
    """Windows no deja renombrar una carpeta con un archivo abierto: aviso claro y nada se pierde."""
    col, s, FakeMatcher = fake_env
    first = core.run_job(col, s, matcher=FakeMatcher(), include={1, 2})
    disc1 = first.discs[0].folder
    before = sorted(p.name for p in disc1.iterdir())
    real_rename = Path.rename

    def locked(self, target):
        if self.name == "Disco 1" and self.parent == first.folder:
            raise PermissionError(32, "El proceso no tiene acceso al archivo porque está siendo utilizado")
        return real_rename(self, target)
    monkeypatch.setattr(Path, "rename", locked)
    with pytest.raises(core.FolderBusy, match="Disco 1"):
        core.run_job(col, s, matcher=FakeMatcher(), include={1, 2})
    assert sorted(p.name for p in disc1.iterdir()) == before  # intacto
    monkeypatch.setattr(Path, "rename", real_rename)
    again = core.run_job(col, s, matcher=FakeMatcher(), include={1, 2})  # al cerrar el archivo, funciona
    assert sorted(p.name for p in again.discs[0].folder.iterdir()) == before
    assert not list(first.folder.glob(".viejo*")) and not list(first.folder.glob(".nuevo*"))


def test_same_video_is_downloaded_once(fake_env, monkeypatch):
    import threading
    import time as _t
    col, s, FakeMatcher = fake_env
    col.tracks[1].title = col.tracks[0].title  # dos canciones, el mismo vídeo

    class SameVideo(FakeMatcher):
        def find(self, t):
            return Match("vidcomun", t.title, t.artists, 2, 1.0)

    active, peak = [0], [0]
    lock = threading.Lock()

    def slow(m, cache, cookies):
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        _t.sleep(0.2)
        try:
            return _fake_original(cache, m.video_id, 440)
        finally:
            with lock:
                active[0] -= 1
    monkeypatch.setattr(core, "download_original", slow)
    res = core.run_job(col, s, matcher=SameVideo(), include={1, 2})
    assert peak[0] == 1 and not res.failed and len(res.discs[0].items) == 2


def test_track_longer_than_a_cd(fake_env):
    col, s, FakeMatcher = fake_env
    s.mode = "audio"
    col.tracks[0].duration_ms = 95 * 60 * 1000
    res = core.run_job(col, s, matcher=FakeMatcher(), include={1, 2})
    assert [i for i, _, _ in res.failed] == [1] and "CD MP3" in res.failed[0][2]
    s.mode = "mp3"  # en MP3 sí cabe (la duración real del archivo de prueba es de 2 s)
    assert not core.run_job(col, s, matcher=FakeMatcher(), include={1, 2}).failed


def test_score_without_artist():
    t = Track(title="Canción", artists=[], duration_ms=200000)
    assert score(t, "Canción", ["Alguien"], 200) > 0.55


def test_cache_write_failure_is_not_fatal(tmp_path, monkeypatch):
    c = core.JsonCache(tmp_path / "c.json")
    monkeypatch.setattr(Path, "replace", lambda self, target: (_ for _ in ()).throw(PermissionError(13, "bloqueado")))
    c.put("k", 1)  # no lanza
    assert c.get("k") == 1


def test_bridge_claim_and_rename(fake_env, monkeypatch):
    import threading
    from listacd import webapp
    col, s, FakeMatcher = fake_env
    monkeypatch.setattr(webapp.Settings, "load", classmethod(lambda cls: s))
    api = webapp.Api()
    api._col = col
    # Varios clics simultáneos: solo uno consigue el trabajo
    wins = []
    threads = [threading.Thread(target=lambda: wins.append(api._claim())) for _ in range(20)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert wins.count(True) == 1
    api._busy = False
    api._result = object()
    assert api.rename("  " + col.name + " ") == {"name": col.name, "changed": False}
    assert api._result is not None  # sin cambios no se descarta lo preparado
    assert api.rename("Otro nombre") == {"name": "Otro nombre", "changed": True} and api._result is None


def test_window_size_fits_small_screens():
    from types import SimpleNamespace as NS
    from listacd.webapp import window_size
    assert window_size([NS(width=2560, height=1440)]) == (1200, 800)
    assert window_size([NS(width=1280, height=720)]) == (1200, 640)
    assert window_size([NS(width=1024, height=600)]) == (984, 600)
    assert window_size([]) == (1200, 800)


def test_pasted_lists_get_distinct_names():
    from listacd.spotify import pasted_name
    assert pasted_name().startswith("Mi lista del ")


def test_leftover_locked_temp_folders_do_not_block(fake_env):
    """Restos de una ejecución anterior que no se pudieron borrar no impiden preparar."""
    col, s, FakeMatcher = fake_env
    first = core.run_job(col, s, matcher=FakeMatcher(), include={1})
    for name in (".viejo", ".nuevo", ".viejo-viejo"):
        (first.folder / name / "Disco 1").mkdir(parents=True)  # como si estuvieran bloqueados
    again = core.run_job(col, s, matcher=FakeMatcher(), include={1})
    assert not again.failed and again.discs[0].folder.exists()


# ------------------------------------------------------------------ leer un CD

def _write_cda(path: Path, track: int, start: int, length: int):
    """Archivo .cda como los que muestra Windows en un CD de audio (44 bytes)."""
    import struct
    body = struct.pack("<HHIII", 1, track, 0x1234, start, length) + b"\0" * 8
    path.write_bytes(b"RIFF" + struct.pack("<I", 36) + b"CDDA" + b"fmt " + struct.pack("<I", 24) + body)


@pytest.fixture
def config_tmp(tmp_path, monkeypatch):
    from listacd import config
    monkeypatch.setattr(config, "config_dir", lambda: tmp_path)
    from listacd import history
    monkeypatch.setattr(history, "config_dir", lambda: tmp_path)
    return tmp_path


def test_read_cda(tmp_path):
    from listacd.disc_reader import read_cda
    _write_cda(tmp_path / "Track02.cda", 2, 20000, 15000)
    assert read_cda(tmp_path / "Track02.cda") == (2, 20000, 15000)
    (tmp_path / "x.cda").write_bytes(b"nada")
    with pytest.raises(ValueError):
        read_cda(tmp_path / "x.cda")


def test_audio_cd_recognized_from_history(tmp_path, config_tmp):
    from listacd import disc_reader, history
    songs = [Track(title="Uno", artists=["A"], duration_ms=200000, spotify_id="s1"),
             Track(title="Dos", artists=["B"], duration_ms=180000, spotify_id="s2")]
    history.record("Verano", "audio", 1, songs, [200.0, 180.0])
    cdroot = tmp_path / "E"
    cdroot.mkdir()
    # Windows ve la pausa de 2 s antes de la pista siguiente dentro de la pista anterior
    _write_cda(cdroot / "Track01.cda", 1, 0, (200 + 2) * 75)
    _write_cda(cdroot / "Track02.cda", 2, 202 * 75, 180 * 75)
    disc = disc_reader.read_disc(cdroot, lookup=False)
    assert disc.kind == "audio" and disc.source == "historial" and disc.name == "Verano"
    assert [t.title for t in disc.tracks] == ["Uno", "Dos"] and disc.tracks[0].spotify_id == "s1"
    assert "Lo grabó ListaCD" in disc.summary


def test_unknown_audio_cd_and_musicbrainz(tmp_path, config_tmp, monkeypatch):
    from listacd import disc_reader
    cdroot = tmp_path / "E"
    cdroot.mkdir()
    _write_cda(cdroot / "Track01.cda", 1, 0, 300 * 75)
    _write_cda(cdroot / "Track02.cda", 2, 300 * 75, 250 * 75)
    # Sin red: pistas sin identificar
    disc = disc_reader.read_disc(cdroot, lookup=False)
    assert disc.source == "sin datos" and disc.unknown == 2 and all(t.unknown for t in disc.tracks)
    assert disc.name.startswith("CD leído el ")  # nombre propio: no comparte carpeta con otros CDs
    # MusicBrainz (respuesta simulada): la consulta lleva la tabla de pistas correcta
    seen = {}

    class R:
        status_code = 200

        def json(self):
            return {"releases": [{"title": "Disco X", "artist-credit": [{"name": "Grupo", "joinphrase": ""}],
                                  "media": [{"tracks": [{"title": "Primera", "length": 300000},
                                                        {"title": "Segunda", "length": 250000}]}]}]}

    def fake_get(url, params, headers, timeout):
        seen.update(params)
        return R()
    monkeypatch.setattr(disc_reader.requests, "get", fake_get)
    disc = disc_reader.read_disc(cdroot)
    assert seen["toc"] == f"1 2 {550 * 75 + 150} 150 {300 * 75 + 150}"
    assert disc.source == "musicbrainz" and disc.name == "Disco X"
    assert [(t.title, t.artists) for t in disc.tracks] == [("Primera", ["Grupo"]), ("Segunda", ["Grupo"])]


def test_mp3_cd_reads_tags_and_names(tmp_path):
    from listacd import disc_reader
    cdroot = tmp_path / "E"
    (cdroot / "sub").mkdir(parents=True)
    a = _fake_original(tmp_path, "x", 440)  # opus de 2 s
    mp3 = downloader.to_mp3(a, cdroot / "02 - Artista B - Canción Dos.mp3")
    downloader.tag_mp3(mp3, Track(title="Canción Dos", artists=["Artista B", "C"]), None, 2)
    (cdroot / "01 - Sin Etiquetas - Primera.mp3").write_bytes(mp3.read_bytes()[-2000:])  # sin ID3
    (cdroot / "sub" / "leeme.txt").write_text("x")
    disc = disc_reader.read_disc(cdroot, label="VIAJE")
    assert disc.kind == "mp3" and disc.name == "VIAJE"
    assert [(t.title, t.artists) for t in disc.tracks] == [("Primera", ["Sin Etiquetas"]),
                                                            ("Canción Dos", ["Artista B", "C"])]
    empty = tmp_path / "vacio"
    empty.mkdir()
    assert disc_reader.read_disc(empty).kind == "vacio"


def test_merge_tracks_skips_duplicates():
    from listacd.webapp import merge_tracks
    base = [Track(title="Despechá", artists=[], duration_ms=1),            # leída de un CD, sin artista
            Track(title="Bohemian Rhapsody", artists=["Queen"], duration_ms=1, spotify_id="q1"),
            Track(title="Pista 3", artists=[], duration_ms=1, unknown=True)]
    extra = [Track(title="DESPECHÁ", artists=["ROSALÍA"], duration_ms=1, spotify_id="r1"),
             Track(title="Bohemian Rhapsody - Remastered", artists=["Queen"], duration_ms=1, spotify_id="q1"),
             Track(title="Pista 3", artists=["Alguien"], duration_ms=1, spotify_id="p3"),
             Track(title="Nueva", artists=["X"], duration_ms=1, spotify_id="n1"),
             Track(title="Nueva", artists=["X"], duration_ms=1, spotify_id="n1")]
    out, added = merge_tracks(base, extra)
    assert added == 2 and [t.title for t in out[3:]] == ["Pista 3", "Nueva"]


def test_unknown_tracks_are_never_searched(fake_env):
    col, s, FakeMatcher = fake_env
    col.tracks[0].unknown = True
    res = core.run_job(col, s, matcher=FakeMatcher(), include={1, 2})
    assert [i for i, _, _ in res.failed] == [1] and "sin identificar" in res.failed[0][2]


def test_bridge_append_and_burn_history(fake_env, monkeypatch, config_tmp):
    import time
    from listacd import webapp, history
    col, s, FakeMatcher = fake_env
    monkeypatch.setattr(webapp.Settings, "load", classmethod(lambda cls: s))
    api = webapp.Api()
    api._col = spotify.Collection(name="Mi CD", kind="disc", tracks=[col.tracks[0]])
    extra = spotify.Collection(name="Otra", kind="playlist", tracks=[col.tracks[0], col.tracks[1]])
    monkeypatch.setattr(webapp.spotify, "fetch", lambda *a, **k: extra)
    assert api.load("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M", append=True)["ok"]
    ev = []
    for _ in range(100):
        ev += api.poll()
        if any(e["type"] == "loaded" for e in ev):
            break
        time.sleep(0.02)
    loaded = next(e for e in ev if e["type"] == "loaded")["collection"]
    assert loaded["name"] == "Mi CD" and len(loaded["tracks"]) == 2 and "1 ya estaban" in loaded["note"]
    # Grabar (simulado) apunta el disco en el historial
    api._col = col
    res = core.run_job(col, s, matcher=FakeMatcher(), include={1, 2})
    api._result = res
    d = burner.Drive("id", "E:", "Grabadora")
    api._drives = [d]
    monkeypatch.setattr(burner, "burn_audio", lambda *a, **k: None)
    assert api.burn(1, "id")
    for _ in range(100):
        if any(e["type"] == "burn_done" for e in api.poll()):
            break
        time.sleep(0.02)
    entry = history.load()[-1]
    assert entry["name"] == col.name and [t["title"] for t in entry["tracks"]] == ["Canción Uno", "Canción Dos"]
    assert history.match_audio([x + 2 for x in entry["seconds"][:-1]] + entry["seconds"][-1:]) == entry
