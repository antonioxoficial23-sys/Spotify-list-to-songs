# ListaCD

**Pasa listas de Spotify a CDs para el coche, con la mejor calidad posible.**

Pegas el enlace de una lista, eliges el tipo de CD y la app descarga las canciones, las prepara
y graba los discos con tu grabadora. Si la lista no cabe en un CD, la reparte sola en varios.

![Icono](assets/listacd.png)

## Instalar (Windows)

1. Ve a la pestaña **Actions** del repositorio → la última ejecución verde de
   *Compilar ListaCD para Windows* → descarga **ListaCD-Windows** (abajo, en *Artifacts*).
   Si hay una versión publicada, también está en **Releases**.
2. Descomprime y ejecuta **`ListaCD-Setup-x.y.z.exe`**. No necesita permisos de administrador.
   (Hay también una versión portable en `.zip` que no se instala.)
3. Windows puede avisar con «Windows protegió su PC» porque el programa no está firmado:
   pulsa **Más información → Ejecutar de todas formas**.

Todo va incluido (ffmpeg, etc.); no hay que instalar nada más.

## Cómo se usa

1. En Spotify: **⋯** en la lista → **Compartir** → **Copiar enlace**.
2. En ListaCD pulsa **Pegar** (o pega el enlace y pulsa *Cargar lista*).
3. Elige el **tipo de CD**:

   | | **CD de audio** (recomendado) | **CD MP3** |
   |---|---|---|
   | Calidad | Máxima: calidad CD, sin pasar por MP3 | MP3 320 kbps |
   | Canciones por disco | ~18–20 (80 min) | ~60–80 (700 MB) |
   | ¿Funciona en mi coche? | En **cualquier** radio con CD | Solo si la radio lee MP3 |
   | Títulos en la pantalla | Si la radio tiene CD-Text y grabas con ImgBurn | Sí (etiquetas ID3) |

4. Pulsa **Descargar y preparar**. La app te dice cuántos CD-R vas a necesitar.
5. Mete un **CD-R virgen** (mejor que CD-RW: muchas radios no leen los regrabables) y pulsa
   **Grabar disco 1**. Al acabar, lo expulsa y te pide el siguiente.

Los archivos quedan en `Música\ListaCD\<nombre de la lista>\CD Audio\Disco N\` (o `CD MP3`),
por si quieres volver a grabarlos o copiarlos a un USB.

### Listas de más de 100 canciones

Sin configurar nada, Spotify solo deja leer **las primeras 100 canciones** de una lista. Para
listas más largas, pon tus claves de Spotify (gratis, 2 minutos) en **⚙ Ajustes**:

1. Entra en <https://developer.spotify.com/dashboard> con tu cuenta y pulsa **Create app**.
2. Nombre y descripción: lo que quieras. *Redirect URI*: `http://127.0.0.1:8888/callback`. Marca **Web API**.
3. Copia el **Client ID** y el **Client secret** en Ajustes.

Las listas que crea el propio Spotify (Descubrimiento semanal, Top Hits…) no se pueden leer con
claves; la app usa la página pública (máx. 100). Truco: añade esas canciones a una lista tuya.

## Calidad: qué hace exactamente

Spotify cifra su audio, así que no se puede copiar directamente. ListaCD busca cada canción en
**YouTube Music** y descarga la versión oficial del artista:

- **Búsqueda precisa**: primero por código ISRC (identifica la grabación exacta); después por título,
  artista y duración, descartando directos, karaokes, remixes, versiones aceleradas, etc.
- **Sin pérdidas extra**: guarda el audio original (Opus ~160 kbps, o AAC 256 kbps si tienes
  YouTube Premium y activas las cookies en Ajustes) y lo convierte **una sola vez** al formato final.
  Para el CD de audio no pasa por MP3.
- **Conversión de calidad de estudio**: remuestreo a 44,1 kHz con SoX (precisión de 28 bits)
  y dither triangular al pasar a 16 bits.
- **Igualar volumen** (activado por defecto): ajusta solo la ganancia de cada canción para que
  no tengas que tocar el volumen entre una y otra. No comprime el sonido y nunca lo sube tanto
  como para saturar (pico máximo de −1 dBTP).
- **Pensado para el coche**: discos cerrados, MP3 en CBR con etiquetas ID3v2.3 + ID3v1 y carátula de
  500 px (lo que mejor leen las radios), nombres numerados para que suenen en orden y
  como mucho 99 pistas (CD audio) o 255 archivos (CD MP3) por disco.

Es la mejor calidad que se puede obtener sin acceso al audio original de Spotify.

## Si algo falla

- **«No se encontró en YouTube Music»**: la canción queda anotada en `canciones_no_encontradas.txt`.
- **YouTube pide verificación o no descarga**: en Ajustes elige el navegador donde tienes sesión de
  YouTube abierta (Firefox es el que mejor funciona) para usar sus cookies.
- **Error al grabar**: prueba otra marca de CD-R (Verbatim suele ir muy bien). Para CD de audio,
  también puedes grabar el archivo `Disco N.cue` con [ImgBurn](https://www.imgburn.com/) (gratis,
  «Write image file to disc»), que además graba los títulos como CD-Text.
- **Tras un tiempo deja de descargar**: YouTube cambia a menudo; instala la última versión de ListaCD.

## Para desarrolladores

```bash
pip install -r requirements.txt     # y ffmpeg en el PATH
python ListaCD.py                   # interfaz gráfica
python ListaCD.py <enlace> --modo mp3 -o ./salida   # terminal
python -m pytest                    # pruebas
```

- `listacd/spotify.py`: lectura de la lista (API oficial o página pública).
- `listacd/matcher.py`: búsqueda y puntuación de coincidencias en YouTube Music.
- `listacd/downloader.py`: descarga (yt-dlp), volumen, conversión (ffmpeg) y etiquetas.
- `listacd/cd.py`: reparto en discos y hojas `.cue` con CD-Text.
- `listacd/burner.py`: grabación con IMAPI2 de Windows.
- `listacd/gui.py`: interfaz (CustomTkinter).

### Skills de Claude Code incluidas

- `CLAUDE.md`: mapa corto del proyecto para que Claude no gaste tokens explorando.
- `/probar-listacd`: pruebas + comprobación interna + capturas de la interfaz sin pantalla.
- `/critica-listacd`: crítica estructurada (diseño, usabilidad, audio, coche, robustez, recursos)
  con tabla de hallazgos por gravedad. Flujo recomendado: `/critica-listacd` → aplicar mejoras →
  `/probar-listacd`. La primera crítica y su resolución están en `docs/critica-1.md`.

El `.exe` y el instalador se generan en GitHub Actions (`.github/workflows/build-windows.yml`) con
PyInstaller e Inno Setup; para publicar una versión, crea una etiqueta `vX.Y.Z`.

## Aviso legal

Solo para uso personal con música a la que tengas derecho de acceso. Descargar contenido protegido
puede ir contra las condiciones de Spotify y YouTube y contra las leyes de tu país.
