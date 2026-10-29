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


# ---------------- ayudas ----------------
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


def _hero(m: Measurement | None, vals: dict | None, cal: Calibracion, en_curso: bool) -> tuple[list, list]:
    if m is None:
        return [html.Div("Sin medición", className="hero-valor vacio"),
                html.Div("Conecta una fuente y pulsa Medir (tecla M)", className="hero-meta")], []
    if m.error and not m.runs:
        return [html.Div("Error", className="hero-valor error"),
                html.Div(m.error, className="hero-inc")], []
    if vals is None:
        return [html.Div("Midiendo…", className="hero-valor vacio"), html.Div(className="progreso",
                                                                               children=html.Div(style={"width": "4%"}))], []
    num, unidad = ph.formato_c(vals["c"])
    dnum = ph.formato_delta(vals["delta"], vals["c"])
    fuga = ph.nivel_fuga(vals["meseta"])
    rango = cal.etiqueta(m.rango)
    parcial = vals["parcial"] and not m.completa
    hero: list = [
        html.Div([html.Span(num, className="hero-num"), html.Span(unidad, className="hero-unidad")],
                 className="hero-valor" + (" tenue" if parcial or en_curso else "")),
        html.Div([f"± {dnum} {unidad}", html.Span("·", className="sep"), f"± {vals['inc']:.2f} %"],
                 className="hero-inc"),
        html.Div([
            html.Span([icono("ico-resistencia"), NOMBRE_RANGO.get(rango, rango)], className="chip",
                      title="Resistencia de carga usada"),
            html.Span(f"{vals['n']} prueba{'s' if vals['n'] != 1 else ''}", className="chip"),
            html.Span(f"Meseta {vals['meseta']:.1f} %", className="chip", title="P promedio en % de 1023"),
            html.Span(f"Fuga {fuga}", className=f"chip fuga-{fuga}"),
        ], className="chips"),
    ]
    if parcial:
        n_max = m.n_max or 5
        pct = min(100, len(m.runs) / n_max * 100)
        hero += [html.Div(html.Div(style={"width": f"{pct:.0f}%"}), className="progreso"),
                 html.Div(f"Midiendo · prueba {len(m.runs)} de {n_max} (valores parciales)", className="hero-meta")]
    else:
        meta = f"Medición #{m.id} · {m.inicio:%H:%M:%S} · {m.origen}" + (f" · v{m.firmware}" if m.firmware else "")
        hero.append(html.Div("Nueva medición en curso…" if en_curso else meta, className="hero-meta"))
    banner = []
    if fuga == "alta":
        banner.append(aviso([html.Strong("Fuga alta. "),
                             f"La meseta llegó solo al {vals['meseta']:.1f} % de 1023. Revisa el capacitor y su "
                             "polaridad: el valor puede no ser confiable."], "rojo"))
    if m.error:
        banner.append(aviso([html.Strong("Error: "), m.error], "rojo"))
    return hero, banner


def _tarjetas(vals: dict | None, cal: Calibracion) -> list:
    if vals is None:
        return []
    meseta = f"{vals['meseta']:.1f} %"
    datos = [
        ("τ", ph.formato_tau(vals["tau"]), "constante"),
        ("R", ph.formato_r(vals["r"]), "carga + pin"),
        ("Q", f"{vals['q']:.4g} µC" if vals["q"] < 1000 else f"{vals['q'] / 1000:.4g} mC", "C·V"),
        ("E", f"{vals['e']:.4g} µJ" if vals["e"] < 1000 else f"{vals['e'] / 1000:.4g} mJ", "½·C·V²"),
        ("V", f"{cal.v_entrada:.2f} V", "entrada"),
        ("P", meseta, "meseta"),
    ]
    return [html.Div([html.Div([html.Span(s, className="t-sim"), html.Span(d, className="t-desc")],
                               className="t-cab"),
                      html.Div(v, className="t-val")], className="tarjeta") for s, v, d in datos]


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
    ids_nav = [f"nav-{clave}" for clave, _n, _i in VISTAS]
    ids_vista = [f"vista-{clave}" for clave, _n, _i in VISTAS]

    # Navegación entre vistas: en el cliente, sin ida y vuelta al servidor
    app.clientside_callback(
        """
        function() {
            const nombres = NOMBRES;
            const ctx = window.dash_clientside.callback_context;
            let i = 0;
            if (ctx.triggered.length && ctx.triggered[0].prop_id !== ".") {
                const id = ctx.triggered[0].prop_id.split(".")[0];
                i = Math.max(0, IDS.indexOf(id));
            }
            const clases = nombres.map((_, k) => k === i ? "nav-item activa" : "nav-item");
            const estilos = nombres.map((_, k) => k === i ? {} : {display: "none"});
            setTimeout(() => window.dispatchEvent(new Event("resize")), 30);
            return [nombres[i], ...clases, ...estilos];
        }
        """.replace("NOMBRES", json.dumps([n for _c, n, _i in VISTAS])).replace("IDS", json.dumps(ids_nav)),
        Output("titulo-vista", "children"),
        *[Output(i, "className") for i in ids_nav],
        *[Output(i, "style") for i in ids_vista],
        *[Input(i, "n_clicks") for i in ids_nav],
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
        Output("sel-medicion", "options"), Output("hero", "children"), Output("banner", "children"),
        Output("tarjetas", "children"), Output("graf-pruebas", "figure"), Output("nota-incert", "children"),
        Output("historial", "children"), Output("sel-prueba", "options"), Output("ruta-logs", "children"),
        Input("ver", "data"), Input("sel-medicion", "value"),
    )
    def resultado(_ver, sel):
        v = session.snapshot()
        opciones = [{"label": "Última medición", "value": "ultima"}] + [
            {"label": f"#{m.id} · {m.inicio:%H:%M:%S}" + (" · error" if m.error else ""), "value": str(m.id)}
            for m in reversed(v.mediciones)]
        m, en_curso = _elegir_medicion(v.mediciones, sel)
        calc = _calcular(m, cal) if m else []
        vals = _valores(m, calc, cal) if m else None
        hero, banner = _hero(m, vals, cal, en_curso)
        fig_p = figures.pruebas(calc, cal) if calc else figures.vacia("Sin pruebas")
        nota = "banda = media ± (Cmax − Cmin)/2, igual que el firmware" if len(calc) > 1 else ""
        op_pruebas = [{"label": "Todas las pruebas", "value": "todas"}] + [
            {"label": f"Prueba {rc.run.i}" + (" · curva extendida" if rc.run.ext else ""), "value": str(rc.run.i)}
            for rc in calc]
        rutas = ""
        if session.storage is not None:
            rutas = f"Log automático de la sesión: {session.storage.carpeta / session.storage.base}_*"
        return (opciones, hero, banner, _tarjetas(vals, cal), fig_p, nota, _historial(v.mediciones, cal),
                op_pruebas, rutas)

    @app.callback(
        Output("graf-curva", "figure"), Output("pasos", "children"), Output("pasos-sub", "children"),
        Input("ver", "data"), Input("sel-medicion", "value"), Input("sel-prueba", "value"),
    )
    def curva_y_pasos(_ver, sel, sel_prueba):
        v = session.snapshot()
        m, _ = _elegir_medicion(v.mediciones, sel)
        if m is None or not m.runs:
            return (figures.vacia("Sin datos todavía · pulsa Medir"),
                    html.Div("Aquí aparecen las fórmulas con los números de la medición, paso a paso.",
                             className="vacio-msg"), "")
        calc = _calcular(m, cal)
        if not calc:
            raise PreventUpdate
        sel_prueba = sel_prueba or "todas"
        fig = figures.curva_carga(calc, sel_prueba, cal, uirevision=f"{m.id}-{sel_prueba}")
        elegida = next((rc for rc in calc if str(rc.run.i) == sel_prueba), calc[-1])
        p_prueba = steps.pasos_prueba(elegida, cal)
        p_res = steps.pasos_resumen(m, calc, cal) if m.completa else []
        bloques = [html.H3(f"Prueba {elegida.run.i} · rango {NOMBRE_RANGO.get(elegida.run.etiqueta, elegida.run.etiqueta)}",
                           className="pasos-sep")]
        bloques += formulas.panel_pasos(p_prueba)
        if p_res:
            bloques.append(html.H3(f"Resultado de la medición · {len(calc)} pruebas", className="pasos-sep"))
            bloques += formulas.panel_pasos(p_res, inicio=len(p_prueba) + 1)
        sub = f"#{m.id} · prueba {elegida.run.i} de {len(calc)} · recalculado en Python desde t₁ y t₂"
        return fig, bloques, sub

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
