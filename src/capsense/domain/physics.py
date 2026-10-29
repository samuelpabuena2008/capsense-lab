"""Matemática del CapSense Lab: réplica de la del firmware (capsense_lab_v2_x.ino).

Modelo de carga:  V(t) = P · (1 − e^(−t/τ))   (V y P en cuentas del ADC)
De los cruces t1 (ADC = N1) y t2 (ADC = N2) se despejan P y τ.

El Arduino calcula en float de 32 bits y aquí se usa float de 64, así que puede haber
diferencias del orden de 0.001 %. Por eso las comparaciones usan TOLERANCIA_PCT.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from capsense.domain.models import Calibracion, Run

CAL = Calibracion()
ITERACIONES = 30
TOLERANCIA_PCT = 0.1     # diferencia máxima para decir "coincide con el firmware"
FRACCION_TAU = 1.0 - math.exp(-1.0)   # 0.632...


def razon_p(P: float, n1: float, n2: float) -> float:
    """t2/t1 que tendría una curva con meseta P. Baja cuando P sube."""
    return math.log(1.0 - n2 / P) / math.log(1.0 - n1 / P)


@dataclass
class PasoBiseccion:
    iteracion: int
    lo: float
    hi: float
    mid: float
    razon_mid: float


@dataclass
class Ajuste:
    t1: float
    t2: float
    r: float                 # t2 / t1
    P: float                 # meseta en cuentas ADC
    tau: float               # misma unidad que t1 y t2
    tau1: float
    tau2: float
    saturacion: str = ""     # "" | "alta" (P = adc_max) | "baja" (P = n2 + 2)
    pasos: list[PasoBiseccion] = field(default_factory=list)


def ajustar_curva(t1: float, t2: float, cal: Calibracion = CAL) -> Ajuste:
    """Igual que ajustarCurva() del firmware: bisección de 30 iteraciones sobre P."""
    if t1 <= 0 or t2 <= t1:
        raise ValueError(f"Se necesita 0 < t1 < t2 (llegó t1={t1}, t2={t2})")
    n1, n2 = cal.adc_n1, cal.adc_n2
    r = t2 / t1
    lo, hi = n2 + 2.0, cal.adc_max
    pasos: list[PasoBiseccion] = []
    if r <= razon_p(hi, n1, n2):
        P, sat = hi, "alta"          # sin fuga: la meseta llega al máximo del ADC
    elif r >= razon_p(lo, n1, n2):
        P, sat = lo, "baja"
    else:
        for i in range(ITERACIONES):
            mid = 0.5 * (lo + hi)
            rm = razon_p(mid, n1, n2)
            pasos.append(PasoBiseccion(i + 1, lo, hi, mid, rm))
            if rm > r:
                lo = mid
            else:
                hi = mid
        P, sat = 0.5 * (lo + hi), ""
    tau1 = t1 / (-math.log(1.0 - n1 / P))
    tau2 = t2 / (-math.log(1.0 - n2 / P))
    return Ajuste(t1, t2, r, P, 0.5 * (tau1 + tau2), tau1, tau2, sat, pasos)


def reconstruir_t1_t2(tau: float, P: float, cal: Calibracion = CAL) -> tuple[float, float]:
    """Inverso del ajuste: desde (τ, P) recupera t1 y t2 (misma unidad que τ).

    Es exacto cuando la bisección convergió, porque entonces τ1 = τ2.
    Si P saturó (1023 o 702) es solo una aproximación. Sirve para la v2.1, que no manda t1 ni t2.
    """
    P = min(max(P, cal.adc_n2 + 2.0), cal.adc_max)
    return tau * -math.log(1.0 - cal.adc_n1 / P), tau * -math.log(1.0 - cal.adc_n2 / P)


def capacitancia_uf(tau_s: float, r_ohm: float, k_cal: float = 1.0) -> float:
    """C en µF desde τ en segundos y la R total (incluida la del pin)."""
    return tau_s / r_ohm * 1e6 * k_cal


def carga_energia(c_uf: float, v: float) -> tuple[float, float]:
    """Q en µC y E en µJ (µF·V = µC; µF·V²/2 = µJ)."""
    return c_uf * v, 0.5 * c_uf * v * v


def incertidumbre_semirango(cs: Sequence[float]) -> tuple[float, float]:
    """(ΔC, %) con ΔC = (Cmax − Cmin)/2 y % = ΔC / C̄ · 100. Es lo que usa el firmware."""
    prom = sum(cs) / len(cs)
    delta = (max(cs) - min(cs)) / 2.0
    return delta, delta / prom * 100.0


def n_pruebas_por_tau(tau_s: float) -> int:
    """Tras la primera prueba el firmware decide cuántas hace."""
    return 5 if tau_s < 1.0 else (3 if tau_s < 4.0 else 2)


def nivel_fuga(meseta_pct: float) -> str:
    """Mismos cortes que la pantalla de meseta del LCD."""
    if meseta_pct > 98.0:
        return "baja"
    if meseta_pct > 93.0:
        return "media"
    return "alta"


def adc_a_volt(adc: float, cal: Calibracion = CAL) -> float:
    return adc * cal.v_entrada / cal.adc_max


def curva_adc(t: float, tau: float, P: float) -> float:
    return P * (1.0 - math.exp(-t / tau))


def diferencia_pct(python: float, firmware: float) -> float:
    if firmware == 0:
        return 0.0 if python == 0 else math.inf
    return (python - firmware) / abs(firmware) * 100.0


# ---------------- recálculo completo ----------------
@dataclass
class RunCalculado:
    run: Run
    ajuste: Ajuste
    r_ohm: float
    c_uf: float
    tau_s: float


def recalcular_run(run: Run, cal: Calibracion = CAL) -> RunCalculado | None:
    """Rehace en Python lo que hizo el Arduino con una prueba, desde t1 y t2."""
    if run.t1_us is None or run.t2_us is None:
        if run.meseta <= 0 or run.tau_ms <= 0:
            return None
        t1, t2 = reconstruir_t1_t2(run.tau_ms * 1000.0, run.meseta, cal)
        run.t1_us, run.t2_us, run.t_reconstruidos = t1, t2, True
    try:
        aj = ajustar_curva(run.t1_us, run.t2_us, cal)
    except ValueError:
        return None
    rango = run.rango if run.rango is not None else 0
    r = cal.r_total(rango)
    tau_s = aj.tau / 1e6
    return RunCalculado(run, aj, r, capacitancia_uf(tau_s, r, cal.k_cal), tau_s)


@dataclass
class Resumen:
    n: int
    c_uf: float
    c_min: float
    c_max: float
    delta_uf: float
    inc_pct: float
    tau_ms: float
    meseta_pct: float
    q_uc: float
    e_uj: float
    r_ohm: float


def resumir(calculados: Sequence[RunCalculado], cal: Calibracion = CAL) -> Resumen | None:
    """Mismo bloque final de medir() en el firmware, con los valores recalculados."""
    if not calculados:
        return None
    cs = [c.c_uf for c in calculados]
    n = len(cs)
    c_prom = sum(cs) / n
    delta, inc = incertidumbre_semirango(cs)
    q, e = carga_energia(c_prom, cal.v_entrada)
    return Resumen(
        n=n, c_uf=c_prom, c_min=min(cs), c_max=max(cs), delta_uf=delta, inc_pct=inc,
        tau_ms=sum(c.tau_s for c in calculados) / n * 1000.0,
        meseta_pct=sum(c.ajuste.P for c in calculados) / n / cal.adc_max * 100.0,
        q_uc=q, e_uj=e, r_ohm=calculados[-1].r_ohm,
    )


def formato_c(c_uf: float) -> tuple[str, str]:
    """(número, unidad) con unidad automática, con los mismos decimales del LCD."""
    if c_uf >= 1000.0:
        return f"{c_uf / 1000.0:.3f}", "mF"
    if c_uf >= 10.0:
        return f"{c_uf:.2f}", "µF"
    if c_uf >= 1.0:
        return f"{c_uf:.3f}", "µF"
    return f"{c_uf * 1000.0:.1f}", "nF"


def formato_delta(delta_uf: float, c_uf: float) -> str:
    """± en la misma unidad que formato_c(c_uf), con los mismos decimales."""
    num, unidad = formato_c(c_uf)
    escala = {"mF": 1e-3, "µF": 1.0, "nF": 1e3}[unidad]
    dec = len(num.split(".")[1]) if "." in num else 0
    return f"{delta_uf * escala:.{dec}f}"


def formato_tau(tau_ms: float) -> str:
    return f"{tau_ms:.1f} ms" if tau_ms < 1000.0 else f"{tau_ms / 1000.0:.3f} s"


def formato_r(r_ohm: float) -> str:
    if r_ohm >= 1e6:
        return f"{r_ohm / 1e6:.4g} MΩ"
    if r_ohm >= 1e3:
        return f"{r_ohm / 1e3:.4g} kΩ"
    return f"{r_ohm:.4g} Ω"
