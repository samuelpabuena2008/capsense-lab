from datetime import datetime

import pytest

from capsense.domain import physics as ph
from capsense.domain import steps
from capsense.domain.models import Measurement, ReportedResult, Run


def run_ref(**cambios):
    datos = dict(i=1, rango=0, etiqueta="10k", meseta=993.3, tau_ms=1001.524, c_uf=102.040,
                 t1_us=290360.0, t2_us=1221590.0)
    datos.update(cambios)
    return Run(**datos)


def test_pasos_prueba_coinciden_con_firmware(cal):
    rc = ph.recalcular_run(run_ref(), cal)
    pasos = steps.pasos_prueba(rc, cal)
    titulos = [p.titulo for p in pasos]
    assert titulos[0].startswith("Tiempos medidos") and titulos[-1] == "Capacitancia"
    chequeos = [c for p in pasos for c in p.chequeos]
    assert {c.nombre for c in chequeos} == {"P", "τ", "C"}
    assert all(c.coincide for c in chequeos)


def test_numeros_sustituidos_en_latex(cal):
    rc = ph.recalcular_run(run_ref(), cal)
    texto = "\n".join(p.markdown for p in steps.pasos_prueba(rc, cal))
    for numero in ("290.360", "1221.590", "4.20716", "993.344", "1001.524", "9790", "102.040"):
        assert numero in texto, numero


def test_detecta_diferencia_con_firmware(cal):
    rc = ph.recalcular_run(run_ref(c_uf=103.5), cal)        # el "Arduino" reportó otra C
    chequeo = steps.pasos_prueba(rc, cal)[-1].chequeos[0]
    assert not chequeo.coincide
    assert chequeo.diferencia_pct == pytest.approx((102.040 / 103.5 - 1) * 100, abs=0.01)


def test_saturacion_se_explica(cal):
    t1, t2 = ph.reconstruir_t1_t2(500_000.0, cal.adc_max, cal)
    rc = ph.recalcular_run(run_ref(t1_us=t1, t2_us=t2 * 0.999, meseta=1023.0), cal)
    paso_p = steps.pasos_prueba(rc, cal)[2]
    assert "no hay fuga apreciable" in paso_p.markdown


def test_nota_v21_reconstruidos(cal):
    rc = ph.recalcular_run(run_ref(t1_us=None, t2_us=None), cal)
    assert "v2.1" in steps.pasos_prueba(rc, cal)[0].nota


def test_pasos_resumen(cal):
    runs = [run_ref(i=1), run_ref(i=2, t1_us=290360.0 * 1.01, t2_us=1221590.0 * 1.01, tau_ms=1011.539,
                                  c_uf=103.060)]
    calc = [ph.recalcular_run(r, cal) for r in runs]
    res = ph.resumir(calc, cal)
    m = Measurement(1, datetime.now(), runs=runs, completa=True, reportado=ReportedResult(
        tau_ms=res.tau_ms, c_uf=round(res.c_uf, 3), q_uc=round(res.q_uc, 3), e_uj=round(res.e_uj, 3),
        inc_pct=round(res.inc_pct, 2), meseta_pct=97.1, r_ohm=9815.0))
    pasos = steps.pasos_resumen(m, calc, cal)
    assert [p.titulo for p in pasos][1] == "Incertidumbre (semi-rango)"
    assert "desviación estándar" in pasos[1].markdown
    assert all(c.coincide for p in pasos for c in p.chequeos)
