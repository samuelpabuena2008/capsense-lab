"""Pestaña Simulación: animación del circuito RC para explicar, paso a paso, cómo mide el medidor.

Es una presentación, no un simulador con parámetros: usa un ejemplo fijo (ver callbacks.py).
"""
from __future__ import annotations

from dash import dcc, html

from capsense.config import AppConfig
from capsense.ui.simulation import board_view, circuit_schematic


def _icono(nombre: str) -> html.Span:
    return html.Span(className=f"ico {nombre}", **{"aria-hidden": "true"})


def _seg(prefijo: str, opciones: list[tuple[str, str]], activo: str, etiqueta: str) -> html.Div:
    return html.Div([html.Button(txt, id=f"{prefijo}-{val}", className="activo" if val == activo else "",
                                 **{"data-valor": val}) for val, txt in opciones],
                    className="sim-seg", role="group", **{"aria-label": etiqueta})


def vista(cfg: AppConfig) -> html.Section:
    cal, pines = cfg.calibracion, cfg.pines
    svgs = {"esquema": circuit_schematic.svg(cal, pines), "protoboard": board_view.svg(pines)}
    return html.Section([
        dcc.Store(id="sim-svgs", data=svgs),
        dcc.Store(id="sim-datos"),
        html.Div([
            _seg("sim-v", [("esquema", "Esquema"), ("protoboard", "Protoboard")], "esquema", "Vista"),
            _seg("sim-m", [("guiado", "Paso a paso"), ("auto", "Automático")], "guiado", "Modo"),
            html.Div(className="espaciador"),
            html.Div([
                html.Button([_icono("ico-flecha-izq"), "Anterior"], id="sim-ant", className="btn sim-btn"),
                html.Button([_icono("ico-play"), html.Span("Pausa", id="sim-play-txt")], id="sim-play",
                            className="btn sim-btn"),
                html.Button(["Siguiente", _icono("ico-flecha-der")], id="sim-sig", className="btn btn-primario sim-btn"),
                html.Button([_icono("ico-recargar"), "Reiniciar"], id="sim-reiniciar", className="btn sim-btn"),
            ], className="sim-controles"),
        ], className="sim-barra"),
        html.Div([
            html.Div([
                html.Div([
                    html.Div([html.Span("Paso 1", id="sim-paso-num", className="sim-paso-num"),
                              html.H2("—", id="sim-titulo")], className="sim-titulo-wrap"),
                    html.Div(id="sim-puntos", className="sim-puntos"),
                ], className="card-cab"),
                html.Div(id="sim-lienzo", className="sim-lienzo"),
                html.Div([
                    html.Span([html.I(className="e-high"), "5 V (HIGH)"]),
                    html.Span([html.I(className="e-low"), "0 V / tierra (LOW)"]),
                    html.Span([html.I(className="e-hiz"), "desconectado"]),
                    html.Span([html.I(className="e-adc"), "midiendo el voltaje"]),
                    html.Span([html.I(className="e-flujo"), "puntos = corriente"]),
                    html.Span(id="sim-tiempo", className="sim-tiempo"),
                ], className="sim-leyenda"),
            ], className="card sim-card-circuito"),
            html.Div([
                html.Div([
                    html.Div([
                        html.P(id="sim-que-pasa", className="sim-que-pasa"),
                        html.H3("En el Arduino"),
                        html.Pre(id="sim-codigo", className="sim-codigo"),
                        html.H3("Pines"),
                        html.Div(id="sim-pines", className="sim-pines"),
                        html.H3("En la protoboard"),
                        html.P(id="sim-proto", className="sim-proto"),
                    ], className="sim-panel-scroll"),
                ], className="card sim-card-panel"),
                html.Div([
                    html.Div([html.H2("Voltaje en el capacitor")], className="card-cab"),
                    dcc.Graph(id="sim-graf", className="graf", config={"displaylogo": False, "responsive": True,
                                                                       "displayModeBar": False}),
                ], className="card sim-card-graf"),
            ], className="sim-col sim-col-der"),
        ], className="sim-grid"),
    ], id="vista-simulacion", className="vista vista-simulacion", style={"display": "none"})
