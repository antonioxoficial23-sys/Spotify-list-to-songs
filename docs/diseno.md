# Plan de diseño de ListaCD (skill `frontend-design`)

## El tema
Quien usa ListaCD está **haciendo un CD grabado para el coche**: el CD-R plateado con el título
escrito a rotulador y la carátula con la lista de canciones. Ese objeto es lo más reconocible
de este mundo, y de ahí sale el diseño. No es una app de streaming ni un panel de control.

## Primera versión del plan (descartada)
Fondo casi negro (#121212), un solo acento ámbar y tarjetas redondeadas iguales, con metadatos
unidos con puntos («antonio · 45 canciones · 3:18:33»).
**Revisión:** cae de lleno en los clichés 2 (casi negro + un acento vivo), 4 (kit de tarjetas
SaaS) y 5 (cadenas con puntos medios) de la skill. Sirve para cualquier app, no para esta.

## Plan revisado

### Color (escritorio a la luz del día, no salpicadero de noche)
| Nombre | Hex | Uso |
|---|---|---|
| Mesa | `#DADFE3` | Fondo: gris aluminio frío, como la bandeja de la grabadora |
| Papel | `#FCFCFA` | La carátula con la lista (el único «papel») |
| Tinta | `#1F2733` | Texto |
| Lápiz | `#68717D` | Texto secundario |
| Rotulador | `#1E43C8` | Acento: el azul del rotulador permanente. Botones y selección |
| Grabado | `#3B2F5C` | La zona ya grabada de un CD-R (más oscura, violeta tinta) |

Correcto `#2F7A4A`, error `#B83A2E`, aviso `#9A6A00`, siempre acompañados de texto.

### Tipografía
- **Permanent Marker**: solo el título escrito en el disco y el número de cada disco.
  Es el único gesto llamativo; nunca en botones ni en textos.
- **Atkinson Hyperlegible Next**: todo lo demás. Pensada para leerse muy bien. Cifras
  tabulares para las duraciones, sin recurrir a una fuente monoespaciada.
- Escala (Elements of Typographic Style, 1,25): 13 · 15 · 18 · 22 · 28 px.

### Disposición
```
┌──────────────────────────────────────────────────────────────┐
│ ListaCD                                            Ajustes   │
│ ┌──────────────────────────────────────┐ [Pegar] [Cargar]    │
│ │ enlace de Spotify                    │                     │
│ └──────────────────────────────────────┘                     │
├─────────────────────────────┬────────────────────────────────┤
│        ╭──────────╮         │ ┌ carátula de papel ─────────┐ │
│      ╱  Viaje en   ╲        │ │ Disco 1          74 min    │ │
│     │   coche  (o)  │       │ │ ☑ 1 Bohemian Rhapsody 5:54 │ │
│      ╲  ~~~~~~~~   ╱        │ │ ☑ 2 Hotel California  6:31 │ │
│        ╰──────────╯         │ │ Disco 2          78 min    │ │
│   (1)  (2)  (3)  discos     │ │ ...                        │ │
│                             │ └────────────────────────────┘ │
│  Tipo de CD [Audio | MP3]   │                                │
│  [x] Igualar volumen        │                                │
│  [  Preparar 3 discos  ]    │                                │
│  progreso / grabar          │                                │
└─────────────────────────────┴────────────────────────────────┘
```
- A la izquierda, el **disco**: un CD-R dibujado (plata con un leve iris), con el nombre de la
  lista a rotulador. La zona grabada se oscurece del centro hacia fuera según el progreso,
  igual que un CD-R de verdad. Debajo, un disco pequeño por cada CD necesario.
- A la derecha, la **carátula**: una hoja de papel con la lista agrupada por discos, como el
  interior de una caja de CD. Texto alineado a la izquierda y duraciones a la derecha.
- Los pasos 1-2-3 no se numeran con marcadores: el orden lo da la propia disposición.

### Principios
1. Lo memorable es el disco. Todo lo demás es sobrio: sin sombras genéricas ni degradados decorativos.
2. Movimiento solo como respuesta: el disco gira mientras se prepara o se graba; nada se anima al cargar.
3. Textos desde el punto de vista del usuario: «Preparar 3 discos», «Grabar disco 2»,
   «Mete un CD-R virgen». Los errores dicen qué hacer.
4. Mínimos de calidad: foco visible con teclado, `prefers-reduced-motion`, contraste AA
   y la ventana usable desde 1024×700.
