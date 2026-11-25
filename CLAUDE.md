# ListaCD

App de escritorio (Python + CustomTkinter) que pasa listas de Spotify a CDs para el coche.
Interfaz y mensajes al usuario en español.

## Mapa
- `listacd/spotify.py` lee la lista (API con claves o página embed, máx. 100).
- `listacd/matcher.py` busca en YouTube Music y puntúa coincidencias.
- `listacd/downloader.py` descarga original (yt-dlp), volumen, conversión ffmpeg, etiquetas.
- `listacd/core.py` `run_job()`: orquesta y emite `Event`s; reparte en discos.
- `listacd/cd.py` reparto en discos y `.cue`. `listacd/burner.py` grabación y borrado IMAPI2 (solo Windows).
- `listacd/disc_reader.py` lee un CD (MP3: etiquetas; audio: `.cda` → historial o MusicBrainz).
  `listacd/history.py` apunta cada disco grabado (para reconocerlo al leerlo).
- `listacd/web/` interfaz principal (HTML/CSS/JS) y `listacd/webapp.py` su puente (`Api`, eventos con `poll()`).
- `listacd/gui.py` ventana clásica de reserva (si falta WebView2). `listacd/cli.py` entrada (+ `--selftest`).
- Diseño: `docs/diseno.md` (concepto). Para cambios visuales usa la skill `diseno-listacd`
  (tokens, estados, WCAG 2.2 AA y lista de control) y, para ideas nuevas, `frontend-design`.
- Build: `ListaCD.spec`, `installer/ListaCD.iss`, `.github/workflows/build-windows.yml`.

## Comandos
- Pruebas: `python -m pytest -q` (necesita ffmpeg en el PATH).
- Comprobación interna: `python -m listacd --selftest salida.txt`.
- Captura de la interfaz: `node tools/captura_web.js lista /tmp/x.png` (ver skill `probar-listacd`).

## Skills útiles
- `bug-prospector` (auditoría con 7 lentes, informes en `.agents/research/`) y, tras cada arreglo, `bug-echo`.
- `critica-listacd` (producto), `diseno-listacd` + `frontend-design` (diseño), `probar-listacd` (verificar).

## Reglas
- No hay red a Spotify/YouTube en el sandbox: prueba con dobles (ver `tests/`).
- Nunca recodificar dos veces con pérdida: siempre desde el original en caché.
- Lo ya convertido se reutiliza (`.convertidas.json` por carpeta, clave vídeo|modo|ganancia).
- Atributos internos de `webapp.Api` con `_` (pywebview expone a JS todo lo público).
- «Ocupado» se marca con `Api._claim()` (cerrojo): pywebview atiende cada llamada en su propio hilo.
- Nombres por defecto (listas pegadas, CDs leídos) siempre con fecha y hora: el nombre es la carpeta.
- Nombre de volumen de CD de datos: `burner.iso_volume_name()` (≤ 15, A–Z 0–9 _).
- Todo lo de COM/IMAPI2 en el hilo que lo crea; la GUI solo se toca desde el hilo principal (cola `events`).
- Tras cambiar algo de Windows, verificar el job `windows` de GitHub Actions (hace el selftest del .exe).
