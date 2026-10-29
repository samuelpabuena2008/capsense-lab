// CapSense Lab v2.1 - medidor de capacitancia RC (1 uF a 1000 uF) con LCD 16x2, 3 botones y 3 LEDs
// Arduino Uno. Libreria: LiquidCrystal (ya viene con el IDE).
//
// QUE HACE
//  - Mide cualquier capacitor entre ~1 uF y ~1000 uF y muestra SU capacitancia como resultado
//    (en uF, o en mF si pasa de 1000 uF). No compara contra ningun valor esperado.
//  - Mide el tiempo en que el voltaje cruza dos niveles (250 y 700 del ADC) y resuelve la curva de
//    carga V(t) = P (1 - e^(-t/tau)) para tau y para la meseta P. Asi la fuga del capacitor no
//    infla la medida.
//  - Hace varias pruebas (5; 3 si tau > 1 s; 2 si tau > 4 s) y muestra el promedio y la
//    incertidumbre (+/- media diferencia entre la mayor y la menor).
//  - AUTORANGO automatico: empieza con 10 kohm y, si el capacitor es chico (1 a 3 uF), cambia solo a
//    1 Mohm. Si no cableas la de 1 Mohm, pon USAR_AUTORANGO = false y mide desde unos 3 uF.
//
// ---------------- MONTAJE (igual que el v1.4) ----------------
//   MEDICION: 560 ohm c12->c15 | carga 10 kohm d15->d18 | Capacitor (+) e15, (-) e16
//             D3 -> a12 (descarga) | A0 -> a15 (lectura) | D2 -> a18 (carga 10k) | GND -> a16
//   LEDs:     Verde D4 (listo) | Amarillo D5 (midiendo) | Rojo D6 (error)
//   BOTONES:  ATRAS A1 | START A2 | SIGUIENTE A3
//   LCD:      RS D12, E D11, DB4..DB7 = D10, D9, D8, D7
//
// PARA EL AUTORANGO agrega 1 resistencia de 1 Mohm (etapa 6 del artifact):
//   Puente b15 -> a17          (lleva el nodo del capacitor a la fila 17)
//   Resistencia 1 Mohm  b17 -> b20
//   Cable A5 -> a20
//
// COMO SE USA
//  START      : mide y muestra el reporte. El reporte cambia solo de pantalla cada 2,5 s.
//  SIGUIENTE / ATRAS : cambian de pantalla a mano (y detienen el cambio automatico).

#include <LiquidCrystal.h>

// ---------- pines ----------
const uint8_t PIN_DESCARGA = 3;
const uint8_t PIN_LECTURA  = A0;
const uint8_t LED_VERDE    = 4;
const uint8_t LED_AMARILLO = 5;
const uint8_t LED_ROJO     = 6;
const uint8_t BTN[3]       = {A2, A3, A1};   // 0 = START, 1 = SIGUIENTE, 2 = ATRAS
const uint8_t PIN_BUZZER   = 13;
const bool USAR_BUZZER     = false;

LiquidCrystal lcd(12, 11, 10, 9, 8, 7);       // RS, E, DB4, DB5, DB6, DB7

// ---------- resistencias de carga (de menor a mayor) ----------
const uint8_t N_RANGOS = 2;
const uint8_t PIN_R[N_RANGOS]  = {2, A5};                 // 10 kohm | 1 Mohm
const float   R_REAL[N_RANGOS] = {9790.0, 996000.0};      // ohm, medidas con el multimetro
const char*   R_ETIQ[N_RANGOS] = {"10k", "1M"};
const float   R_PIN_ON         = 25.0;                    // ohm: resistencia interna aprox. del pin
const bool    USAR_AUTORANGO   = true;                    // requiere la resistencia de 1 Mohm cableada (etapa 6)

// ---------- calibracion ----------
const float V_ENTRADA = 4.92;      // V: voltaje real del pin 5V
const float K_CAL     = 1.0;       // C_final = C_medida * K_CAL (1.0 = sin correccion)

// ---------- parametros de medicion ----------
const uint8_t N_MAX = 5;
const float   C_MIN_UF = 0.5;                      // por debajo: "sin capacitor"
const float   ADC_N1 = 250.0, ADC_N2 = 700.0;      // niveles del ajuste de curva
const float   ADC_MAX = 1023.0;
const int     ADC_CERO = 5;
const unsigned long T1_MIN_AUTO_US = 3000UL;       // t(250) menor -> subir a 1M
const unsigned long T1_MIN_FIJO_US = 1500UL;       // sin autorango: acepta hasta ~0,5 uF (poca precision)
const unsigned long T1_MAX_US      = 2500000UL;    // t(250) mayor (en 1M) -> bajar a 10k
const unsigned long TIMEOUT_DESCARGA_MS = 8000;
const unsigned long TIMEOUT_CARGA_US    = 25000000UL;   // 25 s

enum Estado { LISTO, REPORTE, ERROR_ESTADO };
Estado estado = LISTO;

// ---------- resultados ----------
float cProm = 0, cMin = 0, cMax = 0, tauPromMs = 0, incPct = 0, qUC = 0, eUJ = 0, mesetaPct = 100;
uint8_t rango = 0, nPruebas = N_MAX;
uint8_t idxPantalla = 0;
const uint8_t N_PANTALLAS = 5;
bool autoCiclo = false;
unsigned long tPantalla = 0;
const unsigned long MS_POR_PANTALLA = 2500;
const char* mensajeError = "";

// ---------- botones (antirrebote) ----------
bool ultimoLeido[3] = {HIGH, HIGH, HIGH};
bool estable[3]     = {HIGH, HIGH, HIGH};
unsigned long tCambio[3] = {0, 0, 0};

bool pulsado(uint8_t i) {
  bool lec = digitalRead(BTN[i]);
  if (lec != ultimoLeido[i]) { tCambio[i] = millis(); ultimoLeido[i] = lec; }
  if (millis() - tCambio[i] > 30 && lec != estable[i]) {
    estable[i] = lec;
    if (lec == LOW) return true;
  }
  return false;
}

void descartarBotones() {
  for (uint8_t i = 0; i < 3; i++) {
    ultimoLeido[i] = digitalRead(BTN[i]);
    estable[i] = ultimoLeido[i];
    tCambio[i] = millis();
  }
}

// ---------- utilidades ----------
void setLeds(bool verde, bool amarillo, bool rojo) {
  digitalWrite(LED_VERDE, verde);
  digitalWrite(LED_AMARILLO, amarillo);
  digitalWrite(LED_ROJO, rojo);
}

void pitido(unsigned int ms) {
  if (!USAR_BUZZER) return;
  digitalWrite(PIN_BUZZER, HIGH);
  delay(ms);
  digitalWrite(PIN_BUZZER, LOW);
}

void lcdLinea(uint8_t fila, const char* txt) {
  char b[17];
  snprintf(b, sizeof(b), "%-16s", txt);
  lcd.setCursor(0, fila);
  lcd.print(b);
}

void soltarCargas() {
  for (uint8_t i = 0; i < N_RANGOS; i++) {
    digitalWrite(PIN_R[i], LOW);
    pinMode(PIN_R[i], INPUT);
  }
}

void modoDescarga() {
  soltarCargas();
  pinMode(PIN_DESCARGA, OUTPUT);
  digitalWrite(PIN_DESCARGA, LOW);
}

void modoCarga(uint8_t r) {
  digitalWrite(PIN_DESCARGA, LOW);
  pinMode(PIN_DESCARGA, INPUT);
  pinMode(PIN_R[r], OUTPUT);
}

// ---------- ajuste de curva ----------
// t2/t1 = ln(1 - N2/P) / ln(1 - N1/P), y esa razon baja cuando P sube.
float razonP(float P) { return log(1.0 - ADC_N2 / P) / log(1.0 - ADC_N1 / P); }

void ajustarCurva(float t1, float t2, float &tau, float &P) {
  float r = t2 / t1;
  float lo = ADC_N2 + 2.0, hi = ADC_MAX;
  if (r <= razonP(hi)) {
    P = hi;                      // sin fuga: la meseta llega al maximo del ADC
  } else if (r >= razonP(lo)) {
    P = lo;
  } else {
    for (uint8_t i = 0; i < 30; i++) {
      float mid = 0.5 * (lo + hi);
      if (razonP(mid) > r) lo = mid; else hi = mid;
    }
    P = 0.5 * (lo + hi);
  }
  float tau1 = t1 / (-log(1.0 - ADC_N1 / P));
  float tau2 = t2 / (-log(1.0 - ADC_N2 / P));
  tau = 0.5 * (tau1 + tau2);
}

// ---------- una medicion (bloqueante) ----------
// Resultados de una medicion (se usan numeros y no un enum para que el IDE de Arduino no se confunda)
const uint8_t RES_OK = 0, RES_NO_DESCARGA = 1, RES_RAPIDO = 2, RES_LENTO = 3, RES_NO_LLEGA = 4;

uint8_t medirUnaVez(uint8_t r, float &tauSeg, float &meseta) {
  modoDescarga();
  unsigned long inicio = millis();
  while (analogRead(PIN_LECTURA) > ADC_CERO) {
    if (millis() - inicio > TIMEOUT_DESCARGA_MS) return RES_NO_DESCARGA;
  }
  delay(100);

  modoCarga(r);
  unsigned long t0 = micros();
  digitalWrite(PIN_R[r], HIGH);
  unsigned long t1 = 0, t2 = 0;
  unsigned long tMin = USAR_AUTORANGO ? T1_MIN_AUTO_US : T1_MIN_FIJO_US;
  while (true) {
    unsigned long dt = micros() - t0;
    int lectura = analogRead(PIN_LECTURA);
    if (t1 == 0 && lectura >= ADC_N1) {
      t1 = dt;
      if (t1 < tMin) { modoDescarga(); return RES_RAPIDO; }
      if (USAR_AUTORANGO && r > 0 && t1 > T1_MAX_US) { modoDescarga(); return RES_LENTO; }
    }
    if (lectura >= ADC_N2) { t2 = dt; break; }
    if (dt > TIMEOUT_CARGA_US) { modoDescarga(); return (t1 == 0) ? RES_LENTO : RES_NO_LLEGA; }
  }
  modoDescarga();
  if (t2 <= t1) return RES_RAPIDO;

  float tauS, P;
  ajustarCurva((float)t1, (float)t2, tauS, P);
  tauSeg = tauS / 1000000.0;
  meseta = P;
  return RES_OK;
}

// ---------- pantallas ----------
void formatoC(float cUF, char* out, size_t n) {
  char a[14];
  if (cUF >= 1000.0) {
    dtostrf(cUF / 1000.0, 1, 3, a);
    snprintf(out, n, "C=%s mF", a);
  } else if (cUF >= 10.0) {
    dtostrf(cUF, 1, 2, a);
    snprintf(out, n, "C=%s uF", a);
  } else {
    dtostrf(cUF, 1, 3, a);
    snprintf(out, n, "C=%s uF", a);
  }
}

void mostrarPantalla() {
  char l1[17], l2[17], a[14], b[14], c[14];
  switch (idxPantalla) {
    case 0:
      formatoC(cProm, l1, sizeof(l1));
      dtostrf(incPct, 1, 2, b);
      snprintf(l2, sizeof(l2), "+/-%s%% n=%d", b, nPruebas);
      break;
    case 1:
      if (tauPromMs < 1000.0) {
        dtostrf(tauPromMs, 1, 1, a);
        snprintf(l1, sizeof(l1), "tau=%s ms", a);
      } else {
        dtostrf(tauPromMs / 1000.0, 1, 3, a);
        snprintf(l1, sizeof(l1), "tau=%s s", a);
      }
      dtostrf(R_REAL[rango] / 1000.0, 1, 1, b);
      dtostrf(V_ENTRADA, 1, 2, c);
      snprintf(l2, sizeof(l2), "R=%sk V=%sV", b, c);
      break;
    case 2:
      dtostrf(qUC, 1, 1, a);
      snprintf(l1, sizeof(l1), "Q=%s uC", a);
      dtostrf(eUJ, 1, 1, b);
      snprintf(l2, sizeof(l2), "E=%s uJ", b);
      break;
    case 3:
      dtostrf(cMin, 1, 2, a);
      snprintf(l1, sizeof(l1), "min %s uF", a);
      dtostrf(cMax, 1, 2, b);
      snprintf(l2, sizeof(l2), "max %s uF", b);
      break;
    default:
      dtostrf(mesetaPct, 1, 1, a);
      snprintf(l1, sizeof(l1), "Meseta=%s%%", a);
      snprintf(l2, sizeof(l2), "%s", mesetaPct > 98.0 ? "Fuga: baja" : (mesetaPct > 93.0 ? "Fuga: media" : "Fuga: alta"));
      break;
  }
  lcdLinea(0, l1);
  lcdLinea(1, l2);
}

void entrarListo() {
  estado = LISTO;
  setLeds(true, false, false);
  lcdLinea(0, "CapSense Lab");
  lcdLinea(1, "Pulsa START");
}

void mostrarError(const char* msg) {
  estado = ERROR_ESTADO;
  setLeds(false, false, true);
  lcdLinea(0, "ERROR");
  lcdLinea(1, msg);
  Serial.print(F("ERROR: "));
  Serial.println(msg);
  pitido(600);
}

const char* textoError(uint8_t r) {
  switch (r) {
    case RES_NO_DESCARGA: return "No descarga";
    case RES_RAPIDO:      return USAR_AUTORANGO ? "Sin capacitor" : "Muy chico";
    case RES_LENTO:       return "Muy grande";
    default:              return "Fuga muy alta";
  }
}

// ---------- secuencia completa de medicion ----------
void medir() {
  setLeds(false, true, false);
  float tau[N_MAX];
  float c[N_MAX];
  float sumaP = 0;
  char l[17];
  rango = 0;
  nPruebas = N_MAX;

  Serial.println(F("prueba,R,meseta,tau_ms,C_uF"));
  for (uint8_t i = 0; i < nPruebas; i++) {
    snprintf(l, sizeof(l), "Midiendo %d/%d", i + 1, nPruebas);
    lcdLinea(0, l);
    lcdLinea(1, R_ETIQ[rango]);

    float P = 0;
    uint8_t res = RES_OK;
    for (uint8_t intento = 0; intento < N_RANGOS + 1; intento++) {
      res = medirUnaVez(rango, tau[i], P);
      if (res == RES_RAPIDO && USAR_AUTORANGO && rango < N_RANGOS - 1) { rango++; continue; }
      if (res == RES_LENTO  && USAR_AUTORANGO && rango > 0)            { rango--; continue; }
      break;
    }
    if (res != RES_OK) {
      mostrarError(textoError(res));
      descartarBotones();
      return;
    }
    c[i] = tau[i] / (R_REAL[rango] + R_PIN_ON) * 1000000.0 * K_CAL;
    if (c[i] < C_MIN_UF) {
      mostrarError("Sin capacitor");
      descartarBotones();
      return;
    }
    sumaP += P;
    Serial.print(i + 1);              Serial.print(',');
    Serial.print(R_ETIQ[rango]);      Serial.print(',');
    Serial.print(P, 1);               Serial.print(',');
    Serial.print(tau[i] * 1000.0, 3); Serial.print(',');
    Serial.println(c[i], 3);

    if (i == 0) {                     // capacitores grandes: menos pruebas para no esperar tanto
      nPruebas = (tau[0] < 1.0) ? 5 : ((tau[0] < 4.0) ? 3 : 2);
    }
  }

  float sumaC = 0, sumaT = 0;
  cMin = c[0];
  cMax = c[0];
  for (uint8_t i = 0; i < nPruebas; i++) {
    sumaC += c[i];
    sumaT += tau[i];
    if (c[i] < cMin) cMin = c[i];
    if (c[i] > cMax) cMax = c[i];
  }
  cProm = sumaC / nPruebas;
  tauPromMs = sumaT / nPruebas * 1000.0;
  mesetaPct = sumaP / nPruebas / ADC_MAX * 100.0;
  incPct = (cMax - cMin) / 2.0 / cProm * 100.0;
  qUC = cProm * V_ENTRADA;                       // uF * V = uC
  eUJ = 0.5 * cProm * V_ENTRADA * V_ENTRADA;     // uF * V^2 / 2 = uJ

  Serial.println(F("---------- RESULTADO ----------"));
  Serial.print(F("Pruebas   = "));  Serial.println(nPruebas);
  Serial.print(F("R carga   = "));  Serial.print(R_REAL[rango] + R_PIN_ON, 1); Serial.println(F(" ohm"));
  Serial.print(F("V entrada = "));  Serial.print(V_ENTRADA, 2); Serial.println(F(" V"));
  Serial.print(F("tau       = "));  Serial.print(tauPromMs, 3);  Serial.println(F(" ms"));
  Serial.print(F("C         = "));  Serial.print(cProm, 3);      Serial.print(F(" uF  (+/- "));
  Serial.print(incPct, 2);         Serial.println(F(" %)"));
  Serial.print(F("C min/max = "));  Serial.print(cMin, 3);       Serial.print(F(" / "));
  Serial.print(cMax, 3);           Serial.println(F(" uF"));
  Serial.print(F("Q         = "));  Serial.print(qUC, 3);        Serial.println(F(" uC"));
  Serial.print(F("E         = "));  Serial.print(eUJ, 3);        Serial.println(F(" uJ"));
  Serial.print(F("Meseta    = "));  Serial.print(mesetaPct, 1);   Serial.println(F(" %"));
  Serial.println(F("CSV (tau_ms,C_uF,Q_uC,E_uJ,incert_pct,meseta_pct,R_ohm):"));
  Serial.print(tauPromMs, 3);  Serial.print(',');
  Serial.print(cProm, 3);      Serial.print(',');
  Serial.print(qUC, 3);        Serial.print(',');
  Serial.print(eUJ, 3);        Serial.print(',');
  Serial.print(incPct, 2);     Serial.print(',');
  Serial.print(mesetaPct, 1);  Serial.print(',');
  Serial.println(R_REAL[rango] + R_PIN_ON, 0);
  Serial.println();

  idxPantalla = 0;
  autoCiclo = true;
  tPantalla = millis();
  estado = REPORTE;
  setLeds(true, false, false);
  mostrarPantalla();
  pitido(120);
  descartarBotones();
}

void setup() {
  Serial.begin(9600);
  pinMode(LED_VERDE, OUTPUT);
  pinMode(LED_AMARILLO, OUTPUT);
  pinMode(LED_ROJO, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  for (uint8_t i = 0; i < 3; i++) pinMode(BTN[i], INPUT_PULLUP);
  soltarCargas();
  modoDescarga();

  lcd.begin(16, 2);
  lcdLinea(0, "CapSense Lab v2.1");
  lcdLinea(1, "Iniciando...");
  setLeds(true, true, true);          // prueba de LEDs
  delay(1200);
  Serial.println(F("=== CapSense Lab v2.1 ==="));
  Serial.println(F("Rango: 1 uF a 1000 uF. Pulsa START para medir."));
  descartarBotones();
  entrarListo();
}

void loop() {
  bool start = pulsado(0);
  bool sig   = pulsado(1);
  bool atras = pulsado(2);

  switch (estado) {
    case LISTO:
    case ERROR_ESTADO:
      if (start) medir();
      break;
    case REPORTE:
      if (start) {
        medir();
      } else if (sig) {
        autoCiclo = false;
        idxPantalla = (idxPantalla + 1) % N_PANTALLAS;
        mostrarPantalla();
      } else if (atras) {
        autoCiclo = false;
        idxPantalla = (idxPantalla + N_PANTALLAS - 1) % N_PANTALLAS;
        mostrarPantalla();
      } else if (autoCiclo && millis() - tPantalla >= MS_POR_PANTALLA) {
        idxPantalla = (idxPantalla + 1) % N_PANTALLAS;
        tPantalla = millis();
        mostrarPantalla();
      }
      break;
  }
}
