# Cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).

## [0.5.0] - 2026-10-29

### Simulación del circuito
- Nueva vista **Simulación** (tecla 5): animación paso a paso de cómo mide el circuito, siguiendo el firmware v2.1 (LCD y LEDs como los escribe el .ino, D3 en LOW durante la pausa, descarga apenas llega a t2, autorango).
- Dos dibujos del mismo circuito: esquema eléctrico y la protoboard real, con las posiciones de `docs/referencia/montaje.html` (copiado al repo).
- Corriente animada en el sentido real, capacitor que se llena, estado de cada pin, LEDs, LCD y curva V(t) con cursor.
- Pasos como datos en `ui/simulation/steps_data.py`; posiciones del montaje en `ui/simulation/board_layout.py`; pines en `[pines]` de `config/capsense.toml` (sin números repetidos en el código).
- Física de carga, descarga y fuga en `domain/simulation.py`, probada contra fórmulas analíticas y contra `physics.py`.

### Hallazgo
- El firmware corta la descarga en ADC ≤ 5 y espera solo 100 ms: con capacitores grandes la carga arranca con voltaje residual y C sale baja (≈ −1 % a 100 µF, ≈ −4 % a 1000 µF). Ver `docs/calculos.md`.

## [0.4.0] - 2026-10-29

### Diseño
- Logo nuevo: cubo isométrico con C, A y P recortadas en sus caras (SVG generado por `scripts/generar_logo.py`).
- Dos temas, Ámbar (negro y naranja) y Neón (azul, turquesa y violeta), con selector en la barra lateral; se recuerda entre sesiones.
- Vista Medición rehecha: saludo y fecha en la cabecera, tarjetas KPI con mini-gráficas y variación contra la medición anterior, curva de carga con área y brillo, panel de calidad por factores, desviación de cada prueba y mediciones recientes.
- Historial con mapa de calor de repetibilidad.
- La curva muestra por defecto la última prueba (la extendida).

### Corregido
- La ventana de escritorio se colgaba: pywebview recorría el objeto ventana expuesto a la página.

## [0.3.0] - 2026-10-29

### Aplicación de escritorio
- Abre en su propia ventana (pywebview + WebView2) en vez del navegador. `CapSense Lab.pyw` y el comando `capsense-app` la lanzan sin consola. `--navegador` y `--servidor` conservan los modos anteriores.
- Nuevo diseño con la skill ui-ux-pro-max: barra lateral con cuatro vistas (Medición, Cálculos, Historial, Conexión), estado del equipo y botón Medir siempre visibles, vista de medición sin scroll a 1440×900.
- Tipografía Segoe UI Variable + Cascadia Code (sin descargas), íconos SVG propios, barra de progreso durante la medición, avisos como toasts, foco visible y movimiento reducido.
- Atajos: M medir, 1–4 vistas, F11 pantalla completa.

## [0.2.0] - 2026-10-29

### Firmware v2.3
- t1 y t2 se detectan sobre la media móvil de las últimas 8 lecturas y se interpolan entre vueltas del bucle, con corrección del retardo de muestreo del ADC.
- En el simulador, el peor error pasa de +5.0 % (1.5 µF con fuga) y −1.6 % (1000 µF con ruido) a menos de 1 % en todo el rango.
- `#PRUEBA` envía t1 y t2 con un decimal. Compila para el Uno con 16 528 bytes de flash (51 %) y 1252 bytes de RAM global (61 %).

### Dashboard
- El simulador imita la v2.3 (por defecto) o la v2.2; se elige en el panel demo o con `[demo] firmware` en `config/capsense.toml`.
- Barrido de tests para las dos versiones.

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
- Error de hasta ~5 % con capacitores de 1 a 5 µF con fuga, y de ~1.5 % con capacitores grandes y ruido (corregido en el firmware v2.3). Ver `docs/calculos.md`.
