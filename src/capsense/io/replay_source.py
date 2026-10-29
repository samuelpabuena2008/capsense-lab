"""Modo replay: reproduce una sesión guardada.

Acepta dos tipos de archivo:
  * Log serial (.log / .txt): texto crudo del Arduino, con o sin marca de tiempo al inicio de cada
    línea ("12.345<TAB>#MUESTRA,..."), como lo graban services/storage.py y scripts/grabar_log.py.
    Si trae tiempos, respeta el ritmo original (multiplicado por la velocidad).
  * CSV de pruebas (*_pruebas.csv) que exporta el dashboard: se convierte a protocolo v2.2.
"""
from __future__ import annotations

import csv
import io
import logging
from pathlib import Path

from capsense.domain import physics as ph
from capsense.domain.models import Calibracion
from capsense.io.base import DataSource

log = logging.getLogger(__name__)

COLUMNAS_PRUEBAS = ["medicion", "prueba", "rango", "t1_us", "t2_us", "meseta", "tau_ms", "c_uf"]


def leer_log(texto: str) -> list[tuple[float, str]]:
    """[(espera en s antes de la línea, línea)]. Sin marcas de tiempo, espera 0."""
    out: list[tuple[float, str]] = []
    previo: float | None = None
    for cruda in texto.splitlines():
        linea = cruda.rstrip("\r")
        espera = 0.0
        marca, sep, resto = linea.partition("\t")
        if sep:
            try:
                t = float(marca)
                espera = max(0.0, t - previo) if previo is not None else 0.0
                previo = t
                linea = resto
            except ValueError:
                pass
        out.append((espera, linea))
    return out


def csv_a_lineas(texto: str, cal: Calibracion) -> list[tuple[float, str]]:
    """Convierte el CSV de pruebas a líneas del protocolo v2.2 (una medición por grupo)."""
    filas = list(csv.DictReader(io.StringIO(texto)))
    if not filas or not set(COLUMNAS_PRUEBAS) <= set(filas[0]):
        raise ValueError("El CSV no tiene las columnas de pruebas: " + ", ".join(COLUMNAS_PRUEBAS))
    grupos: dict[str, list[dict[str, str]]] = {}
    for f in filas:
        grupos.setdefault(f["medicion"], []).append(f)

    out: list[tuple[float, str]] = [(0.0, "#VERSION,replay")]
    for filas_m in grupos.values():
        out.append((1.0, f"#INICIO,{len(filas_m)}"))
        calc = []
        for f in filas_m:
            rango = int(f["rango"])
            out.append((0.3, f"#PRUEBA_INI,{f['prueba']},{rango}"))
            out.append((0.5, f"#PRUEBA,{f['prueba']},{rango},{f['t1_us']},{f['t2_us']},{f['meseta']},"
                             f"{f['tau_ms']},{f['c_uf']},0"))
            aj = ph.ajustar_curva(float(f["t1_us"]), float(f["t2_us"]), cal)
            calc.append((float(f["c_uf"]), float(f["tau_ms"]), aj.P, rango))
        cs = [c[0] for c in calc]
        n = len(cs)
        prom = sum(cs) / n
        _d, inc = ph.incertidumbre_semirango(cs)
        q, e = ph.carga_energia(prom, cal.v_entrada)
        tau = sum(c[1] for c in calc) / n
        mes = sum(c[2] for c in calc) / n / cal.adc_max * 100
        r = cal.r_total(calc[-1][3])
        out.append((0.1, f"#RESULTADO,{n},{r:.1f},{cal.v_entrada:.2f},{tau:.3f},{prom:.3f},{inc:.2f},"
                         f"{min(cs):.3f},{max(cs):.3f},{q:.3f},{e:.3f},{mes:.1f}"))
        out.append((0.0, "#FIN"))
    out.append((0.0, "#LISTO"))
    return out


def cargar_archivo(ruta: Path, cal: Calibracion) -> list[tuple[float, str]]:
    texto = ruta.read_text(encoding="utf-8", errors="replace")
    if ruta.suffix.lower() == ".csv":
        return csv_a_lineas(texto, cal)
    return leer_log(texto)


class ReplaySource(DataSource):
    acepta_comandos = False

    def __init__(self, ruta: Path, cal: Calibracion | None = None, velocidad: float = 1.0,
                 espera_max: float = 3.0) -> None:
        super().__init__()
        self.ruta = Path(ruta)
        self.cal = cal or Calibracion()
        self.velocidad = velocidad
        self.espera_max = espera_max        # recorta pausas largas del log original
        self.nombre = f"Replay {self.ruta.name}"
        self.terminado = False

    def _correr(self) -> None:
        try:
            lineas = cargar_archivo(self.ruta, self.cal)
        except (OSError, ValueError) as e:
            log.error("No pude leer %s: %s", self.ruta, e)
            self._estado(False, f"No pude leer {self.ruta.name}: {e}")
            return
        self._estado(True, f"Reproduciendo {self.ruta.name}")
        acumulado = 0.0
        for espera, linea in lineas:
            acumulado += min(espera, self.espera_max) / max(self.velocidad, 0.01)
            if acumulado >= 0.02:
                if self._parar.wait(acumulado):
                    return
                acumulado = 0.0
            if self._parar.is_set():
                return
            self._emitir(linea)
        self.terminado = True
        self._estado(False, f"Fin del replay ({self.ruta.name})")
