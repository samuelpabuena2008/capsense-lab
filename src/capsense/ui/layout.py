"""Estructura de la página."""
from __future__ import annotations

import math

from dash import dcc, html

from capsense import __version__
from capsense.config import AppConfig


def _control(etiqueta: str, hijo, clase: str = "") -> html.Div:
    return html.Div([html.Label(etiqueta, className="ctl-label"), hijo], className=f"ctl {clase}")


def _barra_conexion(cfg: AppConfig, modo_inicial: str) -> html.Div:
    return html.Div([
        _control("Fuente", dcc.RadioItems(
            id="modo", value=modo_inicial, inline=True, className="radio-modo",
            options=[{"label": "Arduino", "value": "arduino"}, {"label": "Demo", "value": "demo"},
                     {"label": "Replay", "value": "replay"}])),
        html.Div([
            _control("Puerto", dcc.Dropdown(id="puerto", placeholder="Automático", clearable=True,
                                            searchable=False, className="dd dd-puerto")),
            html.Button("↻", id="btn-puertos", className="btn btn-icono", title="Buscar puertos"),
            _control("Baudios", dcc.Dropdown(
                id="baud", value=cfg.serial.baud, clearable=False, searchable=False, className="dd dd-baud",
                options=[{"label": "115200 (v2.2)", "value": 115200}, {"label": "9600 (v2.1)", "value": 9600}])),
        ], id="grupo-arduino", className="grupo"),
        html.Div([
            _control("Archivo", dcc.Dropdown(id="replay-archivo", placeholder="Elige un log o CSV",
                                             className="dd dd-archivo")),
            dcc.Upload(html.Button("Subir…", className="btn"), id="replay-upload", multiple=False),
            _control("Velocidad", dcc.Dropdown(
                id="replay-vel", value=4, clearable=False, searchable=False, className="dd dd-vel",
                options=[{"label": f"×{v}", "value": v} for v in (1, 4, 20, 100)])),
        ], id="grupo-replay", className="grupo"),
        html.Div([
            html.Button("Conectar", id="btn-conectar", className="btn btn-primario"),
            html.Button("Desconectar", id="btn-desconectar", className="btn"),
            html.Button("Medir", id="btn-medir", className="btn btn-medir", title="Envía M por serie (como START)"),
        ], className="grupo grupo-botones"),
    ], className="barra")


def _panel_demo(cfg: AppConfig) -> html.Details:
    d = cfg.demo
    return html.Details([
        html.Summary("Simulador: capacitor, fuga y ruido"),
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
                           marks={65: "65 %", 80: "80 %", 93: "93", 98: "98", 100: "100 %"}, updatemode="drag", allow_direct_input=False),
                html.Div(id="demo-meseta-txt", className="ctl-valor"),
            ]), "ctl-ancho"),
            _control("Ruido ADC", html.Div([
                dcc.Slider(id="demo-ruido", min=0, max=3, step=0.1, value=d.ruido_lsb,
                           marks={0: "0", 1: "1", 2: "2", 3: "3 LSB"}, updatemode="drag", allow_direct_input=False),
            ]), "ctl-medio"),
            _control("Velocidad", dcc.Dropdown(
                id="demo-vel", value=d.velocidad, clearable=False, searchable=False, className="dd dd-vel",
                options=[{"label": f"×{v:g}", "value": v} for v in (1, 2, 5, 20)])),
            dcc.Checklist(id="demo-auto", options=[{"label": " Repetir sola cada 3 s", "value": "auto"}],
                          value=[], className="check-auto"),
        ], className="demo-grid"),
    ], id="panel-demo", className="panel-demo", open=True)


def crear_layout(cfg: AppConfig, modo_inicial: str) -> html.Div:
    return html.Div([
        dcc.Interval(id="tick", interval=400),
        dcc.Store(id="ver", data=-1),
        dcc.Download(id="descarga"),
        html.Header([
            html.Div([
                html.H1(["CapSense ", html.Span("Lab", className="acento")]),
                html.Div("Medidor de capacitancia RC · Arduino Uno · 1 µF a 1000 µF", className="sub"),
            ], className="marca"),
            html.Div([
                html.Div(id="estado-pill", className="pill"),
                html.Div(id="estado-msg", className="estado-msg"),
            ], className="estado"),
        ], className="cabecera"),
        _barra_conexion(cfg, modo_inicial),
        _panel_demo(cfg),
        html.Div(id="aviso", className="aviso"),
        html.Div(id="banner-config"),

        html.Div([
            html.Section([
                html.Div([
                    html.Span("Resultado", className="titulo-sec"),
                    dcc.Dropdown(id="sel-medicion", value="ultima", clearable=False, searchable=False,
                                 className="dd dd-medicion",
                                 options=[{"label": "Última medición", "value": "ultima"}]),
                ], className="sec-cab"),
                html.Div(id="hero"),
                html.Div(id="banner"),
                html.Div(id="tarjetas", className="tarjetas"),
            ], className="card card-hero"),
            html.Section([
                html.Div([
                    html.Span("Curva de carga", className="titulo-sec"),
                    dcc.Dropdown(id="sel-prueba", value="todas", clearable=False, searchable=False,
                                 className="dd dd-prueba",
                                 options=[{"label": "Todas las pruebas", "value": "todas"}]),
                ], className="sec-cab"),
                dcc.Graph(id="graf-curva", config={"displaylogo": False, "responsive": True,
                                                    "toImageButtonOptions": {"filename": "curva_capsense"}}),
            ], className="card card-curva"),
        ], className="fila fila-1"),

        html.Div([
            html.Section([
                html.Div([html.Span("Cálculos paso a paso", className="titulo-sec"),
                          html.Span(id="pasos-sub", className="sec-sub")], className="sec-cab"),
                html.Div(id="pasos", className="pasos"),
            ], className="card card-pasos"),
            html.Section([
                html.Div(html.Span("C de cada prueba", className="titulo-sec"), className="sec-cab"),
                dcc.Graph(id="graf-pruebas", config={"displaylogo": False, "responsive": True}),
                html.Div(id="nota-incert", className="nota"),
            ], className="card card-pruebas"),
        ], className="fila fila-2"),

        html.Section([
            html.Div([
                html.Span("Historial de la sesión", className="titulo-sec"),
                html.Div([
                    html.Button("Exportar CSV", id="btn-exportar", className="btn"),
                    html.Button("Exportar pruebas", id="btn-exportar-pruebas", className="btn"),
                    html.Button("Limpiar", id="btn-limpiar", className="btn btn-tenue"),
                ], className="grupo"),
            ], className="sec-cab"),
            html.Div(id="historial", className="tabla-wrap"),
            html.Div(id="ruta-logs", className="nota"),
        ], className="card"),

        html.Details([
            html.Summary("Consola serie (últimas líneas)"),
            html.Pre(id="consola", className="consola"),
        ], className="card card-consola"),

        html.Footer(f"CapSense Lab · dashboard v{__version__} · Samuel y Joel · GeoExpo de Física, Uninorte",
                    className="pie"),
    ], className="pagina")
