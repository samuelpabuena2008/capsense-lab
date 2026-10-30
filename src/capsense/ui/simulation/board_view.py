"""SVG de la protoboard real, portado del dibujo de docs/referencia/montaje.html.

Todas las posiciones salen de board_layout (una sola fuente). Cada componente va en un grupo con
data-id para resaltarlo o atenuarlo en cada paso; los pines llevan data-pin para colorearlos por estado.
"""
from __future__ import annotations

from capsense.domain.models import Pines
from capsense.ui.simulation import board_layout as bl
from capsense.ui.simulation.board_layout import ALTO, ANCHO, FLAG_Y, PILL_Y, YL, coord, x_fila


def _txt(x, y, t, s=11, c="var(--bb-muted)", a="middle", halo=False, extra="") -> str:
    h = ' stroke="var(--bb-chan)" stroke-width="4" style="paint-order:stroke"' if halo else ""
    return (f'<text x="{x}" y="{y}" text-anchor="{a}" dominant-baseline="central" font-size="{s}" fill="{c}"{h}'
            f'{extra}>{t}</text>')


def _line(x1, y1, x2, y2, c, w=3.0) -> str:
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{c}" stroke-width="{w}" stroke-linecap="round"/>'


def _dot(x, y, c, r=4.5) -> str:
    return f'<circle cx="{x}" cy="{y}" r="{r}" fill="{c}"/>'


def _pata(x, y, signo) -> str:
    color = "#E24B4A" if signo == "+" else "#378ADD"
    return (f'<circle cx="{x}" cy="{y}" r="6.5" fill="{color}"/>'
            + _txt(x, y, "+" if signo == "+" else "−", 11, "#fff", extra=' font-weight="500"'))


def _pastilla(x, py, texto, color, pin: str | None) -> str:
    w = len(texto) * 7 + 16
    cx = min(max(x, w / 2 + 4), ANCHO - 4 - w / 2)
    dp = f' data-pin="{pin}"' if pin else ""
    return (f'<g class="pastilla"{dp}><rect x="{cx - w / 2}" y="{py - 10}" width="{w}" height="20" rx="10" '
            f'fill="var(--bb-surface)" stroke="{color}" stroke-width="1.5"/>'
            + _txt(cx, py, texto, 12, "var(--bb-ink)") + "</g>")


def _componente(c: dict, pines: Pines) -> tuple[str, str, str]:
    """(piezas, cables, pastillas) de un componente."""
    k = c["k"]
    parts = wires = pills = ""
    if k == "res":
        (xa, y), (xb, _) = coord(c["a"]), coord(c["b"])
        x1, x2 = min(xa, xb), max(xa, xb)
        bl_, m = 34, (x1 + x2) / 2
        bx = m - bl_ / 2
        parts += (_line(x1, y, x2, y, "var(--bb-muted)", 2.5) + _dot(x1, y, "var(--bb-muted)", 4)
                  + _dot(x2, y, "var(--bb-muted)", 4)
                  + f'<rect x="{bx}" y="{y - 6}" width="{bl_}" height="12" rx="5" fill="#D9B88F" stroke="#9C7A4D" '
                    f'stroke-width="0.5"/>'
                  + "".join(f'<rect x="{bx + 7 + i * 8}" y="{y - 6}" width="4" height="12" fill="{col}"/>'
                            for i, col in enumerate(c["bands"])))
        if c.get("lp"):
            parts += _txt(m, y + c["lp"], c["lab"], 12, "var(--bb-ink)", halo=True)
    elif k == "cap":
        (xa, y), (xb, _) = coord(c["pos"]), coord(c["neg"])
        cx = (xa + xb) / 2
        parts += (f'<clipPath id="bb-clip-cap"><circle cx="{cx}" cy="{y}" r="17"/></clipPath>'
                  f'<circle cx="{cx}" cy="{y}" r="17" fill="#2C3E5C" stroke="#1B2740" stroke-width="0.5"/>'
                  f'<rect data-relleno="1" data-base="{y + 17}" data-alto="34" clip-path="url(#bb-clip-cap)" '
                  f'x="{cx - 17}" y="{y + 17}" width="34" height="0" class="bb-relleno"/>'
                  f'<path d="M{cx} {y - 17}A17 17 0 0 0 {cx} {y + 17}Z" fill="#8FA3C4" opacity="0.55"/>'
                  + _pata(xa, y, "+") + _pata(xb, y, "-"))
    elif k == "led":
        (xa, y), (xb, _) = coord(c["an"]), coord(c["ca"])
        cx = (xa + xb) / 2
        color = c["id"].split("-")[1]
        parts += (f'<g class="led {color}" data-led="{color}"><circle class="led-halo" cx="{cx}" cy="{y}" r="20"/>'
                  f'<circle cx="{cx}" cy="{y}" r="12" fill="{c["color"]}" stroke="var(--bb-ink)" stroke-width="0.8" '
                  f'class="led-cuerpo"/></g>' + _pata(xa, y, "+") + _pata(xb, y, "-"))
    elif k == "pin":
        x, y = coord(c["at"])
        py = PILL_Y["up"][c["lvl"]]
        nombre = bl.etiqueta(c, pines)
        wires += _line(x, y, x, py + 10, c["color"]) + _dot(x, y, c["color"])
        pills += _pastilla(x, py, nombre, c["color"], nombre if "rol" in c else None)
    elif k == "rail":
        x, y = x_fila(c["fila"]), YL[c["riel"]]
        py = PILL_Y["up"][c["lvl"]]
        wires += _line(x, y, x, py + 10, c["color"]) + _dot(x, y, c["color"])
        pills += _pastilla(x, py, c["texto"], c["color"], None)
    elif k == "jr":
        x, y = coord(c["at"])
        yr = YL[c["riel"]]
        wires += _line(x, y, x, yr, "var(--bb-ink)") + _dot(x, y, "var(--bb-ink)") + _dot(x, yr, "var(--bb-ink)")
    elif k in ("jj", "lane"):
        (xa, ya), (xb, yb) = coord(c["a"]), coord(c["b"])
        wires += (f'<path d="M{xa} {ya}V{c["y"]}H{xb}V{yb}" fill="none" stroke="#7F77DD" stroke-width="3" '
                  f'stroke-linecap="round" stroke-linejoin="round"/>' + _dot(xa, ya, "#7F77DD") + _dot(xb, yb, "#7F77DD"))
    elif k == "btn":
        xa, xb = x_fila(c["fila"]), x_fila(c["fila"] + 2)
        for x, y in ((xa, YL["e"]), (xb, YL["e"]), (xa, YL["f"]), (xb, YL["f"])):
            parts += _line(x, y, x, 241 if y < 230 else 259, "var(--bb-muted)", 2.5) + _dot(x, y, "var(--bb-muted)", 4)
        parts += (f'<rect x="{min(xa, xb) - 8}" y="241" width="{abs(xb - xa) + 16}" height="18" rx="4" '
                  f'fill="var(--bb-btn)" stroke="var(--bb-ink)" stroke-width="0.8"/>'
                  + _txt(x_fila(c["fila"] + 1), 250, c["lab"], 11, "var(--bb-ink)"))
    elif k == "pot":
        xs = [x_fila(f) for f in c["filas"]]
        y = YL[c["letra"]]
        parts += (f'<rect x="{min(xs) - 6}" y="{y - 12}" width="{max(xs) - min(xs) + 12}" height="24" rx="5" '
                  f'fill="var(--bb-btn)" stroke="var(--bb-ink)" stroke-width="0.8"/>'
                  + _txt(sum(xs) / 3, y, "POT", 11, "var(--bb-ink)"))
    elif k == "lcd":
        for i in range(16):
            x, y = x_fila(30 - i), YL["j"]
            parts += (f'<rect x="{x - 9}" y="{y - 9}" width="18" height="18" rx="3" fill="var(--bb-accent)"/>'
                      + _txt(x, y, str(i + 1), 11, "var(--bb-on-accent)"))
        parts += ('<rect x="0" y="354" width="522" height="118" rx="8" fill="var(--bb-accent)" fill-opacity="0.12" '
                  'stroke="var(--bb-accent)" stroke-dasharray="5 4"/>'
                  '<rect x="150" y="384" width="230" height="70" rx="8" fill="#0d1f10" stroke="#2c4a2f"/>'
                  '<text class="lcd-texto" data-lcd="0" x="164" y="410"></text>'
                  '<text class="lcd-texto" data-lcd="1" x="164" y="436"></text>'
                  + _txt(265, 466, "LCD 16×2 (el módulo cuelga debajo de la placa)", 11, "var(--bb-ink)"))
    elif k == "flag":
        x, y = coord(c["at"])
        py = FLAG_Y[c["lvl"]]
        nombre = bl.etiqueta(c, pines)
        wires += _line(x, y, x, py - 9, c["color"], 2.5) + _dot(x, y, c["color"])
        pills += _pastilla(x, py, nombre, c["color"], nombre if "rol" in c else None)
    return parts, wires, pills


def _base() -> str:
    s = ['<rect x="28" y="72" width="624" height="36" rx="6" class="bb-placa"/>',
         '<rect x="28" y="112" width="624" height="112" rx="6" class="bb-placa"/>',
         '<rect x="28" y="224" width="624" height="26" fill="var(--bb-chan)"/>',
         '<rect x="28" y="250" width="624" height="106" rx="6" class="bb-placa"/>',
         '<rect x="28" y="360" width="624" height="40" rx="6" class="bb-placa"/>',
         _line(36, 77, 644, 77, "#E24B4A", 1.5), _line(36, 107, 644, 107, "#378ADD", 1.5),
         _line(36, 364, 644, 364, "#E24B4A", 1.5), _line(36, 396, 644, 396, "#378ADD", 1.5)]
    for r in bl.FILAS:
        for letra in ("tr", "tb", *bl.LETRAS, "br", "bb"):
            s.append(f'<circle cx="{x_fila(r)}" cy="{YL[letra]}" r="3.5" fill="var(--bb-hole)"/>')
    for letra in bl.LETRAS:
        s.append(_txt(36, YL[letra], letra))
    s += [_txt(38, YL["tr"], "+", 12), _txt(38, YL["tb"], "−", 12)]
    return "".join(s)


def svg(pines: Pines) -> str:
    partes, cables, pastillas = [], [], []
    for c in bl.COMPONENTES:
        pz, cb, ps = _componente(c, pines)
        if pz:
            partes.append(f'<g class="sim-el" data-id="{c["id"]}">{pz}</g>')
        if cb:
            cables.append(f'<g class="sim-el" data-id="{c["id"]}">{cb}</g>')
        if ps:
            pastillas.append(f'<g class="sim-el" data-id="{c["id"]}">{ps}</g>')
    numeros = "".join(_txt(x_fila(r), 237, str(r), 11, halo=True) for r in bl.FILAS)
    flujos = []
    for nombre, tramos in bl.caminos().items():
        for tramo in tramos:
            d = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in tramo)
            flujos.append(f'<path class="flujo" data-flujo="{nombre}" d="{d}"/>')
    lectura = ('<g class="bb-lectura"><rect x="532" y="404" width="140" height="64" rx="10" class="bb-lectura-caja"/>'
               + _txt(602, 420, f"Nodo ({pines.lectura})", 11, "var(--bb-muted)")
               + '<text class="valor" data-vc="1" x="602" y="440">0.00 V</text>'
               + '<text class="volt-adc" data-adc="1" x="602" y="458">ADC 0</text></g>')
    return (f'<svg class="sim-svg protoboard" viewBox="0 0 {ANCHO} {ALTO}" role="img" '
            f'aria-label="Protoboard con el montaje real del medidor, con los componentes activos resaltados">'
            + _base() + "".join(partes) + numeros + "".join(cables) + "".join(flujos) + "".join(pastillas)
            + lectura + "</svg>")
