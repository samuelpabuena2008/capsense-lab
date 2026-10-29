# Fixtures

| Archivo | Origen |
|---|---|
| `referencia_100uF_v21.log` | La prueba de referencia real de 100 µF (t1 = 290.36 ms, t2 = 1221.59 ms → C = 102.040 µF), en formato v2.1. Solo una prueba. |
| `sim_100uF_v22.log` | Medición completa v2.2 generada con el simulador (semilla fija), con marcas de tiempo como `logs/*_serial.log`. |
| `sim_2u2F_v23.log` | Medición v2.3 de 2.2 µF con fuga (t1/t2 interpolados), generada con el simulador. |
| `sim_47uF_v21.log` | Medición v2.1 (solo texto legible) generada con el simulador. |
| `sim_error_fuga_v22.log` | Medición que falla con `#ERROR,4,Fuga muy alta`. |

Los `sim_*` se regeneran con `python scripts/generar_fixtures.py`.

Para agregar una medición real del Arduino:

```bash
python scripts/grabar_log.py --port COM3 --medir --salida tests/fixtures/real_100uF_v22.log
```
