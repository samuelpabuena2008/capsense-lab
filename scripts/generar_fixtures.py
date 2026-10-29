"""Regenera los fixtures de tests/fixtures/ con el simulador (semilla fija).

    python scripts/generar_fixtures.py
"""
from __future__ import annotations

from pathlib import Path

from capsense.io.simulator_source import FirmwareSim, ParamsSim

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def con_tiempos(lineas: list[tuple[float, str]]) -> str:
    t, out = 0.0, []
    for espera, linea in lineas:
        t += espera
        out.append(f"{t:.3f}\t{linea}")
    return "\n".join(out) + "\n"


def main() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)

    # v2.2: medición completa de 100 µF con fuga media, con marcas de tiempo (como logs/*_serial.log)
    sim = FirmwareSim(ParamsSim(c_uf=100.0, meseta_pct=97.0, ruido_lsb=0.7, seed=2026, firmware="2.2"))
    (FIXTURES / "sim_100uF_v22.log").write_text(con_tiempos(sim.arranque() + sim.medir()), encoding="utf-8")

    # v2.3: 2.2 µF con fuga (el caso que más mejora con el cruce interpolado)
    sim = FirmwareSim(ParamsSim(c_uf=2.2, meseta_pct=96.0, ruido_lsb=0.7, seed=2026, firmware="2.3"))
    (FIXTURES / "sim_2u2F_v23.log").write_text(con_tiempos(sim.arranque() + sim.medir()), encoding="utf-8")

    # v2.1: lo mismo pero solo con el texto legible (así se ve el Monitor Serie de la v2.1)
    sim = FirmwareSim(ParamsSim(c_uf=47.0, meseta_pct=98.5, ruido_lsb=0.7, seed=7, firmware="2.2"))
    legible = [linea for _e, linea in sim.medir() if not linea.startswith("#")]
    cab = ["=== CapSense Lab v2.1 ===", "Rango: 1 uF a 1000 uF. Pulsa START para medir."]
    (FIXTURES / "sim_47uF_v21.log").write_text("\n".join(cab + legible) + "\n", encoding="utf-8")

    # Error: capacitor que no llega a 700 por fuga
    sim = FirmwareSim(ParamsSim(c_uf=10.0, meseta_pct=66.0, seed=1, firmware="2.2"))
    (FIXTURES / "sim_error_fuga_v22.log").write_text(
        "\n".join(linea for _e, linea in sim.arranque() + sim.medir()) + "\n", encoding="utf-8")
    print("Fixtures regenerados en", FIXTURES)


if __name__ == "__main__":
    main()
