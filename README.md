# CapSense Lab

Medidor de capacitancia RC (1 µF a 1000 µF) con Arduino Uno, y un dashboard en Python para mostrar en proyector el resultado, la curva de carga y los cálculos paso a paso.

Proyecto de Samuel y Joel (Ingeniería de Sistemas, Universidad del Norte) para la GeoExpo de Física.

![Dashboard en modo demo: resultado de 98.96 µF y curva de carga con t1, t2, τ y la meseta](docs/img/dashboard.jpg)

## Qué muestra

- **Resultado grande**, legible a 3 m: C con unidad automática (µF o mF), ± valor y ± %, rango usado (10 kΩ o 1 MΩ), número de pruebas, meseta y aviso rojo si la fuga es alta.
- **Curva de carga** interactiva: muestras reales (firmware v2.2), curva ajustada $V(t) = P(1-e^{-t/\tau})$, los cruces t₁ (ADC 250) y t₂ (ADC 700), la meseta punteada, τ (63.2 % de P) y guías en 2τ, 3τ y 5τ. Eje secundario en cuentas del ADC. Cada prueba por separado o todas superpuestas.
- **Cálculos paso a paso** con los números de la medición sustituidos: razón t₂/t₁ → bisección para P → τ₁, τ₂ → τ → C → promedio → incertidumbre → Q y E. Python recalcula todo desde t₁ y t₂ y marca **✓ coincide con el firmware** o la diferencia.
- C de cada prueba con la media y la banda de incertidumbre, tarjetas con τ, R, V, Q y E, historial de la sesión y exportación CSV.

![Panel de cálculos paso a paso](docs/img/pasos.jpg)

## Instalación

Requiere Python 3.10 o más reciente.

```bash
git clone https://github.com/samuelpabuena2008/capsense-lab.git
cd capsense-lab
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

En Linux o macOS, activa el entorno con `source .venv/bin/activate`.

## Uso

```bash
python -m capsense --demo
```

Abre el navegador en http://127.0.0.1:8050. Otras formas:

| Comando | Qué hace |
|---|---|
| `python -m capsense --demo` | Simulador: no necesita Arduino. Sirve para practicar y de respaldo el día de la expo. |
| `python -m capsense --port auto` | Arduino real, autodetecta el puerto. |
| `python -m capsense --port COM3 --baud 9600` | Arduino con el firmware v2.1. |
| `python -m capsense --replay logs/sesion_..._serial.log` | Reproduce una sesión guardada (log serial o `*_pruebas.csv`). |
| `python -m capsense --host 0.0.0.0` | Permite abrir el dashboard desde otro equipo de la red. |

Todo eso también se elige desde la barra superior del dashboard. Opciones: `python -m capsense --help`.

### En el Arduino

- **Firmware v2.2** ([firmware/capsense_lab_v2_2](firmware/capsense_lab_v2_2/capsense_lab_v2_2.ino)): manda la curva real, t₁ y t₂, y acepta el botón **Medir** del dashboard (envía `M` por serie). 115200 baud.
- **Firmware v2.1**: también funciona (9600 baud). Se mide con el botón START; el dashboard reconstruye t₁ y t₂ desde τ y P y dibuja la curva ajustada.

Las constantes del montaje (V de entrada, resistencias, R del pin) están en [config/capsense.toml](config/capsense.toml) y deben coincidir con las del firmware. Si no coinciden, el dashboard muestra un aviso.

## Estructura

```
src/capsense/
├── domain/      modelos, física (réplica del firmware) y pasos de cálculo — sin serial ni UI
├── io/          parser del protocolo y fuentes: serial, simulador, replay
├── services/    sesión (estado, hilo seguro) y logs/exportación
└── ui/          Dash: layout, callbacks, gráficas, fórmulas, estilo
firmware/        capsense_lab_v2_1 y capsense_lab_v2_2
tests/           unit/, integration/, fixtures/
docs/            arquitectura, protocolo serie, cálculos
scripts/         grabar un log del Arduino, regenerar fixtures
```

Más detalle en [docs/arquitectura.md](docs/arquitectura.md), [docs/protocolo_serial.md](docs/protocolo_serial.md) y [docs/calculos.md](docs/calculos.md).

## Tests

```bash
pytest
pytest -m "not lento"
ruff check src tests
```

`pytest -m "not lento"` omite el barrido de 1 a 1000 µF.

## Solución de problemas

| Problema | Qué hacer |
|---|---|
| "No encuentro ningún Arduino" | Revisa el cable USB (algunos solo cargan). Pulsa ↻ para buscar puertos. |
| "COMx está ocupado" | Cierra el Monitor Serie del IDE de Arduino: solo un programa puede usar el puerto. |
| Llegan caracteres raros o nada | Los baudios no coinciden: 115200 para v2.2, 9600 para v2.1. |
| El botón Medir está apagado | Con la v2.1, en replay o mientras mide no se puede. Usa START en el Arduino. |
| Aviso de calibración distinta | `config/capsense.toml` y el firmware tienen valores diferentes. Corrige uno de los dos. |
| Se soltó el cable | El dashboard reintenta solo (1, 2, 4, 8 s). La medición en curso queda marcada como interrumpida. |
| Sin internet en la expo | No hace falta: Dash, Plotly y MathJax se sirven desde tu PC. |
| Fórmulas sin formato | Recarga la página (F5). |

## Exactitud

El firmware tiene límites conocidos (latencia de `analogRead` con capacitores de 1 a 5 µF con fuga y ruido del ADC con capacitores grandes). Están medidos con el simulador en [docs/calculos.md](docs/calculos.md#9-límites-de-exactitud-del-firmware-medidos-con-el-simulador).
