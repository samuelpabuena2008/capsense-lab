from capsense.io import protocol as pr
from capsense.io.simulator_source import N_MUESTRAS, FirmwareSim, ParamsSim


def medir(**kw):
    sim = FirmwareSim(ParamsSim(seed=1, **kw))
    lineas = sim.medir()
    return lineas, pr.ProtocolParser().feed("\n".join(linea for _e, linea in lineas) + "\n")


def test_formato_es_el_del_firmware_v22():
    lineas, ev = medir(c_uf=100.0)
    textos = [linea for _e, linea in lineas]
    assert textos[0] == "#INICIO,5"
    assert "prueba,R,meseta,tau_ms,C_uF" in textos            # conserva lo legible
    assert textos[-2:] == ["#FIN", "#LISTO"]
    pruebas = [e.run for e in ev if isinstance(e, pr.Prueba)]
    assert len(pruebas) == 5
    assert [r.ext for r in pruebas] == [False] * 4 + [True]     # solo la última se extiende
    assert all(0 < len(r.samples) <= N_MUESTRAS for r in pruebas)
    assert pruebas[-1].samples[-1].t_us > pruebas[-1].t2_us     # la extendida sigue después de t2


def test_menos_pruebas_si_tau_grande():
    _l, ev = medir(c_uf=220.0)          # τ ≈ 2.2 s -> 3 pruebas
    assert sum(isinstance(e, pr.Prueba) for e in ev) == 3
    _l, ev = medir(c_uf=470.0)          # τ ≈ 4.6 s -> 2 pruebas
    assert sum(isinstance(e, pr.Prueba) for e in ev) == 2


def test_autorango_a_1M_con_capacitor_chico():
    _l, ev = medir(c_uf=1.0)
    rangos = [e.rango for e in ev if isinstance(e, pr.CambioRango)]
    assert rangos == [0, 1]
    assert all(e.run.rango == 1 for e in ev if isinstance(e, pr.Prueba))


def test_errores():
    _l, ev = medir(c_uf=0.0)
    assert isinstance(ev[-2], pr.ErrorFirmware) and ev[-2].mensaje == "Sin capacitor"
    _l, ev = medir(c_uf=10.0, meseta_pct=66.0)
    assert any(isinstance(e, pr.ErrorFirmware) and e.codigo == 4 for e in ev)


def test_muestras_espaciado_geometrico():
    _l, ev = medir(c_uf=1000.0, ruido_lsb=0.0)
    s = next(e.run for e in ev if isinstance(e, pr.Prueba)).samples
    ts = [x.t_us for x in s]
    assert ts == sorted(ts) and ts[0] >= 500
    razones = [b / a for a, b in zip(ts[40:], ts[41:], strict=False)]
    assert all(1.08 < r < 1.15 for r in razones)
    assert ts[-1] > 10_000_000        # cubre más de 10 s


def test_t2_siempre_mayor_que_t1():
    _l, ev = medir(c_uf=47.0)
    assert all(e.run.t2_us > e.run.t1_us for e in ev if isinstance(e, pr.Prueba))
