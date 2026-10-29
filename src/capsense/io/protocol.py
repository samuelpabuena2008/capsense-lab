"""Parser de las líneas que manda el Arduino -> eventos tipados.

Entiende dos protocolos:
  * v2.1 (legible): el texto del Monitor Serie (tabla por prueba, bloque RESULTADO, línea CSV, "ERROR: ...").
  * v2.2 (máquina): líneas con prefijo '#'. La v2.2 también imprime el bloque legible; en cuanto el
    parser ve una línea '#' válida pasa a modo v2.2 y desde ahí ignora el texto legible (si no, cada
    prueba llegaría dos veces).

Uso:  p = ProtocolParser();  for ev in p.feed(texto): ...
feed() acepta trozos de cualquier tamaño (líneas partidas) y tolera basura: lo que no entiende lo descarta.
El formato está documentado en docs/protocolo_serial.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from capsense.domain.models import Calibracion, ReportedResult, Run, Sample


# ---------------- eventos ----------------
@dataclass
class Version:
    version: str


@dataclass
class ConfigFirmware:
    v_entrada: float
    r_real: list[float]
    r_pin: float
    k_cal: float
    n1: float
    n2: float


@dataclass
class CambioRango:
    rango: int
    etiqueta: str
    r_ohm: float


@dataclass
class Listo:
    pass


@dataclass
class Inicio:
    n_max: int | None = None


@dataclass
class PruebaIni:
    i: int
    rango: int


@dataclass
class Muestra:
    sample: Sample


@dataclass
class Prueba:
    run: Run


@dataclass
class Resultado:
    resultado: ReportedResult


@dataclass
class Fin:
    pass


@dataclass
class ErrorFirmware:
    mensaje: str
    codigo: int | None = None


Evento = (Version | ConfigFirmware | CambioRango | Listo | Inicio | PruebaIni | Muestra | Prueba
          | Resultado | Fin | ErrorFirmware)

MAX_BUFFER = 4096


def _floats(campos: list[str]) -> list[float]:
    return [float(x) for x in campos]


@dataclass
class ProtocolParser:
    cal: Calibracion = field(default_factory=Calibracion)
    version: str | None = None
    modo_maquina: bool = False
    _buffer: str = ""
    _muestras: list[Sample] = field(default_factory=list)
    _bloque: dict | None = None
    _espera_csv: bool = False

    # ---------- entrada ----------
    def feed(self, texto: str | bytes) -> list[Evento]:
        if isinstance(texto, bytes):
            texto = texto.decode("utf-8", errors="replace")
        self._buffer += texto
        eventos: list[Evento] = []
        while "\n" in self._buffer:
            linea, self._buffer = self._buffer.split("\n", 1)
            eventos.extend(self.linea(linea))
        if len(self._buffer) > MAX_BUFFER:      # basura sin saltos de línea
            self._buffer = ""
        return eventos

    def linea(self, linea: str) -> list[Evento]:
        linea = "".join(ch for ch in linea if ch.isprintable()).strip()
        if not linea:
            return []
        if "#" in linea:
            # Si la línea quedó pegada a basura ("x#MUESTRA,..."), se usa desde el último '#'
            return self._maquina(linea[linea.rfind("#"):])
        if self.modo_maquina:
            return []
        return self._legible(linea)

    # ---------- protocolo v2.2 ----------
    def _maquina(self, linea: str) -> list[Evento]:
        partes = linea[1:].split(",")
        cmd, a = partes[0].strip().upper(), [p.strip() for p in partes[1:]]
        try:
            ev = self._evento_maquina(cmd, a)
        except (ValueError, IndexError):
            return []
        if ev is None:
            return []
        self.modo_maquina = True
        return [ev]

    def _evento_maquina(self, cmd: str, a: list[str]) -> Evento | None:
        if cmd == "VERSION":
            self.version = a[0]
            return Version(a[0])
        if cmd == "CONFIG":
            if len(a) < 7:
                return None
            v, r0, r1, rp, k, n1, n2 = _floats(a[:7])
            return ConfigFirmware(v, [r0, r1], rp, k, n1, n2)
        if cmd == "RANGO":
            return CambioRango(int(a[0]), a[1], float(a[2]))
        if cmd == "LISTO":
            return Listo()
        if cmd == "INICIO":
            return Inicio(int(a[0]) if a and a[0] else None)
        if cmd == "PRUEBA_INI":
            self._muestras = []
            return PruebaIni(int(a[0]), int(a[1]))
        if cmd == "MUESTRA":
            if len(a) < 2:
                return None
            s = Sample(int(a[0]), int(a[1]))
            if not 0 <= s.adc <= 1023 or s.t_us < 0:
                return None
            self._muestras.append(s)
            return Muestra(s)
        if cmd == "PRUEBA":
            # #PRUEBA,i,rango,t1_us,t2_us,meseta,tau_ms,C_uF,ext
            if len(a) < 8:
                return None
            rango = int(a[1])
            run = Run(
                i=int(a[0]), rango=rango, etiqueta=self.cal.etiqueta(rango),
                t1_us=float(a[2]), t2_us=float(a[3]), meseta=float(a[4]),
                tau_ms=float(a[5]), c_uf=float(a[6]),
                ext=len(a) > 7 and a[7] == "1",
                samples=self._muestras,
            )
            self._muestras = []
            return Prueba(run)
        if cmd == "RESULTADO":
            # #RESULTADO,n,R_ohm,V,tau_ms,C_uF,inc_pct,cmin,cmax,Q_uC,E_uJ,meseta_pct
            if len(a) < 11:
                return None
            n = int(a[0])
            r, v, tau, c, inc, cmin, cmax, q, e, mes = _floats(a[1:11])
            return Resultado(ReportedResult(tau, c, q, e, inc, mes, r, n=n, v=v, c_min=cmin, c_max=cmax))
        if cmd == "FIN":
            return Fin()
        if cmd == "ERROR":
            cod = int(a[0]) if a and a[0].lstrip("-").isdigit() else None
            msg = ",".join(a[1:]) if cod is not None else ",".join(a)
            return ErrorFirmware(msg or "Error", cod)
        return None

    # ---------- protocolo v2.1 (legible) ----------
    def _legible(self, linea: str) -> list[Evento]:
        if linea.startswith("=== CapSense Lab"):
            ver = linea.replace("=", "").replace("CapSense Lab", "").strip().lstrip("vV")
            if ver:
                self.version = ver
            return [Version(ver or "?")]
        if linea.startswith("ERROR:"):
            self._bloque, self._espera_csv = None, False
            return [ErrorFirmware(linea[6:].strip() or "Error")]
        if linea.startswith("prueba,R,meseta"):
            self._bloque, self._espera_csv = None, False
            return [Inicio()]
        if linea.startswith("-") and "RESULTADO" in linea:
            self._bloque, self._espera_csv = {}, False
            return []
        if linea.startswith("CSV ("):
            self._espera_csv = True
            return []

        campos = linea.split(",")
        if self._espera_csv and len(campos) == 7:
            try:
                tau, c, q, e, inc, mes, r = _floats(campos)
            except ValueError:
                return []
            b = self._bloque or {}
            self._bloque, self._espera_csv = None, False
            return [Resultado(ReportedResult(tau, c, q, e, inc, mes, r, n=b.get("n"), v=b.get("v"),
                                             c_min=b.get("c_min"), c_max=b.get("c_max")))]

        if self._bloque is not None and "=" in linea:
            self._linea_bloque(linea)
            return []

        if len(campos) == 5 and campos[0].strip().isdigit():
            try:
                i = int(campos[0])
                etiq = campos[1].strip()
                mes, tau, c = _floats(campos[2:])
            except ValueError:
                return []
            return [Prueba(Run(i, self.cal.indice_de(etiq), etiq, mes, tau, c))]
        return []

    def _linea_bloque(self, linea: str) -> None:
        assert self._bloque is not None
        clave, _, valor = linea.partition("=")
        clave, valor = clave.strip().lower(), valor.strip()
        num = valor.split(" ")[0]
        try:
            if clave == "pruebas":
                self._bloque["n"] = int(num)
            elif clave == "v entrada":
                self._bloque["v"] = float(num)
            elif clave == "c min/max":
                lo, _, hi = valor.replace("uF", "").partition("/")
                self._bloque["c_min"], self._bloque["c_max"] = float(lo), float(hi)
        except ValueError:
            pass
