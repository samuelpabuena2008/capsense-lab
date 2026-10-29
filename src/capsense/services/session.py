"""Estado de la sesión: fuente activa, estado del equipo, mediciones e historial.

Las fuentes llaman a la sesión desde su hilo; la interfaz lee con snapshot() desde el suyo.
Todo pasa por un único lock. `version` sube con cada cambio, así la UI solo redibuja cuando hace falta.
"""
from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

from capsense.domain import physics as ph
from capsense.domain.models import Calibracion, DeviceState, Measurement, Run
from capsense.io import protocol as pr
from capsense.io.base import DataSource, EstadoFuente
from capsense.services.storage import Storage

log = logging.getLogger(__name__)


@dataclass
class Vista:
    """Copia de solo lectura del estado, para la interfaz."""

    version: int
    estado: DeviceState
    mensaje: str
    fuente: str
    modo: str
    acepta_comandos: bool
    firmware: str | None
    aviso_config: str
    mediciones: list[Measurement]
    lineas: list[str] = field(default_factory=list)

    @property
    def ultima(self) -> Measurement | None:
        return self.mediciones[-1] if self.mediciones else None


class Session:
    def __init__(self, cal: Calibracion | None = None, storage: Storage | None = None) -> None:
        self.cal = cal or Calibracion()
        self.storage = storage
        self._lock = threading.RLock()
        self.version = 0
        self.estado = DeviceState.DESCONECTADO
        self.mensaje = ""
        self.fuente: DataSource | None = None
        self.modo = ""
        self.firmware: str | None = None
        self.aviso_config = ""
        self.mediciones: list[Measurement] = []
        self._actual: Measurement | None = None
        self._parser = pr.ProtocolParser(self.cal)
        self._lineas: deque[str] = deque(maxlen=300)

    # ---------- fuentes ----------
    def usar_fuente(self, fuente: DataSource, modo: str) -> None:
        self.desconectar()
        with self._lock:
            self.fuente = fuente
            self.modo = modo
            self._parser = pr.ProtocolParser(self.cal)
            self._actual = None
            self.firmware = None
            self.aviso_config = ""
            self.estado = DeviceState.DESCONECTADO
            self.mensaje = "Conectando…"
            self._cambio()
        fuente.conectar_callbacks(self.recibir_linea, self._al_estado_fuente)
        fuente.start()

    def desconectar(self) -> None:
        with self._lock:
            fuente = self.fuente
            self.fuente = None
        if fuente is not None:
            fuente.conectar_callbacks(lambda _l: None, lambda _e: None)
            fuente.stop()
        with self._lock:
            if self._actual is not None and not self._actual.completa:
                self._cerrar_actual(error="Medición interrumpida (desconectado)")
            self.estado = DeviceState.DESCONECTADO
            self.mensaje = ""
            self.modo = ""
            self._cambio()

    def medir(self) -> tuple[bool, str]:
        with self._lock:
            f = self.fuente
            if f is None:
                return False, "No hay ninguna fuente conectada"
            if not f.acepta_comandos:
                return False, "Esta fuente no acepta comandos (replay)"
            if self.estado in (DeviceState.MIDIENDO, DeviceState.DESCARGANDO):
                return False, "Ya hay una medición en curso"
            if self.firmware and self.firmware.startswith("2.1"):
                return False, "El firmware v2.1 no acepta el comando M: usa el botón START"
        ok = f.send("M")
        return ok, "" if ok else "No se pudo enviar el comando"

    def _al_estado_fuente(self, e: EstadoFuente) -> None:
        with self._lock:
            if e.conectada:
                if self.estado == DeviceState.DESCONECTADO:
                    self.estado = DeviceState.CONECTADO
            else:
                if self._actual is not None and not self._actual.completa:
                    self._cerrar_actual(error="Medición interrumpida (se perdió la conexión)")
                self.estado = DeviceState.DESCONECTADO
            self.mensaje = e.mensaje
            self._cambio()

    # ---------- líneas y eventos ----------
    def recibir_linea(self, linea: str) -> None:
        if self.storage is not None:
            self.storage.log_linea(linea)
        with self._lock:
            self._lineas.append(linea)
            for ev in self._parser.feed(linea + "\n"):
                self._aplicar(ev)
            self._cambio()

    def _nueva_medicion(self, n_max: int | None = None) -> Measurement:
        if self._actual is not None and not self._actual.completa:
            self._cerrar_actual(error="Medición incompleta (llegó otra)")
        m = Measurement(
            id=len(self.mediciones) + 1, inicio=datetime.now(),
            origen=self.fuente.nombre if self.fuente else "", firmware=self.firmware, n_max=n_max,
        )
        self.mediciones.append(m)
        self._actual = m
        return m

    def _cerrar_actual(self, error: str | None = None) -> None:
        m = self._actual
        if m is None:
            return
        m.completa = True
        if error and not m.error:
            m.error = error
        if self.storage is not None and (m.runs or m.error):
            self.storage.guardar_medicion(m, self.cal)
        self._actual = None

    def _aplicar(self, ev: pr.Evento) -> None:  # noqa: C901 - una rama por evento
        if isinstance(ev, pr.Version):
            self.firmware = ev.version
            if self.estado in (DeviceState.CONECTADO, DeviceState.DESCONECTADO):
                self.estado = DeviceState.LISTO
        elif isinstance(ev, pr.ConfigFirmware):
            self.aviso_config = self._comparar_config(ev)
        elif isinstance(ev, pr.Listo):
            if self.estado not in (DeviceState.ERROR, DeviceState.MIDIENDO, DeviceState.DESCARGANDO):
                self.estado = DeviceState.LISTO
        elif isinstance(ev, pr.Inicio):
            self._nueva_medicion(ev.n_max)
            self.estado = DeviceState.DESCARGANDO
            self.mensaje = ""
        elif isinstance(ev, pr.PruebaIni):
            if self._actual is None:
                self._nueva_medicion()
            self.estado = DeviceState.MIDIENDO
        elif isinstance(ev, pr.Prueba):
            m = self._actual or self._nueva_medicion()
            self._preparar_run(ev.run)
            m.runs.append(ev.run)
            self.estado = DeviceState.DESCARGANDO if self._parser.modo_maquina else DeviceState.MIDIENDO
        elif isinstance(ev, pr.Resultado):
            m = self._actual or self._nueva_medicion()
            m.reportado = ev.resultado
            self._cerrar_actual()
            self.estado = DeviceState.LISTO
        elif isinstance(ev, pr.ErrorFirmware):
            if self._actual is not None:
                self._actual.error = ev.mensaje
                self._cerrar_actual()
            self.estado = DeviceState.ERROR
            self.mensaje = ev.mensaje
        elif isinstance(ev, pr.Fin) and self._actual is not None:
            self._cerrar_actual()
            self.estado = DeviceState.LISTO

    def _preparar_run(self, run: Run) -> None:
        """Deja t1/t2 listos (reconstruidos si el firmware es v2.1), bajo el lock."""
        if run.t1_us is None or run.t2_us is None:
            ph.recalcular_run(run, self.cal)

    def _comparar_config(self, ev: pr.ConfigFirmware) -> str:
        c = self.cal
        dif = []
        if abs(ev.v_entrada - c.v_entrada) > 0.005:
            dif.append(f"V_ENTRADA {ev.v_entrada} ≠ {c.v_entrada}")
        for i, r in enumerate(ev.r_real[: len(c.rangos)]):
            if abs(r - c.rangos[i].r_ohm) > 0.5:
                dif.append(f"R_{c.rangos[i].etiqueta} {r:.0f} ≠ {c.rangos[i].r_ohm:.0f}")
        if abs(ev.r_pin - c.r_pin) > 0.05:
            dif.append(f"R_PIN {ev.r_pin} ≠ {c.r_pin}")
        if abs(ev.k_cal - c.k_cal) > 1e-4:
            dif.append(f"K_CAL {ev.k_cal} ≠ {c.k_cal}")
        if dif:
            msg = "El firmware usa otra calibración que config/capsense.toml: " + "; ".join(dif)
            log.warning(msg)
            return msg
        return ""

    def _cambio(self) -> None:
        self.version += 1

    # ---------- lectura para la UI ----------
    def snapshot(self, con_lineas: bool = False) -> Vista:
        with self._lock:
            f = self.fuente
            return Vista(
                version=self.version, estado=self.estado, mensaje=self.mensaje,
                fuente=f.nombre if f else "", modo=self.modo,
                acepta_comandos=bool(f and f.acepta_comandos), firmware=self.firmware,
                aviso_config=self.aviso_config,
                mediciones=[_copia(m) for m in self.mediciones],
                lineas=list(self._lineas) if con_lineas else [],
            )

    def limpiar_historial(self) -> None:
        with self._lock:
            self.mediciones = [m for m in self.mediciones if m is self._actual]
            for i, m in enumerate(self.mediciones, 1):
                m.id = i
            self._cambio()


def _copia(m: Measurement) -> Measurement:
    """Copia superficial: las Run no se modifican después de agregarse."""
    return Measurement(m.id, m.inicio, m.origen, m.firmware, m.n_max, list(m.runs), m.reportado,
                       m.error, m.completa)
