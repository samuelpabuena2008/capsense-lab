"""Datos del montaje en la protoboard (única fuente de posiciones), portados de docs/referencia/montaje.html.

Geometría igual a la del montaje: 30 filas (la 1 a la derecha), hoyos a–e arriba y f–j abajo, rieles
de arriba (tr = rojo 5V, tb = azul GND). Las coordenadas se calculan con las mismas fórmulas X(r) e YL.

Los nombres de los pines del Arduino NO están aquí: cada cable tiene un "rol" que se resuelve con
config.Pines (carga0, carga1, descarga, lectura, led_verde, ...).
"""
from __future__ import annotations

import re

from capsense.domain.models import Pines

ANCHO, ALTO = 680, 480
FILAS = range(1, 31)
LETRAS = "abcdefghij"
YL = {"tr": 84, "tb": 100, "a": 130, "b": 150, "c": 170, "d": 190, "e": 210, "f": 262, "g": 282, "h": 302,
      "i": 322, "j": 342, "br": 372, "bb": 388}
PILL_Y = {"up": (44, 18)}
FLAG_Y = (300, 324)

ROJO, AZUL, VERDE, AMBAR, MORADO, AMARILLO, VERDE_LED = (
    "#E24B4A", "#378ADD", "#639922", "#EF9F27", "#7F77DD", "#F2C230", "#3FAF5B")
TIERRA = "currentColor"
BANDAS_220 = ("#B03030", "#B03030", "#7A4A1E")


def x_fila(r: int) -> float:
    return 50 + (30 - r) * 20


_RE_HOYO = re.compile(r"^([a-j])(\d{1,2})$")


def hoyo(ref: str) -> tuple[int, str]:
    """'c12' -> (12, 'c'). Lanza ValueError si el hoyo no existe en la placa."""
    m = _RE_HOYO.match(ref)
    if not m or int(m.group(2)) not in FILAS:
        raise ValueError(f"Hoyo inexistente: {ref!r}")
    return int(m.group(2)), m.group(1)


def coord(ref: str) -> tuple[float, float]:
    fila, letra = hoyo(ref)
    return x_fila(fila), YL[letra]


# ---------------- componentes por etapa (montaje.html) ----------------
# k: res | cap | led | pin | rail | jr | jj | btn | pot | lcd | flag | lane
COMPONENTES: list[dict] = [
    # Etapa 1: medición (filas 12 a 18)
    {"id": "r560", "etapa": 1, "k": "res", "a": "c12", "b": "c15", "lab": "560 Ω",
     "bands": ("#2E9E4F", "#2F6FD0", "#7A4A1E"), "lp": 15},
    {"id": "r10k", "etapa": 1, "k": "res", "a": "d15", "b": "d18", "lab": "10 kΩ",
     "bands": ("#7A4A1E", "#222222", "#E8832A"), "lp": -15},
    {"id": "cap", "etapa": 1, "k": "cap", "pos": "e15", "neg": "e16"},
    {"id": "w-descarga", "etapa": 1, "k": "pin", "at": "a12", "rol": "descarga", "lvl": 0, "color": VERDE},
    {"id": "w-lectura", "etapa": 1, "k": "pin", "at": "a15", "rol": "lectura", "lvl": 0, "color": AMBAR},
    {"id": "w-gnd", "etapa": 1, "k": "pin", "at": "a16", "texto": "GND", "lvl": 1, "color": TIERRA},
    {"id": "w-carga0", "etapa": 1, "k": "pin", "at": "a18", "rol": "carga0", "lvl": 1, "color": MORADO},
    # Etapa 2: alimentación
    {"id": "w-5v", "etapa": 2, "k": "rail", "fila": 30, "riel": "tr", "texto": "5V", "lvl": 0, "color": ROJO},
    {"id": "w-gnd2", "etapa": 2, "k": "rail", "fila": 28, "riel": "tb", "texto": "GND", "lvl": 1, "color": TIERRA},
    # Etapa 3: LEDs
    {"id": "r220-verde", "etapa": 3, "k": "res", "a": "c27", "b": "c30", "lab": "220 Ω", "bands": BANDAS_220, "lp": 0},
    {"id": "led-verde", "etapa": 3, "k": "led", "an": "e30", "ca": "e29", "color": VERDE_LED},
    {"id": "jr-verde", "etapa": 3, "k": "jr", "at": "a29", "riel": "tb"},
    {"id": "w-led_verde", "etapa": 3, "k": "pin", "at": "a27", "rol": "led_verde", "lvl": 0, "color": VERDE_LED},
    {"id": "r220-amarillo", "etapa": 3, "k": "res", "a": "c23", "b": "c26", "lab": "220 Ω", "bands": BANDAS_220, "lp": 0},
    {"id": "led-amarillo", "etapa": 3, "k": "led", "an": "e26", "ca": "e25", "color": AMARILLO},
    {"id": "jr-amarillo", "etapa": 3, "k": "jr", "at": "a25", "riel": "tb"},
    {"id": "w-led_amarillo", "etapa": 3, "k": "pin", "at": "a23", "rol": "led_amarillo", "lvl": 0, "color": AMARILLO},
    {"id": "r220-rojo", "etapa": 3, "k": "res", "a": "c19", "b": "c22", "lab": "220 Ω", "bands": BANDAS_220, "lp": 0},
    {"id": "led-rojo", "etapa": 3, "k": "led", "an": "e22", "ca": "e21", "color": ROJO},
    {"id": "jr-rojo", "etapa": 3, "k": "jr", "at": "a21", "riel": "tb"},
    {"id": "w-led_rojo", "etapa": 3, "k": "pin", "at": "a19", "rol": "led_rojo", "lvl": 0, "color": ROJO},
    # Etapa 4: botones
    {"id": "btn-atras", "etapa": 4, "k": "btn", "fila": 9, "lab": "ATRÁS"},
    {"id": "w-boton_atras", "etapa": 4, "k": "pin", "at": "a9", "rol": "boton_atras", "lvl": 0, "color": AZUL},
    {"id": "gnd-atras", "etapa": 4, "k": "flag", "at": "g11", "texto": "GND↑", "lvl": 0, "color": TIERRA},
    {"id": "btn-start", "etapa": 4, "k": "btn", "fila": 5, "lab": "START"},
    {"id": "w-boton_start", "etapa": 4, "k": "pin", "at": "a5", "rol": "boton_start", "lvl": 0, "color": AZUL},
    {"id": "gnd-start", "etapa": 4, "k": "flag", "at": "g7", "texto": "GND↑", "lvl": 0, "color": TIERRA},
    {"id": "btn-siguiente", "etapa": 4, "k": "btn", "fila": 1, "lab": "SIG."},
    {"id": "w-boton_siguiente", "etapa": 4, "k": "pin", "at": "a1", "rol": "boton_siguiente", "lvl": 0, "color": AZUL},
    {"id": "gnd-siguiente", "etapa": 4, "k": "flag", "at": "g3", "texto": "GND↑", "lvl": 0, "color": TIERRA},
    # Etapa 5: LCD y contraste
    {"id": "lcd", "etapa": 5, "k": "lcd"},
    {"id": "r220-luz", "etapa": 5, "k": "res", "a": "f16", "b": "f13", "lab": "220 Ω", "bands": BANDAS_220, "lp": 0},
    {"id": "lcd-5v-luz", "etapa": 5, "k": "flag", "at": "g13", "texto": "5V↑", "lvl": 1, "color": ROJO},
    {"id": "lcd-vss", "etapa": 5, "k": "flag", "at": "g30", "texto": "GND↑", "lvl": 0, "color": TIERRA},
    {"id": "lcd-vdd", "etapa": 5, "k": "flag", "at": "g29", "texto": "5V↑", "lvl": 1, "color": ROJO},
    {"id": "lcd-rs", "etapa": 5, "k": "flag", "at": "g27", "rol": "lcd_rs", "lvl": 0, "color": MORADO},
    {"id": "lcd-rw", "etapa": 5, "k": "flag", "at": "g26", "texto": "GND↑", "lvl": 1, "color": TIERRA},
    {"id": "lcd-e", "etapa": 5, "k": "flag", "at": "g25", "rol": "lcd_e", "lvl": 0, "color": MORADO},
    {"id": "lcd-db4", "etapa": 5, "k": "flag", "at": "g20", "rol": "lcd_db4", "lvl": 1, "color": MORADO},
    {"id": "lcd-db5", "etapa": 5, "k": "flag", "at": "g19", "rol": "lcd_db5", "lvl": 0, "color": MORADO},
    {"id": "lcd-db6", "etapa": 5, "k": "flag", "at": "g18", "rol": "lcd_db6", "lvl": 1, "color": MORADO},
    {"id": "lcd-db7", "etapa": 5, "k": "flag", "at": "g17", "rol": "lcd_db7", "lvl": 0, "color": MORADO},
    {"id": "lcd-k", "etapa": 5, "k": "flag", "at": "g15", "texto": "GND↑", "lvl": 0, "color": TIERRA},
    {"id": "pot", "etapa": 5, "k": "pot", "filas": (21, 22, 23), "letra": "i"},
    {"id": "pot-gnd", "etapa": 5, "k": "flag", "at": "g21", "texto": "GND↑", "lvl": 0, "color": TIERRA},
    {"id": "pot-5v", "etapa": 5, "k": "flag", "at": "g23", "texto": "5V↑", "lvl": 0, "color": ROJO},
    {"id": "pot-v0", "etapa": 5, "k": "lane", "a": "g22", "b": "g28", "y": 272},
    # Etapa 6: autorango (opcional)
    {"id": "puente", "etapa": 6, "k": "jj", "a": "b15", "b": "a17", "y": 141},
    {"id": "r1m", "etapa": 6, "k": "res", "a": "b17", "b": "b20", "lab": "1 MΩ",
     "bands": ("#7A4A1E", "#222222", "#2E9E4F"), "lp": 0},
    {"id": "w-carga1", "etapa": 6, "k": "pin", "at": "a20", "rol": "carga1", "lvl": 1, "color": AZUL},
]
POR_ID = {c["id"]: c for c in COMPONENTES}


def hoyos_de(c: dict) -> list[str]:
    k = c["k"]
    if k == "res":
        return [c["a"], c["b"]]
    if k == "cap":
        return [c["pos"], c["neg"]]
    if k == "led":
        return [c["an"], c["ca"]]
    if k in ("pin", "jr", "flag"):
        return [c["at"]]
    if k in ("jj", "lane"):
        return [c["a"], c["b"]]
    if k == "btn":
        f = c["fila"]
        return [f"e{f}", f"f{f}", f"e{f + 2}", f"f{f + 2}"]
    if k == "pot":
        return [f"{c['letra']}{f}" for f in c["filas"]]
    if k == "lcd":
        return [f"j{f}" for f in range(15, 31)]
    return []


def todos_los_hoyos() -> set[str]:
    return {h for c in COMPONENTES for h in hoyos_de(c)}


def nombre_pin(rol: str, pines: Pines) -> str:
    """Rol del montaje -> nombre del pin según config (D2, A5, ...)."""
    if rol.startswith("carga"):
        return pines.carga[int(rol[5:])]
    if rol.startswith("lcd_db"):
        return pines.lcd_datos[int(rol[6:]) - 4]
    return getattr(pines, rol)


def etiqueta(c: dict, pines: Pines) -> str:
    return nombre_pin(c["rol"], pines) if "rol" in c else c.get("texto", "")


# ---------------- caminos de la corriente (para los puntos animados) ----------------
def _pill(ref: str, lvl: int) -> tuple[float, float]:
    x, _ = coord(ref)
    return x, PILL_Y["up"][lvl] + 10


def caminos() -> dict[str, list[list[tuple[float, float]]]]:
    """Recorridos en el sentido real de la corriente, en coordenadas de la placa."""
    gnd = [_pill("a16", 1), coord("a16"), coord("e16")]
    return {
        # pin de carga 10k (a18) -> 10 kΩ -> nodo (fila 15) -> capacitor -> GND (a16)
        "carga0": [[_pill("a18", 1), coord("a18"), coord("d18"), coord("d15"), coord("e15"), coord("e16"),
                    coord("a16"), _pill("a16", 1)]],
        # pin de carga 1M (a20) -> 1 MΩ (b20 a b17) -> puente a17 -> b15 -> capacitor -> GND
        "carga1": [[_pill("a20", 1), coord("a20"), coord("b20"), coord("b17"), coord("a17"),
                    (x_fila(17), 141), (x_fila(15), 141), coord("b15"), coord("e15"), coord("e16"),
                    coord("a16"), _pill("a16", 1)]],
        # capacitor (+) -> 560 Ω (c15 a c12) -> pin de descarga (a12) en LOW; vuelve por GND al (−)
        "descarga": [[coord("e15"), coord("c15"), coord("c12"), coord("a12"), _pill("a12", 0)], gnd],
    }
