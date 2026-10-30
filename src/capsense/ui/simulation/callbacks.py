"""Callbacks de la pestaña Simulación (animación explicativa del circuito RC).

Usa un ejemplo fijo para dar forma a la animación: un capacitor de 100 µF cargando por 10 kΩ.
Python arma el guion (domain/simulation.py + steps_data.py); el navegador lo anima (assets/simulation.js).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import dash
from dash import Input, Output

from capsense.domain import simulation as sim
from capsense.ui.simulation import grafica, guion
from capsense.ui.temas import paleta

if TYPE_CHECKING:
    from capsense.ui.app import Controlador

C_EJEMPLO_UF = 100.0


def registrar(app: dash.Dash, ctl: Controlador) -> None:
    cal = ctl.cfg.calibracion
    pines = ctl.cfg.pines
    medicion = sim.simular_medicion(C_EJEMPLO_UF, cal, "auto")
    g = guion.construir(medicion, cal, pines)
    g.datos["r_descarga"] = cal.r_descarga + cal.r_pin
    g.datos["escala"] = grafica.escala(g.datos)[0]
    g.datos["c_real_uf"] = C_EJEMPLO_UF

    @app.callback(Output("sim-datos", "data"), Output("sim-graf", "figure"), Output("sim-graf-titulo", "children"),
                  Input("tema", "data"), Input("sim-magnitud", "value"))
    def preparar(tema, magnitud):
        magnitud = magnitud or "v"
        factor, _titulo, unidad = grafica.factor_magnitud(g.datos, magnitud)
        datos = dict(g.datos, factor_y=factor)        # el navegador escala la meseta animada con este factor
        titulo = (f"Carga en el capacitor (Q = C·V, C = {C_EJEMPLO_UF:g} µF)" if magnitud == "q"
                  else "Voltaje en el capacitor")
        return datos, grafica.figura(datos, paleta(tema), magnitud=magnitud), titulo

    app.clientside_callback(
        """
        function(datos, svgs) {
            if (datos && svgs && window.capsenseSim) { window.capsenseSim.cargar(svgs, datos); }
            return window.dash_clientside.no_update;
        }
        """,
        Output("sim-lienzo", "title"), Input("sim-datos", "data"), Input("sim-svgs", "data"),
    )
