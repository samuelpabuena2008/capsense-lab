"""Gráficas Plotly del dashboard."""
from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
import plotly.graph_objects as go

from capsense.domain import physics as ph
from capsense.domain.models import Calibracion

# Paleta del sistema de diseño (ver assets/style.css)
FONDO = "rgba(0,0,0,0)"
PANEL = "#0d1117"
REJILLA = "#1c2531"
TEXTO = "#e8eef5"
TENUE = "#8592a3"
ACENTO = "#3b9eff"
AJUSTE = "#f59e0b"
VERDE = "#22c55e"
ROJO = "#ef4444"
DORADO = "#facc15"
COLORES_PRUEBA = ["#3b9eff", "#f59e0b", "#a78bfa", "#22c55e", "#f472b6"]
FUENTE = "Segoe UI Variable Text, Segoe UI, Inter, Roboto, Helvetica, Arial, sans-serif"
MONO = "Cascadia Code, Cascadia Mono, Fira Code, Consolas, monospace"


def _base(fig: go.Figure, alto: int | None = None) -> go.Figure:
    fig.update_layout(
        height=alto,
        autosize=True,
        paper_bgcolor=FONDO,
        plot_bgcolor=PANEL,
        font=dict(family=FUENTE, size=14, color=TEXTO),
        margin=dict(l=64, r=64, t=36, b=50),
        hoverlabel=dict(font=dict(family=MONO, size=13), bgcolor="#0d1117", bordercolor=ACENTO),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0, bgcolor="rgba(0,0,0,0)",
                    font=dict(size=12, color="#a3b0bf")),
    )
    fig.update_xaxes(gridcolor=REJILLA, zerolinecolor=REJILLA, linecolor="#2d3a4a", ticks="outside",
                     tickcolor="#2d3a4a", tickfont=dict(family=MONO, size=12, color="#a3b0bf"))
    fig.update_yaxes(gridcolor=REJILLA, zerolinecolor=REJILLA, linecolor="#2d3a4a", ticks="outside",
                     tickcolor="#2d3a4a", tickfont=dict(family=MONO, size=12, color="#a3b0bf"))
    return fig


def vacia(mensaje: str, alto: int | None = None) -> go.Figure:
    fig = _base(go.Figure(), alto)
    fig.add_annotation(text=mensaje, showarrow=False, x=0.5, y=0.5, xref="paper", yref="paper",
                       font=dict(size=17, color=TENUE))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def _escala_tiempo(t_max_us: float) -> tuple[float, str]:
    return (1e3, "ms") if t_max_us < 2e6 else (1e6, "s")


def curva_carga(calculados: Sequence[ph.RunCalculado], seleccion: str, cal: Calibracion,
                uirevision: str = "") -> go.Figure:
    """Curva de carga. seleccion = "todas" o el número de prueba como texto."""
    if not calculados:
        return vacia("Sin datos todavía · pulsa Medir")
    if seleccion != "todas":
        elegidas = [rc for rc in calculados if str(rc.run.i) == seleccion] or [calculados[-1]]
    else:
        elegidas = list(calculados)
    una = len(elegidas) == 1

    t_fin = 0.0
    for rc in elegidas:
        t_ult = rc.run.samples[-1].t_us if rc.run.samples else 0
        t_fin = max(t_fin, 5.2 * rc.ajuste.tau if una else 0, t_ult, rc.ajuste.t2 * 1.3)
    k, unidad = _escala_tiempo(t_fin)
    v = cal.v_entrada / cal.adc_max

    fig = _base(go.Figure())
    for rc in elegidas:
        idx = calculados.index(rc)
        color = COLORES_PRUEBA[idx % len(COLORES_PRUEBA)] if not una else ACENTO
        aj, run = rc.ajuste, rc.run
        sufijo = "" if una else f" · prueba {run.i}"

        # (b) curva ajustada
        t = np.linspace(0, t_fin, 400)
        adc = aj.P * (1 - np.exp(-t / aj.tau))
        fig.add_trace(go.Scatter(
            x=t / k, y=adc * v, mode="lines", legendgroup=f"p{run.i}",
            name="Ajuste P(1−e^(−t/τ))" if una else f"Prueba {run.i}",
            line=dict(color=AJUSTE if una else color, width=3, dash="solid" if una else "dot"),
            customdata=np.round(adc, 1),
            hovertemplate=f"t = %{{x:.3f}} {unidad}<br>V = %{{y:.3f}} V<br>ADC = %{{customdata}}"
                          "<extra>ajuste</extra>",
        ))
        # (a) curva medida
        if run.samples:
            ts = np.array([s.t_us for s in run.samples], dtype=float)
            ad = np.array([s.adc for s in run.samples], dtype=float)
            fig.add_trace(go.Scatter(
                x=ts / k, y=ad * v, mode="markers", name=f"Medido ({len(ts)} muestras){sufijo}",
                legendgroup=f"p{run.i}", showlegend=una,
                marker=dict(color=color, size=8, line=dict(width=1, color="#0b0f14")),
                customdata=ad.astype(int),
                hovertemplate=f"t = %{{x:.3f}} {unidad}<br>V = %{{y:.3f}} V<br>ADC = %{{customdata}}"
                              "<extra>medido</extra>",
            ))
        # (c) t1 y t2
        fig.add_trace(go.Scatter(
            x=[aj.t1 / k, aj.t2 / k], y=[cal.adc_n1 * v, cal.adc_n2 * v], mode="markers+text",
            name=f"t₁ y t₂{sufijo}", legendgroup=f"p{run.i}", showlegend=una,
            marker=dict(symbol="diamond", size=16, color=VERDE if una else color,
                        line=dict(width=2, color="#0b0f14")),
            text=["t₁", "t₂"] if una else ["", ""], textposition="middle right",
            textfont=dict(size=17, color=TEXTO),
            customdata=[int(cal.adc_n1), int(cal.adc_n2)],
            hovertemplate=f"t = %{{x:.3f}} {unidad}<br>V = %{{y:.3f}} V<br>ADC = %{{customdata}}"
                          "<extra>cruce</extra>",
        ))

    if una:
        rc = elegidas[0]
        aj = rc.ajuste
        # (d) meseta P
        fig.add_hline(y=aj.P * v, line=dict(color=TENUE, width=2, dash="dash"),
                      annotation=dict(text=f"Meseta P = {aj.P:.1f} ({aj.P / cal.adc_max * 100:.1f} %)",
                                      font=dict(size=15, color=TENUE), xanchor="right", x=1,
                                      yanchor="top"))
        # (e) τ y guías
        v_tau = aj.P * ph.FRACCION_TAU
        fig.add_trace(go.Scatter(
            x=[aj.tau / k], y=[v_tau * v], mode="markers", name="τ (63.2 % de P)",
            marker=dict(symbol="star", size=20, color=DORADO, line=dict(width=1, color="#0b0f14")),
            customdata=[round(v_tau, 1)],
            hovertemplate=f"τ = %{{x:.3f}} {unidad}<br>V = %{{y:.3f}} V<br>ADC = %{{customdata}}"
                          "<extra>τ</extra>",
        ))
        for n_tau in (1, 2, 3, 5):
            pct = (1 - math.exp(-n_tau)) * 100
            fig.add_vline(x=n_tau * aj.tau / k, line=dict(color="#3a4a5e", width=1.5, dash="dot"),
                          annotation=dict(text=f"{n_tau if n_tau > 1 else ''}τ · {pct:.1f} %",
                                          font=dict(size=13, color=TENUE), yanchor="bottom"),
                          annotation_position="bottom right")
        if not rc.run.samples:
            fig.add_annotation(
                text="Sin curva medida (firmware v2.1): se muestra la curva ajustada y los cruces",
                xref="paper", yref="paper", x=0.99, y=0.04, xanchor="right", showarrow=False,
                font=dict(size=14, color=TENUE))

    y_max = cal.v_entrada * 1.06
    fig.add_trace(go.Scatter(x=[0], y=[0], yaxis="y2", mode="markers", marker=dict(opacity=0),
                             showlegend=False, hoverinfo="skip"))
    fig.update_layout(
        uirevision=uirevision or "curva",
        xaxis=dict(title=dict(text=f"Tiempo ({unidad})"), rangemode="tozero"),
        yaxis=dict(title=dict(text="Voltaje en el capacitor (V)"), range=[0, y_max]),
        yaxis2=dict(title=dict(text="ADC (cuentas)"), overlaying="y", side="right",
                    range=[0, y_max / v], showgrid=False, ticks="outside", linecolor=REJILLA),
        hovermode="closest",
    )
    return fig


def pruebas(calculados: Sequence[ph.RunCalculado], cal: Calibracion) -> go.Figure:
    """C de cada prueba con la media y la banda de incertidumbre (semi-rango)."""
    res = ph.resumir(calculados, cal)
    if res is None:
        return vacia("Sin pruebas")
    escala, unidad = (1000.0, "mF") if res.c_uf >= 1000 else (1.0, "µF")
    xs = [rc.run.i for rc in calculados]
    cs = [rc.c_uf / escala for rc in calculados]
    media, delta = res.c_uf / escala, res.delta_uf / escala

    fig = _base(go.Figure())
    fig.add_hrect(y0=media - delta, y1=media + delta, fillcolor=ACENTO, opacity=0.12, line_width=0)
    fig.add_hline(y=media, line=dict(color=ACENTO, width=2, dash="dash"),
                  annotation=dict(text=f"media {media:.4g} {unidad} ± {delta:.2g}",
                                  font=dict(size=12, family=MONO, color="#a3b0bf")),
                  annotation_position="bottom right")
    fig.add_trace(go.Scatter(
        x=xs, y=cs, mode="markers+text", name="C por prueba",
        marker=dict(size=18, color=[COLORES_PRUEBA[i % 5] for i in range(len(xs))],
                    line=dict(width=2, color="#0b0f14")),
        text=[f"{c:.4g}" for c in cs], textposition="top center", textfont=dict(size=12, family=MONO),
        hovertemplate=f"Prueba %{{x}}<br>C = %{{y:.4f}} {unidad}<extra></extra>",
    ))
    pad = max(delta * 2.5, media * 0.004)
    fig.update_layout(
        showlegend=False, margin=dict(l=64, r=20, t=14, b=44),
        xaxis=dict(title=dict(text="Prueba"), tickmode="array", tickvals=xs, range=[0.5, max(xs) + 0.5]),
        yaxis=dict(title=dict(text=f"C ({unidad})"), range=[media - pad * 1.6, media + pad * 1.6]),
    )
    return fig
