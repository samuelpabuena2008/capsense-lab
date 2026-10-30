"""Arma el guion de la simulación: los pasos de steps_data con los números de una MedicionSim.

No calcula física: toma los resultados de domain.simulation y domain.physics, y los textos de
domain.steps para las fórmulas. Devuelve datos JSON para el navegador (dcc.Store) y los pasos de
fórmulas (domain.steps.Paso) que la interfaz renderiza con MathJax.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from capsense.domain import physics as ph
from capsense.domain import simulation as sim
from capsense.domain import steps as pasos_calc
from capsense.domain.models import Calibracion, Measurement, Pines, ReportedResult, Run
from capsense.ui.simulation.steps_data import CARGA_1M, CARGA_10K, ESTADO_PIN, EXPLICACION_ERROR, PASOS


@dataclass
class Guion:
    datos: dict                                   # va al dcc.Store (JSON)
    formulas: dict[str, list] = field(default_factory=dict)   # id de paso -> [domain.steps.Paso]


_VAR = re.compile(r"\{(\w+)\}")


def rellenar(texto: str, ctx: dict) -> str:
    """Reemplaza solo {variables} conocidas (el código C trae llaves propias)."""
    return _VAR.sub(lambda m: str(ctx[m.group(1)]) if m.group(1) in ctx else m.group(0), texto)


def _t(us: float | None) -> str:
    if us is None:
        return "—"
    return f"{us / 1000:.2f} ms" if us < 1e6 else f"{us / 1e6:.3f} s"


def _c(c_uf: float | None) -> str:
    if c_uf is None:
        return "—"
    num, u = ph.formato_c(c_uf)
    return f"{num} {u}"


def lcd_resultado(c_uf: float, inc_pct: float, n: int) -> tuple[str, str]:
    """Las dos líneas que escribe mostrarPantalla() (pantalla 0) del firmware."""
    if c_uf >= 1000:
        l1 = f"C={c_uf / 1000:.3f} mF"
    elif c_uf >= 10:
        l1 = f"C={c_uf:.2f} uF"
    else:
        l1 = f"C={c_uf:.3f} uF"
    return l1[:16], f"+/-{inc_pct:.2f}% n={n}"[:16]


def _run(p: sim.PruebaSim, cal: Calibracion) -> Run:
    assert p.ajuste is not None and p.tau_s is not None and p.c_uf is not None
    return Run(i=p.numero, rango=p.rango, etiqueta=cal.etiqueta(p.rango), meseta=round(p.ajuste.P, 1),
               tau_ms=round(p.tau_s * 1000, 3), c_uf=round(p.c_uf, 3), t1_us=p.t1_us, t2_us=p.t2_us)


def _indices(serie: dict, p: sim.PruebaSim) -> dict[str, list[int]]:
    t, fase = serie["t"], serie["fase"]
    def primero(cond) -> int:
        return next((k for k, v in enumerate(t) if cond(k, v)), len(t) - 1)
    i_pausa = primero(lambda k, _v: fase[k] == 1)
    i_carga = primero(lambda k, _v: fase[k] == 2)
    i_t1 = primero(lambda k, v: fase[k] == 2 and p.t1_us is not None and v >= p.t1_us / 1e6) if p.t1_us else len(t) - 1
    fin = len(t) - 1
    return {"descarga": [0, max(0, i_pausa - 1)], "pausa": [i_pausa, max(i_pausa, i_carga - 1)],
            "hasta_t1": [i_carga, i_t1], "t1_t2": [i_t1, fin], "inicio_carga": [i_carga, i_carga],
            "t1": [i_t1, i_t1], "fin": [fin, fin], "inicio": [0, 0]}


CURSOR_ESTATICO = {"listo": "inicio", "disparo": "inicio_carga", "t1": "t1", "autorango": "fin", "ajuste": "fin",
                   "calculo": "fin", "repeticiones": "fin", "resultado": "fin", "error": "fin"}


def construir(m: sim.MedicionSim, cal: Calibracion, pines: Pines) -> Guion:
    intentos = m.intentos
    rapido_idx = 0 if (intentos and intentos[0].resultado == sim.RAPIDO and m.cambios_rango) else None
    validas = m.validas
    guia = validas[0] if validas else intentos[-1]
    guia_idx = intentos.index(guia)

    seq: list[tuple[str, int]] = []
    if rapido_idx is not None:
        seq += [(k, rapido_idx) for k in ("listo", "descarga", "pausa", "disparo", "lectura")]
        seq.append(("autorango", guia_idx))
    else:
        seq.append(("listo", guia_idx))
    if guia.resultado == sim.OK:
        seq += [(k, guia_idx) for k in ("descarga", "pausa", "disparo", "lectura", "t1", "t2", "ajuste", "calculo")]
        if m.error:
            seq.append(("error", guia_idx))
        else:
            if m.n_pruebas > 1:
                seq.append(("repeticiones", guia_idx))
            seq.append(("resultado", guia_idx))
    else:
        seq += [(k, guia_idx) for k in ("descarga", "pausa", "disparo", "lectura")]
        if guia.t1_us:
            seq.append(("t1", guia_idx))
        seq.append(("error", guia_idx))

    usados = sorted({idx for _k, idx in seq})
    series = {str(idx): sim.serie_prueba(intentos[idx], cal) for idx in usados}
    indices = {str(idx): _indices(series[str(idx)], intentos[idx]) for idx in usados}

    # variables de los textos
    res = m.resumen
    lcd_c, lcd_inc = lcd_resultado(res.c_uf, res.inc_pct, res.n) if res else ("", "")
    nombres_rango = {0: "10 kΩ", 1: "1 MΩ"}
    base = {
        "n": m.n_pruebas, "pin_descarga": pines.descarga, "pin_lectura": pines.lectura,
        "pin_start": pines.boton_start, "pin_verde": pines.led_verde, "pin_rojo": pines.led_rojo,
        "pin_carga_10k": pines.carga[0], "pin_carga_1m": pines.carga[-1],
        "t1_rapido": _t(intentos[rapido_idx].t1_us) if rapido_idx is not None else "—",
        "lista_c": ", ".join(_c(p.c_uf) for p in validas) or "—",
        "c_final": _c(res.c_uf) if res else "—", "inc": f"{res.inc_pct:.2f} %" if res else "—",
        "q": f"{res.q_uc:.4g} µC" if res else "—", "e": f"{res.e_uj:.4g} µJ" if res else "—",
        "lcd_c": lcd_c, "lcd_inc": lcd_inc, "error": m.error or "",
        "explicacion_error": EXPLICACION_ERROR.get(m.error or "", ""),
    }

    pasos = []
    for k, idx in seq:
        p = intentos[idx]
        d = PASOS[k]
        rango = p.rango
        ctx = dict(base, i=p.numero, rango=cal.etiqueta(rango), pin_carga=pines.carga[rango],
                   r_txt=nombres_rango.get(rango, cal.etiqueta(rango)), t1=_t(p.t1_us), t2=_t(p.t2_us),
                   tau=_t(p.tau_s * 1e6) if p.tau_s else "—", c_prueba=_c(p.c_uf))
        carga = CARGA_10K if rango == 0 else CARGA_1M
        ctx["carga_texto"] = rellenar(carga["texto"], ctx)
        resaltar = []
        for r in d["resaltar"]:
            resaltar += carga["resaltar"] if r == "@carga" else [r]
        hoyos = list(d["hoyos"]) + (carga["hoyos"] if "@carga" in d["resaltar"] else [])
        roles = {"carga": pines.carga[rango], "descarga": pines.descarga, "lectura": pines.lectura}
        if len(pines.carga) > 1:
            roles["carga_otro"] = pines.carga[1 - rango]
        filas_pines, mapa = [], {}
        for rol, nombre in roles.items():
            estado = d["pines"][rol]
            mapa[nombre] = estado
            rol_txt = {"carga": f"carga {nombres_rango.get(rango, '')}",
                       "carga_otro": f"carga {nombres_rango.get(1 - rango, '')}",
                       "descarga": "descarga 560 Ω", "lectura": "lectura del nodo"}[rol]
            filas_pines.append({"pin": nombre, "rol": rol_txt, "estado": estado,
                                "modo": ESTADO_PIN[estado][0], "detalle": ESTADO_PIN[estado][1]})
        filas_pines.sort(key=lambda f: f["pin"])
        flujo = d["flujo"]
        if flujo == "carga":
            flujo = f"carga{rango}"
        seg = d["segmento"]
        cursor = indices[str(idx)][seg] if seg else indices[str(idx)][CURSOR_ESTATICO.get(k, "fin")]
        paso = {
            "id": k, "titulo": rellenar(d["titulo"], ctx), "que_pasa": rellenar(d["que_pasa"], ctx),
            "codigo": [rellenar(linea, ctx) for linea in d["codigo"]], "linea": d["linea"],
            "pines": filas_pines, "mapa_pines": mapa, "leds": d["leds"],
            "lcd": [rellenar(linea, ctx)[:16] for linea in d["lcd"]],
            "resaltar": resaltar, "hoyos": hoyos, "protoboard": rellenar(d["protoboard"], ctx),
            "flujo": flujo, "serie": str(idx), "cursor": cursor, "anima": bool(seg),
            "lectura_s": d["lectura_s"], "prueba": p.numero, "rango": cal.etiqueta(rango),
        }
        if k == "ajuste" and p.ajuste is not None:
            paso["biseccion"] = [round(x.mid, 3) for x in p.ajuste.pasos] or [round(p.ajuste.P, 3)]
        pasos.append(paso)

    serie_guia = series[str(guia_idx)]
    i_max = max((abs(x) for s in series.values() for x in s["i"]), default=1.0) or 1.0
    marcas = {}
    if guia.ajuste is not None:
        marcas = {"t1": guia.t1_us / 1e6, "t2": guia.t2_us / 1e6, "tau": guia.ajuste.tau / 1e6,
                  "p_v": guia.ajuste.P / cal.adc_max * m.v_entrada}
    datos = {
        "pasos": pasos, "series": series, "guia": str(guia_idx), "vin": m.v_entrada, "i_max": i_max,
        "marcas": marcas, "error": m.error,
        "resumen": None if res is None else {"c": _c(res.c_uf), "inc": f"{res.inc_pct:.2f}",
                                             "n": res.n, "c_real": _c(m.c_real_uf)},
        "t_fin_guia": serie_guia["t"][-1],
    }

    formulas: dict[str, list] = {}
    if guia.ajuste is not None and guia.c_uf is not None:
        rc = ph.recalcular_run(_run(guia, cal), cal)
        if rc is not None:
            todos = pasos_calc.pasos_prueba(rc, cal)
            formulas["ajuste"] = todos[1:5]
            formulas["calculo"] = todos[5:6]
        if res is not None:
            runs = [_run(p, cal) for p in validas]
            calc = [x for x in (ph.recalcular_run(r, cal) for r in runs) if x is not None]
            med = Measurement(0, datetime.now(), runs=runs, completa=True, reportado=ReportedResult(
                tau_ms=round(res.tau_ms, 3), c_uf=round(res.c_uf, 3), q_uc=round(res.q_uc, 3),
                e_uj=round(res.e_uj, 3), inc_pct=round(res.inc_pct, 2), meseta_pct=round(res.meseta_pct, 1),
                r_ohm=res.r_ohm, n=res.n, v=m.v_entrada))
            formulas["resultado"] = pasos_calc.pasos_resumen(med, calc, cal)
    return Guion(datos=datos, formulas=formulas)
