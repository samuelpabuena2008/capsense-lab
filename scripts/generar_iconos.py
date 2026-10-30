"""Genera src/capsense/ui/assets/iconos.css: íconos SVG de trazo (24×24) como máscaras CSS.

Toman el color del texto (currentColor), funcionan sin internet y no usan emojis.

    python scripts/generar_iconos.py
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

DESTINO = Path(__file__).resolve().parents[1] / "src" / "capsense" / "ui" / "assets" / "iconos.css"

# Trazos propios, estilo lineal de 2 px
ICONOS = {
    "actividad": '<polyline points="3 12 7 12 10 5 14 19 17 12 21 12"/>',
    "sigma": '<path d="M18 5H6l6 7-6 7h12"/>',
    "tabla": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M3 15h18M9 10v10"/>',
    "enchufe": '<path d="M9 3v5M15 3v5M6 8h12v3a6 6 0 0 1-12 0z"/><path d="M12 17v4"/>',
    "play": '<path d="M7 4.5v15l12.5-7.5z" fill="black"/>',
    "recargar": '<path d="M20 12a8 8 0 1 1-2.34-5.66"/><path d="M20 4v5h-5"/>',
    "pantalla": '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
    "descargar": '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
    "subir": '<path d="M12 20V9M7 14l5-5 5 5M5 4h14"/>',
    "borrar": '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>',
    "alerta": '<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17h.01"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "delta": '<path d="M12 4 3 20h18z"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5h.01"/>',
    "capacitor": '<path d="M3 12h6.5M14.5 12H21M9.5 5v14M14.5 5v14"/>',
    "resistencia": '<path d="M2 12h4l2-4 3 8 3-8 3 8 2-4h3"/>',
    "rayo": '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
    "reloj": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "flecha-arriba": '<path d="M12 19V5M6 11l6-6 6 6"/>',
    "flecha-abajo": '<path d="M12 5v14M6 13l6 6 6-6"/>',
    "calendario": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
    "objetivo": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
    "meseta": '<path d="M3 20c3-9 6-13 10-14h8"/><path d="M3 20h18" opacity="0.5"/>',
    "curva": '<path d="M3 20c2-8 5-12 9-13s7-1 9-1"/><circle cx="7" cy="13" r="1"/><circle cx="12" cy="8" r="1"/><circle cx="17" cy="6.5" r="1"/>',
    "escudo": '<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z"/><path d="M8.5 12l2.5 2.5 4.5-5"/>',
    "tema": '<circle cx="12" cy="12" r="9"/><path d="M12 3a9 9 0 0 0 0 18z" fill="black"/>',
    "barras": '<path d="M5 20V10M12 20V4M19 20v-7"/>',
    "flecha-izq": '<path d="M19 12H5M11 6l-6 6 6 6"/>',
    "flecha-der": '<path d="M5 12h14M13 6l6 6-6 6"/>',
    "circuito": '<path d="M3 7h5l2-3 3 6 2-3h6"/><path d="M3 17h7M14 17h7M10 13v8M14 13v8"/>',
}

PLANTILLA = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' "
             "stroke-width='2' stroke-linecap='round' stroke-linejoin='round'>{}</svg>")


def main() -> None:
    lineas = [
        "/* Generado por scripts/generar_iconos.py. No editar a mano. */",
        ".ico { display: inline-block; width: 18px; height: 18px; flex: none; background-color: currentColor;",
        "       -webkit-mask: var(--ico) center / contain no-repeat; mask: var(--ico) center / contain no-repeat; }",
    ]
    for nombre, cuerpo in ICONOS.items():
        svg = PLANTILLA.format(cuerpo.replace('"', "'"))
        lineas.append(f'.ico-{nombre} {{ --ico: url("data:image/svg+xml,{quote(svg, safe=" =:/,.-")}"); }}')
    DESTINO.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print("Íconos generados en", DESTINO)


if __name__ == "__main__":
    main()
