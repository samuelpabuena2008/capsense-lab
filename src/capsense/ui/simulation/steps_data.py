"""Pasos de la simulación como DATOS (textos editables sin tocar la lógica).

Siguen lo que hace el firmware v2.1 (firmware/capsense_lab_v2_1), línea por línea:
  * el LED amarillo y la LCD "Midiendo i/n" se encienden al empezar medir(), antes de descargar;
  * durante el delay(100) D3 sigue en LOW (sigue descargando);
  * al llegar a t2, modoDescarga() suelta el pin de carga y pone D3 en LOW de nuevo.

Campos:
  titulo, que_pasa      texto para el público (admite {variables}, ver guion.py)
  codigo, linea         fragmento resumido del .ino y la línea activa (índice desde 0)
  pines                 estado por rol: carga (el del rango activo), carga_otro, descarga, lectura
                        valores: high | low | hiz | adc
  leds                  verde / amarillo / rojo (1 = encendido)
  lcd                   las dos líneas de la pantalla (como las escribe el firmware)
  resaltar              ids de board_layout ("@carga" = cable y resistencia del rango activo)
  hoyos, protoboard     hoyos involucrados (se validan contra board_layout) y su explicación
  flujo                 camino de la corriente animado: carga | descarga | None
  segmento              tramo de la curva que se anima: descarga | pausa | hasta_t1 | t1_t2 | None
  lectura_s             segundos de lectura en modo automático (además de la animación)
"""
from __future__ import annotations

CARGA_10K = {"resaltar": ["w-carga0", "r10k"], "hoyos": ["a18", "d18", "d15"],
             "texto": "cable {pin_carga} en a18 → resistencia 10 kΩ de d18 a d15"}
CARGA_1M = {"resaltar": ["w-carga1", "r1m", "puente"], "hoyos": ["a20", "b20", "b17", "a17", "b15"],
            "texto": "cable {pin_carga} en a20 → resistencia 1 MΩ de b20 a b17 → puente de a17 a b15"}

PASOS: dict[str, dict] = {
    "listo": {
        "titulo": "Listo para medir",
        "que_pasa": "El medidor espera. El capacitor está conectado y vacío. Cuando alguien pulsa START, "
                    "empieza la medición.",
        "codigo": ["void entrarListo() {", "  setLeds(true, false, false);   // verde: listo",
                   "  lcdLinea(0, \"CapSense Lab\");", "  lcdLinea(1, \"Pulsa START\");", "}",
                   "// loop(): if (pulsado(0)) medir();"],
        "linea": 5,
        "pines": {"carga": "hiz", "carga_otro": "hiz", "descarga": "low", "lectura": "hiz"},
        "leds": {"verde": 1, "amarillo": 0, "rojo": 0},
        "lcd": ["CapSense Lab", "Pulsa START"],
        "resaltar": ["btn-start", "w-boton_start", "led-verde", "w-led_verde", "lcd"],
        "hoyos": ["e5", "f5", "e7", "f7", "a5", "e30", "e29", "a27"],
        "protoboard": "Botón START en e5/f5/e7/f7 con su cable {pin_start} en a5. LED verde en e30 (+) y e29 (−), "
                      "cable {pin_verde} en a27.",
        "flujo": None, "segmento": None, "lectura_s": 5,
    },
    "descarga": {
        "titulo": "Descarga",
        "que_pasa": "Antes de medir hay que vaciar el capacitor. El pin {pin_descarga} se conecta a tierra y la "
                    "carga sale por la resistencia de 560 Ω, como agua que se va por un desagüe. "
                    "El Arduino espera hasta que el voltaje sea casi cero.",
        "codigo": ["setLeds(false, true, false);        // amarillo: midiendo",
                   "lcdLinea(0, \"Midiendo {i}/{n}\");", "modoDescarga();   // {pin_descarga} LOW, cargas sueltas",
                   "while (analogRead(PIN_LECTURA) > ADC_CERO) {",
                   "  if (millis() - inicio > TIMEOUT_DESCARGA_MS) return RES_NO_DESCARGA;", "}"],
        "linea": 3,
        "pines": {"carga": "hiz", "carga_otro": "hiz", "descarga": "low", "lectura": "adc"},
        "leds": {"verde": 0, "amarillo": 1, "rojo": 0},
        "lcd": ["Midiendo {i}/{n}", "{rango}"],
        "resaltar": ["w-descarga", "r560", "cap", "w-gnd", "w-lectura", "led-amarillo"],
        "hoyos": ["a12", "c12", "c15", "e15", "e16", "a16", "a15"],
        "protoboard": "Cable {pin_descarga} en a12 → resistencia 560 Ω de c12 a c15 → nodo (fila 15) → capacitor "
                      "(+) en e15. El (−) en e16 vuelve a tierra por a16. {pin_lectura} vigila en a15.",
        "flujo": "descarga", "segmento": "descarga", "lectura_s": 4,
    },
    "pausa": {
        "titulo": "Pausa de 100 ms",
        "que_pasa": "Una pausa corta para que todo se asiente. {pin_descarga} sigue conectado a tierra, así que "
                    "el capacitor termina de vaciarse.",
        "codigo": ["while (analogRead(PIN_LECTURA) > ADC_CERO) { ... }", "delay(100);"],
        "linea": 1,
        "pines": {"carga": "hiz", "carga_otro": "hiz", "descarga": "low", "lectura": "hiz"},
        "leds": {"verde": 0, "amarillo": 1, "rojo": 0},
        "lcd": ["Midiendo {i}/{n}", "{rango}"],
        "resaltar": ["w-descarga", "r560", "cap"],
        "hoyos": ["a12", "c12", "c15", "e15"],
        "protoboard": "Sigue activo el camino de descarga: a12 → 560 Ω (c12 a c15) → capacitor en e15.",
        "flujo": "descarga", "segmento": "pausa", "lectura_s": 3,
    },
    "disparo": {
        "titulo": "Arranca la carga",
        "que_pasa": "El Arduino suelta {pin_descarga} y pone {pin_carga} en 5 V. La corriente sale por "
                    "{pin_carga}, cruza la resistencia de {r_txt} y llena el capacitor. Justo en ese momento "
                    "arranca el cronómetro.",
        "codigo": ["modoCarga(r);          // {pin_descarga} suelto, {pin_carga} como salida",
                   "unsigned long t0 = micros();   // cronómetro en cero",
                   "digitalWrite(PIN_R[r], HIGH);  // {pin_carga} = 5 V"],
        "linea": 2,
        "pines": {"carga": "high", "carga_otro": "hiz", "descarga": "hiz", "lectura": "hiz"},
        "leds": {"verde": 0, "amarillo": 1, "rojo": 0},
        "lcd": ["Midiendo {i}/{n}", "{rango}"],
        "resaltar": ["@carga", "cap", "w-gnd"],
        "hoyos": ["e15", "e16", "a16"],
        "protoboard": "{carga_texto} → nodo (fila 15) → capacitor (+) en e15; el (−) en e16 va a tierra por a16.",
        "flujo": "carga", "segmento": None, "lectura_s": 4,
    },
    "lectura": {
        "titulo": "Lectura continua",
        "que_pasa": "Mientras el capacitor se llena, {pin_lectura} mide su voltaje una y otra vez, unas 9000 veces "
                    "por segundo, y el cronómetro sigue corriendo.",
        "codigo": ["while (true) {", "  unsigned long dt = micros() - t0;",
                   "  int lectura = analogRead(PIN_LECTURA);   // ~112 µs",
                   "  if (t1 == 0 && lectura >= ADC_N1) { ... }", "  if (lectura >= ADC_N2) { ... }", "}"],
        "linea": 2,
        "pines": {"carga": "high", "carga_otro": "hiz", "descarga": "hiz", "lectura": "adc"},
        "leds": {"verde": 0, "amarillo": 1, "rojo": 0},
        "lcd": ["Midiendo {i}/{n}", "{rango}"],
        "resaltar": ["@carga", "cap", "w-gnd", "w-lectura"],
        "hoyos": ["a15", "e15"],
        "protoboard": "Cable {pin_lectura} en a15, en la misma fila que el (+) del capacitor (e15).",
        "flujo": "carga", "segmento": "hasta_t1", "lectura_s": 3,
    },
    "t1": {
        "titulo": "Primer punto: ADC = 250",
        "que_pasa": "El voltaje llegó a 250 de 1023 (un cuarto del máximo). El Arduino anota la hora: "
                    "t₁ = {t1}.",
        "codigo": ["if (t1 == 0 && lectura >= ADC_N1) {   // 250", "  t1 = dt;",
                   "  if (t1 < tMin) { modoDescarga(); return RES_RAPIDO; }",
                   "  if (USAR_AUTORANGO && r > 0 && t1 > T1_MAX_US) { ... return RES_LENTO; }", "}"],
        "linea": 1,
        "pines": {"carga": "high", "carga_otro": "hiz", "descarga": "hiz", "lectura": "adc"},
        "leds": {"verde": 0, "amarillo": 1, "rojo": 0},
        "lcd": ["Midiendo {i}/{n}", "{rango}"],
        "resaltar": ["@carga", "cap", "w-lectura"],
        "hoyos": ["a15", "e15"],
        "protoboard": "La lectura sigue entrando por {pin_lectura} en a15.",
        "flujo": "carga", "segmento": None, "lectura_s": 4,
    },
    "t2": {
        "titulo": "Segundo punto: ADC = 700",
        "que_pasa": "Llegó a 700 de 1023. El Arduino anota t₂ = {t2} y deja de cargar: suelta {pin_carga} y "
                    "vuelve a poner {pin_descarga} a tierra.",
        "codigo": ["if (lectura >= ADC_N2) {   // 700", "  t2 = dt;", "  break;", "}",
                   "modoDescarga();   // {pin_carga} suelto, {pin_descarga} LOW"],
        "linea": 1,
        "pines": {"carga": "high", "carga_otro": "hiz", "descarga": "hiz", "lectura": "adc"},
        "leds": {"verde": 0, "amarillo": 1, "rojo": 0},
        "lcd": ["Midiendo {i}/{n}", "{rango}"],
        "resaltar": ["@carga", "cap", "w-lectura"],
        "hoyos": ["a15", "e15"],
        "protoboard": "Después de t₂ el camino activo vuelve a ser a12 → 560 Ω → e15 (descarga).",
        "flujo": "carga", "segmento": "t1_t2", "lectura_s": 4,
    },
    "ajuste": {
        "titulo": "Ajuste de la curva",
        "que_pasa": "Con solo dos tiempos el Arduino reconstruye toda la curva. Prueba valores de la meseta P "
                    "partiendo el intervalo a la mitad 30 veces hasta que la curva pase por los dos puntos, "
                    "y de ahí saca τ = {tau}.",
        "codigo": ["float r = t2 / t1;", "for (uint8_t i = 0; i < 30; i++) {", "  float mid = 0.5 * (lo + hi);",
                   "  if (razonP(mid) > r) lo = mid; else hi = mid;", "}",
                   "tau = 0.5 * (t1 / -log(1 - N1/P) + t2 / -log(1 - N2/P));"],
        "linea": 3,
        "pines": {"carga": "hiz", "carga_otro": "hiz", "descarga": "low", "lectura": "hiz"},
        "leds": {"verde": 0, "amarillo": 1, "rojo": 0},
        "lcd": ["Midiendo {i}/{n}", "{rango}"],
        "resaltar": ["cap"],
        "hoyos": ["e15", "e16"],
        "protoboard": "Aquí todo pasa dentro del Arduino; en la placa, el capacitor (e15 y e16) se va descargando.",
        "flujo": "descarga", "segmento": None, "lectura_s": 7,
    },
    "calculo": {
        "titulo": "Cálculo de C",
        "que_pasa": "τ dice qué tan lento se llena el capacitor. Dividiendo τ por la resistencia sale la "
                    "capacitancia de esta prueba: C = {c_prueba}.",
        "codigo": ["c[i] = tau[i] / (R_REAL[rango] + R_PIN_ON) * 1000000.0 * K_CAL;",
                   "if (c[i] < C_MIN_UF) { mostrarError(\"Sin capacitor\"); return; }"],
        "linea": 0,
        "pines": {"carga": "hiz", "carga_otro": "hiz", "descarga": "low", "lectura": "hiz"},
        "leds": {"verde": 0, "amarillo": 1, "rojo": 0},
        "lcd": ["Midiendo {i}/{n}", "{rango}"],
        "resaltar": ["@carga", "cap"],
        "hoyos": ["e15"],
        "protoboard": "La R del cálculo es la que se usó: {carga_texto}.",
        "flujo": None, "segmento": None, "lectura_s": 6,
    },
    "autorango": {
        "titulo": "Autorango: cambio a 1 MΩ",
        "que_pasa": "El capacitor es tan chico que con 10 kΩ se llenó demasiado rápido (t₁ = {t1_rapido}, menos "
                    "de 3 ms). El Arduino cambia a la resistencia de 1 MΩ, que lo llena 100 veces más lento, "
                    "y repite la prueba.",
        "codigo": ["if (t1 < tMin) { modoDescarga(); return RES_RAPIDO; }   // tMin = 3 ms",
                   "...", "if (res == RES_RAPIDO && USAR_AUTORANGO && rango < N_RANGOS - 1) {",
                   "  rango++;   // {pin_carga_10k} -> {pin_carga_1m}", "  continue;", "}"],
        "linea": 3,
        "pines": {"carga": "high", "carga_otro": "hiz", "descarga": "hiz", "lectura": "adc"},
        "leds": {"verde": 0, "amarillo": 1, "rojo": 0},
        "lcd": ["Midiendo 1/{n}", "1M"],
        "resaltar": ["w-carga1", "r1m", "puente", "cap", "w-lectura"],
        "hoyos": ["b15", "a17", "b17", "b20", "a20"],
        "protoboard": "Ahora carga {pin_carga_1m} en a20 → 1 MΩ de b20 a b17 → puente de a17 a b15 → nodo del "
                      "capacitor.",
        "flujo": "carga", "segmento": None, "lectura_s": 7,
    },
    "repeticiones": {
        "titulo": "Repeticiones",
        "que_pasa": "Una sola medida puede tener errores, así que el Arduino repite todo {n} veces "
                    "(menos veces si el capacitor es grande, para no esperar tanto). Pruebas: {lista_c}.",
        "codigo": ["for (uint8_t i = 0; i < nPruebas; i++) {", "  ... medirUnaVez(...) ...",
                   "  if (i == 0) nPruebas = (tau[0] < 1.0) ? 5 : ((tau[0] < 4.0) ? 3 : 2);", "}"],
        "linea": 2,
        "pines": {"carga": "high", "carga_otro": "hiz", "descarga": "hiz", "lectura": "adc"},
        "leds": {"verde": 0, "amarillo": 1, "rojo": 0},
        "lcd": ["Midiendo {n}/{n}", "{rango}"],
        "resaltar": ["@carga", "w-descarga", "r560", "cap", "w-lectura"],
        "hoyos": ["a12", "c12", "c15", "e15", "e16", "a16"],
        "protoboard": "Cada repetición alterna los dos caminos: descarga (a12 → 560 Ω) y carga ({carga_texto}).",
        "flujo": "carga", "segmento": None, "lectura_s": 6,
    },
    "resultado": {
        "titulo": "Resultado",
        "que_pasa": "Listo: el capacitor mide {c_final} ± {inc}. Guarda {q} de carga y {e} de energía. "
                    "La luz verde y la pantalla muestran el resultado.",
        "codigo": ["cProm = sumaC / nPruebas;", "incPct = (cMax - cMin) / 2.0 / cProm * 100.0;",
                   "qUC = cProm * V_ENTRADA;", "eUJ = 0.5 * cProm * V_ENTRADA * V_ENTRADA;",
                   "setLeds(true, false, false);   // verde", "mostrarPantalla();"],
        "linea": 4,
        "pines": {"carga": "hiz", "carga_otro": "hiz", "descarga": "low", "lectura": "hiz"},
        "leds": {"verde": 1, "amarillo": 0, "rojo": 0},
        "lcd": ["{lcd_c}", "{lcd_inc}"],
        "resaltar": ["led-verde", "w-led_verde", "lcd"],
        "hoyos": ["e30", "e29", "a27"],
        "protoboard": "LED verde: cable {pin_verde} en a27 → 220 Ω de c27 a c30 → LED de e30 (+) a e29 (−) → "
                      "tierra por a29.",
        "flujo": None, "segmento": None, "lectura_s": 10,
    },
    "error": {
        "titulo": "Error: {error}",
        "que_pasa": "La medición no se pudo completar: {explicacion_error}",
        "codigo": ["void mostrarError(const char* msg) {", "  setLeds(false, false, true);   // rojo",
                   "  lcdLinea(0, \"ERROR\");", "  lcdLinea(1, msg);", "}"],
        "linea": 1,
        "pines": {"carga": "hiz", "carga_otro": "hiz", "descarga": "low", "lectura": "hiz"},
        "leds": {"verde": 0, "amarillo": 0, "rojo": 1},
        "lcd": ["ERROR", "{error}"],
        "resaltar": ["led-rojo", "w-led_rojo", "lcd"],
        "hoyos": ["e22", "e21", "a19"],
        "protoboard": "LED rojo: cable {pin_rojo} en a19 → 220 Ω de c19 a c22 → LED de e22 (+) a e21 (−).",
        "flujo": None, "segmento": None, "lectura_s": 10,
    },
}

EXPLICACION_ERROR = {
    "Fuga muy alta": "el capacitor pierde carga tan rápido que nunca llega a 700. Puede estar dañado o al revés.",
    "Sin capacitor": "se llenó instantáneamente: no hay capacitor o es demasiado chico.",
    "Muy grande": "tarda más de 25 s en llenarse: el capacitor es demasiado grande para este medidor.",
    "No descarga": "no logró vaciarse en 8 s.",
}

ESTADO_PIN = {
    "high": ("OUTPUT HIGH", "5 V"),
    "low": ("OUTPUT LOW", "0 V"),
    "hiz": ("INPUT", "alta impedancia"),
    "adc": ("LECTURA ANALÓGICA", "mide el voltaje"),
}
