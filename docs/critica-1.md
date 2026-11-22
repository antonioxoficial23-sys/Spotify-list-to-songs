# Crítica 1 de ListaCD (skill `critica-listacd`)

## Impresión general
El flujo de 3 pasos es claro y la parte de audio es sólida (una sola conversión, soxr + dither,
normalización sin saturar). Lo flojo es el acabado visual (violeta "de IA" y emojis que Tk en
Windows no pinta bien), que no se pueda elegir qué canciones grabar, y algunos huecos de
robustez y de consumo de disco.

## Hallazgos
| # | Apartado | Problema | Gravedad | Propuesta concreta |
|---|---|---|---|---|
| 1 | Robustez | Cerrar la ventana mientras graba estropea el CD sin avisar | alta | `gui.py`: `protocol("WM_DELETE_WINDOW")` con confirmación si hay trabajo en curso |
| 2 | Usabilidad | No se pueden quitar canciones (p. ej. para que la lista quepa en un solo CD) | alta | Columna ☑ clicable; el plan y `run_job(include=…)` solo usan las marcadas |
| 3 | Diseño | Los emojis (🔎 ⬇ ⚙ 💿 📂) en Tk 8.6/Windows salen monocromos, cortados o como cuadros | media | Sustituirlos por símbolos tipográficos (● ✓ ✕ ↻) y puntos de color |
| 4 | Diseño | Paleta violeta y fuente Roboto: el cliché de interfaz generada por IA | media | Paleta propia «salpicadero»: grafito + ámbar; Segoe UI en Windows |
| 5 | Usabilidad | La tabla salta sola a la canción que se descarga aunque estés mirando otra | media | Quitar el `see()` automático |
| 6 | Usabilidad | Si una canción falla no se ve el motivo | media | Al seleccionar la fila, mostrar el motivo bajo la barra de progreso |
| 7 | Usabilidad | Tras grabar no queda constancia de qué discos ya están hechos | media | Marcar «✓ Grabado» en el botón de cada disco |
| 8 | Recursos | La caché de originales crece sin límite y no se puede vaciar | media | Ajustes: mostrar tamaño y botón «Vaciar caché» |
| 9 | Recursos | Se vuelve a medir el volumen (decodificación completa) en cada ejecución | baja | Cachear sonoridad por vídeo en `volumen.json` |
| 10 | Recursos | El instalador incluye `curl_cffi` (~10 MB) que no se usa para YouTube | baja | `excludes` en `ListaCD.spec` |
| 11 | Usabilidad | La ventana de Ajustes tiene tamaño fijo: con escalado 125–150 % se corta | baja | Dejar que se ajuste al contenido |
| 12 | Usabilidad | En 1366×768 los botones de grabar quedan fuera de la vista | baja | Textos de ayuda más cortos y desplazamiento automático al terminar (ya hecho) |

## Las 3 mejoras que más valor aportan
1. Confirmar antes de cerrar mientras se graba (#1).
2. Elegir qué canciones entran (#2).
3. Acabado visual fiable en Windows: sin emojis y con paleta propia (#3, #4).

## Estado tras aplicar las mejoras
| # | Resultado |
|---|---|
| 1 | ✓ Confirmación al cerrar (aviso fuerte si está grabando) |
| 2 | ✓ Columna ☑ por canción y en la cabecera (todas/ninguna); el plan se recalcula |
| 3 | ✓ Sin emojis: ● ✓ ✕ ☑ |
| 4 | ✓ Paleta grafito + ámbar; Segoe UI en Windows |
| 5 | ✓ Sin desplazamiento automático |
| 6 | ✓ Al seleccionar una canción fallida se muestra el motivo |
| 7 | ✓ «✓ Disco N grabado · grabar otra copia» |
| 8 | ✓ Tamaño de la caché y botón «Vaciar caché» en Ajustes |
| 9 | ✓ `volumen.json`: la sonoridad se mide una sola vez por canción |
| 10 | ✓ `curl_cffi` excluido del .exe |
| 11 | ✓ Ajustes se adapta al contenido |
| 12 | ✓ Textos de ayuda más cortos; además, botón principal gris cuando no se puede usar y barra de progreso oculta hasta empezar |
