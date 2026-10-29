"""Interacciones del dashboard."""
from __future__ import annotations

import base64
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

if TYPE_CHECKING:
    from capsense.ui.app import Controlador

log = logging.getLogger(__name__)

CLASE_ESTADO = {
    DeviceState.DESCONECTADO: "pill gris", DeviceState.CONECTADO: "pill azul",
    DeviceState.DESCARGANDO: "pill ambar", DeviceState.MIDIENDO: "pill ambar pulso",
    DeviceState.LISTO: "pill verde", DeviceState.ERROR: "pill rojo",
}


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
        meseta = rep.meseta_pct
        return dict(c=rep.c_uf, inc=rep.inc_pct, delta=rep.c_uf * rep.inc_pct / 100, tau=rep.tau_ms,
                    r=rep.r_ohm, q=rep.q_uc, e=rep.e_uj, meseta=meseta, n=rep.n or len(m.runs), parcial=False)
    assert res is not None
    return dict(c=res.c_uf, inc=res.inc_pct, delta=res.delta_uf, tau=res.tau_ms, r=res.r_ohm, q=res.q_uc,
                e=res.e_uj, meseta=res.meseta_pct, n=res.n, parcial=True)


def _hero(m: Measurement | None, vals: dict | None, cal: Calibracion, en_curso: bool) -> tuple[list, list]:
    if m is None:
        return [html.Div("—", className="hero-valor tenue"),
                html.Div("Conecta una fuente y pulsa Medir", className="hero-inc")], []
    if m.error and not m.runs:
        return [html.Div("Error", className="hero-valor rojo"),
                html.Div(m.error, className="hero-inc")], []
    if vals is None:
        return [html.Div("Midiendo…", className="hero-valor tenue"), html.Div("", className="hero-inc")], []
    num, unidad = ph.formato_c(vals["c"])
    dnum = ph.formato_delta(vals["delta"], vals["c"])
    fuga = ph.nivel_fuga(vals["meseta"])
    rango = cal.etiqueta(m.rango)
    r_txt = {"10k": "10 kΩ", "1M": "1 MΩ"}.get(rango, rango)
    estado = ""
    if vals["parcial"] and not m.completa:
        estado = f"Midiendo · prueba {len(m.runs)} de {m.n_max or '?'} (parcial)"
    elif en_curso:
        estado = "Nueva medición en curso…"
    hero = [
        html.Div([html.Span(num, className="hero-num"), html.Span(unidad, className="hero-unidad")],
                 className="hero-valor" + (" tenue" if vals["parcial"] or en_curso else "")),
        html.Div(f"± {dnum} {unidad}  ·  ± {vals['inc']:.2f} %", className="hero-inc"),
        html.Div([
            html.Span(f"Rango {r_txt}", className="chip"),
            html.Span(f"{vals['n']} prueba{'s' if vals['n'] != 1 else ''}", className="chip"),
            html.Span(f"Meseta {vals['meseta']:.1f} %", className="chip"),
            html.Span(f"Fuga {fuga}", className=f"chip fuga-{fuga}"),
        ], className="chips"),
        html.Div(estado or f"Medición #{m.id} · {m.inicio:%H:%M:%S} · {m.origen}"
                 + (f" · firmware {m.firmware}" if m.firmware else ""), className="hero-meta"),
    ]
    banner = []
    if fuga == "alta":
        banner = [html.Div([html.Strong("⚠ Fuga alta. "),
                            f"La meseta llegó solo al {vals['meseta']:.1f} % de 1023. Revisa el capacitor, "
                            "su polaridad o si está dañado: el valor puede no ser confiable."],
                           className="banner rojo")]
    if m.error:
        banner.append(html.Div([html.Strong("Error: "), m.error], className="banner rojo"))
    return hero, banner


def _tarjetas(vals: dict | None, cal: Calibracion) -> list:
    if vals is None:
        return []
    datos = [
        ("τ", ph.formato_tau(vals["tau"]), "constante de tiempo"),
        ("R", ph.formato_r(vals["r"]), "carga + pin"),
        ("V", f"{cal.v_entrada:.2f} V", "entrada"),
        ("Q", f"{vals['q']:.4g} µC" if vals["q"] < 1000 else f"{vals['q'] / 1000:.4g} mC", "Q = C·V"),
        ("E", f"{vals['e']:.4g} µJ" if vals["e"] < 1000 else f"{vals['e'] / 1000:.4g} mJ", "E = ½·C·V²"),
    ]
    return [html.Div([html.Div(s, className="t-sim"), html.Div(v, className="t-val"),
                      html.Div(d, className="t-desc")], className="tarjeta") for s, v, d in datos]


def _historial(mediciones: list[Measurement], cal: Calibracion) -> html.Table | html.Div:
    if not mediciones:
        return html.Div("Todavía no hay mediciones.", className="nota")
    cab = ["#", "Hora", "C", "±", "τ", "Rango", "Meseta", "n", "Origen", "Estado"]
    filas = []
    for m in reversed(mediciones):
        f = storage.fila_medicion(m, cal)
        if f["C_uF"] is not None:
            num, u = ph.formato_c(f["C_uF"])
            c_txt = f"{num} {u}"
        else:
            c_txt = "—"
        estado = f["error"] or ("OK" if m.completa else "midiendo…")
        filas.append(html.Tr([
            html.Td(f["medicion"]), html.Td(f["hora"]), html.Td(c_txt, className="num"),
            html.Td(f"{f['incert_pct']:.2f} %" if f["incert_pct"] is not None else "—", className="num"),
            html.Td(ph.formato_tau(f["tau_ms"]) if f["tau_ms"] else "—", className="num"),
            html.Td(f["rango"]), html.Td(f"{f['meseta_pct']:.1f} %" if f["meseta_pct"] else "—", className="num"),
            html.Td(f["n_pruebas"], className="num"), html.Td(f["origen"]),
            html.Td(estado, className="rojo" if f["error"] else ""),
        ]))
    return html.Table([html.Thead(html.Tr([html.Th(c) for c in cab])), html.Tbody(filas)], className="tabla")


# ---------------- registro ----------------
def registrar(app: dash.Dash, ctl: Controlador) -> None:  # noqa: C901 - un bloque por callback
    session = ctl.session
    cal = session.cal

    @app.callback(
        Output("ver", "data"), Output("estado-pill", "children"), Output("estado-pill", "className"),
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
            msg = f"{v.fuente}" + (f" · firmware {v.firmware}" if v.firmware else "") + (f" · {msg}" if msg else "")
        medir_off = (not v.acepta_comandos or v.estado in (DeviceState.MIDIENDO, DeviceState.DESCARGANDO,
                                                            DeviceState.DESCONECTADO)
                     or bool(v.firmware and v.firmware.startswith("2.1")))
        aviso = html.Div(v.aviso_config, className="banner ambar") if v.aviso_config else None
        return (v.version, v.estado.value, CLASE_ESTADO[v.estado], msg, medir_off, aviso,
                "\n".join(v.lineas[-40:]))

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
        fig_p = figures.pruebas(calc, cal) if calc else figures.vacia("Sin pruebas", alto=360)
        nota = ""
        if len(calc) > 1:
            nota = ("Banda = media ± semi-rango, (Cmax − Cmin)/2: es la incertidumbre que usa el firmware "
                    "(no la desviación estándar).")
        op_pruebas = [{"label": "Todas las pruebas", "value": "todas"}] + [
            {"label": f"Prueba {rc.run.i}" + (" (curva extendida)" if rc.run.ext else ""), "value": str(rc.run.i)}
            for rc in calc]
        rutas = ""
        if session.storage is not None:
            rutas = f"Log automático: {session.storage.carpeta / session.storage.base}_*.csv / _serial.log"
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
            return figures.vacia("Sin datos todavía · pulsa Medir"), html.Div(
                "Aquí aparecerán las fórmulas con los números de la última medición.", className="nota"), ""
        calc = _calcular(m, cal)
        if not calc:
            raise PreventUpdate
        sel_prueba = sel_prueba or "todas"
        fig = figures.curva_carga(calc, sel_prueba, cal, uirevision=f"{m.id}-{sel_prueba}")
        elegida = next((rc for rc in calc if str(rc.run.i) == sel_prueba), calc[-1])
        p_prueba = steps.pasos_prueba(elegida, cal)
        p_res = steps.pasos_resumen(m, calc, cal) if m.completa else []
        bloques = formulas.panel_pasos(p_prueba)
        if p_res:
            bloques.append(html.H3("Resultado de la medición", className="pasos-sep"))
            bloques += formulas.panel_pasos(p_res, inicio=len(p_prueba) + 1)
        sub = f"medición #{m.id} · prueba {elegida.run.i} de {len(calc)} · recalculado en Python desde t₁ y t₂"
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
        return [{"label": f"{p.dispositivo} · {p.descripcion}" + (" ★" if p.probable_arduino else ""),
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
                return html.Div("Elige un archivo para reproducir.", className="banner ambar")
            ctl.conectar_replay(Path(archivo), float(vel_replay))
            return ""
        if boton == "btn-desconectar":
            ctl.desconectar()
            return ""
        if boton == "btn-medir":
            ok, msg = session.medir()
            return "" if ok else html.Div(msg, className="banner ambar")
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

