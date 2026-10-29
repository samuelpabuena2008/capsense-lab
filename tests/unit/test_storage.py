import csv
import io
from datetime import datetime

from capsense.domain.models import Measurement, ReportedResult, Run, Sample
from capsense.services import storage


def medicion(id_=1, error=None):
    runs = [Run(1, 0, "10k", 993.3, 1001.524, 102.040, t1_us=290360.0, t2_us=1221590.0,
                samples=[Sample(500, 4)])]
    rep = None if error else ReportedResult(1001.524, 102.040, 502.037, 1235.011, 0.0, 97.1, 9815.0, n=1)
    return Measurement(id_, datetime(2026, 10, 29, 14, 2, 11), origen="Demo", firmware="2.2", runs=runs,
                       reportado=rep, error=error, completa=True)


def test_fila_medicion_usa_lo_reportado(cal):
    f = storage.fila_medicion(medicion(), cal)
    assert f["C_uF"] == 102.04 and f["hora"] == "14:02:11" and f["rango"] == "10k"
    assert f["fuga"] == "media" and f["error"] == ""


def test_fila_medicion_sin_reporte_recalcula(cal):
    f = storage.fila_medicion(medicion(error="Medición interrumpida"), cal)
    assert abs(f["C_uF"] - 102.04) < 0.01
    assert f["error"] == "Medición interrumpida"


def test_storage_escribe_logs(tmp_path, cal):
    st = storage.Storage(tmp_path, "sesion_x")
    st.log_linea("#LISTO")
    st.guardar_medicion(medicion(1), cal)
    st.guardar_medicion(medicion(2), cal)
    st.cerrar()
    lineas = st.ruta_serial.read_text(encoding="utf-8").splitlines()
    assert lineas[0].endswith("\t#LISTO")
    filas = list(csv.DictReader(st.ruta_mediciones.open(encoding="utf-8")))
    assert [f["medicion"] for f in filas] == ["1", "2"]
    pruebas = list(csv.DictReader(st.ruta_pruebas.open(encoding="utf-8")))
    assert pruebas[0]["t1_us"] == "290360.0" and pruebas[0]["n_muestras"] == "1"


def test_exportar(cal):
    texto = storage.exportar_historial([medicion(1), medicion(2)], cal)
    filas = list(csv.DictReader(io.StringIO(texto)))
    assert len(filas) == 2 and filas[0].keys() >= {"C_uF", "incert_pct", "tau_ms", "meseta_pct"}
    assert "t1_us" in storage.exportar_pruebas([medicion()]).splitlines()[0]
