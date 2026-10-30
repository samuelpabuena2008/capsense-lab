"""Interacciones de la aplicación."""
from __future__ import annotations

import base64
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import dash
from dash import Input, Output, State, dcc, html, no_update
from dash.exceptions import PreventUpdate

from capsense.domain import physics as ph
from capsense.domain import steps
from capsense.domain.models import Calibracion, DeviceState, Measurement
from capsense.io.serial_source import listar_puertos
from capsense.services import storage
from capsense.ui import figures, formulas
from capsense.ui.layout import VISTAS, icono
from capsense.ui.simulation import callbacks as simulacion_callbacks
from capsense.ui.temas import Paleta, paleta

if TYPE_CHECKING:
    from capsense.ui.app import Controlador

log = logging.getLogger(__name__)

CLASE_ESTADO = {
    DeviceState.DESCONECTADO: "estado gris", DeviceState.CONECTADO: "estado azul",
    DeviceState.DESCARGANDO: "estado ambar pulso", DeviceState.MIDIENDO: "estado azul pulso",
    DeviceState.LISTO: "estado verde", DeviceState.ERROR: "estado rojo",
}
NOMBRE_RANGO = {"10k": "10 kΩ", "1M": "1 MΩ"}


def aviso(texto: str | list, tipo: str = "ambar") -> html.Div:
    return html.Div([icono("ico-alerta"), html.Div(texto)], className=f"banner {tipo}", role="alert")


# ---------------- datos ----------------
def _elegir_medicion(mediciones: list[Measurement], sel: str | int | None) -> tuple[Measurement | None, bool]:
    """(medición a mostrar, hay una medición nueva en curso sin pruebas todavía)."""
    if not mediciones:
        return None, False
    if sel not in (None, "ultima"):
        for m in mediciones:
            if str(m.id) == str(sel):
                return m, False
    ultima = mediciones[-1]
    if not ultima.completa and not ultima.runs:
        previas = [m for m in mediciones[:-1] if m.runs and not m.error]
        return (previas[-1] if previas else ultima), True
    return ultima, False


def _calcular(m: Measurement, cal: Calibracion) -> list[ph.RunCalculado]:
    return [rc for rc in (ph.recalcular_run(r, cal) for r in m.runs) if rc is not None]


def _valores(m: Measurement, calc: list[ph.RunCalculado], cal: Calibracion) -> dict | None:
    """Valores a mostrar: los del Arduino si llegaron, si no los recalculados (medición en curso)."""
    res = ph.resumir(calc, cal)
    rep = m.reportado
    if rep is None and res is None:
        return None
    if rep is not None:
        return dict(c=rep.c_uf, inc=rep.inc_pct, delta=rep.c_uf * rep.inc_pct / 100, tau=rep.tau_ms,
                    r=rep.r_ohm, q=rep.q_uc, e=rep.e_uj, meseta=rep.meseta_pct, n=rep.n or len(m.runs),
                    parcial=False)
    assert res is not None
    return dict(c=res.c_uf, inc=res.inc_pct, delta=res.delta_uf, tau=res.tau_ms, r=res.r_ohm, q=res.q_uc,
                e=res.e_uj, meseta=res.meseta_pct, n=res.n, parcial=True)


def _completas(mediciones: list[Measurement], cal: Calibracion) -> list[tuple[Measurement, dict]]:
    out = []
    for m in mediciones:
        if m.completa and not m.error and m.runs:
            vals = _valores(m, _calcular(m, cal), cal)
            if vals:
                out.append((m, vals))
    return out


# ---------------- piezas de la vista Medición ----------------
def _delta(actual: float, previo: float | None, ref: str) -> html.Span:
    if previo is None or previo == 0:
        return html.Span("primera medición", className="kpi-nota")
    d = (actual / previo - 1) * 100
    if abs(d) < 0.05:
        return html.Span(f"= igual que {ref}", className="delta igual")
    ico = "ico-flecha-arriba" if d > 0 else "ico-flecha-abajo"
    return html.Span([icono(ico), f"{d:+.2f} % vs {ref}"], className="delta " + ("sube" if d > 0 else "baja"))


def _kpi(titulo: str, ico: str, valor, pie, spark: str, clase: str = "", extra: list | None = None) -> html.Div:
    hijos = [html.Div(icono(ico), className="kpi-icono"), html.Div(titulo, className="kpi-etiqueta"),
             html.Div(valor, className="kpi-valor")]
    hijos += extra or []
    hijos.append(html.Div(pie, className="kpi-pie"))
    if spark:
        hijos.append(html.Img(src=spark, className="kpi-spark", alt=""))
    return html.Div(hijos, className=f"card kpi {clase}".strip())


def _kpis(m: Measurement | None, vals: dict | None, calc: list[ph.RunCalculado],
          historial: list[tuple[Measurement, dict]], cal: Calibracion, p: Paleta, en_curso: bool) -> list:
    secundarias = (("Constante de tiempo τ", "ico-reloj"), ("Meseta P", "ico-meseta"),
                   ("Energía almacenada", "ico-rayo"))
    if m is None or (m.error and not m.runs):
        texto = "Sin medición" if m is None else "Error"
        nota = "Conecta una fuente y pulsa Medir (tecla M)" if m is None else (m.error or "")
        clase = "kpi-principal kpi-vacio" if m is None else "kpi-principal kpi-error"
        vacias = [_kpi(t, i, "—", html.Span("", className="kpi-nota"), "", "kpi-vacio") for t, i in secundarias]
        return [_kpi("Capacitancia", "ico-capacitor", texto, html.Span(nota, className="kpi-nota"), "", clase)] + vacias
    if vals is None:
        vacias = [_kpi(t, i, "—", html.Span("", className="kpi-nota"), "", "kpi-vacio") for t, i in secundarias]
        return [_kpi("Capacitancia", "ico-capacitor", "Midiendo…",
                     html.Span("esperando la primera prueba", className="kpi-nota"), "", "kpi-principal kpi-vacio",
                     [html.Div(html.Div(style={"width": "4%"}), className="progreso")])] + vacias

    previas = [(mm, vv) for mm, vv in historial if mm.id < m.id]
    prev = previas[-1] if previas else None
    ref = f"#{prev[0].id}" if prev else ""
    serie = [vv for mm, vv in historial if mm.id <= m.id][-12:]
    if len(serie) >= 2:
        s_c, s_tau = [v["c"] for v in serie], [v["tau"] for v in serie]
        s_mes, s_e = [v["meseta"] for v in serie], [v["e"] for v in serie]
    else:                                    # una sola medición: la serie son sus pruebas
        s_c = [rc.c_uf for rc in calc]
        s_tau = [rc.tau_s * 1000 for rc in calc]
        s_mes = [rc.ajuste.P / cal.adc_max * 100 for rc in calc]
        s_e = [ph.carga_energia(rc.c_uf, cal.v_entrada)[1] for rc in calc]

    num, unidad = ph.formato_c(vals["c"])
    dnum = ph.formato_delta(vals["delta"], vals["c"])
    parcial = vals["parcial"] and not m.completa
    extra = [html.Div([f"± {dnum} {unidad}", html.Span("·", className="sep"), f"± {vals['inc']:.2f} %"],
                      className="kpi-inc")]
    if parcial:
        n_max = m.n_max or 5
        extra.append(html.Div(html.Div(style={"width": f"{min(100, len(m.runs) / n_max * 100):.0f}%"}),
                              className="progreso"))
        pie_c = html.Span(f"midiendo · prueba {len(m.runs)} de {n_max}", className="kpi-nota")
    elif en_curso:
        pie_c = html.Span("nueva medición en curso…", className="kpi-nota")
    else:
        pie_c = _delta(vals["c"], prev[1]["c"] if prev else None, ref)
    principal = _kpi("Capacitancia", "ico-capacitor", [num, html.Small(unidad)], pie_c,
                     figures.sparkline(s_c, p), "kpi-principal", extra)

    fuga = ph.nivel_fuga(vals["meseta"])
    e = vals["e"]
    e_txt = [f"{e:.4g}", html.Small("µJ")] if e < 1000 else [f"{e / 1000:.4g}", html.Small("mJ")]
    q = vals["q"]
    q_txt = f"Q = {q:.4g} µC" if q < 1000 else f"Q = {q / 1000:.4g} mC"
    tau_num, tau_u = ph.formato_tau(vals["tau"]).split(" ")
    return [
        principal,
        _kpi("Constante de tiempo τ", "ico-reloj", [tau_num, html.Small(tau_u)],
             _delta(vals["tau"], prev[1]["tau"] if prev else None, ref), figures.sparkline(s_tau, p)),
        _kpi("Meseta P", "ico-meseta", [f"{vals['meseta']:.1f}", html.Small("%")],
             html.Span(f"fuga {fuga}", className=f"chip fuga-{fuga}"), figures.sparkline(s_mes, p)),
        _kpi("Energía almacenada", "ico-rayo", e_txt, html.Span(q_txt, className="kpi-nota"),
             figures.sparkline(s_e, p)),
    ]


def _factor(nombre: str, ico: str, valor: str, pct: float, clase: str = "") -> html.Div:
    return html.Div([
        html.Div(icono(ico), className="factor-ico"),
        html.Div([html.Div(nombre, className="factor-nombre"),
                  html.Div(html.Div(style={"width": f"{max(3.0, min(100.0, pct)):.0f}%"}),
                           className=f"barra {clase}".strip())]),
        html.Div(valor, className="factor-valor"),
    ], className="factor")


def _calidad(m: Measurement | None, vals: dict | None, calc: list[ph.RunCalculado], cal: Calibracion) -> list:
    if m is None or vals is None:
        return [html.Div("Aquí aparece qué tan confiable es la medición: fuga, repetibilidad, curva capturada "
                         "y concordancia con el Arduino.", className="vacio-msg")]
    fuga = ph.nivel_fuga(vals["meseta"])
    n_muestras = max((len(rc.run.samples) for rc in calc), default=0)
    chequeos = [c for rc in calc for paso in steps.pasos_prueba(rc, cal) for c in paso.chequeos]
    if m.completa and m.reportado:
        chequeos += [c for paso in steps.pasos_resumen(m, calc, cal) for c in paso.chequeos]
    ok = sum(c.coincide for c in chequeos)
    pct_ok = ok / len(chequeos) * 100 if chequeos else 0
    hijos = [html.Div([
        _factor(f"Meseta · fuga {fuga}", "ico-meseta", f"{vals['meseta']:.1f} %", vals["meseta"],
                {"baja": "", "media": "aviso", "alta": "critico"}[fuga]),
        _factor(f"Repetibilidad · {vals['n']} pruebas", "ico-objetivo", f"± {vals['inc']:.2f} %",
                100 - vals["inc"] * 25, "aviso" if vals["inc"] > 2 else ""),
        _factor("Curva capturada" if n_muestras else "Curva · la v2.1 no la envía", "ico-curva",
                f"{n_muestras} pts" if n_muestras else "—", n_muestras),
        _factor(f"Coincide con el Arduino · {ok}/{len(chequeos)}", "ico-escudo", f"{pct_ok:.0f} %", pct_ok,
                "" if pct_ok == 100 else "aviso"),
    ], className="factores")]
    rango = cal.etiqueta(m.rango)
    chips = [html.Span([icono("ico-resistencia"), NOMBRE_RANGO.get(rango, rango)], className="chip"),
             html.Span([icono("ico-barras"), f"{vals['n']} pruebas"], className="chip")]
    if m.firmware:
        chips.append(html.Span(f"firmware v{m.firmware}", className="chip"))
    hijos.append(html.Div(chips, className="chips"))
    if fuga == "alta":
        hijos.append(aviso([html.Strong("Fuga alta. "), f"La meseta llegó solo al {vals['meseta']:.1f} % de 1023. "
                            "Revisa el capacitor y su polaridad: el valor puede no ser confiable."], "rojo"))
    if m.error:
        hijos.append(aviso([html.Strong("Error: "), m.error], "rojo"))
    return hijos


def _recientes(mediciones: list[Measurement], historial: list[tuple[Measurement, dict]]) -> list:
    if not mediciones:
        return [html.Div("Las mediciones de la sesión aparecen aquí.", className="vacio-msg")]
    por_id = {mm.id: vv for mm, vv in historial}
    items = []
    for m in list(reversed(mediciones))[:6]:
        sub = f"#{m.id} · {m.inicio:%H:%M:%S} · {m.origen}"
        if m.error:
            ico, clase, titulo, lado = "ico-alerta", "error", m.error, html.Span("error", className="rojo")
        elif not m.completa:
            ico, clase, titulo = "ico-actividad", "curso", "Midiendo…"
            lado = html.Span(f"{len(m.runs)}/{m.n_max or 5}", className="kpi-nota")
        else:
            vals = por_id.get(m.id)
            if vals is None:
                continue
            num, u = ph.formato_c(vals["c"])
            ico, clase = "ico-check", "ok"
            titulo = f"{num} {u}  ± {vals['inc']:.2f} %"
            previas = [vv for mm, vv in historial if mm.id < m.id]
            if previas:
                d = (vals["c"] / previas[-1]["c"] - 1) * 100
                lado = html.Span(f"{d:+.2f} %", className="delta " + ("sube" if d >= 0 else "baja"))
            else:
                lado = html.Span("primera", className="kpi-nota")
        items.append(html.Div([
            html.Div(icono(ico), className=f"item-ico {clase}"),
            html.Div([html.Div(titulo, className="item-titulo"), html.Div(sub, className="item-sub")]),
            html.Div(lado, className="item-lado"),
        ], className="item"))
    return items


def _historial(mediciones: list[Measurement], cal: Calibracion) -> html.Table | html.Div:
    if not mediciones:
        return html.Div("Todavía no hay mediciones en esta sesión.", className="vacio-msg")
    cab = ["#", "Hora", "C", "±", "τ", "Rango", "Meseta", "n", "Origen", "Estado"]
    filas = []
    for m in reversed(mediciones):
        f = storage.fila_medicion(m, cal)
        if f["C_uF"] is not None:
            num, u = ph.formato_c(f["C_uF"])
            c_txt = f"{num} {u}"
        else:
            c_txt = "—"
        if f["error"]:
            estado = html.Span([icono("ico-alerta"), f["error"]], className="etiqueta error")
        elif m.completa:
            estado = html.Span([icono("ico-check"), "OK"], className="etiqueta ok")
        else:
            estado = html.Span("Midiendo…", className="etiqueta curso")
        filas.append(html.Tr([
            html.Td(f["medicion"], className="num"), html.Td(f["hora"], className="num"),
            html.Td(c_txt, className="num"),
            html.Td(f"{f['incert_pct']:.2f} %" if f["incert_pct"] is not None else "—", className="num"),
            html.Td(ph.formato_tau(f["tau_ms"]) if f["tau_ms"] else "—", className="num"),
            html.Td(NOMBRE_RANGO.get(f["rango"], f["rango"])),
            html.Td(f"{f['meseta_pct']:.1f} %" if f["meseta_pct"] else "—", className="num"),
            html.Td(f["n_pruebas"], className="num"), html.Td(f["origen"]), html.Td(estado),
        ]))
    return html.Table([html.Thead(html.Tr([html.Th(c) for c in cab])), html.Tbody(filas)], className="tabla")


# ---------------- registro ----------------
def registrar(app: dash.Dash, ctl: Controlador) -> None:  # noqa: C901 - un bloque por callback
    session = ctl.session
    cal = session.cal
    simulacion_callbacks.registrar(app, ctl)
    ids_nav = [f"nav-{clave}" for clave, _n, _i in VISTAS]
    ids_vista = [f"vista-{clave}" for clave, _n, _i in VISTAS]

    # Navegación entre vistas en el cliente ("Ver todas" lleva al historial)
    app.clientside_callback(
        """
        function() {
            const nombres = NOMBRES;
            const ids = IDS;
            const ctx = window.dash_clientside.callback_context;
            let i = 0;
            if (ctx.triggered.length && ctx.triggered[0].prop_id !== ".") {
                const id = ctx.triggered[0].prop_id.split(".")[0];
                i = id === "ir-historial" ? 2 : Math.max(0, ids.indexOf(id));
            }
            const clases = nombres.map((_, k) => k === i ? "nav-item activa" : "nav-item");
            const estilos = nombres.map((_, k) => k === i ? {} : {display: "none"});
            [40, 250].forEach(ms => setTimeout(() => window.dispatchEvent(new Event("resize")), ms));
            return [nombres[i], ...clases, ...estilos];
        }
        """.replace("NOMBRES", json.dumps([n for _c, n, _i in VISTAS])).replace("IDS", json.dumps(ids_nav)),
        Output("titulo-vista", "children"),
        *[Output(i, "className") for i in ids_nav],
        *[Output(i, "style") for i in ids_vista],
        *[Input(i, "n_clicks") for i in ids_nav],
        Input("ir-historial", "n_clicks"),
    )
    # Tema: se guarda en el almacenamiento local de la ventana
    app.clientside_callback(
        """
        function(a, n, actual) {
            const ctx = window.dash_clientside.callback_context;
            if (!ctx.triggered.length || ctx.triggered[0].prop_id === ".") {
                return window.dash_clientside.no_update;
            }
            return ctx.triggered[0].prop_id.startsWith("tema-neon") ? "neon" : "ambar";
        }
        """,
        Output("tema", "data"), Input("tema-ambar", "n_clicks"), Input("tema-neon", "n_clicks"),
        State("tema", "data"), prevent_initial_call=True,
    )
    app.clientside_callback(
        """
        function(tema) {
            const t = tema === "neon" ? "neon" : "ambar";
            return ["app tema-" + t, t === "ambar" ? "activo" : "", t === "neon" ? "activo" : ""];
        }
        """,
        Output("app", "className"), Output("tema-ambar", "className"), Output("tema-neon", "className"),
        Input("tema", "data"),
    )
    app.clientside_callback(
        "function(n) { if (n) { window.capsensePantallaCompleta(); } return window.dash_clientside.no_update; }",
        Output("btn-pantalla", "title"), Input("btn-pantalla", "n_clicks"), prevent_initial_call=True,
    )

    @app.callback(
        Output("ver", "data"), Output("estado-pill", "children"), Output("estado-caja", "className"),
        Output("estado-msg", "children"), Output("btn-medir", "disabled"), Output("banner-config", "children"),
        Output("consola", "children"),
        Input("tick", "n_intervals"), State("ver", "data"),
    )
    def tick(_n, ver):
        v = session.snapshot(con_lineas=True)
        if v.version == ver:
            raise PreventUpdate
        msg = v.mensaje
        if v.fuente and v.estado != DeviceState.ERROR:
            msg = f"{v.fuente}" + (f" · v{v.firmware}" if v.firmware else "") + (f" · {msg}" if msg else "")
        medir_off = (not v.acepta_comandos or v.estado in (DeviceState.MIDIENDO, DeviceState.DESCARGANDO,
                                                            DeviceState.DESCONECTADO)
                     or bool(v.firmware and v.firmware.startswith("2.1")))
        banner_cfg = aviso(v.aviso_config) if v.aviso_config else None
        return (v.version, v.estado.value, CLASE_ESTADO[v.estado], msg, medir_off, banner_cfg,
                "\n".join(v.lineas[-60:]))

    @app.callback(
        Output("sel-medicion", "options"), Output("kpis", "children"), Output("calidad", "children"),
        Output("recientes", "children"), Output("graf-desviacion", "figure"), Output("historial", "children"),
        Output("graf-mapa", "figure"), Output("sel-prueba", "options"), Output("ruta-logs", "children"),
        Input("ver", "data"), Input("sel-medicion", "value"), Input("tema", "data"),
    )
    def resultado(_ver, sel, tema):
        p = paleta(tema)
        v = session.snapshot()
        opciones = [{"label": "Última medición", "value": "ultima"}] + [
            {"label": f"#{m.id} · {m.inicio:%H:%M:%S}" + (" · error" if m.error else ""), "value": str(m.id)}
            for m in reversed(v.mediciones)]
        m, en_curso = _elegir_medicion(v.mediciones, sel)
        calc = _calcular(m, cal) if m else []
        vals = _valores(m, calc, cal) if m else None
        historial = _completas(v.mediciones, cal)
        fig_d = figures.desviaciones(calc, cal, p) if calc else figures.vacia("Sin pruebas", p)
        op_pruebas = [{"label": "Última prueba", "value": "ultima"},
                      {"label": "Todas las pruebas", "value": "todas"}] + [
            {"label": f"Prueba {rc.run.i}" + (" · extendida" if rc.run.ext else ""), "value": str(rc.run.i)}
            for rc in calc]
        rutas = ""
        if session.storage is not None:
            rutas = f"Log automático de la sesión: {session.storage.carpeta / session.storage.base}_*"
        return (opciones, _kpis(m, vals, calc, historial, cal, p, en_curso), _calidad(m, vals, calc, cal),
                _recientes(v.mediciones, historial), fig_d, _historial(v.mediciones, cal),
                figures.mapa_repetibilidad(v.mediciones, cal, p), op_pruebas, rutas)

    @app.callback(
        Output("graf-curva", "figure"), Output("pasos", "children"), Output("pasos-sub", "children"),
        Output("nota-curva", "children"), Output("formula-curva", "children"),
        Input("ver", "data"), Input("sel-medicion", "value"), Input("sel-prueba", "value"), Input("tema", "data"),
        Input("magnitud-curva", "value"),
    )
    def curva_y_pasos(_ver, sel, sel_prueba, tema, magnitud):
        p = paleta(tema)
        magnitud = magnitud or "v"
        formula = "Q(t) = C · V(t) = C·P·(1 − e^(−t/τ))" if magnitud == "q" else "V(t) = P · (1 − e^(−t/τ))"
        v = session.snapshot()
        m, _ = _elegir_medicion(v.mediciones, sel)
        if m is None or not m.runs:
            return (figures.vacia("Sin datos todavía · pulsa Medir", p),
                    html.Div("Aquí aparecen las fórmulas con los números de la medición, paso a paso.",
                             className="vacio-msg"), "Mide. Ajusta. Explica.", "", formula)
        calc = _calcular(m, cal)
        if not calc:
            raise PreventUpdate
        sel_prueba = sel_prueba or "ultima"
        if sel_prueba == "ultima":
            sel_prueba = str(calc[-1].run.i)
        fig = figures.curva_carga(calc, sel_prueba, cal, uirevision=f"{m.id}-{sel_prueba}-{tema}-{magnitud}", p=p,
                                  magnitud=magnitud)
        elegida = next((rc for rc in calc if str(rc.run.i) == sel_prueba), calc[-1])
        p_prueba = steps.pasos_prueba(elegida, cal)
        p_res = steps.pasos_resumen(m, calc, cal) if m.completa else []
        etiqueta = NOMBRE_RANGO.get(elegida.run.etiqueta, elegida.run.etiqueta)
        bloques = [html.H3(f"Prueba {elegida.run.i} · rango {etiqueta}", className="pasos-sep")]
        bloques += formulas.panel_pasos(p_prueba)
        if p_res:
            bloques.append(html.H3(f"Resultado de la medición · {len(calc)} pruebas", className="pasos-sep"))
            bloques += formulas.panel_pasos(p_res, inicio=len(p_prueba) + 1)
        sub = f"Medición #{m.id} · prueba {elegida.run.i} de {len(calc)} · recalculado en Python desde t₁ y t₂"
        if sel_prueba == "todas":
            nota = f"{len(calc)} pruebas superpuestas · medición #{m.id}"
        else:
            aj = elegida.ajuste
            nota = (f"prueba {elegida.run.i} · t₁ = {aj.t1 / 1000:.2f} ms · t₂ = {aj.t2 / 1000:.2f} ms · "
                    f"{len(elegida.run.samples)} muestras")
        if magnitud == "q":
            nota += f" · Q = C·V con C = {elegida.c_uf:.4g} µF"
        return fig, bloques, sub, nota, formula

    @app.callback(
        Output("grupo-arduino", "style"), Output("grupo-replay", "style"), Output("panel-demo", "style"),
        Input("modo", "value"),
    )
    def visibilidad(modo):
        ocultar = {"display": "none"}
        return (None if modo == "arduino" else ocultar, None if modo == "replay" else ocultar,
                None if modo == "demo" else ocultar)

    @app.callback(Output("puerto", "options"), Input("btn-puertos", "n_clicks"), Input("modo", "value"))
    def puertos(_n, modo):
        if modo != "arduino":
            raise PreventUpdate
        return [{"label": f"{p.dispositivo} · {p.descripcion}" + (" · posible Arduino" if p.probable_arduino else ""),
                 "value": p.dispositivo} for p in listar_puertos()]

    @app.callback(Output("replay-archivo", "options"), Input("modo", "value"), Input("replay-upload", "contents"),
                  State("replay-upload", "filename"))
    def archivos(modo, contenido, nombre):
        if modo != "replay":
            raise PreventUpdate
        if contenido and nombre:
            _tipo, datos = contenido.split(",", 1)
            ctl.carpeta_replays.mkdir(parents=True, exist_ok=True)
            destino = ctl.carpeta_replays / Path(nombre).name
            destino.write_bytes(base64.b64decode(datos))
        return [{"label": f"{p.name} ({p.parent.name})", "value": str(p)} for p in ctl.archivos_replay()]

    @app.callback(
        Output("aviso", "children"),
        Input("btn-conectar", "n_clicks"), Input("btn-desconectar", "n_clicks"), Input("btn-medir", "n_clicks"),
        Input("btn-limpiar", "n_clicks"),
        State("modo", "value"), State("puerto", "value"), State("baud", "value"),
        State("replay-archivo", "value"), State("replay-vel", "value"),
        State("demo-c", "value"), State("demo-meseta", "value"), State("demo-ruido", "value"),
        State("demo-vel", "value"), State("demo-auto", "value"), State("demo-fw", "value"),
        prevent_initial_call=True,
    )
    def acciones(_c, _d, _m, _l, modo, puerto, baud, archivo, vel_replay, c_log, meseta, ruido, vel, auto, fw):
        boton = dash.ctx.triggered_id
        if boton == "btn-conectar":
            if modo == "demo":
                ctl.conectar_demo(c_uf=10 ** c_log, meseta_pct=meseta, ruido_lsb=ruido, velocidad=vel,
                                  auto=bool(auto), firmware=fw)
                return ""
            if modo == "arduino":
                ctl.conectar_serial(puerto, int(baud))
                return ""
            if not archivo:
                return aviso("Elige un archivo para reproducir.")
            ctl.conectar_replay(Path(archivo), float(vel_replay))
            return ""
        if boton == "btn-desconectar":
            ctl.desconectar()
            return ""
        if boton == "btn-medir":
            ok, msg = session.medir()
            return "" if ok else aviso(msg)
        if boton == "btn-limpiar":
            session.limpiar_historial()
            return ""
        return no_update

    @app.callback(
        Output("demo-c-txt", "children"), Output("demo-meseta-txt", "children"),
        Input("demo-c", "value"), Input("demo-meseta", "value"), Input("demo-ruido", "value"),
        Input("demo-vel", "value"), Input("demo-auto", "value"), Input("demo-fw", "value"),
    )
    def parametros_demo(c_log, meseta, ruido, vel, auto, fw):
        c = 10 ** c_log
        if ctl.sim is not None:
            ctl.sim.set_params(c_uf=c, meseta_pct=meseta, ruido_lsb=ruido, velocidad=vel, auto=bool(auto),
                               firmware=fw)
        num, u = ph.formato_c(c)
        fuga = ph.nivel_fuga(meseta)
        tau_10k = cal.r_total(0) * c / 1e6
        return (f"{num} {u} · τ ≈ {ph.formato_tau(tau_10k * 1000)} con 10 kΩ",
                f"{meseta:.1f} % de 1023 · fuga {fuga}" + (" · no llega a 700: error" if meseta < 68.6 else ""))

    @app.callback(
        Output("descarga", "data"),
        Input("btn-exportar", "n_clicks"), Input("btn-exportar-pruebas", "n_clicks"),
        prevent_initial_call=True,
    )
    def exportar(_a, _b):
        v = session.snapshot()
        if not v.mediciones:
            raise PreventUpdate
        sello = datetime.now().strftime("%Y%m%d_%H%M%S")
        if dash.ctx.triggered_id == "btn-exportar-pruebas":
            return dcc.send_string(storage.exportar_pruebas(v.mediciones), f"capsense_pruebas_{sello}.csv")
        return dcc.send_string(storage.exportar_historial(v.mediciones, cal), f"capsense_historial_{sello}.csv")
