import pytest

from capsense.io import protocol as pr

V21 = """=== CapSense Lab v2.1 ===
Rango: 1 uF a 1000 uF. Pulsa START para medir.
prueba,R,meseta,tau_ms,C_uF
1,10k,993.3,1001.524,102.040
2,10k,992.8,1000.912,101.978
3,10k,993.9,1002.101,102.099
---------- RESULTADO ----------
Pruebas   = 3
R carga   = 9815.0 ohm
V entrada = 4.92 V
tau       = 1001.512 ms
C         = 102.039 uF  (+/- 0.06 %)
C min/max = 101.978 / 102.099 uF
Q         = 502.032 uC
E         = 1234.999 uJ
Meseta    = 97.1 %
CSV (tau_ms,C_uF,Q_uC,E_uJ,incert_pct,meseta_pct,R_ohm):
1001.512,102.039,502.032,1234.999,0.06,97.1,9815

"""


def tipos(eventos):
    return [type(e).__name__ for e in eventos]


def test_v21_completo():
    p = pr.ProtocolParser()
    ev = p.feed(V21)
    assert tipos(ev) == ["Version", "Inicio", "Prueba", "Prueba", "Prueba", "Resultado"]
    assert p.version == "2.1"
    assert not p.modo_maquina
    prueba = ev[2].run
    assert (prueba.i, prueba.rango, prueba.etiqueta) == (1, 0, "10k")
    assert prueba.t1_us is None and prueba.samples == []
    res = ev[-1].resultado
    assert res.c_uf == 102.039 and res.r_ohm == 9815 and res.n == 3
    assert (res.c_min, res.c_max, res.v) == (101.978, 102.099, 4.92)


def test_v21_rango_1M():
    ev = pr.ProtocolParser().feed("1,1M,1010.2,1012.3,1.016\n")
    assert ev[0].run.rango == 1


def test_v21_error():
    ev = pr.ProtocolParser().feed("prueba,R,meseta,tau_ms,C_uF\nERROR: Sin capacitor\n")
    assert tipos(ev) == ["Inicio", "ErrorFirmware"]
    assert ev[1].mensaje == "Sin capacitor" and ev[1].codigo is None


V22 = """#VERSION,2.2
#CONFIG,4.92,9790,996000,25.0,1.000,250,700
=== CapSense Lab v2.2 ===
#LISTO
#INICIO,5
#RANGO,0,10k,9815
prueba,R,meseta,tau_ms,C_uF
#PRUEBA_INI,1,0
#MUESTRA,500,4
#MUESTRA,1004,12
#PRUEBA,1,0,290360,1221590,993.3,1001.524,102.040,0
1,10k,993.3,1001.524,102.040
#PRUEBA_INI,2,0
#MUESTRA,512,5
#PRUEBA,2,0,290100,1221000,993.1,1001.0,101.987,1
2,10k,993.1,1001.000,101.987
#RESULTADO,2,9815.0,4.92,1001.262,102.014,0.03,101.987,102.040,501.907,1234.692,97.1
---------- RESULTADO ----------
Pruebas   = 2
CSV (tau_ms,C_uF,Q_uC,E_uJ,incert_pct,meseta_pct,R_ohm):
1001.262,102.014,501.907,1234.692,0.03,97.1,9815
#FIN
#LISTO
"""


def test_v22_no_duplica_lo_legible():
    p = pr.ProtocolParser()
    ev = p.feed(V22)
    assert tipos(ev) == ["Version", "ConfigFirmware", "Listo", "Inicio", "CambioRango", "PruebaIni", "Muestra",
                         "Muestra", "Prueba", "PruebaIni", "Muestra", "Prueba", "Resultado", "Fin", "Listo"]
    assert p.modo_maquina and p.version == "2.2"


def test_v22_prueba_con_muestras():
    ev = pr.ProtocolParser().feed(V22)
    pruebas = [e.run for e in ev if isinstance(e, pr.Prueba)]
    assert [len(r.samples) for r in pruebas] == [2, 1]     # las muestras no se mezclan entre pruebas
    assert pruebas[0].t1_us == 290360 and pruebas[0].t2_us == 1221590
    assert pruebas[0].samples[1].t_us == 1004 and pruebas[0].samples[1].adc == 12
    assert pruebas[1].ext is True and pruebas[0].ext is False
    cfg = next(e for e in ev if isinstance(e, pr.ConfigFirmware))
    assert cfg.r_real == [9790, 996000] and cfg.n2 == 700


def test_lineas_partidas_en_cualquier_punto():
    p = pr.ProtocolParser()
    ev = []
    for i in range(0, len(V22), 7):
        ev += p.feed(V22[i:i + 7])
    assert tipos(ev) == tipos(pr.ProtocolParser().feed(V22))


def test_crlf_y_bytes():
    ev = pr.ProtocolParser().feed(V22.replace("\n", "\r\n").encode())
    assert len([e for e in ev if isinstance(e, pr.Prueba)]) == 2


def test_tolera_basura():
    p = pr.ProtocolParser()
    basura = "\x00\xff garbage ####\n#MUESTRA,abc,1\n#MUESTRA,10\n#MUESTRA,10,2000\n#DESCONOCIDO,1\n,,,\n"
    assert p.feed(basura) == []
    ev = p.feed("xx#PRUEBA_INI,1,0\n")       # línea pegada a basura
    assert tipos(ev) == ["PruebaIni"]


def test_truncado_a_mitad_de_prueba():
    corte = V22[: V22.index("#PRUEBA,1")] + "#PRUEBA,1,0,2903"   # se cortó el cable
    p = pr.ProtocolParser()
    ev = p.feed(corte)
    assert not any(isinstance(e, pr.Prueba) for e in ev)
    ev = p.feed("\n#INICIO,5\n")              # la línea rota se descarta y sigue normal
    assert tipos(ev) == ["Inicio"]


def test_v21_truncado_sin_csv():
    texto = V21[: V21.index("CSV (")]
    ev = pr.ProtocolParser().feed(texto)
    assert not any(isinstance(e, pr.Resultado) for e in ev)
    assert len([e for e in ev if isinstance(e, pr.Prueba)]) == 3


@pytest.mark.parametrize("linea,codigo,msg", [("#ERROR,4,Fuga muy alta", 4, "Fuga muy alta"),
                                              ("#ERROR,Sin codigo", None, "Sin codigo"),
                                              ("#ERROR,2,Muy, chico", 2, "Muy,chico")])
def test_v22_error(linea, codigo, msg):
    ev = pr.ProtocolParser().feed(linea + "\n")
    assert ev[0].codigo == codigo and ev[0].mensaje == msg


def test_buffer_sin_saltos_no_crece():
    p = pr.ProtocolParser()
    p.feed("x" * (pr.MAX_BUFFER + 10))
    assert p.feed("\n#LISTO\n") and len(p._buffer) == 0


def test_fixture_v21_simulado(fixtures):
    ev = pr.ProtocolParser().feed((fixtures / "sim_47uF_v21.log").read_text(encoding="utf-8"))
    assert tipos(ev).count("Prueba") == 5
    assert isinstance(ev[-1], pr.Resultado)
