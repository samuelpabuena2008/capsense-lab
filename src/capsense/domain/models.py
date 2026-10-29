"""Modelos del dominio (dataclasses tipadas, sin dependencias de serial ni UI)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class DeviceState(str, Enum):
    DESCONECTADO = "Desconectado"
    CONECTADO = "Conectado"
    DESCARGANDO = "Descargando"
    MIDIENDO = "Midiendo"
    LISTO = "Listo"
    ERROR = "Error"


@dataclass(frozen=True)
class Rango:
    etiqueta: str
    r_ohm: float


@dataclass(frozen=True)
class Calibracion:
    """Constantes físicas del montaje (iguales a las del firmware)."""

    v_entrada: float = 4.92
    r_pin: float = 25.0
    k_cal: float = 1.0
    adc_n1: float = 250.0
    adc_n2: float = 700.0
    adc_max: float = 1023.0
    rangos: tuple[Rango, ...] = (Rango("10k", 9790.0), Rango("1M", 996000.0))

    def r_total(self, rango: int) -> float:
        """R de carga + R del pin, en ohm (la que usa el firmware para C)."""
        return self.rangos[rango].r_ohm + self.r_pin

    def etiqueta(self, rango: int | None) -> str:
        if rango is None or not 0 <= rango < len(self.rangos):
            return "?"
        return self.rangos[rango].etiqueta

    def indice_de(self, etiqueta: str) -> int | None:
        for i, r in enumerate(self.rangos):
            if r.etiqueta == etiqueta:
                return i
        return None


@dataclass(frozen=True)
class Sample:
    t_us: int
    adc: int


@dataclass
class Run:
    """Una prueba (una carga del capacitor), tal como la reportó el firmware."""

    i: int
    rango: int | None
    etiqueta: str
    meseta: float           # P reportada (cuentas ADC)
    tau_ms: float           # τ reportada
    c_uf: float             # C reportada
    t1_us: float | None = None
    t2_us: float | None = None
    ext: bool = False       # la curva siguió después de t2 (última prueba en v2.2)
    samples: list[Sample] = field(default_factory=list)
    t_reconstruidos: bool = False   # True si t1/t2 se dedujeron de (τ, P) (firmware v2.1)


@dataclass
class ReportedResult:
    """Bloque RESULTADO que imprime el firmware."""

    tau_ms: float
    c_uf: float
    q_uc: float
    e_uj: float
    inc_pct: float
    meseta_pct: float
    r_ohm: float
    n: int | None = None
    v: float | None = None
    c_min: float | None = None
    c_max: float | None = None


@dataclass
class Measurement:
    """Una medición completa (varias pruebas + resultado)."""

    id: int
    inicio: datetime
    origen: str = ""                 # "Arduino COM3", "Demo", "Replay archivo.log"
    firmware: str | None = None
    n_max: int | None = None
    runs: list[Run] = field(default_factory=list)
    reportado: ReportedResult | None = None
    error: str | None = None
    completa: bool = False

    @property
    def rango(self) -> int | None:
        return self.runs[-1].rango if self.runs else None
