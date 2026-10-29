# Cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).

## [0.1.0] - 2026-10-29

### Dashboard
- Primera versión en Dash + Plotly, tema oscuro y en español.
- Resultado principal con unidad automática, incertidumbre, rango, pruebas, meseta y aviso de fuga alta.
- Curva de carga con muestras reales, ajuste, t₁/t₂, meseta, τ y guías 2τ/3τ/5τ; selector por prueba.
- Panel de cálculos paso a paso con MathJax y chequeo contra lo que reportó el Arduino.
- C por prueba con media y banda, tarjetas τ/R/V/Q/E, historial, exportación CSV y logs automáticos en `logs/`.
- Fuentes de datos: Arduino por serie (autodetección y reconexión), simulador (modo demo) y replay de logs o CSV.
- Botón **Medir** que envía `M` al firmware v2.2.
- Entiende la salida del firmware v2.1 y reconstruye t₁ y t₂ desde τ y P.

### Firmware v2.2
- Captura hasta 100 muestras de la curva con espaciado geométrico y las envía después de cada prueba.
- La última prueba sigue hasta la meseta (ADC ≥ 1015 u 8 s extra).
- Protocolo con prefijo `#`, 115200 baud, comandos `M` y `V`. Conserva la salida legible.
- La medición, el LCD, los LEDs, los botones y el autorango son los de la v2.1.

### Conocido
- Error de hasta ~5 % con capacitores de 1 a 5 µF con fuga, y de ~1.5 % con capacitores grandes y ruido. Ver `docs/calculos.md`.
