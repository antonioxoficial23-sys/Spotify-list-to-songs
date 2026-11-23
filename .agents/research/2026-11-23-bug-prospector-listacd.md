# Bug Prospector Report: listacd/ (aplicación completa)

**Date:** 2026-11-23
**Scope:** `listacd/` — core.py, downloader.py, webapp.py, web/app.js, burner.py, cd.py, matcher.py, spotify.py, config.py, cli.py (gui.py, ventana de reserva, solo revisada por encima)
**Lenses Applied:** las 7 (Assumption, State Machine, Boundary, Data Lifecycle, Error Path, Time, Platform)
**Files Analyzed:** 11
**Source glob:** `**/*.{py,js}`
**Accelerators:** advisory — patrones de Swift en un proyecto Python/JavaScript; las lentes se aplicaron leyendo cada archivo completo
**Plataforma:** aplicación de escritorio Windows distribuida como instalador en GitHub (sin tienda: sin columna 1-Star Risk)

## Summary

| Status | Count |
|--------|-------|
| Bugs Found | 8 |
| Fragile Code | 2 |
| OK (Already Guarded) | 7 |
| Needs Review | 1 |

## Issue Rating Table

| # | Finding | Lens | Urgency | Risk: Fix | Risk: No Fix | ROI | Blast Radius | Fix Effort | Confidence |
|---|---------|------|---------|-----------|-------------|-----|-------------|------------|------------|
| 1 | burner.py:189 — nombre de volumen de hasta 16 caracteres con espacios/acentos; IMAPI2 admite 15 y en ISO 9660 solo A–Z, 0–9 y _ | Platform | 🔴 Critical | ⚪ Low | 🔴 Critical | 🟠 Excellent | ⚪ 1 file | Trivial | verified (docs Microsoft) |
| 2 | core.py:279–291 — si un archivo de un disco anterior está abierto (Explorador, reproductor), el reparto final falla con un error de Windows en inglés y puede perder los archivos reutilizados | Error Path | 🔴 Critical | 🟢 Medium | 🔴 Critical | 🟠 Excellent | ⚪ 1 file | Small | probable |
| 3 | core.py:process — dos canciones que apuntan al mismo vídeo se descargan a la vez en el mismo archivo | Data Lifecycle | 🟡 High | ⚪ Low | 🟡 High | 🟠 Excellent | ⚪ 1 file | Small | verified |
| 4 | webapp.py:144/219 — `start()`/`burn()` comprueban y marcan `_busy` sin cerrojo; un doble clic puede lanzar dos preparaciones sobre la misma carpeta | State Machine | 🟡 High | ⚪ Low | 🟡 High | 🟢 Good | ⚪ 1 file | Trivial | probable |
| 5 | app.js:324 + webapp.py:129 — al salir del título (aunque no cambie) se descartan los discos preparados | State Machine | 🟡 High | ⚪ Low | 🟡 High | 🟠 Excellent | 🟢 2 files | Trivial | verified |
| 6 | spotify.py:24 — todas las listas pegadas se llaman igual y comparten carpeta: preparar una borra los discos de la anterior | Data Lifecycle | 🟡 High | ⚪ Low | 🟡 High | 🟠 Excellent | ⚪ 1 file | Trivial | verified |
| 7 | webapp.py:298 — ventana de 1200×800 con mínimo 1024×700: en portátiles 1920×1080 al 150 % (≈1280×672 útiles) queda tapada por la barra de tareas | Platform | 🟢 Medium | ⚪ Low | 🟢 Medium | 🟢 Good | 🟢 2 files | Small | probable |
| 8 | matcher.py:62 — `track.artists[0]` sin comprobar lista vacía | Assumption | 🟢 Medium | ⚪ Low | 🟢 Medium | 🟢 Good | ⚪ 1 file | Trivial | verified |
| F1 | cd.py:plan — una pista más larga que un CD crea un disco imposible de grabar | Boundary | 🟢 Medium | ⚪ Low | 🟢 Medium | 🟢 Good | ⚪ 1 file | Small | verified |
| F2 | core.py:JsonCache.put — `replace()` falla en Windows si el antivirus tiene abierto el JSON, y hace fallar la canción | Error Path | ⚪ Low | ⚪ Low | ⚪ Low | 🟡 Marginal | ⚪ 1 file | Trivial | probable |

## Implementation Plan

### Phase 1: Grabación — 1 fix
**Files:** listacd/burner.py
**Findings:** 1
**Rationale:** el único que impide por completo una función (CD MP3).
**Verify:** prueba unitaria del saneado del nombre + selftest del .exe en GitHub Actions (crea una imagen ISO real con IMAPI2).

### Phase 2: Proceso de preparación — 4 fixes
**Files:** listacd/core.py, listacd/matcher.py
**Findings:** 2, 3, 8, F1, F2
**Rationale:** mismo archivo y misma función `run_job`; F1 se resuelve en el mismo sitio que el reparto.
**Verify:** `python -m pytest -q` con pruebas nuevas para archivo bloqueado, vídeo duplicado y pista demasiado larga.

### Phase 3: Interfaz y estado — 3 fixes
**Files:** listacd/webapp.py, listacd/web/app.js, listacd/spotify.py
**Findings:** 4, 5, 6, 7
**Rationale:** todos tocan el puente Python↔página o lo que muestra.
**Verify:** pruebas del puente + capturas con `tools/captura_web.js`, incluida 960×600.

## Detailed Findings

### 1. burner.py:189 — nombre de volumen inválido para IMAPI2
**Lens:** Platform Divergence
**Assumption:** IMAPI2 acepta cualquier nombre de hasta 16 caracteres.
**Violation scenario:** la documentación de `IFileSystemImage::put_VolumeName` limita el nombre a 15 caracteres y, en ISO 9660, a A–Z, 0–9 y _. Una lista llamada «Viaje a la playa» (minúsculas y espacios) o con 16 letras devuelve `IMAPI_E_INVALID_VOLUME_NAME`.
**Consequence:** grabar un CD MP3 falla siempre que el nombre no sea ya mayúsculas sin espacios.

**Current code:**
```python
fsi.VolumeName = volume_name[:16]
```
**Suggested fix:**
```python
fsi.VolumeName = iso_volume_name(volume_name)  # «VIAJE_A_LA_PLAY», sin acentos, ≤ 15
```
**User experience:**
- **Before:** pulsas «Grabar disco 1» en modo CD MP3 y sale «Error al grabar» con un código raro; no hay forma de grabar.
- **After:** el disco se graba; en el coche aparece como «VIAJE_A_LA_PLAY».

### 2. core.py:279–291 — archivos abiertos al rehacer los discos
**Lens:** Error Path Exerciser
**Assumption:** las carpetas «Disco N» anteriores siempre se pueden borrar.
**Violation scenario:** el usuario pulsa «Abrir la carpeta de los discos», escucha una canción o deja el Explorador dentro de «Disco 1» y después pulsa «Reintentar». En Windows no se puede borrar una carpeta con archivos abiertos; `rmtree(ignore_errors=True)` falla en silencio y `rename()` lanza `FileExistsError`.
**Consequence:** la preparación acaba con «[WinError 183] No se puede crear un archivo que ya existe…». Los archivos reutilizados ya se habían movido a `.nuevo`, y la ejecución siguiente borra `.nuevo`: hay que convertirlos de nuevo.

**Suggested fix:** antes de mover nada, apartar las carpetas viejas a `.viejo/` con `rename` (falla si hay algo abierto). Si falla, deshacerlo y mostrar «Cierra los archivos del Disco 1 (¿está abierto en un reproductor?) y pulsa Reintentar», sin haber tocado nada.

**User experience:**
- **Before:** tras esperar a que se preparen todas las canciones, aparece un error en inglés al final, y el siguiente intento es más lento.
- **After:** un mensaje claro dice qué cerrar; al reintentar todo sigue donde estaba.

### 3. core.py:process — misma canción descargada dos veces a la vez
**Lens:** Data Lifecycle Tracing
**Assumption:** cada canción de la lista corresponde a un vídeo distinto.
**Violation scenario:** la lista tiene la misma canción dos veces, o la versión «single» y la del álbum coinciden con el mismo vídeo de YouTube Music. Dos hilos escriben en `<vídeo>.webm.part` a la vez.
**Consequence:** una de las dos falla, o el archivo queda corrupto y la conversión falla.

**Suggested fix:** un cerrojo por `video_id` alrededor de la descarga.
**User experience:**
- **Before:** una canción repetida sale como «Falló» sin motivo aparente.
- **After:** se descarga una vez y ambas posiciones salen bien.

### 4. webapp.py:144/219 — doble clic en «Preparar»
**Lens:** State Machine Analysis
**Assumption:** solo puede haber una llamada a `start()` a la vez.
**Violation scenario:** pywebview ejecuta cada llamada de la página en su propio hilo. El botón no se desactiva hasta que vuelve la respuesta, así que un doble clic deja pasar dos llamadas antes de que `_busy` sea `True`.
**Consequence:** dos preparaciones a la vez sobre la misma carpeta; la segunda borra `.trabajo` mientras la primera lo usa.

**Suggested fix:** `threading.Lock` alrededor de la comprobación y la marca de `_busy`.
**User experience:**
- **Before:** un doble clic puede acabar con canciones «Falló» o discos incompletos.
- **After:** no se nota nada; el segundo clic se ignora.

### 5. app.js:324 + webapp.py:129 — el título descarta lo preparado
**Lens:** State Machine Analysis
**Assumption:** si el título pierde el foco es porque se ha cambiado el nombre.
**Violation scenario:** con los discos ya preparados, el usuario hace clic en el título (tiene un subrayado al pasar el ratón que invita a hacerlo) y después en otro sitio.
**Consequence:** desaparecen los botones de grabar y hay que volver a preparar, aunque el nombre sea el mismo.

**Suggested fix:** solo renombrar si el texto ha cambiado, y no permitirlo mientras se trabaja.
**User experience:**
- **Before:** un clic inocente en el título borra la sección «Grabar».
- **After:** no pasa nada salvo que cambies el nombre de verdad.

### 6. spotify.py:24 — listas pegadas con el mismo nombre
**Lens:** Data Lifecycle Tracing
**Assumption:** cada lista tiene un nombre propio.
**Violation scenario:** las listas de más de 100 canciones (método de pegar) se llaman todas «Mi lista para el coche». Preparar una segunda lista usa la misma carpeta y borra los «Disco N» de la primera.
**Consequence:** discos preparados de otra lista desaparecen en silencio.

**Suggested fix:** nombre por defecto con la fecha y la hora («Mi lista del 23-11 18:40»).
**User experience:**
- **Before:** preparas dos listas largas y la carpeta de la primera ya no tiene sus discos.
- **After:** cada lista conserva su carpeta.

### 7. webapp.py:298 — ventana más grande que la pantalla
**Lens:** Platform Divergence
**Assumption:** la pantalla tiene al menos 1024×700 px útiles.
**Violation scenario:** muchos portátiles de 15" vienen con 1920×1080 al 150 % de escala: Windows ofrece unos 1280×672 px útiles.
**Consequence:** la ventana se abre más alta que la pantalla y la parte de abajo (grabar, abrir carpeta) queda tapada por la barra de tareas.

**Suggested fix:** tamaño inicial según la pantalla, mínimo 960×600 y CSS que lo admita.
**User experience:**
- **Before:** en algunos portátiles hay que mover la ventana para ver los botones de grabar.
- **After:** la ventana cabe en la pantalla al abrirse.

### 8. matcher.py:62 — canción sin artista
**Lens:** Assumption Audit
**Assumption:** toda canción tiene al menos un artista.
**Violation scenario:** la página pública de Spotify devuelve alguna entrada con el subtítulo vacío.
**Consequence:** `IndexError` y la canción sale «Falló: list index out of range».

**Suggested fix:** usar el artista solo si existe.
**User experience:**
- **Before:** de vez en cuando una canción falla con un mensaje incomprensible.
- **After:** se busca solo por el título.

## Fragile Code (Works Now, May Break Later)

### F1. cd.py:plan — pista más larga que un CD
**Lens:** Boundary Conditions
**Current behavior:** una pista de más de 79:30 se coloca sola en un disco, que nunca se podrá grabar en modo audio.
**Breaking scenario:** sesiones de DJ o álbumes en una sola pista (cada vez más habituales en Spotify).
**Recommendation:** marcarla como no válida al preparar, con el motivo y la alternativa (modo CD MP3).
**User experience if it breaks:** prepara un disco que, al grabarlo, dice que no cabe en ningún CD-R.

### F2. core.py:JsonCache.put — archivo de caché bloqueado
**Lens:** Error Path Exerciser
**Current behavior:** si `replace()` lanza `PermissionError` (antivirus o copia de seguridad leyendo el JSON), la excepción hace fallar la canción.
**Breaking scenario:** antivirus que escanean `%LOCALAPPDATA%` en tiempo real.
**Recommendation:** la caché es una optimización: si no se puede guardar, seguir sin ella.
**User experience if it breaks:** una canción sale «Falló: PermissionError» aunque se descargó bien.

## Already Guarded (Reference)
- webapp.py:load — entrada inválida devuelve un mensaje en español y no bloquea el botón.
- app.js:load/prepare — `S.busy` impide cargar otra lista mientras se prepara o graba.
- core.py:run_job — cancelar borra solo `.trabajo`; los discos anteriores no se tocan.
- core.py:JsonCache — escritura atómica con archivo temporal y `replace`.
- downloader.py:download_original — limpia los `.part` entre intentos.
- burner.py:burn_audio — `ReleaseMedia` en `finally`.
- webapp.py:_on_closing — confirma antes de cerrar mientras se graba o prepara.

## Needs Human Review
- spotify.py:_tracks_embed — se asume que la página «embed» de una canción tiene `entity.artists[].name` y `entity.duration` como la de una lista. No se puede comprobar sin red desde aquí; si cambia, las canciones pegadas fallarían todas. Conviene probar una lista pegada en el PC real.

## After You Fix These Findings

Ejecutar `/bug-echo` sobre cada arreglo para encontrar otras apariciones del mismo patrón.

## Estado tras aplicar los arreglos (2026-11-23)

| # | Finding | Urgency | Status | Verificación |
|---|---------|---------|--------|--------------|
| 1 | Nombre de volumen inválido (CD MP3) | 🔴 Critical | Fixed | `test_iso_volume_name`; el selftest del .exe crea una imagen IMAPI2 con «Viaje a la playa (Disco 1) ñ» |
| 2 | Archivos abiertos al rehacer los discos | 🔴 Critical | Fixed | `test_open_file_in_old_disc_is_reported_without_losing_work` |
| 3 | Mismo vídeo descargado dos veces a la vez | 🟡 High | Fixed | `test_same_video_is_downloaded_once` |
| 4 | Doble clic lanza dos trabajos | 🟡 High | Fixed | `test_bridge_claim_and_rename` (20 hilos, 1 gana) |
| 5 | El título descarta lo preparado | 🟡 High | Fixed | `test_bridge_claim_and_rename` |
| 6 | Listas pegadas comparten carpeta | 🟡 High | Fixed | `test_pasted_lists_get_distinct_names` |
| 7 | Ventana más alta que la pantalla | 🟢 Medium | Fixed | `test_window_size_fits_small_screens` + captura a 960×600 |
| 8 | Canción sin artista | 🟢 Medium | Fixed | `test_score_without_artist` |
| F1 | Pista más larga que un CD | 🟢 Medium | Fixed | `test_track_longer_than_a_cd` |
| F2 | Caché bloqueada por el antivirus | ⚪ Low | Fixed | `test_cache_write_failure_is_not_fatal` |

### bug-echo tras los arreglos
- `rmtree(ignore_errors=True)` seguido de escribir en la misma carpeta (`.viejo`/`.nuevo`): **BUG → Fixed** (nombre único por ejecución; `test_leftover_locked_temp_folders_do_not_block`).
- Tamaño fijo de ventana en `gui.py` (ventana de reserva): **BUG → Fixed** (se ajusta a la pantalla).
- `webapp.py:_claim` es la implementación de referencia (OK CANON) para «comprobar y marcar ocupado»; el resto de comprobaciones de `_busy` solo leen (OK).
- Resto de `[0]`: todos protegidos (OK). Sin más nombres de volumen ni nombres por defecto fijos.
- Precisión de la inferencia: los 6 patrones salían directamente de las líneas eliminadas (autosuficientes); ninguno necesitó precondición.
