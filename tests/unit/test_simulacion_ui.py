"""Consistencia de la pestaña Simulación: datos del montaje, pasos, pines y guion."""
import json
import re
from pathlib import Path

import pytest

from capsense import config
from capsense.domain import simulation as sim
from capsense.ui.simulation import board_layout as bl
from capsense.ui.simulation import board_view, circuit_schematic, guion, steps_data

SRC = Path(__file__).resolve().parents[2] / "src" / "capsense" / "ui" / "simulation"
MONTAJE = Path(__file__).resolve().parents[2] / "docs" / "referencia" / "montaje.html"
PIN_RE = re.compile(r"\b(?:D(?:[2-9]|1[0-3])|A[0-5])\b")


@pytest.fixture(scope="module")
def cfg():
    return config.cargar()


def test_hoyos_de_los_pasos_existen_en_el_montaje():
    hoyos = bl.todos_los_hoyos()
    for clave, paso in steps_data.PASOS.items():
        for h in paso["hoyos"]:
            bl.hoyo(h)                              # existe en la placa
            assert h in hoyos, f"{clave}: {h} no está ocupado por ningún componente del montaje"
    for extra in (steps_data.CARGA_10K, steps_data.CARGA_1M):
        assert set(extra["hoyos"]) <= hoyos


def test_resaltar_usa_ids_del_montaje():
    ids = set(bl.POR_ID)
    for clave, paso in steps_data.PASOS.items():
        for r in paso["resaltar"]:
            assert r == "@carga" or r in ids, f"{clave}: {r}"
    assert set(steps_data.CARGA_10K["resaltar"]) | set(steps_data.CARGA_1M["resaltar"]) <= ids


def test_montaje_coincide_con_la_referencia():
    """Cada hoyo del montaje.html aparece en board_layout (y no hay hoyos inventados)."""
    html = MONTAJE.read_text(encoding="utf-8")
    ref = {f"{letra}{fila}" for fila, letra in re.findall(r"\[(\d+), '([a-j])'\]", html)}
    nuestros = {h for c in bl.COMPONENTES if c["k"] not in ("btn", "pot", "lcd") for h in bl.hoyos_de(c)}
    assert nuestros == ref
    assert len(bl.COMPONENTES) == html.count("{ k: '")


def test_pines_salen_de_config_sin_duplicar(cfg):
    """board_layout, steps_data y los SVG no escriben nombres de pines: los toman de config."""
    for nombre in ("board_layout.py", "steps_data.py", "circuit_schematic.py", "board_view.py", "guion.py"):
        texto = (SRC / nombre).read_text(encoding="utf-8")
        cuerpo = re.sub(r'""".*?"""', "", texto, flags=re.S)          # sin docstrings
        cuerpo = re.sub(r'"codigo": \[.*?\]', "", cuerpo, flags=re.S)  # el código del .ino se muestra tal cual
        assert not PIN_RE.findall(cuerpo), f"{nombre} tiene pines escritos a mano: {set(PIN_RE.findall(cuerpo))}"
    p = cfg.pines
    esperados = {p.descarga, p.lectura, *p.carga, p.led_verde, p.led_amarillo, p.led_rojo, p.boton_atras,
                 p.boton_start, p.boton_siguiente, p.lcd_rs, p.lcd_e, *p.lcd_datos}
    svg_placa = board_view.svg(p)
    for pin in esperados:
        assert f">{pin}<" in svg_placa, pin
    assert len(p.todos()) == len(set(p.todos()))


def test_config_rechaza_pines_repetidos(tmp_path):
    f = tmp_path / "c.toml"
    f.write_text('[pines]\ndescarga = "D2"\n', encoding="utf-8")
    with pytest.raises(config.ConfigError, match="repetidos"):
        config.cargar(f)


def test_svgs_tienen_lo_que_anima_el_navegador(cfg):
    for svg in (circuit_schematic.svg(cfg.calibracion, cfg.pines), board_view.svg(cfg.pines)):
        for attr in ('data-flujo="carga0"', 'data-flujo="carga1"', 'data-flujo="descarga"', "data-relleno",
                     'data-lcd="0"', 'data-led="verde"', "data-vc", "data-adc"):
            assert attr in svg, attr
        for pin in (*cfg.pines.carga, cfg.pines.descarga, cfg.pines.lectura):
            assert f'data-pin="{pin}"' in svg


@pytest.mark.parametrize("c_uf,rango,r_fuga,esperado", [
    (100.0, "auto", None, ["listo", "descarga", "pausa", "disparo", "lectura", "t1", "t2", "ajuste", "calculo",
                           "repeticiones", "resultado"]),
    (1.0, "auto", None, ["listo", "descarga", "pausa", "disparo", "lectura", "autorango", "descarga", "pausa",
                         "disparo", "lectura", "t1", "t2", "ajuste", "calculo", "repeticiones", "resultado"]),
    (100.0, "auto", 10_000.0, ["listo", "descarga", "pausa", "disparo", "lectura", "t1", "error"]),
    (1000.0, "auto", 2e6, None),
])
def test_guion(cfg, c_uf, rango, r_fuga, esperado):
    m = sim.simular_medicion(c_uf, cfg.calibracion, rango, r_fuga)
    g = guion.construir(m, cfg.calibracion, cfg.pines)
    ids = [p["id"] for p in g.datos["pasos"]]
    if esperado:
        assert ids == esperado
    json.dumps(g.datos)                                  # va a un dcc.Store
    for p in g.datos["pasos"]:
        s = g.datos["series"][p["serie"]]
        assert 0 <= p["cursor"][0] <= p["cursor"][1] < len(s["t"])
        assert "{" not in p["titulo"] + p["que_pasa"] + p["protoboard"] + "".join(p["lcd"])
        assert all(len(linea) <= 16 for linea in p["lcd"])
        assert set(p["mapa_pines"].values()) <= {"high", "low", "hiz", "adc"}


def test_lcd_como_el_firmware(cfg):
    m = sim.simular_medicion(100.0, cfg.calibracion)
    g = guion.construir(m, cfg.calibracion, cfg.pines)
    pasos = {p["id"]: p for p in g.datos["pasos"]}
    assert pasos["listo"]["lcd"] == ["CapSense Lab", "Pulsa START"]
    assert pasos["descarga"]["lcd"] == ["Midiendo 1/5", "10k"]           # ya en la descarga, como el .ino
    assert pasos["descarga"]["leds"] == {"verde": 0, "amarillo": 1, "rojo": 0}
    assert pasos["pausa"]["mapa_pines"][cfg.pines.descarga] == "low"     # delay(100) con D3 aún en LOW
    assert pasos["resultado"]["lcd"][0].startswith("C=") and pasos["resultado"]["lcd"][1].startswith("+/-")
    assert set(g.formulas) == {"ajuste", "calculo", "resultado"}
    assert all(c.coincide for paso in g.formulas["resultado"] for c in paso.chequeos)
    assert guion.lcd_resultado(1500.0, 0.5, 2) == ("C=1.500 mF", "+/-0.50% n=2")
    assert guion.lcd_resultado(4.7, 1.234, 5) == ("C=4.700 uF", "+/-1.23% n=5")
