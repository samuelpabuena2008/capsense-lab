"""Modo demo: un Arduino con firmware v2.2 simulado en Python.

`FirmwareSim` reproduce medir() del firmware v2.2 paso a paso y genera exactamente las mismas
líneas de texto (protocolo '#' + bloque legible), con su instante de salida. Así el dashboard no
distingue la demo de un Arduino real.

Física simulada:
  * Carga V(t) = P·(1 − e^(−t/τ)), con τ = (R + R_pin)·C y P < 1023 según la fuga elegida.
    Es el mismo modelo que asume el firmware: una fuga real también acortaría τ (ver docs/calculos.md).
  * Bucle de medición: cada vuelta lee micros() (resolución de 4 µs) y luego hace analogRead()
    (~112 µs; el ADC toma la muestra ~12 µs después de empezar). Jitter de ±4 µs por vuelta.
  * Ruido gaussiano en el ADC y cuantización por truncamiento a enteros 0..1023.
  * Descarga por 560 Ω hasta ADC ≤ 5, más 100 ms de espera, igual que el firmware.
"""
from __future__ import annotations

import logging
import math
import queue
import random
import threading
from collections.abc import Iterator
from dataclasses import dataclass, replace

from capsense.domain import physics as ph
from capsense.domain.models import Calibracion
from capsense.io.base import DataSource

log = logging.getLogger(__name__)

VERSION_SIM = "2.2"

# Constantes del firmware v2.2
T1_MIN_AUTO_US = 3000
T1_MAX_US = 2_500_000
TIMEOUT_CARGA_US = 25_000_000
C_MIN_UF = 0.5
N_MAX = 5
N_MUESTRAS = 100
T_MUESTRA0_US = 500.0
RAZON_MUESTRA = 1.1147
ADC_EXT_FIN = 1015
EXT_MAX_US = 8_000_000
ADC_CERO = 5
R_DESCARGA = 560.0
BAUD = 115200

# Tiempos del bucle de medición del Uno
PERIODO_US = 116.0
RETARDO_MUESTREO_US = 12.0
RETARDO_INICIO_US = 4.0

RES_OK, RES_NO_DESCARGA, RES_RAPIDO, RES_LENTO, RES_NO_LLEGA = 0, 1, 2, 3, 4
TEXTO_ERROR = {RES_NO_DESCARGA: "No descarga", RES_RAPIDO: "Sin capacitor",
               RES_LENTO: "Muy grande", RES_NO_LLEGA: "Fuga muy alta"}


@dataclass(frozen=True)
class ParamsSim:
    c_uf: float = 100.0
    meseta_pct: float = 97.0     # P = 1023 · meseta / 100
    ruido_lsb: float = 0.7       # desviación del ruido del ADC
    jitter_us: float = 4.0
    velocidad: float = 1.0       # solo afecta el ritmo de salida, no los números
    auto: bool = False           # repetir la medición sola
    seed: int | None = None


@dataclass
class _Carga:
    res: int
    t1: int = 0
    t2: int = 0
    muestras: list[tuple[int, int]] | None = None
    t_fin_us: float = 0.0
    adc_fin: int = 0
    ext: bool = False


def _f(x: float, dec: int) -> str:
    """Como Serial.print(float, dec)."""
    return f"{x:.{dec}f}"


class FirmwareSim:
    def __init__(self, params: ParamsSim, cal: Calibracion | None = None) -> None:
        self.p = params
        self.cal = cal or Calibracion()
        self.rng = random.Random(params.seed)
        self._adc_actual = 0       # voltaje del capacitor al terminar la última carga

    # ---------- textos fijos ----------
    def lineas_config(self) -> list[str]:
        c = self.cal
        rs = ",".join(_f(r.r_ohm, 0) for r in c.rangos[:2])
        return [f"#VERSION,{VERSION_SIM}",
                f"#CONFIG,{_f(c.v_entrada, 2)},{rs},{_f(c.r_pin, 1)},{_f(c.k_cal, 3)},"
                f"{_f(c.adc_n1, 0)},{_f(c.adc_n2, 0)}"]

    def arranque(self) -> list[tuple[float, str]]:
        lineas = self.lineas_config() + [
            f"=== CapSense Lab v{VERSION_SIM} ===",
            "Rango: 1 uF a 1000 uF. Pulsa START o envia M para medir.",
            "#LISTO",
        ]
        return [(1.2 if i == 0 else 0.0, linea) for i, linea in enumerate(lineas)]

    # ---------- física de una carga ----------
    def _bucle(self, tau_us: float, P: float) -> Iterator[tuple[int, int]]:
        """Vueltas del while de medición: (dt de micros(), lectura del ADC)."""
        t = RETARDO_INICIO_US + 1.0
        j, sigma = self.p.jitter_us, self.p.ruido_lsb
        rng = self.rng
        while True:
            dt = int(t // 4) * 4
            ts = t + RETARDO_MUESTREO_US - RETARDO_INICIO_US
            v = P * (1.0 - math.exp(-ts / tau_us)) if ts > 0 else 0.0
            if sigma > 0:
                v += rng.gauss(0.0, sigma)
            # El AVR trunca: código = floor(Vin·1024/Vref)
            adc = min(1023, max(0, int(math.floor(v * 1024.0 / 1023.0))))
            yield dt, adc
            t += PERIODO_US + (rng.uniform(-j, j) if j > 0 else 0.0)

    def _cargar(self, rango: int, extender: bool) -> _Carga:
        c = self.cal
        tau_us = max(c.r_total(rango) * max(self.p.c_uf, 0.0), 1e-3)   # Ω·µF = µs
        P = c.adc_max * self.p.meseta_pct / 100.0
        n1, n2 = c.adc_n1, c.adc_n2
        t1 = t2 = 0
        muestras: list[tuple[int, int]] = []
        t_obj = int(T_MUESTRA0_US)
        extendiendo = False
        for dt, adc in self._bucle(tau_us, P):
            if len(muestras) < N_MUESTRAS and dt >= t_obj:
                muestras.append((dt, adc))
                t_obj = int(t_obj * RAZON_MUESTRA)   # unsigned long en el Arduino
            if extendiendo:
                if adc >= ADC_EXT_FIN or dt - t2 > EXT_MAX_US or len(muestras) >= N_MUESTRAS \
                        or dt > TIMEOUT_CARGA_US:
                    return _Carga(RES_OK, t1, t2, muestras, dt, adc, ext=True)
                continue
            if t1 == 0 and adc >= n1:
                t1 = dt
                if t1 < T1_MIN_AUTO_US:
                    return _Carga(RES_RAPIDO, t_fin_us=dt, adc_fin=adc)
                if rango > 0 and t1 > T1_MAX_US:
                    return _Carga(RES_LENTO, t_fin_us=dt, adc_fin=adc)
            if adc >= n2:
                t2 = dt
                if extender:
                    extendiendo = True
                    continue
                break
            if dt > TIMEOUT_CARGA_US:
                return _Carga(RES_LENTO if t1 == 0 else RES_NO_LLEGA, t_fin_us=dt, adc_fin=adc)
        if t2 <= t1:
            return _Carga(RES_RAPIDO, t_fin_us=t2, adc_fin=adc)
        return _Carga(RES_OK, t1, t2, muestras, t2, adc)

    def _t_descarga_s(self) -> float:
        adc = self._adc_actual
        t = 0.0
        if adc > ADC_CERO:
            t = (R_DESCARGA + self.cal.r_pin) * max(self.p.c_uf, 0.0) * 1e-6 * math.log(adc / ADC_CERO)
        self._adc_actual = 0
        return min(t, 8.0) + 0.1

    # ---------- medir() ----------
    def medir(self) -> list[tuple[float, str]]:
        """Devuelve [(segundos de espera antes de la línea, línea), ...]."""
        c = self.cal
        out: list[tuple[float, str]] = []
        espera = 0.0

        def emitir(linea: str) -> None:
            nonlocal espera
            out.append((espera + len(linea) * 10 / BAUD, linea))
            espera = 0.0

        rango = 0
        n_pruebas = N_MAX
        cs: list[float] = []
        taus: list[float] = []
        ps: list[float] = []
        emitir(f"#INICIO,{N_MAX}")
        emitir(f"#RANGO,{rango},{c.rangos[rango].etiqueta},{_f(c.r_total(rango), 0)}")
        emitir("prueba,R,meseta,tau_ms,C_uF")
        i = 0
        while i < n_pruebas:
            ultima = i == n_pruebas - 1 and i > 0
            carga = _Carga(RES_OK)
            for _intento in range(len(c.rangos) + 1):
                espera += self._t_descarga_s()
                emitir(f"#PRUEBA_INI,{i + 1},{rango}")
                carga = self._cargar(rango, ultima)
                espera += carga.t_fin_us / 1e6
                self._adc_actual = carga.adc_fin
                if carga.res == RES_RAPIDO and rango < len(c.rangos) - 1:
                    rango += 1
                    emitir(f"#RANGO,{rango},{c.rangos[rango].etiqueta},{_f(c.r_total(rango), 0)}")
                    continue
                if carga.res == RES_LENTO and rango > 0:
                    rango -= 1
                    emitir(f"#RANGO,{rango},{c.rangos[rango].etiqueta},{_f(c.r_total(rango), 0)}")
                    continue
                break
            if carga.res != RES_OK:
                return out + self._error(carga.res, TEXTO_ERROR[carga.res], espera)

            aj = ph.ajustar_curva(float(carga.t1), float(carga.t2), c)
            tau_s = aj.tau / 1e6
            cuf = ph.capacitancia_uf(tau_s, c.r_total(rango), c.k_cal)
            if cuf < C_MIN_UF:
                return out + self._error(5, "Sin capacitor", espera)
            for t, a in carga.muestras or []:
                emitir(f"#MUESTRA,{t},{a}")
            emitir(f"#PRUEBA,{i + 1},{rango},{carga.t1},{carga.t2},{_f(aj.P, 1)},{_f(tau_s * 1000, 3)},"
                   f"{_f(cuf, 3)},{1 if carga.ext else 0}")
            emitir(f"{i + 1},{c.rangos[rango].etiqueta},{_f(aj.P, 1)},{_f(tau_s * 1000, 3)},{_f(cuf, 3)}")
            cs.append(cuf)
            taus.append(tau_s)
            ps.append(aj.P)
            if i == 0:
                n_pruebas = ph.n_pruebas_por_tau(tau_s)
            i += 1

        n = len(cs)
        c_prom = sum(cs) / n
        tau_ms = sum(taus) / n * 1000.0
        meseta = sum(ps) / n / c.adc_max * 100.0
        _d, inc = ph.incertidumbre_semirango(cs)
        q, e = ph.carga_energia(c_prom, c.v_entrada)
        r = c.r_total(rango)
        emitir(f"#RESULTADO,{n},{_f(r, 1)},{_f(c.v_entrada, 2)},{_f(tau_ms, 3)},{_f(c_prom, 3)},{_f(inc, 2)},"
               f"{_f(min(cs), 3)},{_f(max(cs), 3)},{_f(q, 3)},{_f(e, 3)},{_f(meseta, 1)}")
        for linea in [
            "---------- RESULTADO ----------",
            f"Pruebas   = {n}",
            f"R carga   = {_f(r, 1)} ohm",
            f"V entrada = {_f(c.v_entrada, 2)} V",
            f"tau       = {_f(tau_ms, 3)} ms",
            f"C         = {_f(c_prom, 3)} uF  (+/- {_f(inc, 2)} %)",
            f"C min/max = {_f(min(cs), 3)} / {_f(max(cs), 3)} uF",
            f"Q         = {_f(q, 3)} uC",
            f"E         = {_f(e, 3)} uJ",
            f"Meseta    = {_f(meseta, 1)} %",
            "CSV (tau_ms,C_uF,Q_uC,E_uJ,incert_pct,meseta_pct,R_ohm):",
            f"{_f(tau_ms, 3)},{_f(c_prom, 3)},{_f(q, 3)},{_f(e, 3)},{_f(inc, 2)},{_f(meseta, 1)},{_f(r, 0)}",
        ]:
            emitir(linea)
        emitir("#FIN")
        emitir("#LISTO")
        return out

    def _error(self, codigo: int, msg: str, espera: float) -> list[tuple[float, str]]:
        return [(espera, f"#ERROR,{codigo},{msg}"), (0.0, f"ERROR: {msg}"), (0.0, "#LISTO")]


class SimulatorSource(DataSource):
    """Fuente de datos del modo demo. Acepta los comandos M (medir) y V (versión)."""

    nombre = "Demo"
    acepta_comandos = True

    def __init__(self, params: ParamsSim | None = None, cal: Calibracion | None = None) -> None:
        super().__init__()
        self.cal = cal or Calibracion()
        self._params = params or ParamsSim()
        self._lock = threading.Lock()
        self._comandos: queue.Queue[str] = queue.Queue()

    @property
    def params(self) -> ParamsSim:
        with self._lock:
            return self._params

    def set_params(self, **cambios: object) -> None:
        with self._lock:
            self._params = replace(self._params, **cambios)  # type: ignore[arg-type]

    def send(self, comando: str) -> bool:
        self._comandos.put(comando.strip().upper()[:1])
        return True

    def _dormir(self, s: float) -> bool:
        """Espera s segundos (ajustado a la velocidad). Devuelve False si hay que parar."""
        if s <= 0:
            return not self._parar.is_set()
        return not self._parar.wait(s / max(self.params.velocidad, 0.01))

    def _reproducir(self, lineas: list[tuple[float, str]]) -> bool:
        acumulado = 0.0
        for espera, linea in lineas:
            acumulado += espera
            if acumulado >= 0.02:
                if not self._dormir(acumulado):
                    return False
                acumulado = 0.0
            self._emitir(linea)
        return True

    def _correr(self) -> None:
        sim = FirmwareSim(self.params, self.cal)
        self._estado(True, "Simulador")
        if not self._reproducir(sim.arranque()):
            return
        while not self._parar.is_set():
            try:
                cmd = self._comandos.get(timeout=0.2)
            except queue.Empty:
                continue
            p = self.params
            sim.p = p
            if cmd == "V":
                self._reproducir([(0.0, linea) for linea in sim.lineas_config()] + [(0.0, "#LISTO")])
            elif cmd == "M":
                log.info("Demo: midiendo C=%.3f µF, meseta=%.1f %%", p.c_uf, p.meseta_pct)
                if not self._reproducir(sim.medir()):
                    return
                if self.params.auto and self._dormir(3.0 * self.params.velocidad):
                    self._comandos.put("M")
        self._estado(False, "Demo detenida")
