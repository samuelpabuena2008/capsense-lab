"""Interfaz común de las fuentes de datos (Arduino, demo, replay).

Todas entregan texto línea por línea, igual que el puerto serie, así la sesión no
distingue de dónde vienen los datos. Las fuentes corren en su propio hilo y avisan
por callbacks; nunca tocan la interfaz.
"""
from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class EstadoFuente:
    conectada: bool
    mensaje: str = ""


AlRecibirLinea = Callable[[str], None]
AlCambiarEstado = Callable[[EstadoFuente], None]


class DataSource(ABC):
    nombre: str = "fuente"
    acepta_comandos: bool = False

    def __init__(self) -> None:
        self._al_linea: AlRecibirLinea = lambda _l: None
        self._al_estado: AlCambiarEstado = lambda _e: None
        self._parar = threading.Event()
        self._hilo: threading.Thread | None = None

    def conectar_callbacks(self, al_linea: AlRecibirLinea, al_estado: AlCambiarEstado) -> None:
        self._al_linea = al_linea
        self._al_estado = al_estado

    def start(self) -> None:
        if self._hilo and self._hilo.is_alive():
            return
        self._parar.clear()
        self._hilo = threading.Thread(target=self._correr_seguro, name=self.nombre, daemon=True)
        self._hilo.start()

    def stop(self, espera: float = 2.0) -> None:
        self._parar.set()
        if self._hilo and self._hilo.is_alive() and self._hilo is not threading.current_thread():
            self._hilo.join(espera)

    def send(self, comando: str) -> bool:
        """Envía un comando de una letra ("M", "V"). Devuelve False si la fuente no lo acepta."""
        return False

    @property
    def activa(self) -> bool:
        return bool(self._hilo and self._hilo.is_alive())

    def _correr_seguro(self) -> None:
        try:
            self._correr()
        except Exception:  # noqa: BLE001 - un hilo no debe morir en silencio
            log.exception("La fuente %s falló", self.nombre)
            self._al_estado(EstadoFuente(False, "Falla interna de la fuente (ver logs/capsense.log)"))

    @abstractmethod
    def _correr(self) -> None: ...

    def _emitir(self, linea: str) -> None:
        self._al_linea(linea)

    def _estado(self, conectada: bool, mensaje: str = "") -> None:
        self._al_estado(EstadoFuente(conectada, mensaje))
