"""Parser del puerto serie del CapSense Lab.

Entiende dos protocolos:
  * v2.1 (legible): el texto del Monitor Serie (tabla por prueba, bloque RESULTADO, línea CSV, "ERROR: ...").
  * v2.2 (máquina): líneas con prefijo '#'. La v2.2 también imprime el bloque legible; en cuanto
    el parser ve una línea '#' pasa a modo v2.2 y desde ahí ignora el texto legible (si no, cada
    prueba llegaría dos veces).

Uso:  p = Parser();  for ev in p.feed(texto): ...
feed() acepta trozos de cualquier tamaño (líneas partidas), y tolera basura: lo que no entiende lo descarta.
"""
from dataclasses import dataclass, field
from typing import Optional

import config


# ---------------- eventos ----------------
@dataclass
class Version:
    version: str


@dataclass
class Config:
    v_entrada: float
    r_real: list
    r_pin: float
    k_cal: float
    n1: float
    n2: float


@dataclass
class Rango:
    rango: int
    etiqueta: str
    r_ohm: float


@dataclass
class Listo:
    pass


@dataclass
class Inicio:
    n_max: Optional[int] = None


@dataclass
class PruebaIni:
    i: int
    rango: int


@dataclass
class Muestra:
    t_us: int
    adc: int


@dataclass
class Prueba:
    i: int
    rango: Optional[int]
    etiqueta: str
    meseta: float
    tau_ms: float
    c_uf: float
    t1_us: Optional[float] = None    # None en la v2.1 (hay que reconstruirlos)
    t2_us: Optional[float] = None
    ext: bool = False
    muestras: list = field(default_factory=list)   # [(t_us, adc), ...] solo en v2.2


@dataclass
class Resultado:
    tau_ms: float
    c_uf: float
    q_uc: float
    e_uj: float
    inc_pct: float
    meseta_pct: float
    r_ohm: float
    n: Optional[int] = None
    v: Optional[float] = None
    c_min: Optional[float] = None
    c_max: Optional[float] = None


@dataclass
class Fin:
    pass


@dataclass
class Error:
    mensaje: str
    codigo: Optional[int] = None


def _rango_de_etiqueta(etiq):
    try:
        return config.R_ETIQ.index(etiq)
    except ValueError:
        return None


def _floats(campos):
    return [float(x) for x in campos]


class Parser:
    def __init__(self):
        self.buffer = ""
        self.version = None          # "2.1" | "2.2" | None (aún no se sabe)
        self.modo_maquina = False
        self.muestras = []           # muestras de la prueba en curso (v2.2)
        self._bloque = None          # dict del bloque RESULTADO legible (v2.1)
        self._espera_csv = False

    # ---------- entrada ----------
    def feed(self, texto):
        if isinstance(texto, bytes):
            texto = texto.decode("utf-8", errors="replace")
        self.buffer += texto
        eventos = []
        while "\n" in self.buffer:
            linea, self.buffer = self.buffer.split("\n", 1)
            eventos.extend(self.linea(linea))
        if len(self.buffer) > 4096:      # basura sin saltos de línea
            self.buffer = ""
        return eventos

    def linea(self, linea):
        linea = "".join(ch for ch in linea if ch.isprintable()).strip()
        if not linea:
            return []
        if "#" in linea:
            # Si una línea quedó pegada a basura ("xx#MUESTRA,..."), uso desde el último '#'
            return self._maquina(linea[linea.rfind("#"):])
        if self.modo_maquina:
            return []                    # el texto legible de la v2.2 ya llegó por '#'
        return self._legible(linea)

    # ---------- protocolo v2.2 ----------
    def _maquina(self, linea):
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

    def _evento_maquina(self, cmd, a):
        if cmd == "VERSION":
            self.version = a[0]
            return Version(a[0])
        if cmd == "CONFIG":
            if len(a) < 7:
                return None
            v, r0, r1, rp, k, n1, n2 = _floats(a[:7])
            return Config(v, [r0, r1], rp, k, n1, n2)
        if cmd == "RANGO":
            return Rango(int(a[0]), a[1], float(a[2]))
        if cmd == "LISTO":
            return Listo()
        if cmd == "INICIO":
            return Inicio(int(a[0]) if a and a[0] else None)
        if cmd == "PRUEBA_INI":
            self.muestras = []
            return PruebaIni(int(a[0]), int(a[1]))
        if cmd == "MUESTRA":
            if len(a) < 2:
                return None
            m = Muestra(int(a[0]), int(a[1]))
            if not (0 <= m.adc <= 1023) or m.t_us < 0:
                return None
            self.muestras.append((m.t_us, m.adc))
            return m
        if cmd == "PRUEBA":
            # #PRUEBA,i,rango,t1_us,t2_us,meseta,tau_ms,C_uF,ext
            if len(a) < 8:
                return None
            rango = int(a[1])
            etiq = config.R_ETIQ[rango] if 0 <= rango < len(config.R_ETIQ) else str(rango)
            ev = Prueba(
                i=int(a[0]), rango=rango, etiqueta=etiq,
                t1_us=float(a[2]), t2_us=float(a[3]), meseta=float(a[4]),
                tau_ms=float(a[5]), c_uf=float(a[6]),
                ext=(len(a) > 7 and a[7] == "1"),
                muestras=self.muestras,
            )
            self.muestras = []
            return ev
        if cmd == "RESULTADO":
            # #RESULTADO,n,R_ohm,V,tau_ms,C_uF,inc_pct,cmin,cmax,Q_uC,E_uJ,meseta_pct
            if len(a) < 11:
                return None
            n = int(a[0])
            r, v, tau, c, inc, cmin, cmax, q, e, mes = _floats(a[1:11])
            return Resultado(tau, c, q, e, inc, mes, r, n=n, v=v, c_min=cmin, c_max=cmax)
        if cmd == "FIN":
            return Fin()
        if cmd == "ERROR":
            cod = int(a[0]) if a and a[0].lstrip("-").isdigit() else None
            msg = ",".join(a[1:]) if cod is not None else ",".join(a)
            return Error(msg or "Error", cod)
        return None

    # ---------- protocolo v2.1 (legible) ----------
    def _legible(self, linea):
        if linea.startswith("=== CapSense Lab"):
            ver = linea.replace("=", "").replace("CapSense Lab", "").strip().lstrip("vV")
            self.version = ver or self.version
            return [Version(ver)]
        if linea.startswith("ERROR:"):
            return [Error(linea[6:].strip() or "Error")]
        if linea.startswith("prueba,R,meseta"):
            self._bloque, self._espera_csv = None, False
            return [Inicio()]
        if "RESULTADO" in linea and linea.startswith("-"):
            self._bloque = {}
            self._espera_csv = False
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
            return [Resultado(tau, c, q, e, inc, mes, r, n=b.get("n"), v=b.get("v"),
                              c_min=b.get("c_min"), c_max=b.get("c_max"))]

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
            return [Prueba(i, _rango_de_etiqueta(etiq), etiq, mes, tau, c)]
        return []

    def _linea_bloque(self, linea):
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
