"""Doble clic para abrir CapSense Lab como aplicación (sin consola ni navegador)."""
import sys
from pathlib import Path

# Funciona aunque el paquete no esté instalado con pip install -e .
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from capsense.cli import main_app  # noqa: E402

sys.exit(main_app())
