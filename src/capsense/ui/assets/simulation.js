// CapSense Lab · animación de la pestaña Simulación.
// No calcula física: interpola los arreglos (t, V, I, ADC) que precalcula Python (domain/simulation.py)
// y aplica a los SVG los estados de cada paso (ui/simulation/steps_data.py, armado en guion.py).
(function () {
  "use strict";
  const ESTADO_CHIP = { high: "HIGH · 5 V", low: "LOW · 0 V", hiz: "INPUT", adc: "LECTURA" };
  const REPOSO_REINICIO_S = 120;      // modo guiado: si nadie toca, vuelve al inicio
  const PAUSA_FINAL_AUTO_S = 10;      // modo automático: espera al terminar antes de reiniciar

  const S = {
    svgs: null, d: null, k: 0, vista: "esquema", modo: "guiado", vel: "auto",
    jugando: true, prog: 0, espera: 0, ultimo: 0, toque: Date.now(), offset: 0, ultimoCursor: 0, raf: null,
  };
  const el = (id) => document.getElementById(id);
  const paso = () => (S.d ? S.d.pasos[S.k] : null);

  function lienzo() { return el("sim-lienzo"); }
  function visible() { const v = el("vista-simulacion"); return v && v.style.display !== "none"; }

  // ---------- montaje ----------
  function cargar(svgs, datos) {
    const recarga = S.d !== null;
    S.svgs = svgs; S.d = datos;
    if (!recarga || S.k >= datos.pasos.length) { S.k = 0; }
    montarVista();
    conectar();
    irA(S.k, true);
    if (!S.raf) { S.ultimo = performance.now(); S.raf = requestAnimationFrame(cuadro); }
  }

  function montarVista() {
    const l = lienzo();
    if (!l || !S.svgs) return;
    l.innerHTML = S.svgs[S.vista];
    l.dataset.vista = S.vista;
    const grid = l.closest(".sim-grid");
    if (grid) grid.classList.toggle("modo-protoboard", S.vista === "protoboard");
    [40, 250].forEach((ms) => setTimeout(() => window.dispatchEvent(new Event("resize")), ms));
  }

  let conectado = false;
  function conectar() {
    if (conectado) return;
    conectado = true;
    const click = (id, f) => { const b = el(id); if (b) b.addEventListener("click", () => { S.toque = Date.now(); f(); }); };
    click("sim-ant", () => irA(Math.max(0, S.k - 1)));
    click("sim-sig", () => irA(Math.min(S.d.pasos.length - 1, S.k + 1)));
    click("sim-reiniciar", () => irA(0));
    click("sim-play", () => {
      const p = paso();
      if (S.prog >= 1 && p && p.anima) { S.prog = 0; S.jugando = true; } else { S.jugando = !S.jugando; }
      etiquetaPlay();
    });
    document.querySelectorAll("[id^='sim-v-']").forEach((b) => b.addEventListener("click", () => {
      S.vista = b.dataset.valor; marcar("sim-v-", S.vista); montarVista(); aplicar(); actualizarLecturas(indiceActual());
    }));
    document.querySelectorAll("[id^='sim-m-']").forEach((b) => b.addEventListener("click", () => {
      S.modo = b.dataset.valor; marcar("sim-m-", S.modo); S.espera = 0; S.jugando = true; etiquetaPlay();
    }));
    document.querySelectorAll("[id^='sim-vel-']").forEach((b) => b.addEventListener("click", () => {
      S.vel = b.dataset.valor; marcar("sim-vel-", S.vel);
    }));
    document.addEventListener("keydown", (e) => {
      if (!visible() || e.target.tagName === "INPUT") return;
      if (e.key === "ArrowRight") { S.toque = Date.now(); irA(Math.min(S.d.pasos.length - 1, S.k + 1)); }
      else if (e.key === "ArrowLeft") { S.toque = Date.now(); irA(Math.max(0, S.k - 1)); }
      else if (e.key === " ") { e.preventDefault(); el("sim-play").click(); }
    });
  }

  function marcar(prefijo, valor) {
    document.querySelectorAll(`[id^='${prefijo}']`).forEach((b) => b.classList.toggle("activo", b.dataset.valor === valor));
  }
  function etiquetaPlay() { const t = el("sim-play-txt"); if (t) t.textContent = S.jugando ? "Pausa" : "Play"; }

  // ---------- pasos ----------
  function irA(k, silencioso) {
    if (!S.d) return;
    S.k = k; S.prog = 0; S.espera = 0; S.jugando = true; etiquetaPlay();
    const p = paso();
    el("sim-titulo").textContent = p.titulo;
    el("sim-paso-num").textContent = `Paso ${k + 1} de ${S.d.pasos.length}`;
    el("sim-que-pasa").textContent = p.que_pasa;
    el("sim-proto").textContent = p.protoboard;
    el("sim-codigo").innerHTML = `<span class="linea activa">${esc(p.codigo[p.linea].trim())}</span>`;
    el("sim-pines").innerHTML = "<table><thead><tr><th>Pin</th><th>Para qué</th><th>Estado</th></tr></thead><tbody>" +
      p.pines.map((f) => `<tr><td class="pin">${f.pin}</td><td>${f.rol}</td>` +
        `<td><span class="estado-chip e-${f.estado}">${f.modo}</span> <small>${f.detalle}</small></td></tr>`).join("") +
      "</tbody></table>";
    el("sim-puntos").innerHTML = S.d.pasos.map((q, i) =>
      `<button class="punto-paso${i === k ? " actual" : ""}${i < k ? " hecho" : ""}" data-i="${i}" ` +
      `title="${esc(q.titulo)}" aria-label="Ir al paso ${i + 1}: ${esc(q.titulo)}"></button>`).join("");
    el("sim-puntos").querySelectorAll("button").forEach((b) =>
      b.addEventListener("click", () => { S.toque = Date.now(); irA(+b.dataset.i); }));
    document.querySelectorAll(".sim-formula").forEach((f) => { f.style.display = f.dataset.paso === p.id ? "" : "none"; });
    aplicar();
    graficaPorPaso();
    actualizarLecturas(indiceActual());
  }

  function esc(t) { return String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

  function aplicar() {
    const p = paso(); const l = lienzo();
    if (!p || !l) return;
    const res = new Set(p.resaltar);
    l.querySelectorAll(".sim-el").forEach((g) => {
      const on = res.has(g.dataset.id);
      g.classList.toggle("activo", on);
      g.classList.toggle("apagado", res.size > 0 && !on);
    });
    l.querySelectorAll("[data-pin]").forEach((c) => {
      const est = p.mapa_pines[c.dataset.pin];
      ["high", "low", "hiz", "adc"].forEach((e) => c.classList.toggle("estado-" + e, est === e));
      const t = c.querySelector("text");
      if (t && c.classList.contains("chip")) t.textContent = est ? ESTADO_CHIP[est] : "—";
    });
    l.querySelectorAll("[data-led]").forEach((led) => led.classList.toggle("encendido", !!p.leds[led.dataset.led]));
    l.querySelectorAll("[data-lcd]").forEach((t) => { t.textContent = (p.lcd[+t.dataset.lcd] || "").padEnd(16, " "); });
    l.querySelectorAll("[data-flujo]").forEach((f) => f.classList.toggle("activo", f.dataset.flujo === p.flujo));
  }

  // ---------- tiempo ----------
  function serie() { const p = paso(); return p ? S.d.series[p.serie] : null; }
  function indiceActual() {
    const p = paso(); if (!p) return 0;
    const [a, b] = p.cursor;
    return a + (b - a) * (p.anima ? Math.min(1, S.prog) : 1);
  }
  function duracionReal() { const p = paso(); const s = serie(); if (!p || !s || !p.anima) return 0;
    return Math.max(0, s.t[p.cursor[1]] - s.t[p.cursor[0]]); }
  function duracionReproduccion() {
    const real = duracionReal();
    if (real <= 0) return 0;
    if (S.vel === "auto") { const p = paso(); return p.id === "descarga" || p.id === "pausa" ? 2.5 : 5; }
    return Math.max(0.6, real / +S.vel);
  }
  function interp(arr, x) {
    const i = Math.floor(x); const f = x - i;
    if (i >= arr.length - 1) return arr[arr.length - 1];
    return arr[i] + (arr[i + 1] - arr[i]) * f;
  }

  function actualizarLecturas(x) {
    const s = serie(); const p = paso(); const l = lienzo();
    if (!s || !l) return;
    const v = interp(s.v, x), adc = Math.round(interp(s.adc, x)), t = interp(s.t, x);
    let i = Math.abs(interp(s.i, x));
    if (p.flujo === "descarga" && s.fase[Math.floor(x)] === 2) i = v / S.d.r_descarga * 1000;  // tras t2 ya descarga
    l.querySelectorAll("[data-vc]").forEach((e) => { e.textContent = v.toFixed(2) + " V"; });
    l.querySelectorAll("[data-adc]").forEach((e) => { e.textContent = "ADC " + adc; });
    l.querySelectorAll("[data-relleno]").forEach((r) => {
      const base = +r.dataset.base, alto = +r.dataset.alto, h = Math.max(0, Math.min(1, v / S.d.vin)) * alto;
      r.setAttribute("y", base - h); r.setAttribute("height", h);
    });
    S.intensidad = Math.min(1, i / S.d.i_max);
    const tt = el("sim-tiempo");
    if (tt) {
      const real = duracionReal(), rep = duracionReproduccion();
      let ritmo = "";
      if (real > 0 && rep > 0) {
        const f = rep / real;
        ritmo = f > 1.05 ? ` · cámara lenta ÷${fmtVel(f)}` : (f < 0.95 ? ` · acelerado ×${fmtVel(1 / f)}` : " · tiempo real");
      }
      tt.textContent = `t = ${fmtT(t)} (${t < 0 ? "descarga" : "carga"}) · I = ${fmtI(i)}${ritmo}`;
    }
    moverCursor(t);
  }
  function fmtT(t) { const a = Math.abs(t); const sg = t < 0 ? "−" : ""; return a < 1 ? sg + (a * 1000).toFixed(a < 0.01 ? 3 : 1) + " ms" : sg + a.toFixed(2) + " s"; }
  function fmtI(ma) { return ma < 0.001 ? (ma * 1000).toFixed(2) + " µA" : ma.toFixed(3) + " mA"; }
  function fmtVel(x) { return x >= 100 ? Math.round(x) : x >= 10 ? x.toFixed(0) : x.toFixed(1); }

  // ---------- gráfica ----------
  function gd() { const g = el("sim-graf"); return g ? g.querySelector(".js-plotly-plot") : null; }
  function graficaPorPaso() {
    const g = gd(); const p = paso();
    if (!g || !window.Plotly || !g.data || !p) return;
    const orden = S.d.pasos.map((q) => q.id);
    const desde = (id) => { const i = orden.indexOf(id); return i >= 0 && S.k >= i; };
    const vis = { t1: desde("t1"), t2: desde("t2"), ajuste: desde("ajuste"), tau: desde("ajuste") };
    const idx = [], val = [];
    g.data.forEach((tr, i) => { if (tr.name in vis) { idx.push(i); val.push(vis[tr.name]); } });
    if (idx.length) window.Plotly.restyle(g, { visible: val }, idx);
    const m = S.d.marcas || {};
    const upd = { "shapes[1].visible": vis.ajuste && !!m.p_v, "shapes[0].visible": p.serie === S.d.guia };
    const fy = S.d.factor_y || 1;
    if (m.p_v) { upd["shapes[1].y0"] = m.p_v * fy; upd["shapes[1].y1"] = m.p_v * fy; }
    window.Plotly.relayout(g, upd);
  }
  function moverCursor(t) {
    const g = gd(); const p = paso();
    if (!g || !window.Plotly || !g.layout || !p || p.serie !== S.d.guia) return;
    const ahora = performance.now();
    if (ahora - S.ultimoCursor < 60) return;
    S.ultimoCursor = ahora;
    const x = t * S.d.escala;
    const upd = { "shapes[0].x0": x, "shapes[0].x1": x };
    if (p.id === "ajuste" && p.biseccion) {
      const n = p.biseccion.length, j = Math.min(n - 1, Math.floor(S.prog * n));
      const y = p.biseccion[j] / 1023 * S.d.vin * (S.d.factor_y || 1);
      upd["shapes[1].y0"] = y; upd["shapes[1].y1"] = y; upd["shapes[1].visible"] = true;
      const tt = el("sim-tiempo");
      if (tt) tt.textContent = `Bisección: iteración ${j + 1} de ${n} · P = ${p.biseccion[j].toFixed(2)} cuentas`;
    }
    window.Plotly.relayout(g, upd);
  }

  // ---------- bucle ----------
  function cuadro(ahora) {
    S.raf = requestAnimationFrame(cuadro);
    const dt = Math.min(0.1, (ahora - S.ultimo) / 1000);
    S.ultimo = ahora;
    if (!S.d || !visible()) return;
    const p = paso();
    if (S.jugando) {
      if (p.id === "ajuste") {                       // la bisección se anima aunque no haya tramo de tiempo
        S.prog = Math.min(1, S.prog + dt / 4);
        moverCursor(S.d.series[p.serie].t[p.cursor[1]]);
      } else if (p.anima && S.prog < 1) {
        const dur = duracionReproduccion();
        S.prog = dur > 0 ? Math.min(1, S.prog + dt / dur) : 1;
        actualizarLecturas(indiceActual());
      } else {
        S.prog = 1;
      }
      if (S.prog >= 1 && S.modo === "auto") {
        S.espera += dt;
        const ultimo = S.k === S.d.pasos.length - 1;
        if (S.espera > p.lectura_s + (ultimo ? PAUSA_FINAL_AUTO_S : 0)) irA(ultimo ? 0 : S.k + 1);
      }
    }
    if (S.modo === "guiado" && Date.now() - S.toque > REPOSO_REINICIO_S * 1000 && S.k !== 0) { S.toque = Date.now(); irA(0); }
    // puntos de corriente: velocidad proporcional a I; quietos cuando I ≈ 0
    const l = lienzo();
    if (l) {
      const vel = (S.intensidad || 0) > 0.01 ? 18 + 140 * S.intensidad : 0;
      S.offset -= vel * dt;
      l.querySelectorAll("[data-flujo].activo").forEach((f) => {
        f.style.strokeDashoffset = S.offset;
        f.style.opacity = vel > 0 ? 0.35 + 0.65 * S.intensidad : 0.15;
      });
    }
  }

  window.capsenseSim = { cargar, irA: (k) => irA(k), estado: () => ({ paso: S.k, vista: S.vista, modo: S.modo, prog: S.prog }) };
})();
