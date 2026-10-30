"""Carga y valida config/capsense.toml. Si falta el archivo o una clave, usa los valores por defecto."""
from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from capsense.domain.models import Calibracion, Pines, Rango

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

log = logging.getLogger(__name__)

RAIZ_PROYECTO = Path(__file__).resolve().parents[2]
RUTA_POR_DEFECTO = RAIZ_PROYECTO / "config" / "capsense.toml"


class ConfigError(ValueError):
    pass


@dataclass
class SerialCfg:
    puerto: str = ""
    baud: int = 115200


@dataclass
class UiCfg:
    host: str = "127.0.0.1"
    puerto_http: int = 8050
    usuario: str = "Samuel"
    tema: str = "ambar"


@dataclass
class DemoCfg:
    c_uf: float = 100.0
    meseta_pct: float = 97.0
    ruido_lsb: float = 0.7
    velocidad: float = 1.0
    firmware: str = "2.3"


@dataclass
class AppConfig:
    calibracion: Calibracion = field(default_factory=Calibracion)
    pines: Pines = field(default_factory=Pines)
    serial: SerialCfg = field(default_factory=SerialCfg)
    ui: UiCfg = field(default_factory=UiCfg)
    demo: DemoCfg = field(default_factory=DemoCfg)
    carpeta_logs: Path = RAIZ_PROYECTO / "logs"
    origen: str = "valores por defecto"


def _num(sec: dict[str, Any], clave: str, defecto: float, minimo: float | None = None,
         maximo: float | None = None) -> float:
    valor = sec.get(clave, defecto)
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ConfigError(f"'{clave}' debe ser un número (llegó {valor!r})")
    valor = float(valor)
    if minimo is not None and valor < minimo:
        raise ConfigError(f"'{clave}' = {valor} es menor que {minimo}")
    if maximo is not None and valor > maximo:
        raise ConfigError(f"'{clave}' = {valor} es mayor que {maximo}")
    return valor


def _pines(sec: dict[str, Any], n_rangos: int) -> Pines:
    d = Pines()
    valores: dict[str, Any] = {}
    for campo in ("descarga", "lectura", "led_verde", "led_amarillo", "led_rojo", "boton_atras", "boton_start",
                  "boton_siguiente", "lcd_rs", "lcd_e"):
        valores[campo] = str(sec.get(campo, getattr(d, campo))).upper()
    carga = tuple(str(x).upper() for x in sec.get("carga", d.carga))
    datos = tuple(str(x).upper() for x in sec.get("lcd_datos", d.lcd_datos))
    if len(carga) != n_rangos:
        raise ConfigError(f"[pines] carga debe tener un pin por rango ({n_rangos})")
    if len(datos) != 4:
        raise ConfigError("[pines] lcd_datos debe tener 4 pines (DB4 a DB7)")
    pines = Pines(carga=carga, lcd_datos=datos, **valores)
    todos = pines.todos()
    repetidos = sorted({p for p in todos if todos.count(p) > 1})
    if repetidos:
        raise ConfigError(f"[pines] hay pines repetidos: {', '.join(repetidos)}")
    return pines


def _tema(valor: object) -> str:
    v = str(valor)
    if v not in ("ambar", "neon"):
        raise ConfigError(f"[ui] tema debe ser \"ambar\" o \"neon\" (llegó {valor!r})")
    return v


def _firmware_demo(valor: object) -> str:
    v = str(valor)
    if v not in ("2.2", "2.3"):
        raise ConfigError(f"[demo] firmware debe ser \"2.2\" o \"2.3\" (llegó {valor!r})")
    return v


def desde_dict(datos: dict[str, Any], base: Path = RAIZ_PROYECTO) -> AppConfig:
    d = Calibracion()
    med = datos.get("medicion", {})
    rangos_raw = datos.get("rangos")
    if rangos_raw is None:
        rangos = d.rangos
    else:
        if not isinstance(rangos_raw, list) or not rangos_raw:
            raise ConfigError("[[rangos]] debe tener al menos una resistencia")
        rangos = tuple(
            Rango(str(r.get("etiqueta", f"R{i}")), _num(r, "r_ohm", 0, minimo=1))
            for i, r in enumerate(rangos_raw)
        )
        if any(b.r_ohm <= a.r_ohm for a, b in zip(rangos, rangos[1:], strict=False)):
            raise ConfigError("Los rangos deben ir de menor a mayor resistencia")

    cal = Calibracion(
        v_entrada=_num(med, "v_entrada", d.v_entrada, 1.0, 6.0),
        r_pin=_num(med, "r_pin", d.r_pin, 0.0, 1000.0),
        k_cal=_num(med, "k_cal", d.k_cal, 0.5, 2.0),
        adc_n1=_num(med, "adc_n1", d.adc_n1, 1, 1022),
        adc_n2=_num(med, "adc_n2", d.adc_n2, 1, 1022),
        adc_max=_num(med, "adc_max", d.adc_max, 255, 65535),
        rangos=rangos,
        r_descarga=_num(med, "r_descarga", d.r_descarga, 1.0, 1e5),
    )
    if not cal.adc_n1 < cal.adc_n2 < cal.adc_max - 2:
        raise ConfigError("Debe cumplirse adc_n1 < adc_n2 < adc_max - 2")

    ser = datos.get("serial", {})
    ui = datos.get("ui", {})
    demo = datos.get("demo", {})
    logs = datos.get("logs", {})
    carpeta = Path(str(logs.get("carpeta", "logs")))
    if not carpeta.is_absolute():
        carpeta = base / carpeta

    return AppConfig(
        calibracion=cal,
        pines=_pines(datos.get("pines", {}), len(cal.rangos)),
        serial=SerialCfg(str(ser.get("puerto", "")), int(_num(ser, "baud", 115200, 300))),
        ui=UiCfg(str(ui.get("host", "127.0.0.1")), int(_num(ui, "puerto_http", 8050, 1, 65535)),
                 usuario=str(ui.get("usuario", "Samuel")), tema=_tema(ui.get("tema", "ambar"))),
        demo=DemoCfg(
            c_uf=_num(demo, "c_uf", 100.0, 0.0, 5000.0),
            meseta_pct=_num(demo, "meseta_pct", 97.0, 50.0, 100.0),
            ruido_lsb=_num(demo, "ruido_lsb", 0.7, 0.0, 20.0),
            velocidad=_num(demo, "velocidad", 1.0, 0.1, 100.0),
            firmware=_firmware_demo(demo.get("firmware", "2.3")),
        ),
        carpeta_logs=carpeta,
    )


def cargar(ruta: str | Path | None = None) -> AppConfig:
    """Lee el TOML. Sin ruta, usa config/capsense.toml si existe."""
    explicita = ruta is not None
    p = Path(ruta) if ruta else RUTA_POR_DEFECTO
    if not p.exists():
        if explicita:
            raise ConfigError(f"No existe el archivo de configuración {p}")
        log.warning("No encontré %s; uso los valores por defecto", p)
        return AppConfig()
    try:
        datos = tomllib.loads(p.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{p} tiene un error de sintaxis: {e}") from e
    base = p.parent.parent if p.parent.name == "config" else p.parent
    cfg = desde_dict(datos, base)
    cfg.origen = str(p)
    return cfg
