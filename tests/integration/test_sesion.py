"""Sesión completa sin hardware: simulador, replay y barrido de capacitores."""
import time

import pytest

from capsense.domain import physics as ph
from capsense.domain.models import DeviceState
from capsense.io.replay_source import ReplaySource, csv_a_lineas
from capsense.io.simulator_source import FirmwareSim, ParamsSim, SimulatorSource
from capsense.services import storage
from capsense.services.session import Session


def esperar(cond, timeout=20.0):
    fin = time.monotonic() + timeout
    while time.monotonic() < fin:
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_demo_de_punta_a_punta(tmp_path, cal):
    st = storage.Storage(tmp_path, "s")
    s = Session(cal, st)
    s.usar_fuente(SimulatorSource(ParamsSim(c_uf=47.0, velocidad=1000, seed=5), cal), "demo")
    assert esperar(lambda: s.snapshot().estado == DeviceState.LISTO)
    assert s.snapshot().firmware == "2.3"
    assert s.medir() == (True, "")
    assert esperar(lambda: bool(s.mediciones) and s.mediciones[-1].completa)
    m = s.snapshot().ultima
    assert m.error is None and len(m.runs) == 5 and m.reportado is not None
    assert m.reportado.c_uf == pytest.approx(47.0, rel=0.02)
    # Python y "Arduino" coinciden prueba por prueba
    for run in m.runs:
        rc = ph.recalcular_run(run, cal)
        assert rc.c_uf == pytest.approx(run.c_uf, rel=ph.TOLERANCIA_PCT / 100)
    s.desconectar()
    assert s.snapshot().estado == DeviceState.DESCONECTADO
    st.cerrar()
    assert st.ruta_mediciones.exists() and st.ruta_pruebas.exists()
    assert "#RESULTADO" in st.ruta_serial.read_text(encoding="utf-8")


def test_error_del_firmware_queda_visible(cal):
    s = Session(cal)
    for _e, linea in FirmwareSim(ParamsSim(c_uf=10.0, meseta_pct=66.0, seed=1), cal).medir():
        s.recibir_linea(linea)
    v = s.snapshot()
    assert v.estado == DeviceState.ERROR       # #LISTO posterior no borra el error
    assert v.mensaje == "Fuga muy alta"
    assert v.ultima.error == "Fuga muy alta"


def test_replay_log_v22(fixtures, cal):
    s = Session(cal)
    fuente = ReplaySource(fixtures / "sim_100uF_v22.log", cal, velocidad=1000)
    s.usar_fuente(fuente, "replay")
    assert esperar(lambda: fuente.terminado)
    m = s.snapshot().ultima
    assert m.completa and len(m.runs) == 5 and m.reportado.c_uf == pytest.approx(98.901)
    assert s.medir()[0] is False                # replay no acepta comandos


def test_replay_v21_reconstruye_t1_t2(fixtures, cal):
    s = Session(cal)
    for linea in (fixtures / "referencia_100uF_v21.log").read_text(encoding="utf-8").splitlines():
        s.recibir_linea(linea)
    v = s.snapshot()
    assert v.firmware == "2.1"
    run = v.ultima.runs[0]
    assert run.t_reconstruidos and run.t1_us == pytest.approx(290360, rel=1e-3)
    assert s.medir()[0] is False                # sin fuente


def test_csv_de_pruebas_a_protocolo(tmp_path, cal):
    s = Session(cal, storage.Storage(tmp_path, "a"))
    for _e, linea in FirmwareSim(ParamsSim(c_uf=22.0, seed=3), cal).medir():
        s.recibir_linea(linea)
    s.storage.cerrar()
    lineas = csv_a_lineas(s.storage.ruta_pruebas.read_text(encoding="utf-8"), cal)
    s2 = Session(cal)
    for _e, linea in lineas:
        s2.recibir_linea(linea)
    orig, rep = s.snapshot().ultima.reportado, s2.snapshot().ultima.reportado
    assert rep.c_uf == pytest.approx(orig.c_uf, abs=1e-3)
    assert rep.inc_pct == pytest.approx(orig.inc_pct, abs=0.01)


def tope_error(c_uf: float, meseta: float, ruido: float) -> float:
    """Error máximo esperado del firmware v2.1/v2.2 (medido con el simulador, ver docs/calculos.md).

    * Sin fuga y ruido bajo: < 1 %.
    * Ruido de 0.7 LSB: las curvas lentas (C grande) cruzan los umbrales un poco antes: hasta ~1.6 %.
    * Con fuga y C de 1 a 4.7 µF en 10 kΩ: la latencia de analogRead (~116 µs) sobre un t1 de pocos ms,
      amplificada por el ajuste de P, llega a ~5 %. Interpolar el cruce lo corrige (propuesta v2.3).
    """
    if meseta < 99.5 and 1.05 < c_uf < 4.7:
        return 5.5
    return 1.0 if ruido <= 0.3 else 2.0


@pytest.mark.lento
@pytest.mark.parametrize("firmware", ["2.2", "2.3"])
@pytest.mark.parametrize("c_uf", [1.0, 1.5, 2.2, 4.7, 10.0, 22.0, 47.0, 100.0, 220.0, 470.0, 1000.0])
@pytest.mark.parametrize("meseta", [100.0, 96.0])
def test_barrido_1_a_1000_uF(cal, c_uf, meseta, firmware):
    """Barrido con el simulador (ruido y latencia del Uno). La v2.2 queda dentro de sus límites conocidos;
    la v2.3 (media móvil + cruce interpolado) bajo 1 % en todo el rango."""
    errores = {}
    for ruido in (0.3, 0.7):
        tope = tope_error(c_uf, meseta, ruido) if firmware == "2.2" else 1.0
        s = Session(cal)
        for _e, linea in FirmwareSim(ParamsSim(c_uf=c_uf, meseta_pct=meseta, ruido_lsb=ruido, seed=11,
                                               firmware=firmware), cal).medir():
            s.recibir_linea(linea)
        rep = s.snapshot().ultima.reportado
        assert rep is not None, f"{c_uf} µF no dio resultado"
        errores[ruido] = (rep.c_uf / c_uf - 1) * 100
        assert abs(errores[ruido]) < tope, errores
