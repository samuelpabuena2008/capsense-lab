"""Genera los "cálculos paso a paso" con los números reales sustituidos.

Cada paso trae Markdown con LaTeX ($$ ... $$) y, si aplica, un chequeo contra lo que
reportó el Arduino. No depende de la interfaz: la UI solo renderiza el texto.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from capsense.domain import physics as ph
from capsense.domain.models import Calibracion, Measurement


@dataclass
class Chequeo:
    nombre: str
    python: float
    firmware: float
    unidad: str = ""
    decimales: int = 3          # decimales con que imprime el Arduino ese valor

    @property
    def diferencia_pct(self) -> float:
        return ph.diferencia_pct(self.python, self.firmware)

    @property
    def coincide(self) -> bool:
        """Coincide si la diferencia es menor que 0.1 % o que el redondeo de lo que imprimió el Arduino."""
        redondeo = 0.5 * 10 ** -self.decimales * 1.001
        return (abs(self.diferencia_pct) <= ph.TOLERANCIA_PCT
                or abs(self.python - self.firmware) <= redondeo)


@dataclass
class Paso:
    titulo: str
    markdown: str
    chequeos: list[Chequeo] = field(default_factory=list)
    nota: str = ""


def _ms(us: float) -> str:
    return f"{us / 1000.0:.3f}"


def _g(x: float, dec: int = 3) -> str:
    return f"{x:.{dec}f}"


def pasos_prueba(rc: ph.RunCalculado, cal: Calibracion) -> list[Paso]:
    run, aj = rc.run, rc.ajuste
    n1, n2 = int(cal.adc_n1), int(cal.adc_n2)
    pasos: list[Paso] = []

    nota = ""
    if run.t_reconstruidos:
        nota = ("El firmware v2.1 no envía t1 ni t2: se reconstruyeron desde τ y P "
                "(es exacto cuando la bisección converge, porque τ1 = τ2).")
    pasos.append(Paso(
        f"Tiempos medidos (prueba {run.i}, R = {run.etiqueta})",
        f"El Arduino carga el capacitor y anota cuándo el ADC cruza {n1} y {n2}:\n\n"
        f"$$t_1 = t(\\text{{ADC}} \\geq {n1}) = {_ms(aj.t1)}\\ \\text{{ms}} \\qquad "
        f"t_2 = t(\\text{{ADC}} \\geq {n2}) = {_ms(aj.t2)}\\ \\text{{ms}}$$",
        nota=nota,
    ))

    pasos.append(Paso(
        "Razón entre los tiempos",
        f"$$r = \\dfrac{{t_2}}{{t_1}} = \\dfrac{{{_ms(aj.t2)}}}{{{_ms(aj.t1)}}} = {aj.r:.5f}$$",
    ))

    ecuacion = (f"$$\\dfrac{{\\ln\\left(1 - \\dfrac{{{n2}}}{{P}}\\right)}}"
                f"{{\\ln\\left(1 - \\dfrac{{{n1}}}{{P}}\\right)}} = r = {aj.r:.5f}$$")
    if aj.saturacion == "alta":
        cuerpo = (f"La meseta P cumple\n\n{ecuacion}\n\nComo $r \\leq {ph.razon_p(cal.adc_max, n1, n2):.5f}$ "
                  f"(la razón con $P = {int(cal.adc_max)}$), no hay fuga apreciable y el firmware fija "
                  f"$P = {int(cal.adc_max)}$.")
    elif aj.saturacion == "baja":
        cuerpo = (f"La meseta P cumple\n\n{ecuacion}\n\nLa razón es tan grande que P queda en el mínimo "
                  f"permitido: $P = {aj.P:.0f}$ (fuga muy alta).")
    else:
        prim = aj.pasos[:3]
        ult = aj.pasos[-1]
        filas = "\n".join(
            f"| {p.iteracion} | {p.lo:.3f} | {p.hi:.3f} | {p.mid:.3f} | {p.razon_mid:.5f} |" for p in prim
        )
        cuerpo = (
            f"La meseta P cumple\n\n{ecuacion}\n\n"
            f"No tiene despeje cerrado, así que se resuelve por **bisección** entre "
            f"{n2 + 2} y {int(cal.adc_max)} durante {ph.ITERACIONES} iteraciones "
            f"(si la razón en el punto medio es mayor que r, P está más arriba):\n\n"
            f"| it | lo | hi | medio | razón(medio) |\n|---|---|---|---|---|\n{filas}\n"
            f"| … | | | | |\n"
            f"| {ult.iteracion} | {ult.lo:.4f} | {ult.hi:.4f} | {ult.mid:.4f} | {ult.razon_mid:.5f} |\n\n"
            f"$$P = {aj.P:.3f}\\ \\text{{cuentas}} = {aj.P / cal.adc_max * 100:.2f}\\ \\%\\ \\text{{de}}\\ "
            f"{int(cal.adc_max)}$$"
        )
    pasos.append(Paso("Meseta P por bisección", cuerpo,
                      [Chequeo("P", aj.P, run.meseta, "cuentas", 1)]))

    pasos.append(Paso(
        "Constante de tiempo desde cada cruce",
        f"$$\\tau_1 = \\dfrac{{t_1}}{{-\\ln\\left(1 - \\dfrac{{{n1}}}{{P}}\\right)}} = "
        f"\\dfrac{{{_ms(aj.t1)}}}{{-\\ln\\left(1 - \\dfrac{{{n1}}}{{{aj.P:.3f}}}\\right)}} = "
        f"{_ms(aj.tau1)}\\ \\text{{ms}}$$\n\n"
        f"$$\\tau_2 = \\dfrac{{t_2}}{{-\\ln\\left(1 - \\dfrac{{{n2}}}{{P}}\\right)}} = "
        f"\\dfrac{{{_ms(aj.t2)}}}{{-\\ln\\left(1 - \\dfrac{{{n2}}}{{{aj.P:.3f}}}\\right)}} = "
        f"{_ms(aj.tau2)}\\ \\text{{ms}}$$",
    ))

    pasos.append(Paso(
        "τ promedio",
        f"$$\\tau = \\dfrac{{\\tau_1 + \\tau_2}}{{2}} = \\dfrac{{{_ms(aj.tau1)} + {_ms(aj.tau2)}}}{{2}} = "
        f"{_ms(aj.tau)}\\ \\text{{ms}}$$",
        [Chequeo("τ", aj.tau / 1000.0, run.tau_ms, "ms")],
    ))

    r_carga = cal.rangos[run.rango].r_ohm if run.rango is not None else rc.r_ohm - cal.r_pin
    k = f" \\cdot {cal.k_cal:g}" if cal.k_cal != 1.0 else ""
    por_k = " \\cdot K" if k else ""
    pasos.append(Paso(
        "Capacitancia",
        f"$$C = \\dfrac{{\\tau}}{{R + R_{{pin}}}}{por_k} = "
        f"\\dfrac{{{rc.tau_s:.6f}\\ \\text{{s}}}}{{{r_carga:.0f} + {cal.r_pin:g}\\ \\Omega}}{k} = "
        f"{rc.c_uf:.3f}\\ \\mu\\text{{F}}$$",
        [Chequeo("C", rc.c_uf, run.c_uf, "µF")],
    ))
    return pasos


def pasos_resumen(m: Measurement, calculados: Sequence[ph.RunCalculado], cal: Calibracion) -> list[Paso]:
    res = ph.resumir(calculados, cal)
    if res is None:
        return []
    rep = m.reportado
    cs = [c.c_uf for c in calculados]
    pasos: list[Paso] = []

    suma = " + ".join(f"{c:.3f}" for c in cs)
    pasos.append(Paso(
        f"Promedio de las {res.n} pruebas",
        f"$$\\bar{{C}} = \\dfrac{{{suma}}}{{{res.n}}} = {res.c_uf:.3f}\\ \\mu\\text{{F}}$$",
        [Chequeo("C promedio", res.c_uf, rep.c_uf, "µF")] if rep else [],
    ))

    pasos.append(Paso(
        "Incertidumbre (semi-rango)",
        "El firmware **no usa desviación estándar**: usa la mitad de la diferencia entre la prueba "
        "más alta y la más baja, relativa al promedio.\n\n"
        f"$$\\Delta C = \\dfrac{{C_{{max}} - C_{{min}}}}{{2}} = \\dfrac{{{res.c_max:.3f} - {res.c_min:.3f}}}{{2}} "
        f"= {res.delta_uf:.3f}\\ \\mu\\text{{F}}$$\n\n"
        f"$$\\dfrac{{\\Delta C}}{{\\bar{{C}}}} \\cdot 100 = \\dfrac{{{res.delta_uf:.3f}}}{{{res.c_uf:.3f}}} "
        f"\\cdot 100 = {res.inc_pct:.2f}\\ \\%$$",
        [Chequeo("Incertidumbre", res.inc_pct, rep.inc_pct, "%", 2)] if rep else [],
        nota="Con una sola prueba la incertidumbre es 0." if res.n == 1 else "",
    ))

    v = cal.v_entrada
    pasos.append(Paso(
        "Carga y energía almacenadas",
        f"$$Q = \\bar{{C}} \\cdot V = {res.c_uf:.3f}\\ \\mu\\text{{F}} \\cdot {v:.2f}\\ \\text{{V}} = "
        f"{res.q_uc:.3f}\\ \\mu\\text{{C}}$$\n\n"
        f"$$E = \\tfrac{{1}}{{2}} \\bar{{C}} V^2 = \\tfrac{{1}}{{2}} \\cdot {res.c_uf:.3f}\\ \\mu\\text{{F}} "
        f"\\cdot ({v:.2f}\\ \\text{{V}})^2 = {res.e_uj:.3f}\\ \\mu\\text{{J}}$$",
        ([Chequeo("Q", res.q_uc, rep.q_uc, "µC"), Chequeo("E", res.e_uj, rep.e_uj, "µJ")] if rep else []),
    ))
    return pasos
