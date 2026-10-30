"""SVG del esquema eléctrico del circuito de medición (vista principal para explicar).

Usa los mismos ids lógicos que board_layout (data-id) para que el resaltado funcione igual en las dos vistas:
  w-carga0 / r10k, w-carga1 / r1m / puente, w-descarga / r560, w-lectura, cap, w-gnd, led-*, lcd.
Proporción ancha (900×430) para que llene la tarjeta y se lea en proyector.
"""
from __future__ import annotations

from capsense.domain.models import Calibracion, Pines
from capsense.domain.physics import formato_r

W, H = 900, 430
ARD_X, ARD_W = 16, 190
Y = {"carga0": 105, "carga1": 160, "descarga": 235, "lectura": 305, "gnd": 380}
NODO = (610, Y["descarga"])
CAP_X = 715
R_X1, R_X2 = 280, 470


def _resistencia(x1: float, x2: float, y: float, etiqueta: str, rid: str) -> str:
    """Zigzag con el cuerpo centrado entre x1 y x2."""
    cuerpo = 120
    a = (x1 + x2 - cuerpo) / 2
    b = a + cuerpo
    pts = [f"{a},{y}"]
    for k in range(6):
        px = a + (k + 0.5) * cuerpo / 6
        pts.append(f"{px:.1f},{y - 13 if k % 2 == 0 else y + 13}")
    pts.append(f"{b},{y}")
    return (f'<g class="sim-el" data-id="{rid}">'
            f'<line class="cable" x1="{x1}" y1="{y}" x2="{a}" y2="{y}"/>'
            f'<polyline class="resistor" points="{" ".join(pts)}"/>'
            f'<line class="cable" x1="{b}" y1="{y}" x2="{x2}" y2="{y}"/>'
            f'<text class="et" x="{(a + b) / 2}" y="{y - 24}">{etiqueta}</text></g>')


def _pin(nombre: str, y: float, rol: str) -> str:
    """Nombre del pin en el borde del Arduino + chip de estado (lo llena el navegador)."""
    x = ARD_X + ARD_W
    return (f'<g class="pin-ard"><circle cx="{x}" cy="{y}" r="6" class="pin-punto"/>'
            f'<text class="pin-nombre" x="{x - 12}" y="{y + 1}" text-anchor="end">{nombre}</text>'
            f'<g class="chip" data-pin="{nombre}" data-rol="{rol}">'
            f'<rect x="{ARD_X + 10}" y="{y - 15}" width="112" height="30" rx="15"/>'
            f'<text x="{ARD_X + 66}" y="{y + 1}">—</text></g></g>')


def svg(cal: Calibracion, pines: Pines) -> str:
    r10k = formato_r(cal.rangos[0].r_ohm)
    r1m = formato_r(cal.rangos[1].r_ohm) if len(cal.rangos) > 1 else "—"
    nx, ny = NODO
    x0 = ARD_X + ARD_W
    gy = Y["gnd"]
    p = [f'<svg class="sim-svg esquema" viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid meet" role="img" '
         f'aria-label="Esquema del circuito de medición: Arduino, resistencias, capacitor y lectura en el nodo">']
    # Arduino y sus pines
    p.append(f'<rect class="arduino" x="{ARD_X}" y="24" width="{ARD_W}" height="382" rx="18"/>'
             f'<text class="ard-titulo" x="{ARD_X + ARD_W / 2}" y="54">Arduino Uno</text>')
    p.append(_pin(pines.carga[0], Y["carga0"], "carga0"))
    if len(pines.carga) > 1:
        p.append(_pin(pines.carga[1], Y["carga1"], "carga1"))
    p.append(_pin(pines.descarga, Y["descarga"], "descarga"))
    p.append(_pin(pines.lectura, Y["lectura"], "lectura"))
    p.append(f'<g class="pin-ard"><circle cx="{x0}" cy="{gy}" r="6" class="pin-punto"/>'
             f'<text class="pin-nombre" x="{x0 - 12}" y="{gy + 1}" text-anchor="end">GND</text></g>')
    # Carga 10 kΩ
    p.append(f'<g class="sim-el" data-id="w-carga0"><line class="cable" x1="{x0}" y1="{Y["carga0"]}" x2="{R_X1}" '
             f'y2="{Y["carga0"]}"/><polyline class="cable" points="{R_X2},{Y["carga0"]} {nx},{Y["carga0"]} '
             f'{nx},{ny}"/></g>')
    p.append(_resistencia(R_X1, R_X2, Y["carga0"], f"{r10k} · carga", "r10k"))
    # Carga 1 MΩ (autorango)
    if len(pines.carga) > 1:
        p.append(f'<g class="sim-el" data-id="w-carga1"><line class="cable" x1="{x0}" y1="{Y["carga1"]}" '
                 f'x2="{R_X1}" y2="{Y["carga1"]}"/></g>')
        p.append(_resistencia(R_X1, R_X2, Y["carga1"], f"{r1m} · autorango", "r1m"))
        p.append(f'<g class="sim-el" data-id="puente"><polyline class="cable" '
                 f'points="{R_X2},{Y["carga1"]} {nx - 40},{Y["carga1"]} {nx - 40},{ny}"/></g>')
    # Descarga 560 Ω
    p.append(f'<g class="sim-el" data-id="w-descarga"><line class="cable" x1="{x0}" y1="{ny}" x2="{R_X1}" y2="{ny}"/>'
             f'<line class="cable" x1="{R_X2}" y1="{ny}" x2="{nx - 40}" y2="{ny}"/></g>')
    p.append(_resistencia(R_X1, R_X2, ny, f"{formato_r(cal.r_descarga)} · descarga", "r560"))
    # Nodo y capacitor
    p.append(f'<line class="cable" x1="{nx - 40}" y1="{ny}" x2="{CAP_X}" y2="{ny}"/>'
             f'<circle class="nodo" cx="{nx}" cy="{ny}" r="8"/>'
             f'<text class="et" x="{nx + 12}" y="{ny - 14}" text-anchor="start">nodo</text>')
    p.append(f'<g class="sim-el" data-id="cap">'
             f'<line class="cable" x1="{CAP_X}" y1="{ny}" x2="{CAP_X}" y2="{ny + 30}"/>'
             f'<line class="placa" x1="{CAP_X - 36}" y1="{ny + 30}" x2="{CAP_X + 36}" y2="{ny + 30}"/>'
             f'<path class="placa" d="M{CAP_X - 36} {ny + 54} Q{CAP_X} {ny + 43} {CAP_X + 36} {ny + 54}" fill="none"/>'
             f'<line class="cable" x1="{CAP_X}" y1="{ny + 50}" x2="{CAP_X}" y2="{gy}"/>'
             f'<text class="polaridad" x="{CAP_X - 52}" y="{ny + 24}">+</text>'
             f'<text class="et" x="{CAP_X + 48}" y="{ny + 47}" text-anchor="start">C</text>'
             f'<rect class="tanque" x="{CAP_X + 72}" y="{ny - 55}" width="40" height="150" rx="10"/>'
             f'<rect class="tanque-nivel" data-relleno="1" data-base="{ny + 93}" data-alto="146" x="{CAP_X + 74}" '
             f'y="{ny + 93}" width="36" height="0" rx="8"/>'
             f'<text class="valor" data-vc="1" x="{CAP_X + 92}" y="{ny - 68}">0.00 V</text></g>')
    # Lectura en el nodo (voltímetro del ADC)
    p.append(f'<g class="sim-el" data-id="w-lectura"><polyline class="cable lectura" '
             f'points="{x0},{Y["lectura"]} {nx},{Y["lectura"]} {nx},{ny}"/>'
             f'<rect class="voltimetro" x="310" y="{Y["lectura"] - 36}" width="190" height="66" rx="14"/>'
             f'<text class="volt-v" data-vc="1" x="405" y="{Y["lectura"] - 9}">0.00 V</text>'
             f'<text class="volt-adc" data-adc="1" x="405" y="{Y["lectura"] + 17}">ADC 0</text></g>')
    # Tierra
    p.append(f'<g class="sim-el" data-id="w-gnd"><line class="cable" x1="{x0}" y1="{gy}" x2="{CAP_X}" y2="{gy}"/>'
             f'<path class="tierra" d="M{CAP_X - 20} {gy + 12}h40M{CAP_X - 12} {gy + 20}h24M{CAP_X - 5} {gy + 28}h10"/></g>')
    # Corriente (puntos animados), en el sentido real
    flujos = [
        ("carga0", f"M{x0} {Y['carga0']} H{nx} V{ny} H{CAP_X} V{gy} H{x0}"),
        ("carga1", f"M{x0} {Y['carga1']} H{nx - 40} V{ny} H{CAP_X} V{gy} H{x0}"),
        ("descarga", f"M{CAP_X} {ny + 30} V{ny} H{x0}"),
        ("descarga", f"M{x0} {gy} H{CAP_X} V{ny + 54}"),
    ]
    for grupo, d in flujos:
        p.append(f'<path class="flujo" data-flujo="{grupo}" d="{d}"/>')
    # LEDs
    for i, (color, rol, pin) in enumerate((("verde", "led-verde", pines.led_verde),
                                           ("amarillo", "led-amarillo", pines.led_amarillo),
                                           ("rojo", "led-rojo", pines.led_rojo))):
        cx = 620 + i * 72
        p.append(f'<g class="sim-el led {color}" data-id="{rol}" data-led="{color}">'
                 f'<circle class="led-halo" cx="{cx}" cy="42" r="24"/><circle class="led-cuerpo" cx="{cx}" cy="42" r="14"/>'
                 f'<text class="et" x="{cx}" y="78">{pin}</text></g>')
    # LCD 16×2
    p.append('<g class="sim-el" data-id="lcd"><rect class="lcd-marco" x="748" y="352" width="148" height="72" rx="10"/>'
             '<rect class="lcd-pantalla" x="755" y="359" width="134" height="58" rx="4"/>'
             '<text class="lcd-texto" data-lcd="0" x="760" y="382"></text>'
             '<text class="lcd-texto" data-lcd="1" x="760" y="405"></text></g>')
    p.append("</svg>")
    return "".join(p)
