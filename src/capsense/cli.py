"""Punto de entrada:  python -m capsense  [--demo | --replay ARCHIVO | --port COM3] ..."""
from __future__ import annotations

import argparse
import logging
import sys
import threading
import webbrowser
from pathlib import Path

from capsense import __version__
from capsense import config as cfgmod
from capsense.logging_setup import configurar

log = logging.getLogger("capsense")


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="capsense",
        description="Dashboard del CapSense Lab (medidor de capacitancia RC con Arduino Uno).",
    )
    fuente = p.add_mutually_exclusive_group()
    fuente.add_argument("--demo", action="store_true", help="arranca con el simulador (sin Arduino)")
    fuente.add_argument("--replay", metavar="ARCHIVO", type=Path,
                        help="reproduce un log serial (.log/.txt) o un CSV de pruebas")
    fuente.add_argument("--port", metavar="PUERTO",
                        help="conecta al Arduino en ese puerto (COM3, /dev/ttyACM0). 'auto' = autodetectar")
    p.add_argument("--baud", type=int, help="baudios (115200 para v2.2, 9600 para v2.1)")
    p.add_argument("--config", type=Path, help="archivo TOML de configuración (por defecto config/capsense.toml)")
    p.add_argument("--host", help="interfaz HTTP (por defecto 127.0.0.1; 0.0.0.0 para verlo desde otro equipo)")
    p.add_argument("--http-port", type=int, help="puerto HTTP del dashboard (por defecto 8050)")
    vista = p.add_mutually_exclusive_group()
    vista.add_argument("--navegador", action="store_true",
                       help="abrir en el navegador en vez de la ventana de la aplicación")
    vista.add_argument("--servidor", "--no-browser", dest="servidor", action="store_true",
                       help="solo el servidor, sin ventana ni navegador (para verlo desde otro equipo)")
    p.add_argument("--debug", action="store_true", help="logs detallados")
    p.add_argument("--version", action="version", version=f"capsense {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    for flujo in (sys.stdout, sys.stderr):   # µ, τ, Ω en la consola de Windows
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8", errors="replace")
    args = construir_parser().parse_args(argv)

    try:
        cfg = cfgmod.cargar(args.config)
    except cfgmod.ConfigError as e:
        print(f"Error de configuración: {e}", file=sys.stderr)
        return 2
    configurar(cfg.carpeta_logs, args.debug)
    log.info("CapSense Lab %s · configuración: %s", __version__, cfg.origen)

    # Importes pesados (Dash) después de validar argumentos
    from capsense.services.session import Session
    from capsense.services.storage import Storage
    from capsense.ui.app import crear_app

    session = Session(cfg.calibracion, Storage(cfg.carpeta_logs))
    modo = "demo"
    if args.port:
        modo = "arduino"
    elif args.replay:
        modo = "replay"
    app, ctl = crear_app(session, cfg, modo)

    if args.demo:
        ctl.conectar_demo()
    elif args.replay:
        if not args.replay.exists():
            print(f"No existe {args.replay}", file=sys.stderr)
            return 2
        ctl.conectar_replay(args.replay)
    elif args.port:
        ctl.conectar_serial(None if args.port == "auto" else args.port, args.baud or cfg.serial.baud)

    host = args.host or cfg.ui.host
    puerto = args.http_port or cfg.ui.puerto_http

    def cerrar() -> None:
        ctl.desconectar()
        if session.storage is not None:
            session.storage.cerrar()

    if not (args.navegador or args.servidor):
        # Modo aplicación: ventana propia con el servidor en un hilo, solo en 127.0.0.1
        from capsense import desktop

        # Puerto aleatorio: ninguna pestaña vieja del navegador puede colarse en la sesión
        puerto = desktop.puerto_libre("127.0.0.1", args.http_port or 0)
        servidor = desktop.iniciar_servidor(app.server, "127.0.0.1", puerto)
        url = f"http://127.0.0.1:{puerto}"
        try:
            if desktop.abrir_ventana(url, cerrar, debug=args.debug):
                return 0
            log.warning("Sin ventana nativa: abro el dashboard en el navegador")
            webbrowser.open(url)
            threading.Event().wait()          # hasta Ctrl+C
        except KeyboardInterrupt:
            pass
        finally:
            servidor.shutdown()
            cerrar()
        return 0

    url = f"http://{'127.0.0.1' if host in ('0.0.0.0', '') else host}:{puerto}"
    log.info("Dashboard en %s (Ctrl+C para salir)", url)
    if args.navegador:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    try:
        app.run(host=host, port=puerto, debug=False)
    except KeyboardInterrupt:
        pass
    finally:
        cerrar()
    return 0


def main_app() -> int:
    """Entrada sin consola (pythonw): abre la ventana de la aplicación."""
    return main([])
