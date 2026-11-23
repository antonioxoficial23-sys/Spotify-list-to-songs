---
name: diseno-listacd
description: Sistema de diseño de ListaCD (tokens, estados de componentes, accesibilidad WCAG 2.2 AA y lista de control). Úsala para cualquier cambio visual en listacd/web/ y al revisar el diseño.
license: MIT
metadata:
  formato: "Estructura de typeui.sh / bergside/awesome-design-skills (MIT), con los tokens propios de ListaCD"
---

# Sistema de diseño de ListaCD

## Intención
Grabar un CD para el coche debe sentirse como hacer un CD de los de antes: un CD-R plateado
escrito a rotulador y una carátula de papel con la lista. Concepto completo en `docs/diseno.md`
y tokens en `DESIGN.md` (esta misma carpeta). Para ideas nuevas, combínala con `frontend-design`.

## Tokens (variables CSS en `listacd/web/app.css`, nunca valores sueltos)
| Token | Valor | Uso |
|---|---|---|
| `--mesa` | #DADFE3 | Fondo |
| `--mesa-hondo` | #C9CFD5 | Fondo de controles agrupados |
| `--papel` | #FCFCFA | Carátula y diálogos |
| `--tinta` | #1F2733 | Texto principal |
| `--lapiz` | #4A5361 | Texto secundario (≥ 4,5:1 sobre mesa, mesa-hondo y papel) |
| `--rotulador` | #1E43C8 | Acción principal, selección, foco |
| `--grabado` | #3B2F5C | Zona grabada del disco |
| `--ok` / `--error` / `--aviso` | #22643A / #A8342A / #8A5E00 | Estados, siempre con texto |
| `--borde` | #727B86 | Bordes de controles (≥ 3:1 sobre mesa) |

- Tipografía: Atkinson Hyperlegible Next para todo; Permanent Marker **solo** en el título del disco
  y los números de los pasos vacíos. Escala 13/15/18/22/28 px. Cifras tabulares en duraciones.
- Espaciado: 4/8/12/16/24/28 px. Radios: 4 (papel), 8 (campos), 10 (botones), 12 (grupos), 50 % (discos).

## Reglas
- **Debe**: cada control tiene estados normal, hover, foco visible (contorno de 3 px `--rotulador`),
  pulsado, desactivado y, si procede, cargando y error.
  **No**: un botón desactivado que parezca activo (ej.: azul con texto apagado).
- **Debe**: contraste ≥ 4,5:1 en texto y ≥ 3:1 en bordes e iconos de controles (WCAG 2.2 AA).
  **No**: texto `--lapiz` sobre fondos más oscuros que `--mesa-hondo`.
- **Debe**: objetivos táctiles de al menos 24×24 px (WCAG 2.2, 2.5.8).
  **No**: casillas o enlaces de menos de 24 px de alto.
- **Debe**: el estado se comunica con texto, no solo con color («Falló», «Lista»).
- **Debe**: movimiento solo como respuesta (el disco gira al preparar o grabar) y respetar
  `prefers-reduced-motion`. **No**: animaciones de entrada en cada sección.
- **Debe**: textos en español, en segunda persona y con el verbo de la acción («Grabar disco 2»).
  Los errores dicen qué hacer. **No**: mensajes técnicos en inglés a la vista del usuario.
- **No**: Inter/Roboto, degradados violeta, tarjetas iguales con sombra gris, mayúsculas en etiquetas
  ni cadenas con puntos medios («A · B · C»).

## Lista de control antes de terminar
1. `node tools/captura_web.js <estado> /tmp/x.png` en vacia, preparando, lista, grabando,
   sin-grabadora y ajustes, y a 1024×700. Ningún «ERROR JS».
2. Recorre la pantalla solo con el teclado (Tab/Mayús+Tab/Espacio): todo se alcanza y el foco se ve.
3. Comprueba contraste de cualquier color nuevo (script en `tools/contraste.py`).
4. Textos largos (nombres de canción de 80 caracteres, lista de 300 canciones): sin desbordes.
5. Estados vacío, cargando, error y éxito presentes en lo que hayas tocado.
