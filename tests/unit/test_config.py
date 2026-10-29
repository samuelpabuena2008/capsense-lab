import pytest

from capsense import config


def test_defaults_sin_archivo():
    cfg = config.desde_dict({})
    assert cfg.calibracion.v_entrada == 4.92
    assert cfg.calibracion.r_total(0) == 9815.0
    assert cfg.serial.baud == 115200


def test_archivo_del_repo_coincide_con_firmware():
    cfg = config.cargar(config.RUTA_POR_DEFECTO)
    c = cfg.calibracion
    assert (c.v_entrada, c.r_pin, c.k_cal, c.adc_n1, c.adc_n2) == (4.92, 25.0, 1.0, 250, 700)
    assert [r.r_ohm for r in c.rangos] == [9790.0, 996000.0]
    assert [r.etiqueta for r in c.rangos] == ["10k", "1M"]


def test_override_parcial(tmp_path):
    p = tmp_path / "config" / "capsense.toml"
    p.parent.mkdir()
    p.write_text('[medicion]\nv_entrada = 5.01\n[serial]\npuerto = "COM7"\n', encoding="utf-8")
    cfg = config.cargar(p)
    assert cfg.calibracion.v_entrada == 5.01
    assert cfg.calibracion.r_pin == 25.0
    assert cfg.serial.puerto == "COM7"
    assert cfg.carpeta_logs == tmp_path / "logs"


@pytest.mark.parametrize("toml,mensaje", [
    ("[medicion]\nv_entrada = 'cinco'", "número"),
    ("[medicion]\nv_entrada = 12", "mayor"),
    ("[medicion]\nadc_n1 = 800", "adc_n1"),
    ("[[rangos]]\netiqueta='a'\nr_ohm=2000\n[[rangos]]\netiqueta='b'\nr_ohm=1000", "menor a mayor"),
    ("esto no es toml = = =", "sintaxis"),
])
def test_errores_claros(tmp_path, toml, mensaje):
    p = tmp_path / "c.toml"
    p.write_text(toml, encoding="utf-8")
    with pytest.raises(config.ConfigError, match=mensaje):
        config.cargar(p)


def test_ruta_explicita_inexistente(tmp_path):
    with pytest.raises(config.ConfigError):
        config.cargar(tmp_path / "no.toml")
