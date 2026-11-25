// Simula el puente de Python para ver la interfaz en un navegador (tools/captura_web.py).
(() => {
  const state = new URLSearchParams(location.search).get("estado") || "vacia";
  const SONGS = [["Bohemian Rhapsody","Queen",354],["Hotel California","Eagles",391],["Sweet Child O' Mine","Guns N' Roses",356],
    ["Billie Jean","Michael Jackson",294],["Despechá","ROSALÍA",157],["Tití Me Preguntó","Bad Bunny",243],
    ["La Bachata","Manuel Turizo",162],["Wonderwall","Oasis",258],["Smells Like Teen Spirit","Nirvana",301],
    ["Mr. Brightside","The Killers",222],["Africa","TOTO",295],["Take On Me","a-ha",225],
    ["Livin' On A Prayer","Bon Jovi",249],["Don't Stop Me Now","Queen",209],["Back In Black","AC/DC",255],
    ["Cuando zarpa el amor","Camela",233],["Mediterráneo","Joan Manuel Serrat",203],["Zombie","The Cranberries",306],
    ["La Flaca","Jarabe de Palo",240],["Rosas","La Oreja de Van Gogh",232]];
  const tracks = [...SONGS, ...SONGS.slice(0, 18)].map(([title, artist, seconds]) => ({ title, artist, seconds }));
  let mode = "audio";
  const plan = (ex) => {
    const discs = []; let cur = null, used = 0;
    tracks.forEach((t, k) => {
      const i = k + 1; if (ex.includes(i)) return;
      const cost = t.seconds + (cur && cur.items.length ? 2 : 0);
      const capOk = mode === "audio" ? used + cost <= 4770 : used + t.seconds * 40000 <= 716800000;
      if (!cur || !capOk) { cur = { number: discs.length + 1, items: [], seconds: 0, size: 0 }; discs.push(cur); used = 0; }
      cur.items.push(i); cur.seconds += t.seconds; cur.size += t.seconds * 40000; used += mode === "audio" ? t.seconds + 2 : t.seconds * 40000;
    });
    return discs;
  };
  const cover = (() => { const c = document.createElement("canvas"); c.width = c.height = 200; const g = c.getContext("2d");
    const gr = g.createLinearGradient(0, 0, 200, 200); gr.addColorStop(0, "#F2B84B"); gr.addColorStop(1, "#C2462E");
    g.fillStyle = gr; g.fillRect(0, 0, 200, 200); g.fillStyle = "rgba(255,255,255,.85)"; g.beginPath(); g.arc(150, 60, 26, 0, 7); g.fill();
    g.fillStyle = "#3A2418"; g.fillRect(0, 150, 200, 50); return c.toDataURL(); })();
  window.pywebview = { api: {
    init: async () => ({ version: "demo", canBurn: true, settings: { mode, normalize: true, outputDir: "C:\\Users\\Antonio\\Music\\ListaCD", clientId: "", hasSecret: false, cookies: "", workers: 4 } }),
    poll: async () => [], plan: async (ex) => plan(ex), set_options: async (m) => { mode = m; return true; },
    load: async () => ({ ok: true }), start: async () => true, cancel: async () => {}, drives: async () => (state === "sin-grabadora" ? [] : [{ id: "1", name: "E: ASUS SDRW-08U9M-U" }]),
    check_disc: async () => ({ ok: true, message: "CD-R virgen en E:." }), burn: async () => true,
    cache_info: async () => ({ bytes: 812e6 }), clear_cache: async () => ({ ok: true, bytes: 0 }),
    save_settings: async () => ({}), read_disc: async () => ({ ok: true }), rename: async (n) => ({ name: n.trim(), changed: true }), paste: async () => "", open_url: async () => {}, open_folder: async () => {}, choose_folder: async () => null,
  } };
  window.LISTACD_DEMO = async (emit, S, render) => {
    if (state === "pelicula") {  // secuencia para el GIF de demostración (tools/grabar_demo.js)
      const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
      await sleep(700);
      const url = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M";
      for (let k = 0; k <= url.length; k += 3) { document.getElementById("url").value = url.slice(0, k); await sleep(25); }
      await sleep(400);
      emit({ type: "loaded", collection: { name: "Viaje a la playa 2026", owner: "Antonio", kind: "playlist", cover, warning: "", note: "", tracks } });
      await sleep(1600);
      await window.prepare();
      const order = tracks.map((_, k) => k + 1);
      for (let k = 0; k < order.length; k++) {
        const i = order[k];
        emit({ type: "track", index: i, status: "Descargando" });
        if (k > 0) emit({ type: "track", index: order[k - 1], status: "Lista" });
        emit({ type: "progress", done: k, total: order.length });
        await sleep(90);
      }
      emit({ type: "track", index: order[order.length - 1], status: "Lista" });
      emit({ type: "job_done", cancelled: false, folder: "", discs: plan([]), failed: [] });
      await sleep(1800);
      S.busy = S.burning = true; S.selectedDisc = 1; render();
      for (let f = 0; f <= 20; f++) {
        emit({ type: "burn_progress", disc: 1, text: `Grabando la pista ${Math.min(17, 1 + Math.floor(f * 17 / 20))} de 17…`, frac: f / 20 });
        await sleep(140);
      }
      emit({ type: "burn_done", disc: 1, more: true });
      return;
    }
    if (state === "cd-leido") {
      const disc = [...tracks.slice(0, 9).map((t) => ({ ...t, unknown: false })),
        ...[10, 11, 12].map((n) => ({ title: `Pista ${n}`, artist: "", seconds: 214 + n, unknown: true }))];
      tracks.splice(0, tracks.length, ...disc);  // el plan simulado usa estas canciones
      emit({ type: "loaded", collection: { name: "Verano 2024", owner: "", kind: "disc", cover: "", warning: "",
        note: "CD de audio con 12 pistas. Lo grabó ListaCD: las canciones salen de su historial. 3 pistas no se pudieron identificar: no se pueden volver a grabar, pero sí puedes añadir canciones nuevas.", tracks: disc } });
      return;
    }
    if (state === "ajustes") { setTimeout(() => document.getElementById("open-settings").click(), 100); return; }
    if (state === "vacia") return;
    emit({ type: "loaded", collection: { name: "Viaje a la playa 2026", owner: "Antonio", kind: "playlist", cover, warning: "", tracks } });
    await new Promise((r) => setTimeout(r, 50));
    for (const i of [5, 6]) S.excluded.add(i);
    S.discs = plan([...S.excluded]); render();
    if (state === "preparando") {
      S.busy = true; S.t0 = Date.now() - 70000; render();
      for (let i = 1; i <= 14; i++) if (!S.excluded.has(i)) emit({ type: "track", index: i, status: "Lista" });
      emit({ type: "track", index: 4, status: "Error", text: "No está en YouTube Music. Prueba a quitarla o busca otra versión en Spotify." });
      emit({ type: "track", index: 15, status: "Convirtiendo" }); emit({ type: "track", index: 16, status: "Descargando" });
      emit({ type: "track", index: 17, status: "Buscando" });
      emit({ type: "progress", done: 13, total: 36 });
    }
    if (state === "lista" || state === "grabando" || state === "sin-grabadora") {
      const discs = plan([...S.excluded, 4]);
      tracks.forEach((_, k) => { if (!S.excluded.has(k + 1) && k + 1 !== 4) emit({ type: "track", index: k + 1, status: "Lista" }); });
      emit({ type: "job_done", cancelled: false, folder: "", discs, failed: [{ index: 4, reason: "YouTube bloqueó la descarga (error 403). Pulsa «Reintentar»; si sigue fallando, en Ajustes elige el navegador con el que entras en YouTube." }] });
      S.burned.add(1); render();
      if (state === "grabando") { S.busy = S.burning = true; S.selectedDisc = 2; render(); emit({ type: "burn_progress", disc: 2, text: "Grabando la pista 7 de 17…", frac: 0.38 }); }
    }
  };
})();
