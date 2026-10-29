"""Crea la app Dash y la conecta con la sesión."""
from __future__ import annotations

import logging
from pathlib import Path

import dash

from capsense.config import RAIZ_PROYECTO, AppConfig
from capsense.io.replay_source import ReplaySource
from capsense.io.serial_source import SerialSource
from capsense.io.simulator_source import ParamsSim, SimulatorSource
from capsense.services.session import Session
from capsense.ui import callbacks
from capsense.ui.layout import crear_layout

log = logging.getLogger(__name__)
ASSETS = Path(__file__).resolve().parent / "assets"


class Controlador:
    """Puente entre la interfaz y la sesión: crea y cambia las fuentes de datos."""

    def __init__(self, session: Session, cfg: AppConfig) -> None:
        self.session = session
        self.cfg = cfg
        self.sim: SimulatorSource | None = None
        self.carpeta_replays = cfg.carpeta_logs / "replays"

    def conectar_demo(self, **params: object) -> None:
        d = self.cfg.demo
        base = ParamsSim(c_uf=d.c_uf, meseta_pct=d.meseta_pct, ruido_lsb=d.ruido_lsb, velocidad=d.velocidad)
        self.sim = SimulatorSource(base, self.session.cal)
        if params:
            self.sim.set_params(**params)
        self.session.usar_fuente(self.sim, "demo")

    def conectar_serial(self, puerto: str | None, baud: int) -> None:
        self.sim = None
        self.session.usar_fuente(SerialSource(puerto, baud), "arduino")

    def conectar_replay(self, ruta: Path, velocidad: float = 4.0) -> None:
        self.sim = None
        self.session.usar_fuente(ReplaySource(ruta, self.session.cal, velocidad), "replay")

    def desconectar(self) -> None:
        self.sim = None
        self.session.desconectar()

    def archivos_replay(self) -> list[Path]:
        carpetas = [self.cfg.carpeta_logs, self.carpeta_replays, RAIZ_PROYECTO / "tests" / "fixtures"]
        archivos: list[Path] = []
        for c in carpetas:
            if c.exists():
                archivos += [p for p in c.iterdir()
                             if p.is_file() and (p.suffix in (".log", ".txt") or p.name.endswith("_pruebas.csv"))
                             and p.name != "capsense.log"]
        return sorted(archivos, key=lambda p: p.stat().st_mtime, reverse=True)


def crear_app(session: Session, cfg: AppConfig, modo_inicial: str = "demo") -> tuple[dash.Dash, Controlador]:
    app = dash.Dash(
        __name__,
        assets_folder=str(ASSETS),
        title="CapSense Lab",
        update_title=None,
        suppress_callback_exceptions=False,
    )
    ctl = Controlador(session, cfg)
    app.layout = crear_layout(cfg, modo_inicial)
    callbacks.registrar(app, ctl)
    return app, ctl
