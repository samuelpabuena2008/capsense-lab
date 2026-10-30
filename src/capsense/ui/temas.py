"""Paletas de las gráficas para cada tema (deben coincidir con los tokens de assets/style.css)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Paleta:
    nombre: str
    acento: str            # línea principal
    acento_2: str          # segunda serie
    acento_rgb: str        # "r,g,b" para transparencias
    acento_2_rgb: str
    muestras: str          # puntos medidos
    t12: str               # marcadores t1/t2
    tau: str
    texto: str
    texto_2: str
    texto_3: str
    rejilla: str
    eje: str
    hover_bg: str
    pruebas: tuple[str, ...]
    escala_mapa: tuple[tuple[float, str], ...]
    ok: str
    critico: str


AMBAR = Paleta(
    nombre="ambar", acento="#ff6a13", acento_2="#ffa149", acento_rgb="255,106,19", acento_2_rgb="255,161,73",
    muestras="#ffd2ad", t12="#f2efea", tau="#ffd166",
    texto="#f2efea", texto_2="#b3ada5", texto_3="#8a847c", rejilla="#1d1d1d", eje="#2e2e2e", hover_bg="#141414",
    pruebas=("#ff6a13", "#ffa149", "#ffc78a", "#e2540a", "#ffdcb8"),
    escala_mapa=((0.0, "#3a1500"), (0.5, "#0f0f0f"), (1.0, "#ff6a13")),
    ok="#3fb950", critico="#f04438",
)

NEON = Paleta(
    nombre="neon", acento="#2de2c4", acento_2="#8b5cf6", acento_rgb="45,226,196", acento_2_rgb="139,92,246",
    muestras="#a5f3e6", t12="#eaf0ff", tau="#facc15",
    texto="#eaf0ff", texto_2="#a9b6d6", texto_3="#8190b4", rejilla="rgba(120,150,255,0.10)", eje="rgba(120,150,255,0.25)",
    hover_bg="#0b1330",
    pruebas=("#2de2c4", "#8b5cf6", "#38bdf8", "#a78bfa", "#f472b6"),
    escala_mapa=((0.0, "#8b5cf6"), (0.5, "#0b1330"), (1.0, "#2de2c4")),
    ok="#34d399", critico="#fb7185",
)

TEMAS = {"ambar": AMBAR, "neon": NEON}


def paleta(nombre: str | None) -> Paleta:
    return TEMAS.get(nombre or "ambar", AMBAR)
