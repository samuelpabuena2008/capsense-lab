"""Las gráficas se construyen con datos reales del simulador, en los dos temas."""
import pytest

from capsense import config
from capsense.domain import physics as ph
from capsense.io.simulator_source import FirmwareSim, ParamsSim
from capsense.services.session import Session
from capsense.ui import figures, layout
from capsense.ui.temas import TEMAS, paleta


def sesion_con_mediciones(cal, n=2):
    s = Session(cal)
    for k in range(n):
        for _e, linea in FirmwareSim(ParamsSim(c_uf=47.0, seed=k), cal).medir():
            s.recibir_linea(linea)
    return s.snapshot().mediciones


@pytest.mark.parametrize("tema", list(TEMAS))
def test_figuras_en_ambos_temas(cal, tema):
    p = paleta(tema)
    mediciones = sesion_con_mediciones(cal)
    calc = [ph.recalcular_run(r, cal) for r in mediciones[-1].runs]
    una = figures.curva_carga(calc, "5", cal, p=p)
    nombres = [t.type for t in una.data]
    assert "scatter" in nombres and any(getattr(t, "fillgradient", None) for t in una.data)
    todas = figures.curva_carga(calc, "todas", cal, p=p)
    assert todas.layout.showlegend
    assert figures.desviaciones(calc, cal, p).data[0].type == "bar"
    mapa = figures.mapa_repetibilidad(mediciones, cal, p)
    assert len(mapa.data[0].y) == 2


def test_paleta_desconocida_cae_en_ambar():
    assert paleta("rosado").nombre == "ambar"
    assert paleta(None).nombre == "ambar"


def test_sparkline():
    assert figures.sparkline([1.0]) == ""
    uri = figures.sparkline([1.0, 2.0, 1.5, 3.0], paleta("neon"))
    assert uri.startswith("data:image/svg+xml,") and "polyline" in uri


def test_tema_en_config(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text('[ui]\ntema = "neon"\nusuario = "Joel"\n', encoding="utf-8")
    cfg = config.cargar(p)
    assert (cfg.ui.tema, cfg.ui.usuario) == ("neon", "Joel")
    p.write_text('[ui]\ntema = "rosado"\n', encoding="utf-8")
    with pytest.raises(config.ConfigError, match="tema"):
        config.cargar(p)


@pytest.mark.parametrize("hora,esperado", [(8, "Buenos días"), (15, "Buenas tardes"), (22, "Buenas noches")])
def test_saludo(hora, esperado):
    from datetime import datetime
    assert layout.saludo("Samuel", datetime(2026, 10, 29, hora)) == f"{esperado}, Samuel"
