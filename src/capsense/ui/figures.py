"""Gráficas Plotly de la aplicación, con la paleta del tema activo."""
from __future__ import annotations

import math
from collections.abc import Sequence
from urllib.parse import quote

import numpy as np
import plotly.graph_objects as go

from capsense.domain import physics as ph
from capsense.domain.models import Calibracion, Measurement
from capsense.ui.temas import AMBAR, Paleta

FUENTE = "Segoe UI Variable Text, Segoe UI, Inter, Roboto, Helvetica, Arial, sans-serif"
DISPLAY = "Segoe UI Variable Display, Segoe UI, Inter, sans-serif"
MONO = "Cascadia Code, Cascadia Mono, Fira Code, Consolas, monospace"


def _base(fig: go.Figure, p: Paleta) -> go.Figure:
    fig.update_layout(
        autosize=True,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FUENTE, size=13, color=p.texto_2),
        margin=dict(l=58, r=58, t=10, b=42),
        hoverlabel=dict(font=dict(family=MONO, size=13, color=p.texto), bgcolor=p.hover_bg, bordercolor=p.acento),
        showlegend=False,
    )
    ejes = dict(gridcolor=p.rejilla, zeroline=False, linecolor=p.eje, showline=False, ticks="",
                tickfont=dict(family=FUENTE, size=12, color=p.texto_3))
    fig.update_xaxes(**ejes)
    fig.update_yaxes(**ejes)
    return fig


def vacia(mensaje: str, p: Paleta = AMBAR) -> go.Figure:
    fig = _base(go.Figure(), p)
    fig.add_annotation(text=mensaje, showarrow=False, x=0.5, y=0.5, xref="paper", yref="paper",
                       font=dict(size=16, color=p.texto_3))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def _escala_tiempo(t_max_us: float) -> tuple[float, str]:
    return (1e3, "ms") if t_max_us < 2e6 else (1e6, "s")


def _area_brillante(fig: go.Figure, x, y, rgb: str, nombre: str, hover: str, customdata, ancho: float = 3.0) -> None:
    """Línea con halo y relleno degradado (el "brillo" de las referencias)."""
    fig.add_trace(go.Scatter(x=x, y=y, mode="lines", hoverinfo="skip",
                             line=dict(color=f"rgba({rgb},0.18)", width=ancho * 4, shape="spline", smoothing=0.6)))
    fig.add_trace(go.Scatter(
        x=x, y=y, mode="lines", name=nombre, line=dict(color=f"rgb({rgb})", width=ancho, shape="spline", smoothing=0.6),
        fill="tozeroy",
        fillgradient=dict(type="vertical", colorscale=[[0, f"rgba({rgb},0)"], [1, f"rgba({rgb},0.30)"]]),
        customdata=customdata, hovertemplate=hover,
    ))


def unidad_carga(c_uf_max: float, v_entrada: float) -> tuple[float, str]:
    """(divisor, unidad) para Q en µC: si la carga máxima pasa de 1000 µC se muestra en mC."""
    return (1000.0, "mC") if c_uf_max * v_entrada >= 1000 else (1.0, "µC")


def curva_carga(calculados: Sequence[ph.RunCalculado], seleccion: str, cal: Calibracion,
                uirevision: str = "", p: Paleta = AMBAR, magnitud: str = "v") -> go.Figure:
    """Curva de carga. seleccion = "todas" o el número de prueba como texto.

    magnitud = "v": voltaje del capacitor V(t). magnitud = "q": carga almacenada Q(t) = C·V(t), con la C
    calculada de cada prueba (tiene la misma forma que V(t), escalada por C).
    """
    if not calculados:
        return vacia("Sin datos todavía · pulsa Medir", p)
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
    es_q = magnitud == "q"
    div_q, u_q = unidad_carga(max(rc.c_uf for rc in elegidas), cal.v_entrada)
    fig = _base(go.Figure(), p)
    if es_q:
        hover = (f"t = %{{x:.3f}} {unidad}<br>Q = %{{y:.4g}} {u_q}<br>ADC = %{{customdata}}<extra></extra>")
    else:
        hover = f"t = %{{x:.3f}} {unidad}<br>V = %{{y:.3f}} V<br>ADC = %{{customdata}}<extra></extra>"
    v_base = v

    for idx, rc in enumerate(elegidas):
        aj, run = rc.ajuste, rc.run
        # cuentas ADC -> unidad del eje (V, o µC/mC con la C de esta prueba)
        v = v_base * (rc.c_uf / div_q if es_q else 1.0)
        color_prueba = p.pruebas[calculados.index(rc) % len(p.pruebas)]
        t = np.linspace(0, t_fin, 400)
        adc = aj.P * (1 - np.exp(-t / aj.tau))
        if una:
            _area_brillante(fig, t / k, adc * v, p.acento_rgb, "Ajuste", hover, np.round(adc, 1))
        else:
            fig.add_trace(go.Scatter(x=t / k, y=adc * v, mode="lines", name=f"Prueba {run.i}",
                                     line=dict(color=color_prueba, width=2.2, shape="spline"),
                                     customdata=np.round(adc, 1), hovertemplate=hover, showlegend=True))
        if run.samples:
            ts = np.array([s.t_us for s in run.samples], dtype=float)
            ad = np.array([s.adc for s in run.samples], dtype=float)
            fig.add_trace(go.Scatter(
                x=ts / k, y=ad * v, mode="markers", name=f"Medido · prueba {run.i}", showlegend=False,
                marker=dict(color=p.muestras if una else color_prueba, size=6 if una else 4,
                            opacity=0.95 if una else 0.6, line=dict(width=0)),
                customdata=ad.astype(int), hovertemplate=hover,
            ))
        if una or idx == len(elegidas) - 1:
            fig.add_trace(go.Scatter(
                x=[aj.t1 / k, aj.t2 / k], y=[cal.adc_n1 * v, cal.adc_n2 * v], mode="markers+text", showlegend=False,
                marker=dict(symbol="circle", size=13, color=p.hover_bg, line=dict(width=3, color=p.t12)),
                text=["t₁", "t₂"], textposition="middle right", textfont=dict(size=15, color=p.texto, family=DISPLAY),
                customdata=[int(cal.adc_n1), int(cal.adc_n2)], hovertemplate=hover,
            ))

    if una:
        aj = elegidas[0].ajuste
        if es_q:
            meseta_txt = f"Q máx = C·V_P = {aj.P * v:.4g} {u_q} · {aj.P / cal.adc_max * 100:.1f} %"
        else:
            meseta_txt = f"meseta P = {aj.P:.1f} · {aj.P / cal.adc_max * 100:.1f} %"
        fig.add_hline(y=aj.P * v, line=dict(color=p.texto_3, width=1.5, dash="dash"),
                      annotation=dict(text=meseta_txt,
                                      font=dict(size=12, color=p.texto_2), xanchor="right", x=1, yanchor="bottom"))
        v_tau = aj.P * ph.FRACCION_TAU
        for n_tau in (1, 2, 3, 5):
            pct = (1 - math.exp(-n_tau)) * 100
            fig.add_vline(x=n_tau * aj.tau / k, line=dict(color=p.eje, width=1, dash="dot"),
                          annotation=dict(text=f"{n_tau if n_tau > 1 else ''}τ · {pct:.0f}%",
                                          font=dict(size=11, color=p.texto_3), yanchor="bottom"),
                          annotation_position="bottom right")
        fig.add_trace(go.Scatter(x=[aj.tau / k, aj.tau / k], y=[0, v_tau * v], mode="lines", hoverinfo="skip",
                                 line=dict(color=f"rgba({p.acento_rgb},0.55)", width=1.5)))
        fig.add_trace(go.Scatter(
            x=[aj.tau / k], y=[v_tau * v], mode="markers+text", text=[f"τ = {aj.tau / 1000:.1f} ms"],
            textposition="top left", textfont=dict(size=13, color=p.tau, family=DISPLAY),
            marker=dict(size=16, color=p.tau, line=dict(width=4, color=f"rgba({p.acento_rgb},0.35)")),
            customdata=[round(v_tau, 1)], hovertemplate=hover))
        if not elegidas[0].run.samples:
            fig.add_annotation(text="Firmware v2.1: sin curva medida, se muestra el ajuste",
                               xref="paper", yref="paper", x=0.99, y=0.04, xanchor="right", showarrow=False,
                               font=dict(size=12, color=p.texto_3))

    v_max = cal.v_entrada * 1.08
    if es_q:
        y_max = v_max * max(rc.c_uf for rc in elegidas) / div_q
        y_titulo = f"carga Q ({u_q})"
        # con una prueba, el eje derecho muestra el voltaje equivalente (Q = C·V)
        eje2 = dict(title=dict(text="voltaje (V)", font=dict(size=12, color=p.texto_3)), range=[0, v_max]) if una \
            else None
    else:
        y_max = v_max
        y_titulo = "voltaje (V)"
        eje2 = dict(title=dict(text="ADC", font=dict(size=12, color=p.texto_3)), range=[0, v_max / v_base])
    if eje2:
        fig.add_trace(go.Scatter(x=[0], y=[0], yaxis="y2", mode="markers", marker=dict(opacity=0),
                                 hoverinfo="skip", showlegend=False))
    fig.update_layout(
        uirevision=uirevision or "curva", hovermode="closest", showlegend=not una,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, font=dict(size=12, color=p.texto_2),
                    bgcolor="rgba(0,0,0,0)"),
        xaxis=dict(title=dict(text=f"tiempo ({unidad})", font=dict(size=12, color=p.texto_3)), rangemode="tozero"),
        yaxis=dict(title=dict(text=y_titulo, font=dict(size=12, color=p.texto_3)), range=[0, y_max]),
    )
    if eje2:
        fig.update_layout(yaxis2=dict(overlaying="y", side="right", showgrid=False,
                                      tickfont=dict(size=12, color=p.texto_3), **eje2))
    return fig


def desviaciones(calculados: Sequence[ph.RunCalculado], cal: Calibracion, p: Paleta = AMBAR) -> go.Figure:
    """Cuánto se aparta cada prueba del promedio (%), con la banda de incertidumbre (semi-rango)."""
    res = ph.resumir(calculados, cal)
    if res is None:
        return vacia("Sin pruebas", p)
    xs = [f"P{rc.run.i}" for rc in calculados]
    ds = [(rc.c_uf / res.c_uf - 1) * 100 for rc in calculados]
    fig = _base(go.Figure(), p)
    fig.add_hrect(y0=-res.inc_pct, y1=res.inc_pct, fillcolor=f"rgba({p.acento_rgb},0.07)", line_width=0)
    fig.add_hline(y=0, line=dict(color=p.texto_3, width=1))
    for signo in (1, -1):
        fig.add_hline(y=signo * res.inc_pct, line=dict(color=f"rgba({p.acento_rgb},0.5)", width=1, dash="dot"))
    fig.add_trace(go.Bar(
        x=xs, y=ds, marker=dict(color=[p.acento if d >= 0 else p.acento_2 for d in ds], line=dict(width=0),
                                cornerradius=6),
        width=0.5, text=[f"{rc.c_uf:.4g}" for rc in calculados], textposition="outside",
        textfont=dict(family=FUENTE, size=12, color=p.texto_2), cliponaxis=False,
        customdata=[rc.c_uf for rc in calculados],
        hovertemplate="%{x}<br>C = %{customdata:.4f} µF<br>%{y:+.3f} % del promedio<extra></extra>",
    ))
    tope = max(max(abs(d) for d in ds), res.inc_pct, 0.05) * 1.6
    fig.update_layout(margin=dict(l=56, r=16, t=16, b=30), bargap=0.4,
                      yaxis=dict(range=[-tope, tope], ticksuffix=" %", zeroline=False),
                      annotations=[dict(text=f"banda ± {res.inc_pct:.2f} %", x=0, xref="paper", y=res.inc_pct,
                                        yanchor="bottom", xanchor="left", showarrow=False,
                                        font=dict(size=11, color=p.texto_3))])
    return fig


def mapa_repetibilidad(mediciones: Sequence[Measurement], cal: Calibracion, p: Paleta = AMBAR) -> go.Figure:
    """Mapa de calor: desviación de cada prueba respecto al promedio de su medición."""
    filas, textos, etiquetas = [], [], []
    n_max = 1
    for m in mediciones:
        calc = [rc for rc in (ph.recalcular_run(r, cal) for r in m.runs) if rc is not None]
        res = ph.resumir(calc, cal)
        if res is None:
            continue
        ds = [(rc.c_uf / res.c_uf - 1) * 100 for rc in calc]
        n_max = max(n_max, len(ds))
        filas.append(ds)
        textos.append([f"{rc.c_uf:.4g}" for rc in calc])
        num, u = ph.formato_c(res.c_uf)
        etiquetas.append(f"#{m.id} · {num} {u}")
    if not filas:
        return vacia("Sin mediciones todavía", p)
    z = [f + [None] * (n_max - len(f)) for f in filas]
    t = [f + [""] * (n_max - len(f)) for f in textos]
    lim = max(0.2, max(abs(x) for f in filas for x in f))
    fig = _base(go.Figure(), p)
    fig.add_trace(go.Heatmap(
        z=z, x=[f"Prueba {i}" for i in range(1, n_max + 1)], y=etiquetas, text=t, texttemplate="%{text}",
        textfont=dict(family=FUENTE, size=13, color=p.texto), zmin=-lim, zmax=lim, xgap=4, ygap=4,
        colorscale=[[a, c] for a, c in p.escala_mapa],
        colorbar=dict(title=dict(text="% vs promedio", font=dict(size=11, color=p.texto_3)), thickness=10,
                      outlinewidth=0, tickfont=dict(size=11, color=p.texto_3), ticksuffix=" %"),
        hovertemplate="%{y}<br>%{x}: %{text} µF<br>%{z:+.3f} %<extra></extra>",
    ))
    fig.update_layout(margin=dict(l=130, r=20, t=8, b=30), yaxis=dict(autorange="reversed", showgrid=False),
                      xaxis=dict(showgrid=False, side="top"))
    return fig


def sparkline(valores: Sequence[float], p: Paleta = AMBAR, ancho: int = 140, alto: int = 46) -> str:
    """Mini-gráfica como SVG en data URI (sin un dcc.Graph por tarjeta)."""
    vals = [v for v in valores if v is not None and math.isfinite(v)]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-12:
        lo, hi = lo - 1, hi + 1
    pad = 4
    pts = [(pad + i * (ancho - 2 * pad) / (len(vals) - 1),
            alto - pad - (v - lo) / (hi - lo) * (alto - 2 * pad)) for i, v in enumerate(vals)]
    linea = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"{pad},{alto} " + linea + f" {ancho - pad},{alto}"
    ux, uy = pts[-1]
    svg = (f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {ancho} {alto}' preserveAspectRatio='none'>"
           f"<defs><linearGradient id='g' x1='0' y1='0' x2='0' y2='1'>"
           f"<stop offset='0' stop-color='rgb({p.acento_rgb})' stop-opacity='0.35'/>"
           f"<stop offset='1' stop-color='rgb({p.acento_rgb})' stop-opacity='0'/></linearGradient></defs>"
           f"<polygon points='{area}' fill='url(#g)'/>"
           f"<polyline points='{linea}' fill='none' stroke='rgb({p.acento_rgb})' stroke-width='2.2' "
           f"stroke-linejoin='round' stroke-linecap='round' vector-effect='non-scaling-stroke'/>"
           f"<circle cx='{ux:.1f}' cy='{uy:.1f}' r='3' fill='rgb({p.acento_rgb})'/></svg>")
    return "data:image/svg+xml," + quote(svg, safe=" =:/,.'-")
