"""Simulación física del circuito de medición (sin UI ni serie): carga, descarga y fuga.

Modelo (montaje de docs/referencia/montaje.html):
  * Carga por la resistencia R (10 kΩ o 1 MΩ, más la del pin) desde el pin de carga a V_entrada.
    Con una fuga R_f en paralelo con el capacitor:
        meseta   Vp = Vin · R_f / (R + R_f)
        constante τ' = (R ‖ R_f) · C
        V(t) = Vp + (V0 − Vp) · e^(−t/τ')
  * Descarga por la resistencia de 560 Ω (más la del pin) hacia D3 en LOW:  V(t) = V0 · e^(−t/((R_d ‖ R_f)·C)).
  * ADC simulado = round(V / Vin · 1023), acotado a 0..1023.
  * El bucle del firmware lee el ADC cada ~112 µs: t1 y t2 son el instante de la primera lectura que
    pasa el umbral (como en la v2.1).

`simular_medicion` repite la secuencia de medir() del firmware v2.1: autorango, 5/3/2 pruebas según τ,
promedio e incertidumbre por semi-rango, usando physics.py para el ajuste. Todo es determinista.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from capsense.domain import physics as ph
from capsense.domain.models import Calibracion

PERIODO_LECTURA_US = 112.0       # una vuelta del bucle de medición (analogRead domina)
PAUSA_S = 0.1                    # delay(100) después de descargar
T1_MIN_AUTO_US = 3000.0
T1_MIN_FIJO_US = 1500.0
T1_MAX_US = 2_500_000.0
TIMEOUT_CARGA_S = 25.0
TIMEOUT_DESCARGA_S = 8.0
C_MIN_UF = 0.5
N_MAX = 5

RAPIDO, LENTO, NO_LLEGA, NO_DESCARGA, OK = "rapido", "lento", "no_llega", "no_descarga", "ok"
TEXTO_ERROR = {RAPIDO: "Sin capacitor", LENTO: "Muy grande", NO_LLEGA: "Fuga muy alta", NO_DESCARGA: "No descarga"}


@dataclass(frozen=True)
class Circuito:
    c_uf: float
    v_entrada: float
    r_carga: float               # ohm, incluida la del pin
    r_descarga: float            # ohm, incluida la del pin
    r_fuga: float | None = None  # ohm; None = capacitor ideal

    @property
    def c_f(self) -> float:
        return self.c_uf * 1e-6

    def _paralelo(self, r: float) -> float:
        return r if self.r_fuga is None else r * self.r_fuga / (r + self.r_fuga)

    @property
    def tau_carga(self) -> float:
        return self._paralelo(self.r_carga) * self.c_f

    @property
    def tau_descarga(self) -> float:
        return self._paralelo(self.r_descarga) * self.c_f

    @property
    def v_meseta(self) -> float:
        if self.r_fuga is None:
            return self.v_entrada
        return self.v_entrada * self.r_fuga / (self.r_carga + self.r_fuga)


# ---------------- fórmulas (aceptan números o arreglos de numpy) ----------------
def v_carga(t, circ: Circuito, v0: float = 0.0):
    t = np.asarray(t, dtype=float)
    vp = circ.v_meseta
    return vp + (v0 - vp) * np.exp(-np.maximum(t, 0) / circ.tau_carga)


def i_carga(t, circ: Circuito, v0: float = 0.0):
    """Corriente que sale del pin de carga y cruza la resistencia (A)."""
    return (circ.v_entrada - v_carga(t, circ, v0)) / circ.r_carga


def v_descarga(t, circ: Circuito, v0: float):
    t = np.asarray(t, dtype=float)
    return v0 * np.exp(-np.maximum(t, 0) / circ.tau_descarga)


def i_descarga(t, circ: Circuito, v0: float):
    """Corriente que sale del capacitor hacia D3 por la resistencia de descarga (A)."""
    return v_descarga(t, circ, v0) / circ.r_descarga


def carga_q(v, circ: Circuito):
    """Carga almacenada en µC (µF · V)."""
    return circ.c_uf * np.asarray(v, dtype=float)


def adc(v, v_entrada: float, adc_max: float = 1023.0):
    """Lectura del ADC: round(V / Vin · 1023), acotada a 0..1023."""
    return np.clip(np.round(np.asarray(v, dtype=float) / v_entrada * adc_max), 0, adc_max).astype(int)


def t_carga_hasta(v: float, circ: Circuito, v0: float = 0.0) -> float:
    """Tiempo en que la carga llega a v (inf si la meseta no alcanza)."""
    vp = circ.v_meseta
    if v <= v0:
        return 0.0
    if v >= vp:
        return math.inf
    return -circ.tau_carga * math.log((vp - v) / (vp - v0))


def t_descarga_hasta(v: float, circ: Circuito, v0: float) -> float:
    if v0 <= v:
        return 0.0
    return -circ.tau_descarga * math.log(v / v0)


def _umbral_v(nivel_adc: float, v_entrada: float, adc_max: float) -> float:
    """Voltaje mínimo que el ADC (con redondeo) lee como >= nivel."""
    return (nivel_adc - 0.5) / adc_max * v_entrada


def primera_lectura(t_exacto: float, periodo_s: float, fase_s: float) -> float:
    """Instante de la primera vuelta del bucle (fase + k·periodo) en o después de t_exacto."""
    if not math.isfinite(t_exacto):
        return math.inf
    k = max(0, math.ceil((t_exacto - fase_s) / periodo_s - 1e-12))
    return fase_s + k * periodo_s


# ---------------- una prueba y la medición completa ----------------
@dataclass
class PruebaSim:
    numero: int                  # 1..n (prueba del firmware)
    intento: int                 # 0, 1, 2 (reintentos por autorango)
    rango: int
    circuito: Circuito
    v_inicio: float              # voltaje al empezar a descargar
    t_descarga: float            # s hasta ADC <= 5
    v_inicio_carga: float
    resultado: str = OK
    t1_us: float | None = None
    t2_us: float | None = None
    t_fin_carga: float = 0.0     # s de carga simulados
    ajuste: ph.Ajuste | None = None
    tau_s: float | None = None
    c_uf: float | None = None
    v_fin: float = 0.0


@dataclass
class ResumenSim:
    n: int
    c_uf: float
    inc_pct: float
    delta_uf: float
    tau_ms: float
    meseta_pct: float
    q_uc: float
    e_uj: float
    r_ohm: float


@dataclass
class MedicionSim:
    c_real_uf: float
    modo_rango: str              # "auto", "10k", "1M"
    r_fuga: float | None
    v_entrada: float
    intentos: list[PruebaSim] = field(default_factory=list)
    n_pruebas: int = N_MAX
    error: str | None = None
    resumen: ResumenSim | None = None

    @property
    def validas(self) -> list[PruebaSim]:
        """La prueba aceptada de cada número (la última de sus intentos, si salió bien)."""
        return [p for p in self.intentos if p.resultado == OK and p.c_uf is not None]

    @property
    def cambios_rango(self) -> list[tuple[int, int, str]]:
        """(número de prueba, rango nuevo, motivo) por cada salto del autorango."""
        out = []
        for a, b in zip(self.intentos, self.intentos[1:], strict=False):
            if b.numero == a.numero and b.rango != a.rango:
                out.append((a.numero, b.rango, a.resultado))
        return out


def _simular_prueba(numero: int, intento: int, rango: int, circ: Circuito, v_inicio: float, cal: Calibracion,
                    autorango: bool, fase_s: float, periodo_s: float) -> PruebaSim:
    vin, amax = circ.v_entrada, cal.adc_max
    # 1) descarga hasta ADC <= 5 (se lee cada vuelta), con tope de 8 s
    v_cero = _umbral_v(cal.adc_cero + 1, vin, amax)       # ADC <= 5  <=>  V < umbral de 6
    t_d = primera_lectura(t_descarga_hasta(v_cero, circ, v_inicio), periodo_s, 0.0) if v_inicio > v_cero else 0.0
    p = PruebaSim(numero, intento, rango, circ, v_inicio, t_d, 0.0)
    if t_d > TIMEOUT_DESCARGA_S:
        p.resultado, p.t_descarga = NO_DESCARGA, TIMEOUT_DESCARGA_S
        return p
    # 2) pausa de 100 ms: D3 sigue en LOW, así que sigue descargando
    p.v_inicio_carga = float(v_descarga(t_d + PAUSA_S, circ, v_inicio))
    # 3) carga y cruces
    t_min = (T1_MIN_AUTO_US if autorango else T1_MIN_FIJO_US) / 1e6
    t1 = primera_lectura(t_carga_hasta(_umbral_v(cal.adc_n1, vin, amax), circ, p.v_inicio_carga), periodo_s, fase_s)
    t2 = primera_lectura(t_carga_hasta(_umbral_v(cal.adc_n2, vin, amax), circ, p.v_inicio_carga), periodo_s, fase_s)
    if not math.isfinite(t1) or t1 > TIMEOUT_CARGA_S:
        p.resultado, p.t_fin_carga = LENTO, TIMEOUT_CARGA_S
    elif t1 < t_min:
        p.resultado, p.t_fin_carga, p.t1_us = RAPIDO, t1, t1 * 1e6
    elif autorango and rango > 0 and t1 > T1_MAX_US / 1e6:
        p.resultado, p.t_fin_carga, p.t1_us = LENTO, t1, t1 * 1e6
    elif not math.isfinite(t2) or t2 > TIMEOUT_CARGA_S:
        p.resultado, p.t_fin_carga, p.t1_us = NO_LLEGA, TIMEOUT_CARGA_S, t1 * 1e6
    elif t2 <= t1:
        p.resultado, p.t_fin_carga = RAPIDO, t2
    else:
        p.t1_us, p.t2_us, p.t_fin_carga = t1 * 1e6, t2 * 1e6, t2
        p.ajuste = ph.ajustar_curva(p.t1_us, p.t2_us, cal)
        p.tau_s = p.ajuste.tau / 1e6
        p.c_uf = ph.capacitancia_uf(p.tau_s, cal.r_total(rango), cal.k_cal)
    p.v_fin = float(v_carga(p.t_fin_carga, circ, p.v_inicio_carga))
    return p


def circuito(c_uf: float, rango: int, cal: Calibracion, r_fuga: float | None = None,
             v_entrada: float | None = None) -> Circuito:
    return Circuito(c_uf=c_uf, v_entrada=v_entrada or cal.v_entrada, r_carga=cal.r_total(rango),
                    r_descarga=cal.r_descarga + cal.r_pin, r_fuga=r_fuga)


def simular_medicion(c_uf: float, cal: Calibracion, modo_rango: str = "auto", r_fuga: float | None = None,
                     v_entrada: float | None = None, v_inicial: float | None = None,
                     periodo_us: float = PERIODO_LECTURA_US) -> MedicionSim:
    """Repite medir() del firmware v2.1 con un capacitor ideal (o con fuga)."""
    vin = v_entrada or cal.v_entrada
    autorango = modo_rango == "auto"
    rango = 0 if modo_rango in ("auto", cal.rangos[0].etiqueta) else (cal.indice_de(modo_rango) or 0)
    periodo_s = periodo_us / 1e6
    # Por defecto el capacitor llega con la carga de una prueba anterior (≈ ADC 700)
    v_actual = vin * cal.adc_n2 / cal.adc_max if v_inicial is None else v_inicial
    m = MedicionSim(c_real_uf=c_uf, modo_rango=modo_rango, r_fuga=r_fuga, v_entrada=vin)
    i = 0
    while i < m.n_pruebas:
        # cada prueba arranca el bucle en otra fase respecto a micros(): da la pequeña dispersión real
        fase = (0.37 * (i + 1) % 1.0) * periodo_s
        p = None
        for intento in range(len(cal.rangos) + 1):
            p = _simular_prueba(i + 1, intento, rango, circuito(c_uf, rango, cal, r_fuga, vin), v_actual, cal,
                                autorango, fase, periodo_s)
            m.intentos.append(p)
            v_actual = p.v_fin
            if p.resultado == RAPIDO and autorango and rango < len(cal.rangos) - 1:
                rango += 1
                continue
            if p.resultado == LENTO and autorango and rango > 0:
                rango -= 1
                continue
            break
        assert p is not None
        if p.resultado != OK:
            m.error = TEXTO_ERROR[p.resultado]
            return m
        if p.c_uf is not None and p.c_uf < C_MIN_UF:
            m.error = "Sin capacitor"
            return m
        if i == 0:
            m.n_pruebas = ph.n_pruebas_por_tau(p.tau_s or 0.0)
        i += 1

    validas = m.validas
    cs = [p.c_uf for p in validas if p.c_uf is not None]
    delta, inc = ph.incertidumbre_semirango(cs)
    c_prom = sum(cs) / len(cs)
    q, e = ph.carga_energia(c_prom, vin)
    m.resumen = ResumenSim(
        n=len(cs), c_uf=c_prom, inc_pct=inc, delta_uf=delta,
        tau_ms=sum(p.tau_s or 0 for p in validas) / len(validas) * 1000,
        meseta_pct=sum(p.ajuste.P for p in validas if p.ajuste) / len(validas) / cal.adc_max * 100,
        q_uc=q, e_uj=e, r_ohm=cal.r_total(validas[-1].rango),
    )
    return m


# ---------------- series para animar (las precalcula Python; el navegador solo interpola) ----------------
def serie_prueba(p: PruebaSim, cal: Calibracion, n_descarga: int = 90, n_pausa: int = 12,
                 n_carga: int = 260) -> dict[str, list]:
    """Arreglos de una prueba con t = 0 en el inicio de la carga (descarga y pausa en t < 0).

    fase: 0 = descarga, 1 = pausa, 2 = carga. i en mA (positiva = carga, negativa = descarga).
    """
    c = p.circuito
    t0 = -(p.t_descarga + PAUSA_S)
    ts, vs, is_, fases = [], [], [], []
    if p.t_descarga > 0:
        td = np.linspace(0, p.t_descarga, n_descarga)
        ts += list(t0 + td)
        vs += list(v_descarga(td, c, p.v_inicio))
        is_ += list(-i_descarga(td, c, p.v_inicio) * 1e3)
        fases += [0] * len(td)
    tp = np.linspace(p.t_descarga, p.t_descarga + PAUSA_S, n_pausa)
    ts += list(t0 + tp)
    vs += list(v_descarga(tp, c, p.v_inicio))
    is_ += list(-i_descarga(tp, c, p.v_inicio) * 1e3)
    fases += [1] * len(tp)
    if p.t_fin_carga > 0:
        tc = np.linspace(0, p.t_fin_carga, n_carga)
        ts += list(tc)
        vc = v_carga(tc, c, p.v_inicio_carga)
        vs += list(vc)
        is_ += list((c.v_entrada - vc) / c.r_carga * 1e3)
        fases += [2] * len(tc)
    v_arr = np.array(vs)
    return {
        "t": [round(float(x), 7) for x in ts],
        "v": [round(float(x), 5) for x in v_arr],
        "i": [round(float(x), 6) for x in is_],
        "adc": [int(x) for x in adc(v_arr, c.v_entrada, cal.adc_max)],
        "fase": fases,
    }
