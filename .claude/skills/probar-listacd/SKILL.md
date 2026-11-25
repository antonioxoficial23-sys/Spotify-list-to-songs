---
name: probar-listacd
description: Ejecuta las pruebas, la comprobación interna y captura pantallas de la interfaz de ListaCD sin monitor. Úsala tras cualquier cambio en listacd/ y antes de hacer commit.
---

# Probar ListaCD

Ejecuta en este orden y para en el primer fallo:

1. `python -m pytest -q`
2. `python -m listacd --selftest /tmp/st.txt && cat /tmp/st.txt`
3. Capturas de la interfaz principal (HTML; usa el Playwright de Node ya instalado, sin red ni Python):
   ```bash
   for s in vacia preparando lista grabando ajustes; do node tools/captura_web.js $s /tmp/web_$s.png; done
   node tools/captura_web.js lista /tmp/web_pequena.png 1024 700   # tamaño mínimo
   ```
   Los datos salen de `tools/web_demo.js`. Cualquier «ERROR JS» impreso es un fallo.
   Ventana clásica de reserva (requiere `python3-tk` y `xvfb`; en Linux usa un Python con tkinter):
   ```bash
   Xvfb :99 -screen 0 1280x800x24 & sleep 1
   for s in vacia cargada progreso lista; do
     DISPLAY=:99 PYTHONPATH=. python tools/captura_gui.py $s /tmp/gui_$s.png
   done
   ```
   Mira cada PNG con la herramienta Read (una captura solo para ti: escala 1).
4. Si tocaste `burner.py`, `ListaCD.spec` o el workflow: haz push y revisa el job `windows`
   de GitHub Actions; el paso «Comprobación interna» muestra el selftest del .exe.

Informa solo de lo que falle, con la línea relevante del error. No pegues logs enteros.

## GIF de demostración
`node tools/grabar_demo.js docs/capturas/demo.gif` vuelve a grabar la secuencia del README
(estado «pelicula» de `tools/web_demo.js`). Hazlo tras cambios visibles en la interfaz.
