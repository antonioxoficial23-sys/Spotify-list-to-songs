// Captura la interfaz HTML con datos de ejemplo (sin Python ni red).
// Uso: node tools/captura_web.js <vacia|cargada|preparando|lista|grabando> salida.png [ancho alto]
const { chromium } = require("playwright");
const path = require("path");
const { pathToFileURL } = require("url");

(async () => {
  const [state, out, w = "1280", h = "800"] = process.argv.slice(2);
  const root = path.resolve(__dirname, "..");
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: +w, height: +h }, deviceScaleFactor: +(process.env.ESCALA || 1) });
  page.on("pageerror", (e) => console.log("ERROR JS:", e.message));
  page.on("console", (m) => m.type() === "error" && console.log("ERROR JS:", m.text()));
  await page.addInitScript({ path: path.join(root, "tools", "web_demo.js") });
  await page.goto(pathToFileURL(path.join(root, "listacd", "web", "index.html")).href + `?estado=${state}`);
  await page.waitForTimeout(900);
  await page.screenshot({ path: out });
  await browser.close();
})();
