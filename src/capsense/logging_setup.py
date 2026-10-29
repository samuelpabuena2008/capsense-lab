"""Logging estándar: consola + archivo rotativo en logs/capsense.log."""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

FORMATO = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def configurar(carpeta_logs: Path | None = None, debug: bool = False) -> None:
    nivel = logging.DEBUG if debug else logging.INFO
    raiz = logging.getLogger()
    raiz.setLevel(nivel)
    for h in list(raiz.handlers):
        raiz.removeHandler(h)

    if sys.stderr is not None:          # con pythonw no hay consola
        consola = logging.StreamHandler()
        consola.setFormatter(logging.Formatter(FORMATO, "%H:%M:%S"))
        raiz.addHandler(consola)

    if carpeta_logs is not None:
        carpeta_logs.mkdir(parents=True, exist_ok=True)
        archivo = RotatingFileHandler(
            carpeta_logs / "capsense.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        archivo.setFormatter(logging.Formatter(FORMATO))
        raiz.addHandler(archivo)

    # Dash/Flask hablan mucho en INFO
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
