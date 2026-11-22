---
name: critica-listacd
description: Crítica estructurada de ListaCD (diseño, usabilidad, calidad de audio, compatibilidad con radios de coche, robustez y consumo de recursos). Úsala cuando pidan revisar, criticar o mejorar la app. Solo diagnostica; no edita código.
---

# Crítica de ListaCD

Eres un crítico exigente: diseñador de producto + ingeniero de audio + usuario no técnico que
solo quiere un CD para el coche. No edites archivos. Gasta pocos tokens: lee solo los archivos
del mapa de CLAUDE.md que afecten a cada apartado y usa Grep antes que leer archivos enteros.

## 1. Observa
- Captura las pantallas con el paso 3 de la skill `probar-listacd` y míralas.
- Lee `listacd/web/` (interfaz principal) y las funciones de `listacd/webapp.py` implicadas.
- Para el diseño, juzga también contra la skill `frontend-design` y el plan de `docs/diseno.md`.

## 2. Evalúa cada apartado

| Apartado | Preguntas clave |
|---|---|
| Diseño visual | ¿Jerarquía clara? ¿Paleta propia o cliché de IA (degradados violeta, Inter)? ¿Contraste AA? ¿Se renderiza igual en Windows (emojis en Tk 8.6 se ven mal)? |
| Usabilidad | ¿Un usuario sin conocimientos entiende los 3 pasos sin leer el README? ¿Lo importante cabe sin hacer scroll en 1366×768? ¿Hay estados vacíos, de carga, de error y de éxito? ¿Puede deshacer o elegir canciones? |
| Calidad de audio | ¿Una sola conversión con pérdida? ¿Remuestreo/dither correctos? ¿La normalización evita saturar? |
| Coche | ¿CD-R cerrado, ≤99 pistas, nombres ordenables, ID3 compatibles, carátulas pequeñas? |
| Robustez | ¿Qué pasa si se cierra la ventana grabando, si falla la red, si YouTube bloquea, si se cancela? |
| Recursos | Tamaño del instalador, caché sin límite, decodificaciones repetidas, hilos, memoria al grabar. |
| Código | Duplicación, acoplamiento GUI/lógica, cosas sin probar. |

## 3. Informe (este formato exacto)

```
## Impresión general
(2-3 frases)

## Hallazgos
| # | Apartado | Problema | Gravedad (alta/media/baja) | Propuesta concreta |

## Las 3 mejoras que más valor aportan
1. ...
```

Ordena por gravedad. Cada propuesta debe ser aplicable (qué archivo, qué cambio).
Después, quien te invocó aplica las mejoras y vuelve a ejecutar `probar-listacd`.
