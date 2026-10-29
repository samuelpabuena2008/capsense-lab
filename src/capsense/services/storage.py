"""Logs por sesión y exportación CSV.

Por cada sesión se crean en logs/:
  sesion_AAAAMMDD_HHMMSS_serial.log      todo lo que llegó por serie, con marca de tiempo (sirve para replay)
  sesion_AAAAMMDD_HHMMSS_mediciones.csv  una fila por medición (el historial)
  sesion_AAAAMMDD_HHMMSS_pruebas.csv     una fila por prueba (también sirve para replay)
"""
from __future__ import annotations

import csv
import io
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from capsense.domain import physics as ph
from capsense.domain.models import Calibracion, Measurement

log = logging.getLogger(__name__)

COLUMNAS_MEDICION = ["medicion", "hora", "origen", "firmware", "n_pruebas", "rango", "C_uF", "delta_uF",
                     "incert_pct", "tau_ms", "meseta_pct", "fuga", "Q_uC", "E_uJ", "R_ohm", "error"]
COLUMNAS_PRUEBA = ["medicion", "prueba", "rango", "t1_us", "t2_us", "meseta", "tau_ms", "c_uf",
                   "ext", "n_muestras", "t_reconstruidos"]


def fila_medicion(m: Measurement, cal: Calibracion) -> dict[str, Any]:
    """Una fila del historial. Usa lo que reportó el firmware y, si falta, lo recalculado en Python."""
    calc = [rc for rc in (ph.recalcular_run(r, cal) for r in m.runs) if rc is not None]
    res = ph.resumir(calc, cal)
    rep = m.reportado
    c = rep.c_uf if rep else (res.c_uf if res else None)
    inc = rep.inc_pct if rep else (res.inc_pct if res else None)
    mes = rep.meseta_pct if rep else (res.meseta_pct if res else None)
    fila: dict[str, Any] = {
        "medicion": m.id,
        "hora": m.inicio.strftime("%H:%M:%S"),
        "origen": m.origen,
        "firmware": m.firmware or "",
        "n_pruebas": len(m.runs),
        "rango": cal.etiqueta(m.rango),
        "C_uF": None if c is None else round(c, 4),
        "delta_uF": None if c is None or inc is None else round(c * inc / 100, 4),
        "incert_pct": None if inc is None else round(inc, 2),
        "tau_ms": round(rep.tau_ms if rep else res.tau_ms, 3) if (rep or res) else None,
        "meseta_pct": None if mes is None else round(mes, 1),
        "fuga": "" if mes is None else ph.nivel_fuga(mes),
        "Q_uC": round(rep.q_uc if rep else res.q_uc, 3) if (rep or res) else None,
        "E_uJ": round(rep.e_uj if rep else res.e_uj, 3) if (rep or res) else None,
        "R_ohm": round(rep.r_ohm if rep else res.r_ohm, 1) if (rep or res) else None,
        "error": m.error or "",
    }
    return fila


def filas_pruebas(m: Measurement) -> list[dict[str, Any]]:
    return [{
        "medicion": m.id, "prueba": r.i, "rango": r.rango if r.rango is not None else "",
        "t1_us": round(r.t1_us, 1) if r.t1_us is not None else "",
        "t2_us": round(r.t2_us, 1) if r.t2_us is not None else "",
        "meseta": r.meseta, "tau_ms": r.tau_ms, "c_uf": r.c_uf, "ext": int(r.ext),
        "n_muestras": len(r.samples), "t_reconstruidos": int(r.t_reconstruidos),
    } for r in m.runs]


def a_csv(filas: list[dict[str, Any]], columnas: list[str]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columnas, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    w.writerows(filas)
    return buf.getvalue()


class Storage:
    def __init__(self, carpeta: Path, nombre: str | None = None) -> None:
        self.carpeta = Path(carpeta)
        self.base = nombre or datetime.now().strftime("sesion_%Y%m%d_%H%M%S")
        self._lock = threading.Lock()
        self._t0 = time.monotonic()
        self._serial = None

    @property
    def ruta_serial(self) -> Path:
        return self.carpeta / f"{self.base}_serial.log"

    @property
    def ruta_mediciones(self) -> Path:
        return self.carpeta / f"{self.base}_mediciones.csv"

    @property
    def ruta_pruebas(self) -> Path:
        return self.carpeta / f"{self.base}_pruebas.csv"

    def log_linea(self, linea: str) -> None:
        with self._lock:
            try:
                if self._serial is None:
                    self.carpeta.mkdir(parents=True, exist_ok=True)
                    self._serial = open(self.ruta_serial, "a", encoding="utf-8")  # noqa: SIM115
                self._serial.write(f"{time.monotonic() - self._t0:.3f}\t{linea}\n")
                self._serial.flush()
            except OSError as e:
                log.warning("No pude escribir el log serial: %s", e)

    def _anexar(self, ruta: Path, filas: list[dict[str, Any]], columnas: list[str]) -> None:
        nuevo = not ruta.exists()
        with open(ruta, "a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=columnas, extrasaction="ignore", lineterminator="\n")
            if nuevo:
                w.writeheader()
            w.writerows(filas)

    def guardar_medicion(self, m: Measurement, cal: Calibracion) -> None:
        with self._lock:
            try:
                self.carpeta.mkdir(parents=True, exist_ok=True)
                self._anexar(self.ruta_mediciones, [fila_medicion(m, cal)], COLUMNAS_MEDICION)
                if m.runs:
                    self._anexar(self.ruta_pruebas, filas_pruebas(m), COLUMNAS_PRUEBA)
            except OSError as e:
                log.warning("No pude guardar la medición %d: %s", m.id, e)

    def cerrar(self) -> None:
        with self._lock:
            if self._serial is not None:
                self._serial.close()
                self._serial = None


def exportar_historial(mediciones: list[Measurement], cal: Calibracion) -> str:
    return a_csv([fila_medicion(m, cal) for m in mediciones], COLUMNAS_MEDICION)


def exportar_pruebas(mediciones: list[Measurement]) -> str:
    filas = [f for m in mediciones for f in filas_pruebas(m)]
    return a_csv(filas, COLUMNAS_PRUEBA)
