"""Graba lo que manda el Arduino a un archivo, con marca de tiempo por línea.

El archivo sirve para el modo replay del dashboard y como fixture de tests.

    python scripts/grabar_log.py                 # autodetecta el puerto, 115200 baud
    python scripts/grabar_log.py --port COM3 --baud 9600 --salida tests/fixtures/mi_medicion.log
    python scripts/grabar_log.py --medir         # además envía "M" para disparar una medición (v2.2)

Ctrl+C para terminar.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import serial

from capsense.io.serial_source import autodetectar


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", help="puerto (por defecto autodetecta)")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--salida", type=Path,
                   default=Path("logs") / datetime.now().strftime("grabacion_%Y%m%d_%H%M%S.log"))
    p.add_argument("--medir", action="store_true", help='envía "M" al conectar')
    args = p.parse_args()

    puerto = args.port or autodetectar()
    if not puerto:
        print("No encuentro ningún Arduino. Usa --port.", file=sys.stderr)
        return 1
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    with serial.Serial(puerto, args.baud, timeout=0.2) as ser, open(args.salida, "w", encoding="utf-8") as f:
        print(f"Grabando {puerto} a {args.baud} baud en {args.salida} (Ctrl+C para terminar)")
        time.sleep(2.0)                      # el Uno se reinicia al abrir el puerto
        if args.medir:
            ser.write(b"M\n")
        t0 = time.monotonic()
        pendiente = b""
        try:
            while True:
                pendiente += ser.read(ser.in_waiting or 1)
                while b"\n" in pendiente:
                    linea, pendiente = pendiente.split(b"\n", 1)
                    texto = linea.decode("utf-8", errors="replace").rstrip("\r")
                    f.write(f"{time.monotonic() - t0:.3f}\t{texto}\n")
                    f.flush()
                    print(texto)
        except KeyboardInterrupt:
            print(f"\nListo: {args.salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
