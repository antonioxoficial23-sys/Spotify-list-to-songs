"use strict";
// Interfaz de ListaCD. Habla con Python a través de window.pywebview.api.

const $ = (id) => document.getElementById(id);
const S = {
  api: null, mode: "audio", normalize: true, canBurn: false, drives: [], failed: [],
  col: null, excluded: new Set(), status: {}, errors: {},
  discs: [], prepared: false, burned: new Set(), busy: false, burning: false,
  selectedDisc: 1, t0: 0, done: 0, total: 0,
};
const STATUS_TEXT = { Buscando: "Buscando", Descargando: "Descargando", Convirtiendo: "Convirtiendo", Lista: "Lista", Error: "Falló" };
const MODE_HINT = {
  audio: "Calidad CD, sin pasar por MP3. Suena en cualquier radio con CD. Unas 18 canciones por disco.",
  mp3: "MP3 a 320 kbps, unas 70 canciones por disco. Solo si tu radio pone «MP3» en el frontal.",
};

function fmt(sec) {
  sec = Math.round(sec);
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}` : `${m}:${String(s).padStart(2, "0")}`;
}
function minutes(sec) { return `${Math.round(sec / 60)} min`; }
function longDur(sec) {
  const h = Math.floor(sec / 3600), m = Math.round((sec % 3600) / 60);
  return h ? `${h} h ${m} min` : `${m} min`;
}
function el(tag, attrs = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") n.className = v; else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) n.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kids.flat()) if (k != null) n.append(k.nodeType ? k : document.createTextNode(k));
  return n;
}

// ------------------------------------------------------------------ diálogos
function ask(title, text, okText = "Aceptar", cancelText = "Cancelar") {
  $("m-title").textContent = title; $("m-text").textContent = text;
  $("m-ok").textContent = okText;
  $("m-cancel").hidden = !cancelText; $("m-cancel").textContent = cancelText || "";
  const d = $("dlg-msg"); d.returnValue = ""; d.showModal();
  return new Promise((res) => d.addEventListener("close", () => res(d.returnValue === "ok"), { once: true }));
}
const tell = (title, text) => ask(title, text, "Entendido", null);

// --------------------------------------------------------------------- disco
function renderDisc() {
  const disc = $("disc");
  disc.classList.toggle("empty", !S.col);
  $("disc-title").textContent = S.col ? S.col.name : "Tu lista aquí";
  disc.classList.toggle("spinning", S.busy && !reduceMotion());
  let burn = 0;
  if (S.burning) burn = S.burnFrac || 0;
  else if (S.busy && S.total) burn = S.done / S.total;
  else if (S.prepared) burn = S.burned.has(S.selectedDisc) ? 1 : 0;
  disc.style.setProperty("--burn", burn.toFixed(3));
}
const reduceMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

function renderChips() {
  const box = $("chips"); box.replaceChildren();
  const cap = S.mode === "audio" ? 79.5 * 60 : 716800000;
  for (const d of S.discs) {
    const fill = S.mode === "audio" ? (d.seconds + 2 * (d.items.length - 1)) / cap : d.size / cap;
    const done = S.burned.has(d.number);
    box.append(el("button", {
      class: "chip" + (done ? " done" : ""), style: `--fill:${Math.min(1, fill).toFixed(3)}`,
      "aria-current": String(d.number === S.selectedDisc),
      title: `Disco ${d.number}: ${d.items.length} canciones, ${minutes(d.seconds)}${done ? ", grabado" : ""}`,
      onclick: () => { S.selectedDisc = d.number; renderChips(); renderDisc(); scrollToDisc(d.number); },
    }, el("span", {}, String(d.number))));
  }
  const n = S.discs.length;
  const kind = S.mode === "audio" ? "CD-R de 80 minutos" : "CD-R de 700 MB";
  $("plan").textContent = !S.col ? "Pega un enlace para ver cuántos CD necesitas."
    : n === 0 ? "No has marcado ninguna canción."
    : `${n === 1 ? `Cabe en un ${kind}` : `Necesitas ${n} ${kind}`}${S.prepared ? "" : " (aproximado)"}.`;
}
function scrollToDisc(n) { const g = document.querySelector(`[data-disc="${n}"]`); if (g) g.scrollIntoView({ behavior: reduceMotion() ? "auto" : "smooth", block: "start" }); }

// ------------------------------------------------------------------- lista
function renderTracks() {
  const box = $("tracks"); box.replaceChildren();
  if (!S.col) {
    box.append(el("ol", { class: "empty-steps" },
      el("li", {}, el("span", {}, "En Spotify, abre tu lista y pulsa ", el("b", {}, "⋯"), ".")),
      el("li", {}, el("span", {}, "Elige ", el("b", {}, "Compartir"), " y después ", el("b", {}, "Copiar enlace"), ".")),
      el("li", {}, el("span", {}, "Vuelve aquí y pulsa ", el("b", {}, "Pegar"), "."))),
      el("p", { class: "empty-note" }, el("b", {}, "¿Más de 100 canciones? "),
        "En Spotify para ordenador, abre la lista, pulsa en una canción y después ",
        el("kbd", {}, "Ctrl"), "+", el("kbd", {}, "A"), " y ", el("kbd", {}, "Ctrl"), "+", el("kbd", {}, "C"),
        ". Vuelve aquí y pulsa ", el("b", {}, "Pegar"), ": se leerán todas, una a una."));
    return;
  }
  const groups = S.discs.map((d) => ({ title: "Disco", n: d.number, items: d.items, seconds: d.seconds }));
  const off = S.col.tracks.map((_, i) => i + 1).filter((i) => S.excluded.has(i));
  const assigned = new Set(S.discs.flatMap((d) => d.items));
  const failed = S.col.tracks.map((_, i) => i + 1).filter((i) => !assigned.has(i) && !S.excluded.has(i));
  if (failed.length) groups.push({ title: "No se pudieron conseguir", items: failed, failed: true });
  if (off.length) groups.push({ title: "No se grabarán", items: off, off: true });

  for (const g of groups) {
    const head = el("div", { class: "group-head" },
      el("h2", {}, g.title, g.n ? el("span", { class: "n" }, String(g.n)) : null),
      el("span", {}, g.n ? `${g.items.length} canciones, ${minutes(g.seconds)}` : `${g.items.length}`));
    const sec = el("section", { class: "group" + (g.off ? " off" : ""), "data-disc": g.n || "" }, head);
    for (const i of g.items) sec.append(trackRow(i));
    box.append(sec);
  }
}
function trackRow(i) {
  const t = S.col.tracks[i - 1], on = !S.excluded.has(i);
  const st = S.prepared && S.status[i] === "Lista" ? null : S.status[i];
  const cls = st === "Lista" ? "ok" : st === "Error" ? "err" : st ? "work" : "";
  const row = el("div", { class: "row-t" + (on ? "" : " off"), id: `t${i}` },
    el("button", { class: "chk", role: "checkbox", "aria-checked": String(on), disabled: S.busy || null,
      "aria-label": `${on ? "Quitar" : "Poner"} ${t.title}`, onclick: () => toggle(i) }),
    el("span", { class: "num" }, String(i)),
    el("div", { class: "what" }, el("strong", {}, t.title), el("span", {}, t.artist)),
    el("span", { class: "dur" }, fmt(t.seconds)),
    el("span", { class: "st " + cls }, st ? STATUS_TEXT[st] || st : ""));
  if (st === "Error" && S.errors[i]) row.append(el("span", { class: "row-why" }, S.errors[i]));
  return row;
}
function updateRow(i) { const old = $(`t${i}`); if (old) old.replaceWith(trackRow(i)); }

async function toggle(i) {
  if (S.busy) return;
  S.excluded.has(i) ? S.excluded.delete(i) : S.excluded.add(i);
  S.prepared = false; S.burned.clear();
  await replan();
}
async function replan() {
  S.discs = S.col ? await S.api.plan([...S.excluded]) : [];
  if (!S.discs.some((d) => d.number === S.selectedDisc)) S.selectedDisc = 1;
  render();
}

// ---------------------------------------------------------------- controles
function render() {
  renderDisc(); renderChips(); renderTracks();
  document.querySelectorAll(".segmented button").forEach((b) => {
    b.setAttribute("aria-checked", String(b.dataset.mode === S.mode)); b.disabled = S.busy;
  });
  $("mode-hint").textContent = MODE_HINT[S.mode];
  $("normalize").checked = S.normalize; $("normalize").disabled = S.busy;
  const n = S.discs.length;
  const prep = $("prepare");
  prep.disabled = S.busy || !S.col || n === 0;
  prep.textContent = S.busy && !S.burning ? "Preparando…" : n > 1 ? `Preparar los ${n} discos` : "Preparar el disco";
  if (!S.col) prep.textContent = "Preparar los discos";
  $("cancel").hidden = !(S.busy && !S.burning);
  // Con los discos preparados, las opciones se resumen en una línea para dejar sitio al disco
  $("options").hidden = S.prepared; prep.hidden = S.prepared;
  $("summary").hidden = !S.prepared;
  $("summary-text").textContent = `${S.mode === "audio" ? "CD de audio" : "CD MP3"}${S.normalize ? ", volumen igualado" : ""}`;
  $("change").disabled = S.busy;
  $("load").disabled = S.busy;
  if (S.col) $("list-name").contentEditable = S.busy ? "false" : "plaintext-only";
  renderBurn();
}
function setStatus(html, cls = "") { $("status").replaceChildren(cls ? el("span", { class: cls }, html) : html); }

function renderBurn() {
  const box = $("burn");
  box.hidden = !S.prepared || !S.discs.length;
  if (box.hidden) return;
  const list = $("burn-list"); list.replaceChildren();
  const noDrive = S.canBurn && !S.drives.length;
  $("drive").closest(".field").hidden = !S.canBurn || noDrive;
  if (noDrive) {
    list.append(el("p", { class: "hint" }, "No se encuentra ninguna grabadora. Conéctala y pulsa ",
      el("button", { class: "btn link inline", onclick: loadDrives }, "Buscar de nuevo"), "."));
  }
  if (S.failed.length && !S.busy) {
    const n = S.failed.length;
    list.append(el("div", { class: "retry" },
      el("span", {}, n === 1 ? "Falta una canción." : `Faltan ${n} canciones.`),
      el("button", { class: "btn quiet", onclick: prepare }, n === 1 ? "Reintentar" : `Reintentar las ${n}`)));
  }
  if (!S.canBurn) {
    list.append(el("p", { class: "hint" }, "Desde aquí solo se puede grabar en Windows. Graba la carpeta de cada disco con tu programa de grabación."));
  }
  for (const d of S.discs) {
    const done = S.burned.has(d.number);
    list.append(el("div", { class: "burn-item" + (done ? " done" : "") },
      el("div", {}, el("strong", {}, done ? `Disco ${d.number} grabado` : `Disco ${d.number}`),
        el("small", {}, `${d.items.length} canciones, ${minutes(d.seconds)}`)),
      el("button", { class: "btn " + (done ? "quiet" : "primary"), disabled: !S.canBurn || noDrive || S.busy || null,
        onclick: () => burn(d.number) }, done ? "Grabar otra copia" : `Grabar disco ${d.number}`)));
  }
}

async function loadDrives() {
  if (!S.canBurn) return renderBurn();
  S.drives = await S.api.drives();
  const sel = $("drive"); sel.replaceChildren();
  for (const d of S.drives) sel.append(el("option", { value: d.id }, d.name));
  renderBurn();
}

// ------------------------------------------------------------------ acciones
async function load(ev) {
  ev && ev.preventDefault();
  const url = $("url").value.trim();
  if (!url || S.busy) return;
  $("load").disabled = true; $("load").textContent = "Cargando…";
  const r = await S.api.load(url);
  if (!r.ok) { $("load").disabled = false; $("load").textContent = "Cargar lista"; tell("Revisa el enlace", r.error); }
}
async function prepare() {
  if (!(await S.api.start([...S.excluded]))) return;
  S.busy = true; S.prepared = false; S.status = {}; S.errors = {}; S.failed = []; S.burned.clear();
  S.t0 = Date.now(); S.done = 0; S.total = S.col.tracks.length - S.excluded.size;
  setStatus("Buscando las canciones…");
  render();
}
async function burn(n) {
  const drive = $("drive").value;
  if (!drive) return tell("Falta la grabadora", "Conecta la grabadora de CD y vuelve a abrir ListaCD.");
  setStatus("Comprobando el disco…");
  const chk = await S.api.check_disc(n, drive);
  if (!chk.ok) { setStatus(chk.message, "bad"); return tell("Todavía no se puede grabar", chk.message); }
  const d = S.discs.find((x) => x.number === n);
  const go = await ask(`Grabar disco ${n}`,
    `${chk.message} Se grabarán ${d.items.length} canciones (${minutes(d.seconds)}). Tarda unos minutos; no cierres ListaCD mientras tanto.`,
    `Grabar disco ${n}`);
  if (!go) return setStatus("");
  if (await S.api.burn(n, drive)) {
    S.busy = S.burning = true; S.selectedDisc = n; S.burnFrac = 0;
    setStatus("Grabando…"); render();
  }
}

// -------------------------------------------------------------------- eventos
function onEvent(e) {
  switch (e.type) {
    case "loaded":
      S.col = e.collection; S.excluded.clear(); S.status = {}; S.errors = {}; S.prepared = false; S.burned.clear();
      $("load").disabled = false; $("load").textContent = "Cargar lista";
      $("list-name").textContent = S.col.name;
      $("list-name").contentEditable = "plaintext-only";  // se bloquea mientras se trabaja (render)
      $("list-name").title = "Pulsa para cambiar el nombre (es el que se escribe en el disco)";
      $("list-meta").textContent = [S.col.owner, `${S.col.tracks.length} canciones, ${longDur(S.col.tracks.reduce((a, t) => a + t.seconds, 0))}`].filter(Boolean).join(", ");
      $("list-warn").hidden = !S.col.warning; $("list-warn").textContent = S.col.warning || "";
      $("cover").hidden = !S.col.cover; if (S.col.cover) $("cover").src = S.col.cover;
      setStatus(""); replan(); break;
    case "load_progress":
      $("load").textContent = `Leyendo ${e.done} de ${e.total}…`; break;
    case "load_error":
      $("load").disabled = false; $("load").textContent = "Cargar lista"; tell("No se pudo cargar", e.message); break;
    case "track":
      S.status[e.index] = e.status; if (e.text) S.errors[e.index] = e.text; updateRow(e.index); break;
    case "progress": {
      S.done = e.done; S.total = e.total;
      const left = S.done ? (Date.now() - S.t0) / S.done * (S.total - S.done) / 1000 : 0;
      setStatus(`${S.done} de ${S.total} canciones preparadas.` + (S.done && left > 30 ? ` Quedan unos ${Math.ceil(left / 60)} min.` : ""));
      renderDisc(); break;
    }
    case "job_done":
      S.busy = false;
      if (e.cancelled) { setStatus("Preparación cancelada."); render(); break; }
      S.discs = e.discs; S.prepared = true; S.selectedDisc = 1;
      S.failed = e.failed.map((f) => f.index);
      for (const f of e.failed) S.errors[f.index] = f.reason;
      setStatus(!e.failed.length ? "Discos listos para grabar."
        : e.failed.length === 1 ? "Discos listos, pero falta una canción." : `Discos listos, pero faltan ${e.failed.length} canciones.`,
        e.failed.length ? "" : "good");
      render(); loadDrives(); break;
    case "job_error":
      S.busy = false; setStatus(e.message, "bad"); render(); break;
    case "burn_progress":
      S.burnFrac = e.frac; setStatus(e.text); renderDisc(); break;
    case "burn_done":
      S.busy = S.burning = false; S.burned.add(e.disc); setStatus(`Disco ${e.disc} grabado.`, "good"); render();
      tell(`Disco ${e.disc} grabado`, e.more ? `Saca el disco, mete otro CD-R virgen y pulsa «Grabar disco ${e.disc + 1}».` : "Ya puedes llevártelo al coche.");
      break;
    case "burn_error":
      S.busy = S.burning = false; setStatus("No se pudo grabar.", "bad"); render();
      tell(`No se pudo grabar el disco ${e.disc}`, e.message); break;
  }
}
async function pump() {
  try { for (const e of await S.api.poll()) onEvent(e); } catch (err) { console.error(err); }
  setTimeout(pump, 150);
}

// ------------------------------------------------------------------- ajustes
async function openSettings() {
  const info = await S.api.init(); const s = info.settings;
  $("s-out").value = s.outputDir; $("s-id").value = s.clientId; $("s-secret").value = "";
  $("s-secret").placeholder = s.hasSecret ? "Guardado (déjalo vacío para no cambiarlo)" : "";
  $("s-cookies").value = s.cookies; $("s-workers").value = String(s.workers);
  showCache((await S.api.cache_info()).bytes);
  const d = $("dlg-settings"); d.returnValue = ""; d.showModal();
  d.addEventListener("close", async () => {
    if (d.returnValue !== "save") return;
    await S.api.save_settings({ outputDir: $("s-out").value, clientId: $("s-id").value, clientSecret: $("s-secret").value,
      cookies: $("s-cookies").value, workers: $("s-workers").value });
  }, { once: true });
}
function showCache(bytes) { $("s-cache").textContent = `Audios guardados para no volver a descargarlos: ${Math.round(bytes / 1e6)} MB`; }

// ----------------------------------------------------------------------- inicio
async function start() {
  S.api = window.pywebview.api;
  const info = await S.api.init();
  S.mode = info.settings.mode; S.normalize = info.settings.normalize; S.canBurn = info.canBurn;
  $("link-form").addEventListener("submit", load);
  $("paste").addEventListener("click", async () => {
    let t = await S.api.paste();
    if (!t && navigator.clipboard) { try { t = await navigator.clipboard.readText(); } catch (_) {} }
    if (t) { $("url").value = t.trim(); load(); } else $("url").focus();
  });
  document.querySelectorAll(".segmented button").forEach((b) => b.addEventListener("click", async () => {
    if (S.busy || b.dataset.mode === S.mode) return;
    S.mode = b.dataset.mode; S.prepared = false; S.burned.clear();
    await S.api.set_options(S.mode, S.normalize); replan();
  }));
  $("normalize").addEventListener("change", async () => { S.normalize = $("normalize").checked; S.prepared = false; await S.api.set_options(S.mode, S.normalize); render(); });
  $("prepare").addEventListener("click", prepare);
  const nameEl = $("list-name");
  nameEl.addEventListener("keydown", (ev) => { if (ev.key === "Enter") { ev.preventDefault(); nameEl.blur(); } });
  nameEl.addEventListener("blur", async () => {
    if (!S.col) return;
    const r = await S.api.rename(nameEl.textContent);
    nameEl.textContent = r.name || S.col.name;
    if (r.changed) { S.col.name = r.name; S.prepared = false; S.burned.clear(); render(); }
  });
  $("change").addEventListener("click", () => { if (S.busy) return; S.prepared = false; S.burned.clear(); setStatus(""); render(); });
  $("cancel").addEventListener("click", () => { S.api.cancel(); setStatus("Cancelando: se terminan las canciones en curso…"); });
  $("open-folder").addEventListener("click", () => S.api.open_folder());
  $("open-settings").addEventListener("click", openSettings);
  $("s-pick").addEventListener("click", async () => { const p = await S.api.choose_folder(); if (p) $("s-out").value = p; });
  $("s-dash").addEventListener("click", () => S.api.open_url("https://developer.spotify.com/dashboard"));
  $("s-clear").addEventListener("click", async () => { const r = await S.api.clear_cache(); if (r.ok) showCache(r.bytes); });
  render(); pump();
  if (window.LISTACD_DEMO) window.LISTACD_DEMO(onEvent, S, render);
}
if (window.pywebview && window.pywebview.api) start(); else window.addEventListener("pywebviewready", start);
