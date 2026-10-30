"""Genera el logo de CapSense Lab: un cubo isométrico con las letras C, A y P en sus tres caras.

Cada letra se dibuja en un cuadrado plano de 100×100 (la cara y sus recortes) y luego se proyecta
sobre su cara del cubo con una transformación afín isométrica. Los recortes son máscaras, así que el
fondo se ve a través de ellos y el logo funciona sobre cualquier color.

    python scripts/generar_logo.py
"""
from __future__ import annotations

from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1] / "src" / "capsense" / "ui" / "assets"
C30, S30 = 0.8660254, 0.5
COLOR = "#EEECE7"

# Proyección (u, v) ∈ [0,100]² -> plano, con el vértice central del cubo en (0, 0)
TRANSFORMACIONES = {
    # cara superior: u hacia el vértice de arriba, v hacia el centro
    "C": f"matrix({C30} {-S30} {C30} {S30} {-100 * C30} {-100 * S30})",
    # cara izquierda: u hacia el centro, v hacia abajo
    "A": f"matrix({C30} {S30} 0 1 {-100 * C30} {-100 * S30})",
    # cara derecha: u hacia la derecha, v hacia abajo
    "P": f"matrix({C30} {-S30} 0 1 0 0)",
}


def cara(r_si: float, r_sd: float, r_id: float, r_ii: float, m: float = 5.0) -> str:
    """Cuadrado redondeado con radios distintos por esquina (sup-izq, sup-der, inf-der, inf-izq)."""
    a, b = m, 100 - m
    return (f"M{a + r_si} {a} H{b - r_sd} Q{b} {a} {b} {a + r_sd} V{b - r_id} Q{b} {b} {b - r_id} {b} "
            f"H{a + r_ii} Q{a} {b} {a} {b - r_ii} V{a + r_si} Q{a} {a} {a + r_si} {a} Z")


# Forma de la cara y recortes (rectángulos redondeados: x, y, ancho, alto, radio)
LETRAS = {
    "C": (cara(12, 12, 12, 12), [(40, 39, 75, 22, 11)]),
    "A": (cara(34, 34, 10, 10), [(41, 27, 18, 24, 9), (40, 68, 20, 45, 9)]),
    "P": (cara(10, 32, 10, 10), [(36, 23, 24, 21, 10.5), (56, 61, 60, 60, 10)]),
}


def svg(fondo: str | None = None) -> str:
    defs, caras = [], []
    for letra, (forma, recortes) in LETRAS.items():
        huecos = "".join(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="black"/>'
                         for x, y, w, h, r in recortes)
        defs.append(f'<mask id="m{letra}" maskUnits="userSpaceOnUse" x="-10" y="-10" width="140" height="140">'
                    f'<rect x="-10" y="-10" width="140" height="140" fill="white"/>{huecos}</mask>')
        caras.append(f'<g transform="{TRANSFORMACIONES[letra]}"><path d="{forma}" fill="{COLOR}" '
                     f'mask="url(#m{letra})"/></g>')
    base = f'<rect x="-110" y="-115" width="220" height="230" rx="40" fill="{fondo}"/>' if fondo else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-104 -108 208 216" role="img" '
            f'aria-label="CapSense Lab">{base}<defs>{"".join(defs)}</defs>{"".join(caras)}</svg>\n')


def main() -> None:
    (ASSETS / "logo-cap.svg").write_text(svg(), encoding="utf-8")
    (ASSETS / "logo-cap-fondo.svg").write_text(svg("#0A0A0A"), encoding="utf-8")
    print("Logo generado en", ASSETS)


if __name__ == "__main__":
    main()
