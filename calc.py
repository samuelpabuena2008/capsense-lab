"""Matemática del CapSense Lab: réplica del firmware (capsense_lab_v2_x.ino).

Modelo de carga:  V(t) = P · (1 − e^(−t/τ))   (V y P en cuentas del ADC)
De los cruces t1 (ADC = N1) y t2 (ADC = N2) se despejan P y τ.
"""
import math
from dataclasses import dataclass, field

import config

N1, N2, ADC_MAX = config.ADC_N1, config.ADC_N2, config.ADC_MAX
P_MIN = N2 + 2.0          # límite inferior de la bisección (igual que el firmware)
ITERACIONES = 30


def razon_p(P, n1=N1, n2=N2):
    """t2/t1 que tendría una curva con meseta P. Baja cuando P sube."""
    return math.log(1.0 - n2 / P) / math.log(1.0 - n1 / P)


@dataclass
class Ajuste:
    t1: float
    t2: float
    r: float                 # t2 / t1
    P: float                 # meseta en cuentas ADC
    tau: float               # misma unidad que t1 y t2
    tau1: float
    tau2: float
    saturacion: str = ""     # "" | "alta" (P = 1023) | "baja" (P = 702)
    pasos: list = field(default_factory=list)   # (iteración, lo, hi, mid, razon(mid))


def ajustar_curva(t1, t2, n1=N1, n2=N2, adc_max=ADC_MAX):
    """Igual que ajustarCurva() del firmware: bisección de 30 iteraciones sobre P."""
    r = t2 / t1
    lo, hi = n2 + 2.0, adc_max
    pasos = []
    if r <= razon_p(hi, n1, n2):
        P, sat = hi, "alta"          # sin fuga: la meseta llega al máximo del ADC
    elif r >= razon_p(lo, n1, n2):
        P, sat = lo, "baja"
    else:
        for i in range(ITERACIONES):
            mid = 0.5 * (lo + hi)
            rm = razon_p(mid, n1, n2)
            pasos.append((i + 1, lo, hi, mid, rm))
            if rm > r:
                lo = mid
            else:
                hi = mid
        P, sat = 0.5 * (lo + hi), ""
    tau1 = t1 / (-math.log(1.0 - n1 / P))
    tau2 = t2 / (-math.log(1.0 - n2 / P))
    return Ajuste(t1, t2, r, P, 0.5 * (tau1 + tau2), tau1, tau2, sat, pasos)


def reconstruir_t1_t2(tau, P, n1=N1, n2=N2):
    """Inverso del ajuste: desde (τ, P) recupera t1 y t2 (misma unidad que τ).

    Es exacto cuando la bisección convergió (τ1 = τ2). Si P saturó (1023 o 702) no lo es.
    Sirve para la v2.1, que solo manda τ y P.
    """
    return tau * -math.log(1.0 - n1 / P), tau * -math.log(1.0 - n2 / P)


def r_total(rango):
    return config.R_REAL[rango] + config.R_PIN


def capacitancia(tau_s, R_ohm, k_cal=None):
    """C en µF desde τ en segundos y la R total (con la del pin)."""
    k = config.K_CAL if k_cal is None else k_cal
    return tau_s / R_ohm * 1e6 * k


def carga_energia(c_uf, v=None):
    """Q en µC y E en µJ (µF·V = µC, µF·V²/2 = µJ)."""
    v = config.V_ENTRADA if v is None else v
    return c_uf * v, 0.5 * c_uf * v * v


def incertidumbre(cs):
    """Semi-rango en %: (cMax − cMin) / 2 / cProm · 100 (igual que el firmware)."""
    prom = sum(cs) / len(cs)
    return (max(cs) - min(cs)) / 2.0 / prom * 100.0


def n_pruebas_por_tau(tau_s):
    """Tras la primera prueba el firmware decide cuántas hace."""
    return 5 if tau_s < 1.0 else (3 if tau_s < 4.0 else 2)


def nivel_fuga(meseta_pct):
    if meseta_pct > 98.0:
        return "baja"
    if meseta_pct > 93.0:
        return "media"
    return "alta"


@dataclass
class Resumen:
    n: int
    c_uf: float
    c_min: float
    c_max: float
    inc_pct: float
    tau_ms: float
    meseta_pct: float
    q_uc: float
    e_uj: float
    r_ohm: float


def resumir(cs_uf, taus_s, mesetas, R_ohm, v=None):
    """Mismo bloque final de medir() en el firmware."""
    n = len(cs_uf)
    c_prom = sum(cs_uf) / n
    q, e = carga_energia(c_prom, v)
    return Resumen(
        n=n, c_uf=c_prom, c_min=min(cs_uf), c_max=max(cs_uf),
        inc_pct=incertidumbre(cs_uf),
        tau_ms=sum(taus_s) / n * 1000.0,
        meseta_pct=sum(mesetas) / n / ADC_MAX * 100.0,
        q_uc=q, e_uj=e, r_ohm=R_ohm,
    )


def formato_c(c_uf, dec=None):
    """Devuelve (texto del número, unidad) con unidad automática."""
    if c_uf >= 1000.0:
        return f"{c_uf / 1000.0:.{3 if dec is None else dec}f}", "mF"
    if c_uf >= 10.0:
        return f"{c_uf:.{2 if dec is None else dec}f}", "µF"
    if c_uf >= 1.0:
        return f"{c_uf:.{3 if dec is None else dec}f}", "µF"
    return f"{c_uf * 1000.0:.{1 if dec is None else dec}f}", "nF"


def curva(t, tau, P):
    return P * (1.0 - math.exp(-t / tau))
