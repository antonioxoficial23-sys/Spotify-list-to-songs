// Graba la secuencia de demostración (estado «pelicula» de web_demo.js) y la convierte en GIF.
// Uso: node tools/grabar_demo.js docs/capturas/demo.gif
const { chromium } = require("playwright");
const path = require("path");
const fs = require("fs");
const os = require("os");
const { execFileSync } = require("child_process");
const { pathToFileURL } = require("url");

(async () => {
  const out = path.resolve(process.argv[2] || "demo.gif");
  const root = path.resolve(__dirname, "..");
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "listacd-demo-"));
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1200, height: 760 }, recordVideo: { dir: tmp, size: { width: 1200, height: 760 } } });
  const page = await ctx.newPage();
  page.on("pageerror", (e) => console.log("ERROR JS:", e.message));
  await page.addInitScript({ path: path.join(root, "tools", "web_demo.js") });
  await page.goto(pathToFileURL(path.join(root, "listacd", "web", "index.html")).href + "?estado=pelicula");
  await page.waitForTimeout(16000);
  const video = await page.video().path();
  await ctx.close();
  await browser.close();
  // Paleta propia para que el GIF tenga buenos colores; 12 fps y 900 px de ancho
  const filters = "fps=12,scale=900:-1:flags=lanczos";
  execFileSync("ffmpeg", ["-loglevel", "error", "-y", "-ss", "0.6", "-i", video,
    "-vf", `${filters},split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle`,
    "-loop", "0", out]);
  fs.rmSync(tmp, { recursive: true, force: true });
  console.log(`${out} ${(fs.statSync(out).size / 1e6).toFixed(1)} MB`);
})();
