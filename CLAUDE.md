# ListaCD

App de escritorio (Python + CustomTkinter) que pasa listas de Spotify a CDs para el coche.
Interfaz y mensajes al usuario en español.

## Mapa
- `listacd/spotify.py` lee la lista (API con claves o página embed, máx. 100).
- `listacd/matcher.py` busca en YouTube Music y puntúa coincidencias.
- `listacd/downloader.py` descarga original (yt-dlp), volumen, conversión ffmpeg, etiquetas.
- `listacd/core.py` `run_job()`: orquesta y emite `Event`s; reparte en discos.
- `listacd/cd.py` reparto en discos y `.cue`. `listacd/burner.py` grabación IMAPI2 (solo Windows).
- `listacd/gui.py` interfaz. `listacd/cli.py` entrada (+ `--selftest`).
- Build: `ListaCD.spec`, `installer/ListaCD.iss`, `.github/workflows/build-windows.yml`.

## Comandos
- Pruebas: `python -m pytest -q` (necesita ffmpeg en el PATH).
- Comprobación interna: `python -m listacd --selftest salida.txt`.
- Captura de la interfaz sin pantalla: ver skill `probar-listacd`.

## Reglas
- No hay red a Spotify/YouTube en el sandbox: prueba con dobles (ver `tests/`).
- Nunca recodificar dos veces con pérdida: siempre desde el original en caché.
- Todo lo de COM/IMAPI2 en el hilo que lo crea; la GUI solo se toca desde el hilo principal (cola `events`).
- Tras cambiar algo de Windows, verificar el job `windows` de GitHub Actions (hace el selftest del .exe).
