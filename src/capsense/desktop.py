"""Ventana de escritorio: la app corre en su propia ventana (pywebview + WebView2), sin navegador.

El servidor Dash queda escuchando solo en 127.0.0.1, en un puerto libre, dentro de un hilo.
Al cerrar la ventana se apaga el servidor y se sueltan el puerto serie y los logs.
"""
from __future__ import annotations

import logging
import socket
import threading
from collections.abc import Callable

from werkzeug.serving import BaseWSGIServer, make_server

log = logging.getLogger(__name__)

TITULO = "CapSense Lab"
FONDO = "#07090D"


def puerto_libre(host: str = "127.0.0.1", preferido: int = 8050) -> int:
    for puerto in (preferido, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, puerto))
                return s.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("No hay puertos libres")


def iniciar_servidor(wsgi_app, host: str, puerto: int) -> BaseWSGIServer:
    servidor = make_server(host, puerto, wsgi_app, threaded=True)
    hilo = threading.Thread(target=servidor.serve_forever, name="servidor-dash", daemon=True)
    hilo.start()
    log.info("Servidor interno en http://%s:%d", host, puerto)
    return servidor


class ApiVentana:
    """Funciones que la página puede llamar con window.pywebview.api.<nombre>()."""

    def __init__(self) -> None:
        self.ventana = None

    def pantalla_completa(self) -> None:
        if self.ventana is not None:
            self.ventana.toggle_fullscreen()


def abrir_ventana(url: str, al_cerrar: Callable[[], None], debug: bool = False) -> bool:
    """Abre la ventana y bloquea hasta que se cierre. Devuelve False si pywebview no está disponible."""
    try:
        import webview
    except ImportError:
        log.warning("Falta pywebview (pip install pywebview)")
        return False
    webview.settings["ALLOW_DOWNLOADS"] = True      # para "Exportar CSV"
    api = ApiVentana()
    ventana = webview.create_window(
        TITULO, url, js_api=api, width=1440, height=900, min_size=(1100, 700),
        background_color=FONDO, text_select=True,
    )
    api.ventana = ventana
    ventana.events.closed += al_cerrar
    try:
        webview.start(debug=debug, private_mode=False)
    except Exception:  # noqa: BLE001 - p. ej. sin WebView2: se cae al navegador
        log.exception("No se pudo abrir la ventana nativa")
        return False
    return True
