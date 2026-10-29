# CapSense Lab

Medidor de capacitancia RC (1 µF a 1000 µF) con Arduino Uno, y un dashboard en Python para mostrar en proyector la curva de carga y los cálculos paso a paso.

Proyecto de Samuel y Joel (Ingeniería de Sistemas, Universidad del Norte) para la GeoExpo de Física.

## Cómo mide

El Arduino carga el capacitor a través de una resistencia conocida (10 kΩ o 1 MΩ, con autorango) y mide el tiempo en que el ADC cruza dos niveles: t1 (ADC = 250) y t2 (ADC = 700). Con eso resuelve la curva

$$V(t) = P\,(1 - e^{-t/\tau})$$

para la meseta P y la constante de tiempo τ, y calcula C = τ / R. Al estimar P, la fuga del capacitor no infla la medida. Repite la prueba varias veces (5; 3 si τ > 1 s; 2 si τ > 4 s) y entrega el promedio con su incertidumbre (semi-rango).

## Contenido

| Archivo | Qué es |
|---|---|
| `capsense_lab_v2_1.ino` | Firmware actual (LCD 16x2, 3 botones, 3 LEDs, autorango) |
| `config.py` | Constantes del montaje (V de entrada, resistencias, niveles del ADC). Se pueden cambiar con un `config.json` |
| `calc.py` | Réplica en Python de la matemática del firmware: ajuste de curva por bisección, C, Q, E, incertidumbre |
| `parser.py` | Lector del puerto serie: entiende el protocolo legible de la v2.1 y el de prefijos `#` de la v2.2 |

## En construcción

- Pruebas automáticas (`tests/`)
- Simulador del Arduino para el modo demo
- Dashboard en Dash + Plotly (tema oscuro, curva de carga, fórmulas con los números reales)
- Lectura del Arduino real por USB con reconexión
- Firmware v2.2: 100 muestras de la curva, t1/t2 explícitos, 115200 baud y comando `M` para medir desde el PC

## Requisitos

Python 3.11+ y:

```bash
pip install dash plotly pyserial numpy pytest
```
