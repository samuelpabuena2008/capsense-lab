"""Física de la simulación del circuito contra fórmulas analíticas y contra physics.py."""
import math

import numpy as np
import pytest

from capsense.domain import physics as ph
from capsense.domain import simulation as sim


@pytest.fixture
def circ(cal):
    return sim.circuito(100.0, 0, cal)


def test_carga_analitica(circ):
    tau = (9790 + 25) * 100e-6
    assert circ.tau_carga == pytest.approx(tau)
    t = np.array([0, tau, 2 * tau, 5 * tau])
    v = sim.v_carga(t, circ)
    assert v == pytest.approx(4.92 * (1 - np.exp(-t / tau)))
    assert sim.v_carga(tau, circ) / 4.92 == pytest.approx(1 - math.exp(-1))     # 63.2 %
    assert sim.i_carga(0, circ) == pytest.approx(4.92 / 9815)
    assert sim.i_carga(50 * tau, circ) == pytest.approx(0, abs=1e-12)            # I ≈ 0 en la meseta


def test_descarga_analitica(circ):
    tau_d = (560 + 25) * 100e-6
    assert circ.tau_descarga == pytest.approx(tau_d)
    assert sim.v_descarga(tau_d, circ, 3.0) == pytest.approx(3.0 * math.exp(-1))
    assert sim.i_descarga(0, circ, 3.0) == pytest.approx(3.0 / 585)
    assert sim.carga_q(3.0, circ) == pytest.approx(300.0)                        # µC


def test_meseta_y_tau_con_fuga(cal):
    c = sim.circuito(100.0, 0, cal, r_fuga=200_000)
    r = 9815
    assert c.v_meseta == pytest.approx(4.92 * 200_000 / (r + 200_000))
    assert c.tau_carga == pytest.approx(r * 200_000 / (r + 200_000) * 100e-6)
    assert sim.v_carga(1e3, c) == pytest.approx(c.v_meseta)


def test_adc_acotado():
    lect = sim.adc([-1.0, 0.0, 2.46, 4.92, 9.0], 4.92)
    assert list(lect) == [0, 0, 512, 1023, 1023]


@pytest.mark.parametrize("c_uf", [1.0, 4.7, 47.0, 100.0, 1000.0])
@pytest.mark.parametrize("rango", [0, 1])
def test_physics_recupera_c_de_la_simulacion(cal, c_uf, rango):
    """Cruces exactos de la curva simulada -> ajuste de physics.py -> la misma C (< 1 %)."""
    c = sim.circuito(c_uf, rango, cal)
    vin = c.v_entrada
    t1 = sim.t_carga_hasta(cal.adc_n1 / cal.adc_max * vin, c)
    t2 = sim.t_carga_hasta(cal.adc_n2 / cal.adc_max * vin, c)
    aj = ph.ajustar_curva(t1 * 1e6, t2 * 1e6, cal)
    c_rec = ph.capacitancia_uf(aj.tau / 1e6, cal.r_total(rango), cal.k_cal)
    assert abs(c_rec / c_uf - 1) < 0.01


def test_physics_recupera_tau_y_meseta_con_fuga(cal):
    c = sim.circuito(47.0, 0, cal, r_fuga=300_000)
    vin = c.v_entrada
    t1 = sim.t_carga_hasta(cal.adc_n1 / cal.adc_max * vin, c)
    t2 = sim.t_carga_hasta(cal.adc_n2 / cal.adc_max * vin, c)
    aj = ph.ajustar_curva(t1 * 1e6, t2 * 1e6, cal)
    assert aj.P / cal.adc_max == pytest.approx(c.v_meseta / vin, rel=1e-4)
    assert aj.tau / 1e6 == pytest.approx(c.tau_carga, rel=1e-4)


@pytest.mark.parametrize("c_uf", [1.0, 100.0, 1000.0])
def test_medicion_completa(cal, c_uf):
    m = sim.simular_medicion(c_uf, cal)
    assert m.error is None and m.resumen is not None
    assert m.resumen.n == ph.n_pruebas_por_tau(m.validas[0].tau_s)
    # el firmware v2.1 tiene un sesgo conocido (ver docs/calculos.md): queda bajo 5 %
    assert abs(m.resumen.c_uf / c_uf - 1) < 0.05


def test_autorango_sube_a_1M(cal):
    m = sim.simular_medicion(1.0, cal)
    assert m.cambios_rango == [(1, 1, sim.RAPIDO)]
    assert all(p.rango == 1 for p in m.validas)
    fijo = sim.simular_medicion(1.0, cal, "10k")
    assert all(p.rango == 0 for p in fijo.intentos)


def test_fuga_alta_da_error(cal):
    m = sim.simular_medicion(100.0, cal, r_fuga=10_000)      # meseta ≈ 50 %: nunca llega a 700
    assert m.error == "Fuga muy alta"


def test_residuo_de_descarga_sesga_capacitores_grandes(cal):
    """El firmware corta la descarga en ADC <= 5 y espera 100 ms: con C grande queda voltaje residual."""
    m = sim.simular_medicion(1000.0, cal)
    p = m.validas[0]
    assert sim.adc(p.v_inicio_carga, p.circuito.v_entrada) >= 3
    assert m.resumen.c_uf < 1000.0


def test_serie_para_animar(cal):
    m = sim.simular_medicion(10.0, cal)
    s = sim.serie_prueba(m.validas[1], cal)
    assert len(s["t"]) == len(s["v"]) == len(s["i"]) == len(s["adc"]) == len(s["fase"])
    assert s["t"] == sorted(s["t"]) and s["t"][-1] > 0 > s["t"][0]
    assert set(s["fase"]) == {0, 1, 2}
    assert max(s["adc"]) >= 700 and min(s["adc"]) >= 0
