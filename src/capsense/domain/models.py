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
    r_descarga: float = 560.0      # ohm: resistencia de descarga (D3 -> nodo)
    adc_cero: int = 5              # el firmware considera descargado el capacitor con ADC <= 5

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
class Pines:
    """Pines del Arduino en el montaje (iguales a los del firmware). Única fuente de estos nombres."""

    carga: tuple[str, ...] = ("D2", "A5")     # uno por rango: 10k, 1M
    descarga: str = "D3"
    lectura: str = "A0"
    led_verde: str = "D4"
    led_amarillo: str = "D5"
    led_rojo: str = "D6"
    boton_atras: str = "A1"
    boton_start: str = "A2"
    boton_siguiente: str = "A3"
    lcd_rs: str = "D12"
    lcd_e: str = "D11"
    lcd_datos: tuple[str, ...] = ("D10", "D9", "D8", "D7")   # DB4..DB7

    def todos(self) -> list[str]:
        return [*self.carga, self.descarga, self.lectura, self.led_verde, self.led_amarillo, self.led_rojo,
                self.boton_atras, self.boton_start, self.boton_siguiente, self.lcd_rs, self.lcd_e, *self.lcd_datos]


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
