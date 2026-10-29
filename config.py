"""Constantes del CapSense Lab (iguales al firmware).

Si existe config.json junto a este archivo, sus claves reemplazan a los valores por defecto.
Ejemplo de config.json:  {"V_ENTRADA": 4.95, "R_REAL": [9800, 998000]}
"""
import json
from pathlib import Path

CARPETA = Path(__file__).resolve().parent

DEFAULTS = {
    "V_ENTRADA": 4.92,            # V: voltaje real del pin 5V
    "R_REAL": [9790.0, 996000.0], # ohm: resistencias de carga medidas (10k, 1M)
    "R_ETIQ": ["10k", "1M"],
    "R_PIN": 25.0,                # ohm: resistencia interna del pin
    "K_CAL": 1.0,                 # factor de calibración
    "ADC_N1": 250.0,              # primer nivel del ajuste
    "ADC_N2": 700.0,              # segundo nivel del ajuste
    "ADC_MAX": 1023.0,
    "BAUD": 115200,               # v2.2 (la v2.1 usa 9600)
}


def cargar(ruta=None):
    datos = dict(DEFAULTS)
    ruta = Path(ruta) if ruta else CARPETA / "config.json"
    if ruta.exists():
        try:
            extra = json.loads(ruta.read_text(encoding="utf-8"))
            datos.update({k: v for k, v in extra.items() if k in DEFAULTS})
        except (OSError, ValueError) as e:
            print(f"[config] No pude leer {ruta}: {e}. Uso los valores por defecto.")
    return datos


_c = cargar()
V_ENTRADA = float(_c["V_ENTRADA"])
R_REAL = [float(r) for r in _c["R_REAL"]]
R_ETIQ = list(_c["R_ETIQ"])
R_PIN = float(_c["R_PIN"])
K_CAL = float(_c["K_CAL"])
ADC_N1 = float(_c["ADC_N1"])
ADC_N2 = float(_c["ADC_N2"])
ADC_MAX = float(_c["ADC_MAX"])
BAUD = int(_c["BAUD"])
