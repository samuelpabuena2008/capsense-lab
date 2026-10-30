"""Gráfica V(t) de la simulación. El navegador mueve el cursor y muestra/oculta las marcas por paso.

Las trazas tienen nombre fijo para que simulation.js las encuentre: sim, ajuste, t1, t2, tau, real.
shapes[0] = cursor de tiempo, shapes[1] = meseta P (se anima en el paso de ajuste).
"""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go

from capsense.ui.figures import DISPLAY, _base
from capsense.ui.temas import Paleta


def escala(datos: dict) -> tuple[float, str]:
    s = datos["series"][datos["guia"]]
    span = max(abs(s["t"][0]), abs(s["t"][-1]))
    return (1000.0, "ms") if span < 2 else (1.0, "s")


def figura(datos: dict, p: Paleta, real: list[tuple[float, float]] | None = None) -> go.Figure:
    k, unidad = escala(datos)
    s = datos["series"][datos["guia"]]
    vin = datos["vin"]
    t = np.array(s["t"]) * k
    fig = _base(go.Figure(), p)
    fig.add_trace(go.Scatter(
        x=t, y=s["v"], mode="lines", name="sim", line=dict(color=f"rgb({p.acento_rgb})", width=3),
        fill="tozeroy", fillgradient=dict(type="vertical",
                                          colorscale=[[0, f"rgba({p.acento_rgb},0)"], [1, f"rgba({p.acento_rgb},0.25)"]]),
        customdata=s["adc"], hovertemplate=f"t = %{{x:.3f}} {unidad}<br>V = %{{y:.3f}} V<br>ADC = %{{customdata}}<extra></extra>"))
    m = datos.get("marcas") or {}
    if m:
        tt = np.linspace(0, max(s["t"][-1], m["t2"]) * 1.25, 200)
        fig.add_trace(go.Scatter(x=tt * k, y=m["p_v"] * (1 - np.exp(-tt / m["tau"])), mode="lines", name="ajuste",
                                 visible=False, line=dict(color=p.acento_2, width=2, dash="dash"), hoverinfo="skip"))
        n1 = 250 / 1023 * vin
        n2 = 700 / 1023 * vin
        for nombre, x, y, txt in (("t1", m["t1"], n1, "t₁"), ("t2", m["t2"], n2, "t₂")):
            fig.add_trace(go.Scatter(x=[x * k], y=[y], mode="markers+text", name=nombre, visible=False, text=[txt],
                                     textposition="middle right", textfont=dict(size=15, family=DISPLAY, color=p.texto),
                                     marker=dict(size=13, color=p.hover_bg, line=dict(width=3, color=p.t12)),
                                     hovertemplate=f"{txt} = %{{x:.3f}} {unidad}<extra></extra>"))
        v_tau = m["p_v"] * (1 - np.exp(-1))
        fig.add_trace(go.Scatter(x=[m["tau"] * k], y=[v_tau], mode="markers+text", name="tau", visible=False,
                                 text=["τ (63.2 %)"], textposition="top left",
                                 textfont=dict(size=13, family=DISPLAY, color=p.tau),
                                 marker=dict(size=15, color=p.tau), hovertemplate=f"τ = %{{x:.3f}} {unidad}<extra></extra>"))
    if real:
        fig.add_trace(go.Scatter(x=[x * k for x, _ in real], y=[y for _, y in real], mode="markers", name="real",
                                 marker=dict(size=6, color=p.muestras, line=dict(width=1, color=p.hover_bg)),
                                 hovertemplate=f"medido: t = %{{x:.3f}} {unidad}<br>V = %{{y:.3f}} V<extra></extra>"))
    t0 = s["t"][0] * k
    fig.update_layout(
        shapes=[
            dict(type="line", x0=t0, x1=t0, y0=0, y1=1, yref="paper", line=dict(color=p.texto, width=2)),
            dict(type="line", x0=0, x1=1, xref="paper", y0=vin, y1=vin, visible=False,
                 line=dict(color=p.acento_2, width=1.5, dash="dot")),
            dict(type="rect", x0=t0, x1=0, y0=0, y1=1, yref="paper", fillcolor=f"rgba({p.acento_2_rgb},0.07)",
                 line_width=0, layer="below"),
        ],
        annotations=[dict(x=t0, y=1, yref="paper", xanchor="left", yanchor="top", showarrow=False,
                          text="descarga", font=dict(size=12, color=p.texto_3)),
                     dict(x=0, y=1, yref="paper", xanchor="left", yanchor="top", showarrow=False,
                          text="  carga →", font=dict(size=12, color=p.texto_3))],
        margin=dict(l=52, r=16, t=10, b=40), hovermode="closest", uirevision="sim",
        xaxis=dict(title=dict(text=f"tiempo ({unidad}) · 0 = arranca la carga", font=dict(size=12, color=p.texto_3))),
        yaxis=dict(title=dict(text="V capacitor", font=dict(size=12, color=p.texto_3)), range=[0, vin * 1.08]),
    )
    return fig
