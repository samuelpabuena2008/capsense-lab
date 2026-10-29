"""Arduino real por puerto serie: pyserial en un hilo, autodetección y reconexión.

* Sin puerto fijo, busca uno que parezca Arduino (VID conocidos o "Arduino", "CH340", "USB" en la
  descripción). En Windows son COMx; en Linux /dev/ttyACM* o /dev/ttyUSB*; en macOS /dev/cu.*.
* Si se suelta el cable, cierra el puerto y reintenta con espera creciente (1, 2, 4, 8 s, tope 8 s).
* El Uno se reinicia al abrir el puerto: espera 2 s y manda "V" para que el firmware se identifique.
"""
from __future__ import annotations

import contextlib
import logging
import threading
from dataclasses import dataclass

from capsense.io.base import DataSource

try:
    import serial
    from serial.tools import list_ports
except ImportError:  # pragma: no cover
    serial = None
    list_ports = None

log = logging.getLogger(__name__)

# VID USB de placas Arduino y adaptadores comunes (Arduino, CH340, FTDI, CP210x)
VIDS_ARDUINO = {0x2341, 0x2A03, 0x1A86, 0x0403, 0x10C4}
PALABRAS = ("arduino", "ch340", "ch341", "usb-serial", "usb serial", "ftdi", "cp210")
ESPERA_RESET_S = 2.0
BACKOFF_MAX_S = 8.0


@dataclass
class PuertoInfo:
    dispositivo: str
    descripcion: str
    probable_arduino: bool


def listar_puertos() -> list[PuertoInfo]:
    """Puertos disponibles, primero los que parecen Arduino."""
    if list_ports is None:
        return []
    puertos = []
    for p in list_ports.comports():
        desc = f"{p.description or ''} {p.manufacturer or ''}".strip()
        probable = (p.vid in VIDS_ARDUINO) or any(w in desc.lower() for w in PALABRAS)
        puertos.append(PuertoInfo(p.device, desc or p.device, probable))
    puertos.sort(key=lambda x: (not x.probable_arduino, x.dispositivo))
    return puertos


def autodetectar() -> str | None:
    puertos = listar_puertos()
    probables = [p for p in puertos if p.probable_arduino]
    if probables:
        return probables[0].dispositivo
    return puertos[0].dispositivo if len(puertos) == 1 else None


class SerialSource(DataSource):
    acepta_comandos = True

    def __init__(self, puerto: str | None = None, baud: int = 115200) -> None:
        super().__init__()
        self.puerto_fijo = puerto or None
        self.baud = baud
        self.puerto_actual: str | None = None
        self._ser: serial.Serial | None = None
        self._lock_tx = threading.Lock()
        self.nombre = f"Arduino {puerto or '(auto)'}"

    def send(self, comando: str) -> bool:
        with self._lock_tx:
            if self._ser is None or not self._ser.is_open:
                return False
            try:
                self._ser.write((comando.strip() + "\n").encode("ascii"))
                self._ser.flush()
                log.info("TX %s -> %s", comando.strip(), self.puerto_actual)
                return True
            except (serial.SerialException, OSError) as e:
                log.warning("No pude enviar %r: %s", comando, e)
                return False

    def _abrir(self) -> bool:
        puerto = self.puerto_fijo or autodetectar()
        if puerto is None:
            self._estado(False, "No encuentro ningún Arduino. Revisa el cable USB.")
            return False
        try:
            ser = serial.Serial(puerto, self.baud, timeout=0.2)
        except (serial.SerialException, OSError, ValueError) as e:
            msg = str(e)
            if "PermissionError" in msg or "Acceso denegado" in msg or "Access is denied" in msg:
                msg = f"{puerto} está ocupado (¿Monitor Serie del IDE abierto?)"
            self._estado(False, f"No pude abrir {puerto}: {msg}")
            return False
        with self._lock_tx:
            self._ser = ser
        self.puerto_actual = puerto
        self.nombre = f"Arduino {puerto}"
        log.info("Conectado a %s a %d baud", puerto, self.baud)
        self._estado(True, f"{puerto} · {self.baud} baud")
        return True

    def _cerrar(self) -> None:
        with self._lock_tx:
            if self._ser is not None:
                with contextlib.suppress(serial.SerialException, OSError):
                    self._ser.close()
            self._ser = None

    def _correr(self) -> None:
        if serial is None:
            self._estado(False, "Falta pyserial: pip install pyserial")
            return
        espera = 1.0
        while not self._parar.is_set():
            if not self._abrir():
                if self._parar.wait(espera):
                    break
                espera = min(espera * 2, BACKOFF_MAX_S)
                continue
            espera = 1.0
            self._leer_hasta_desconexion()
            self._cerrar()
            if not self._parar.is_set():
                self._estado(False, "Se perdió la conexión. Reintentando…")
        self._cerrar()
        self._estado(False, "Desconectado")

    def _leer_hasta_desconexion(self) -> None:
        assert self._ser is not None
        if self._parar.wait(ESPERA_RESET_S):
            return
        self.send("V")
        pendiente = b""
        while not self._parar.is_set():
            try:
                datos = self._ser.read(self._ser.in_waiting or 1)
            except (serial.SerialException, OSError) as e:
                log.warning("Error leyendo %s: %s", self.puerto_actual, e)
                return
            if not datos:
                continue
            pendiente += datos
            while b"\n" in pendiente:
                linea, pendiente = pendiente.split(b"\n", 1)
                self._emitir(linea.decode("utf-8", errors="replace").rstrip("\r"))
            if len(pendiente) > 4096:
                pendiente = b""
