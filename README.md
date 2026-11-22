# Spotify-list-to-songs

Pega el enlace de una lista de Spotify y obtén **una carpeta con el nombre de la lista y todas sus canciones en MP3**, con etiquetas (título, artista, álbum, año) y carátula.

También funciona con enlaces de álbumes y de canciones sueltas.

```
Música/
└── Mi lista de verano/
    ├── Bad Bunny - Tití Me Preguntó.mp3
    ├── Rosalía - Despechá.mp3
    ├── …
    └── Mi lista de verano.m3u8      ← la lista en su orden original
```

## Cómo funciona

Spotify no permite descargar su audio (está cifrado con DRM), así que la app:

1. Lee de Spotify la lista de canciones (título, artistas, duración, álbum, ISRC, carátula).
2. Busca cada canción en **YouTube Music**, priorizando la pista oficial del artista y
   comparando título, artista y duración para no bajar versiones en directo, karaokes, remixes, etc.
3. Descarga el mejor audio disponible con `yt-dlp` y lo convierte a **MP3 320 kbps** con `ffmpeg`.
4. Escribe las etiquetas ID3 y la carátula con los datos de Spotify.

### Sobre la "máxima calidad"

La fuente es YouTube Music, que sirve el audio en Opus (~160 kbps) o AAC (128–256 kbps).
Convertir a MP3 320 kbps es la opción de MP3 que **menos calidad pierde** en la recodificación,
pero no puede añadir calidad que la fuente no tiene. Si quieres el audio exacto de la fuente
sin ninguna pérdida extra, usa `--formato best` (guarda Opus/M4A en vez de MP3).

## Instalación

Necesitas **Python 3.10+** y **ffmpeg**.

```bash
# ffmpeg
#   Windows: winget install ffmpeg
#   macOS:   brew install ffmpeg
#   Linux:   sudo apt install ffmpeg

git clone https://github.com/antonioxoficial23-sys/Spotify-list-to-songs.git
cd Spotify-list-to-songs
pip install -r requirements.txt
```

### Claves de Spotify (recomendado)

Sin claves, la app lee la página pública de Spotify, que **solo da las primeras 100 canciones**
y no incluye el álbum de cada tema. Con claves (gratis) se lee la lista completa:

1. Entra en <https://developer.spotify.com/dashboard> con tu cuenta de Spotify y pulsa **Create app**.
2. Pon cualquier nombre, en *Redirect URI* pon `http://127.0.0.1:8888/callback` y marca *Web API*.
3. Copia el **Client ID** y el **Client secret**.
4. Copia `.env.example` como `.env` y pégalos ahí:

```
SPOTIFY_CLIENT_ID=tu_client_id
SPOTIFY_CLIENT_SECRET=tu_client_secret
```

> Las listas creadas por el propio Spotify (p. ej. "Today's Top Hits", "Descubrimiento semanal")
> ya no son accesibles por la API; en ese caso la app usa automáticamente la página pública (máx. 100).
> Truco: copia esa lista a una lista tuya y descarga la tuya.

## Uso

### Con ventana

```bash
python -m spotify_to_mp3 --gui
```

Pega el enlace, elige la carpeta y pulsa **Descargar**.

### Desde la terminal

```bash
python -m spotify_to_mp3 "https://open.spotify.com/playlist/XXXXXXXXXXXXXXXXXXXXXX"
```

| Opción | Qué hace |
|---|---|
| `-o CARPETA` | Dónde crear la carpeta de la lista (por defecto, la actual) |
| `-b 320` / `-b V0` | Calidad del MP3: 320 kbps CBR (por defecto) o VBR V0 |
| `-f best` | Guarda el audio original sin recodificar (Opus/M4A), sin pérdida extra |
| `-n` | Numera los archivos según su posición en la lista |
| `-j 4` | Canciones descargadas a la vez |

Puedes pasar varios enlaces a la vez. Si vuelves a ejecutar la misma lista, **solo baja las canciones
que falten** (útil para actualizar una lista o reintentar las que fallaron). Las que no se encuentran
quedan anotadas en `_canciones_fallidas.txt` dentro de la carpeta.

## Pruebas

```bash
pip install pytest
python -m pytest
```

## Aviso legal

Úsalo solo para uso personal con música a la que tengas derecho de acceso. Descargar contenido protegido
puede infringir los términos de servicio de Spotify/YouTube y las leyes de propiedad intelectual de tu país.
