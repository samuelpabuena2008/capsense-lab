import math

import pytest

from capsense.domain import physics as ph
from capsense.domain.models import Run

# Valores de referencia de una medición real de 100 µF (t en ms)
T1, T2 = 290.36, 1221.59


def test_referencia_100uF(cal):
    aj = ph.ajustar_curva(T1, T2, cal)
    assert aj.saturacion == ""
    assert pytest.approx(993.344, abs=1e-3) == aj.P
    assert aj.tau == pytest.approx(1001.524, abs=1e-3)
    c = ph.capacitancia_uf(aj.tau / 1000.0, cal.r_total(0), cal.k_cal)
    assert c == pytest.approx(102.040, abs=1e-3)
    assert aj.P / cal.adc_max * 100 == pytest.approx(97.10, abs=0.01)


def test_biseccion_converge_tau1_igual_tau2(cal):
    aj = ph.ajustar_curva(T1, T2, cal)
    assert len(aj.pasos) == ph.ITERACIONES
    assert aj.tau1 == pytest.approx(aj.tau2, rel=1e-6)


def test_saturacion_alta_sin_fuga(cal):
    # r menor o igual que la razón con P = 1023: el firmware fija P = 1023
    r_max = ph.razon_p(cal.adc_max, cal.adc_n1, cal.adc_n2)
    aj = ph.ajustar_curva(100.0, 100.0 * r_max * 0.99, cal)
    assert aj.saturacion == "alta"
    assert cal.adc_max == aj.P
    assert aj.pasos == []


def test_saturacion_baja_fuga_extrema(cal):
    r_min = ph.razon_p(cal.adc_n2 + 2, cal.adc_n1, cal.adc_n2)
    aj = ph.ajustar_curva(100.0, 100.0 * r_min * 1.01, cal)
    assert aj.saturacion == "baja"
    assert cal.adc_n2 + 2 == aj.P


@pytest.mark.parametrize("P", [705.0, 800.0, 950.0, 993.344, 1020.0])
@pytest.mark.parametrize("tau", [10.0, 1001.524, 9800.0])
def test_round_trip_t1_t2(cal, P, tau):
    t1, t2 = ph.reconstruir_t1_t2(tau, P, cal)
    aj = ph.ajustar_curva(t1, t2, cal)
    assert pytest.approx(P, abs=1e-4) == aj.P
    assert aj.tau == pytest.approx(tau, rel=1e-7)


def test_razon_baja_cuando_p_sube(cal):
    rs = [ph.razon_p(p, cal.adc_n1, cal.adc_n2) for p in (710, 800, 900, 1023)]
    assert rs == sorted(rs, reverse=True)


def test_t_invalidos(cal):
    with pytest.raises(ValueError):
        ph.ajustar_curva(100.0, 50.0, cal)
    with pytest.raises(ValueError):
        ph.ajustar_curva(0.0, 50.0, cal)


def test_incertidumbre_es_semirango_no_desviacion():
    cs = [98.0, 99.0, 100.0, 101.0, 102.0]
    delta, pct = ph.incertidumbre_semirango(cs)
    assert delta == pytest.approx(2.0)
    assert pct == pytest.approx(2.0)          # 2/100·100
    # una desviación estándar daría otra cosa
    media = sum(cs) / len(cs)
    std = math.sqrt(sum((c - media) ** 2 for c in cs) / (len(cs) - 1))
    assert pct != pytest.approx(std / media * 100)


def test_carga_energia():
    q, e = ph.carga_energia(100.0, 4.92)
    assert q == pytest.approx(492.0)
    assert e == pytest.approx(0.5 * 100 * 4.92**2)


@pytest.mark.parametrize("tau,n", [(0.5, 5), (0.999, 5), (1.0, 3), (3.9, 3), (4.0, 2), (12.0, 2)])
def test_n_pruebas(tau, n):
    assert ph.n_pruebas_por_tau(tau) == n


@pytest.mark.parametrize("pct,nivel", [(99.0, "baja"), (98.0, "media"), (95.0, "media"), (93.0, "alta"), (80, "alta")])
def test_nivel_fuga(pct, nivel):
    assert ph.nivel_fuga(pct) == nivel


@pytest.mark.parametrize("c,esperado", [(1500.0, ("1.500", "mF")), (102.04, ("102.04", "µF")),
                                        (4.7, ("4.700", "µF")), (0.68, ("680.0", "nF"))])
def test_formato_c(c, esperado):
    assert ph.formato_c(c) == esperado


def test_formato_delta_misma_unidad():
    assert ph.formato_delta(0.5058, 99.71) == "0.51"
    assert ph.formato_delta(2.0, 1500.0) == "0.002"


def test_recalcular_run_v21_reconstruye(cal):
    run = Run(1, 0, "10k", 993.3, 1001.524, 102.040)
    rc = ph.recalcular_run(run, cal)
    assert rc is not None
    assert run.t_reconstruidos
    assert rc.c_uf == pytest.approx(102.040, abs=2e-3)
    assert run.t1_us == pytest.approx(T1 * 1000, rel=1e-3)


def test_resumir(cal):
    runs = [Run(i, 0, "10k", 0, 0, 0, t1_us=T1 * 1000 * f, t2_us=T2 * 1000 * f)
            for i, f in enumerate((0.99, 1.0, 1.01), 1)]
    calc = [ph.recalcular_run(r, cal) for r in runs]
    res = ph.resumir(calc, cal)
    assert res.n == 3
    assert res.c_uf == pytest.approx(102.040, rel=1e-4)
    assert res.inc_pct == pytest.approx(1.0, rel=1e-3)
    assert ph.resumir([], cal) is None
