"""Render del panel "Cálculos paso a paso" (MathJax vía dcc.Markdown)."""
from __future__ import annotations

from collections.abc import Sequence

from dash import dcc, html

from capsense.domain.steps import Chequeo, Paso
from capsense.ui.layout import icono


def _chequeo(c: Chequeo) -> html.Span:
    if c.coincide:
        return html.Span([icono("ico-check"), f"{c.nombre} coincide con el firmware"], className="check ok",
                         title=f"Python {c.python:.6g} · Arduino {c.firmware:.6g} {c.unidad}")
    return html.Span(
        [icono("ico-delta"),
         f"{c.nombre}: {c.diferencia_pct:+.3f} % (Python {c.python:.5g} vs Arduino {c.firmware:.5g} {c.unidad})"],
        className="check dif",
    )


def panel_pasos(pasos: Sequence[Paso], inicio: int = 1) -> list[html.Div]:
    bloques = []
    for n, p in enumerate(pasos, inicio):
        hijos: list = [
            html.Div([html.Span(str(n), className="paso-num"), html.Span(p.titulo, className="paso-titulo")],
                     className="paso-cab"),
            dcc.Markdown(p.markdown, mathjax=True, className="paso-md"),
        ]
        if p.nota:
            hijos.append(html.Div([icono("ico-info"), html.Span(p.nota)], className="paso-nota"))
        if p.chequeos:
            hijos.append(html.Div([_chequeo(c) for c in p.chequeos], className="checks"))
        bloques.append(html.Div(hijos, className="paso"))
    return bloques
