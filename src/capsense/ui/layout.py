"""Estructura de la aplicación: barra lateral + cabecera + cuatro vistas.

Sistema de diseño (skill ui-ux-pro-max): "Dark Mode (OLED) + Data-Dense Dashboard + Real-Time
Monitoring", par tipográfico "Dashboard Data" (sans para etiquetas, mono para valores), íconos SVG
(sin emojis), estados con texto además de color, foco visible y movimiento reducido.
"""
from __future__ import annotations

import math

from dash import dcc, html

from capsense import __version__
from capsense.config import AppConfig

VISTAS = [
    ("medicion", "Medición", "ico-actividad"),
    ("calculos", "Cálculos", "ico-sigma"),
    ("historial", "Historial", "ico-tabla"),
    ("conexion", "Conexión", "ico-enchufe"),
]


def icono(nombre: str, extra: str = "") -> html.Span:
    return html.Span(className=f"ico {nombre} {extra}".strip(), **{"aria-hidden": "true"})


def _control(etiqueta: str, hijo, clase: str = "") -> html.Div:
    return html.Div([html.Label(etiqueta, className="ctl-label"), hijo], className=f"ctl {clase}".strip())


def _barra_lateral() -> html.Aside:
    return html.Aside([
        html.Div([
            html.Div(icono("ico-capacitor"), className="logo"),
            html.Div([html.Div("CapSense Lab", className="marca-nombre"),
                      html.Div("Medidor de capacitancia RC", className="marca-sub")]),
        ], className="marca"),
        html.Nav([
            html.Button([icono(ico), html.Span(nombre), html.Kbd(str(i))], id=f"nav-{clave}",
                        className="nav-item" + (" activa" if i == 1 else ""), title=f"{nombre} (tecla {i})")
            for i, (clave, nombre, ico) in enumerate(VISTAS, 1)
        ], className="nav", **{"aria-label": "Vistas"}),
        html.Div(className="espaciador"),
        html.Div([
            html.Div([html.Span(className="punto"), html.Span(id="estado-pill")],
                     id="estado-caja", className="estado gris"),
            html.Div(id="estado-msg", className="estado-msg"),
        ], className="equipo", **{"aria-live": "polite"}),
        html.Button([icono("ico-play"), html.Span("Medir")], id="btn-medir", className="btn btn-medir",
                    title="Medir (tecla M). Envía M al Arduino, igual que START"),
        html.Div(f"v{__version__} · Samuel y Joel · Uninorte", className="pie"),
    ], className="lateral")


def _cabecera() -> html.Header:
    return html.Header([
        html.Div([html.H1("Medición", id="titulo-vista"), html.Div(id="pasos-sub", className="cab-sub")],
                 className="cab-titulo"),
        html.Div([
            dcc.Dropdown(id="sel-medicion", value="ultima", clearable=False, searchable=False,
                         className="dd dd-medicion", options=[{"label": "Última medición", "value": "ultima"}]),
            dcc.Dropdown(id="sel-prueba", value="todas", clearable=False, searchable=False,
                         className="dd dd-prueba", options=[{"label": "Todas las pruebas", "value": "todas"}]),
            html.Button(icono("ico-pantalla"), id="btn-pantalla", className="btn btn-icono",
                        title="Pantalla completa (F11)", **{"aria-label": "Pantalla completa"}),
        ], className="cab-acciones"),
    ], className="cabecera")


def _vista_medicion() -> html.Section:
    return html.Section([
        html.Div([
            html.Div([
                html.Div("Capacitancia", className="kpi-etiqueta"),
                html.Div(id="hero"),
                html.Div(id="banner"),
            ], className="card card-hero"),
            html.Div(id="tarjetas", className="tarjetas"),
        ], className="col-kpi"),
        html.Div([
            html.Div([
                html.Div([html.H2("Curva de carga"),
                          html.Span("V(t) = P·(1 − e^(−t/τ))", className="formula-chip")], className="card-cab"),
                dcc.Graph(id="graf-curva", className="graf graf-curva",
                          config={"displaylogo": False, "responsive": True,
                                  "modeBarButtonsToRemove": ["lasso2d", "select2d"],
                                  "toImageButtonOptions": {"filename": "curva_capsense", "scale": 2}}),
            ], className="card card-curva"),
            html.Div([
                html.Div([html.H2("C de cada prueba"), html.Div(id="nota-incert", className="card-nota")],
                         className="card-cab"),
                dcc.Graph(id="graf-pruebas", className="graf graf-pruebas",
                          config={"displaylogo": False, "responsive": True, "displayModeBar": False}),
            ], className="card card-pruebas"),
        ], className="col-graficas"),
    ], id="vista-medicion", className="vista vista-medicion")


def _vista_calculos() -> html.Section:
    return html.Section([
        html.Div(id="pasos", className="pasos"),
    ], id="vista-calculos", className="vista vista-calculos", style={"display": "none"})


def _vista_historial() -> html.Section:
    return html.Section([
        html.Div([
            html.Div([
                html.H2("Mediciones de la sesión"),
                html.Div([
                    html.Button([icono("ico-descargar"), "Exportar CSV"], id="btn-exportar", className="btn"),
                    html.Button([icono("ico-descargar"), "Exportar pruebas"], id="btn-exportar-pruebas",
                                className="btn"),
                    html.Button([icono("ico-borrar"), "Limpiar"], id="btn-limpiar", className="btn btn-tenue"),
                ], className="grupo"),
            ], className="card-cab"),
            html.Div(id="historial", className="tabla-wrap"),
            html.Div(id="ruta-logs", className="card-nota"),
        ], className="card card-historial"),
    ], id="vista-historial", className="vista vista-historial", style={"display": "none"})


def _vista_conexion(cfg: AppConfig, modo_inicial: str) -> html.Section:
    d = cfg.demo
    return html.Section([
        html.Div([
            html.Div([html.H2("Fuente de datos")], className="card-cab"),
            dcc.RadioItems(
                id="modo", value=modo_inicial, inline=True, className="segmentado",
                options=[{"label": "Arduino", "value": "arduino"}, {"label": "Demo", "value": "demo"},
                         {"label": "Replay", "value": "replay"}]),
            html.Div([
                _control("Puerto", dcc.Dropdown(id="puerto", placeholder="Automático", clearable=True,
                                                searchable=False, className="dd dd-puerto")),
                html.Button(icono("ico-recargar"), id="btn-puertos", className="btn btn-icono",
                            title="Buscar puertos", **{"aria-label": "Buscar puertos"}),
                _control("Baudios", dcc.Dropdown(
                    id="baud", value=cfg.serial.baud, clearable=False, searchable=False, className="dd dd-baud",
                    options=[{"label": "115200 (v2.2 / v2.3)", "value": 115200},
                             {"label": "9600 (v2.1)", "value": 9600}])),
            ], id="grupo-arduino", className="grupo-campos"),
            html.Div([
                _control("Archivo", dcc.Dropdown(id="replay-archivo", placeholder="Elige un log o CSV",
                                                 className="dd dd-archivo")),
                dcc.Upload(html.Button([icono("ico-subir"), "Subir…"], className="btn"), id="replay-upload",
                           multiple=False),
                _control("Velocidad", dcc.Dropdown(
                    id="replay-vel", value=4, clearable=False, searchable=False, className="dd dd-vel",
                    options=[{"label": f"×{v}", "value": v} for v in (1, 4, 20, 100)])),
            ], id="grupo-replay", className="grupo-campos"),
            html.Div([
                html.Button("Conectar", id="btn-conectar", className="btn btn-primario"),
                html.Button("Desconectar", id="btn-desconectar", className="btn"),
            ], className="grupo"),
            html.Div(id="banner-config"),
        ], className="card card-fuente"),

        html.Div([
            html.Div([html.H2("Simulador"),
                      html.Span("se aplica a la próxima medición", className="card-nota")], className="card-cab"),
            html.Div([
                _control("Capacitor", html.Div([
                    dcc.Slider(id="demo-c", min=-0.3, max=3.3, step=0.01, value=math.log10(d.c_uf),
                               marks={math.log10(x): (f"{x:g}" if x < 1000 else "1 mF")
                                      for x in (0.5, 1, 3, 10, 33, 100, 330, 1000, 2000)},
                               tooltip=None, updatemode="drag", allow_direct_input=False),
                    html.Div(id="demo-c-txt", className="ctl-valor"),
                ]), "ctl-ancho"),
                _control("Meseta (fuga)", html.Div([
                    dcc.Slider(id="demo-meseta", min=65, max=100, step=0.5, value=d.meseta_pct,
                               marks={65: "65 %", 80: "80 %", 93: "93", 98: "98", 100: "100 %"},
                               updatemode="drag", allow_direct_input=False),
                    html.Div(id="demo-meseta-txt", className="ctl-valor"),
                ]), "ctl-ancho"),
                _control("Ruido del ADC", dcc.Slider(id="demo-ruido", min=0, max=3, step=0.1, value=d.ruido_lsb,
                                                     marks={0: "0", 1: "1", 2: "2", 3: "3 LSB"},
                                                     updatemode="drag", allow_direct_input=False), "ctl-ancho"),
                html.Div([
                    _control("Firmware simulado", dcc.Dropdown(
                        id="demo-fw", value=d.firmware, clearable=False, searchable=False, className="dd dd-fw",
                        options=[{"label": "v2.3 (cruce interpolado)", "value": "2.3"},
                                 {"label": "v2.2 (primera lectura)", "value": "2.2"}])),
                    _control("Velocidad", dcc.Dropdown(
                        id="demo-vel", value=d.velocidad, clearable=False, searchable=False, className="dd dd-vel",
                        options=[{"label": f"×{v:g}", "value": v} for v in (1, 2, 5, 20)])),
                    dcc.Checklist(id="demo-auto", options=[{"label": "Repetir sola cada 3 s", "value": "auto"}],
                                  value=[], className="check-auto"),
                ], className="grupo-campos"),
            ], className="demo-grid"),
        ], id="panel-demo", className="card card-demo"),

        html.Div([
            html.Div([html.H2("Consola serie"), html.Span("últimas líneas recibidas", className="card-nota")],
                     className="card-cab"),
            html.Pre(id="consola", className="consola"),
        ], className="card card-consola"),
    ], id="vista-conexion", className="vista vista-conexion", style={"display": "none"})


def crear_layout(cfg: AppConfig, modo_inicial: str) -> html.Div:
    return html.Div([
        dcc.Interval(id="tick", interval=400),
        dcc.Store(id="ver", data=-1),
        dcc.Store(id="vista", data="medicion"),
        dcc.Download(id="descarga"),
        _barra_lateral(),
        html.Main([
            _cabecera(),
            html.Div([
                _vista_medicion(),
                _vista_calculos(),
                _vista_historial(),
                _vista_conexion(cfg, modo_inicial),
            ], className="contenido"),
        ], className="principal"),
        html.Div(id="aviso", className="toasts", **{"aria-live": "assertive"}),
    ], className="app")
