// CapSense Lab v2.3 - medidor de capacitancia RC (1 uF a 1000 uF) con LCD 16x2, 3 botones y 3 LEDs
// Arduino Uno. Libreria: LiquidCrystal (ya viene con el IDE).
//
// NOVEDADES v2.3 (mas exactitud al detectar t1 y t2)
//  - Los cruces de 250 y 700 se detectan sobre la MEDIA MOVIL de las ultimas 8 lecturas (con su tiempo
//    medio), no sobre una lectura suelta: el ruido del ADC ya no adelanta el cruce en las curvas lentas.
//  - El instante del cruce se INTERPOLA entre la vuelta anterior y la actual, y se corrige el retardo
//    entre micros() y el muestreo del ADC: ya no se pierde hasta una vuelta del bucle (~116 us), que
//    pesaba en los capacitores chicos en 10k.
//  - En el simulador del dashboard el peor error pasa de ~5 % a ~0,7 % (ver docs/calculos.md).
//    Por vuelta solo se agregan sumas y restas de enteros; la cuenta en float se hace solo en el cruce.
//  - t1 y t2 salen por Serial con un decimal (#PRUEBA,...). Todo lo demas es igual a la v2.2.
//
// NOVEDADES v2.2 (la medicion es la misma que en la v2.1)
//  - Captura la curva de carga real: hasta 100 muestras (tiempo, ADC) con espaciado geometrico
//    (desde 0,5 ms, razon 1,1147: cubre hasta ~23 s). Se guardan en RAM durante la carga y se envian
//    por Serial DESPUES de cada prueba: no hay ningun Serial.print mientras se mide t1 y t2.
//  - La ultima prueba sigue cargando despues de t2 (hasta ADC >= 1015 u 8 s extra) para ver la meseta.
//    t1 y t2 se capturan igual que en las demas pruebas.
//  - Serial a 115200 baud y protocolo con prefijo '#' para el dashboard (ver docs/protocolo_serial.md).
//    Se conserva la salida legible de siempre para el Monitor Serie.
//  - Comandos por Serial: 'M' = medir (igual que START), 'V' = version y configuracion.
//  - LCD, LEDs, botones, autorango y ajustarCurva quedan identicos a la v2.1.
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
//  Desde el PC: enviar "M" por Serial (115200 baud) equivale a START.

#include <LiquidCrystal.h>

#define VERSION_FW "2.3"

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

// ---------- captura de la curva (v2.2) ----------
// 100 x (4 + 2) bytes = 600 bytes de RAM.
const uint8_t       N_MUESTRAS     = 100;
const unsigned long T_MUESTRA0_US  = 500UL;        // primera muestra a 0,5 ms
const float         RAZON_MUESTRA  = 1.1147;       // cada muestra ~11 % mas tarde que la anterior
const int           ADC_EXT_FIN    = 1015;         // la prueba extendida termina aqui...
const unsigned long EXT_MAX_US     = 8000000UL;    // ...o 8 s despues de t2
uint32_t muestraT[N_MUESTRAS];
uint16_t muestraADC[N_MUESTRAS];
uint8_t  nMuestras = 0;

// ---------- deteccion de cruces (v2.3) ----------
// Media movil de las ultimas VENTANA lecturas, con su tiempo medio. 8 x (4 + 2) = 48 bytes.
const uint8_t  VENTANA = 8;
const uint16_t N1_ENTERO = 250, N2_ENTERO = 700;   // = ADC_N1, ADC_N2
const float    OFFSET_MUESTREO_US = 8.0;           // el ADC muestrea ~12 us despues de micros(); la carga empieza ~4 us despues de t0
uint32_t ventT[VENTANA];
uint16_t ventA[VENTANA];

// Instante en que la media movil cruzo el nivel n, interpolando entre la vuelta anterior y la actual.
float instanteCruce(float n, uint32_t sT, uint16_t sA, uint8_t cnt, uint32_t pT, uint16_t pA, uint8_t pCnt) {
  float tm = (float)sT / cnt + OFFSET_MUESTREO_US;
  float am = (float)sA / cnt;
  if (pCnt == 0) return tm;
  float tp = (float)pT / pCnt + OFFSET_MUESTREO_US;
  float ap = (float)pA / pCnt;
  if (am <= ap) return tm;
  return tp + (n - ap) / (am - ap) * (tm - tp);
}

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

// ---------- protocolo para el PC (v2.2) ----------
void imprimirConfig() {
  Serial.println(F("#VERSION," VERSION_FW));
  Serial.print(F("#CONFIG,"));
  Serial.print(V_ENTRADA, 2);  Serial.print(',');
  Serial.print(R_REAL[0], 0);  Serial.print(',');
  Serial.print(R_REAL[1], 0);  Serial.print(',');
  Serial.print(R_PIN_ON, 1);   Serial.print(',');
  Serial.print(K_CAL, 3);      Serial.print(',');
  Serial.print(ADC_N1, 0);     Serial.print(',');
  Serial.println(ADC_N2, 0);
}

void imprimirRango(uint8_t r) {
  Serial.print(F("#RANGO,"));
  Serial.print(r);                       Serial.print(',');
  Serial.print(R_ETIQ[r]);               Serial.print(',');
  Serial.println(R_REAL[r] + R_PIN_ON, 0);
}

void volcarMuestras() {
  for (uint8_t k = 0; k < nMuestras; k++) {
    Serial.print(F("#MUESTRA,"));
    Serial.print(muestraT[k]);
    Serial.print(',');
    Serial.println(muestraADC[k]);
  }
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
const uint8_t ERR_SIN_CAPACITOR = 5;

// numPrueba: 1..n (solo para el protocolo). extender: seguir cargando despues de t2 (ultima prueba).
uint8_t medirUnaVez(uint8_t numPrueba, uint8_t r, bool extender, float &tauSeg, float &meseta,
                    float &t1Sal, float &t2Sal, bool &extendida) {
  modoDescarga();
  unsigned long inicio = millis();
  while (analogRead(PIN_LECTURA) > ADC_CERO) {
    if (millis() - inicio > TIMEOUT_DESCARGA_MS) return RES_NO_DESCARGA;
  }
  delay(100);

  Serial.print(F("#PRUEBA_INI,"));
  Serial.print(numPrueba);
  Serial.print(',');
  Serial.println(r);
  Serial.flush();                  // que no quede nada saliendo por Serial mientras se mide

  nMuestras = 0;
  unsigned long tObj = T_MUESTRA0_US;
  bool extendiendo = false;
  extendida = false;

  modoCarga(r);
  unsigned long t0 = micros();
  digitalWrite(PIN_R[r], HIGH);
  float t1 = 0, t2 = 0;
  bool hayT1 = false;
  float tMin = USAR_AUTORANGO ? T1_MIN_AUTO_US : T1_MIN_FIJO_US;
  // Media movil: sumas enteras de la ventana y las de la vuelta anterior (para interpolar).
  uint8_t  vIdx = 0, vCnt = 0, pCnt = 0;
  uint32_t sT = 0, pT = 0;
  uint16_t sA = 0, pA = 0;
  while (true) {
    unsigned long dt = micros() - t0;
    int lectura = analogRead(PIN_LECTURA);
    // Captura de la curva: solo una comparacion de enteros por vuelta; nada de Serial aqui.
    if (nMuestras < N_MUESTRAS && dt >= tObj) {
      muestraT[nMuestras] = dt;
      muestraADC[nMuestras] = (uint16_t)lectura;
      nMuestras++;
      tObj = (unsigned long)(tObj * RAZON_MUESTRA);
    }
    // Ventana movil (solo sumas y restas de enteros)
    if (vCnt == VENTANA) { sT -= ventT[vIdx]; sA -= ventA[vIdx]; } else { vCnt++; }
    ventT[vIdx] = dt;
    ventA[vIdx] = (uint16_t)lectura;
    sT += dt;
    sA += (uint16_t)lectura;
    vIdx = (vIdx + 1) % VENTANA;

    if (extendiendo) {
      if (lectura >= ADC_EXT_FIN || dt - (unsigned long)t2 > EXT_MAX_US || nMuestras >= N_MUESTRAS || dt > TIMEOUT_CARGA_US) {
        extendida = true;
        break;
      }
      continue;
    }
    // media >= N  <=>  suma >= N * cantidad (sin dividir)
    if (!hayT1 && sA >= N1_ENTERO * vCnt) {
      hayT1 = true;
      t1 = instanteCruce(ADC_N1, sT, sA, vCnt, pT, pA, pCnt);
      if (t1 < tMin) { modoDescarga(); return RES_RAPIDO; }
      if (USAR_AUTORANGO && r > 0 && t1 > T1_MAX_US) { modoDescarga(); return RES_LENTO; }
    }
    if (sA >= N2_ENTERO * vCnt) {
      t2 = instanteCruce(ADC_N2, sT, sA, vCnt, pT, pA, pCnt);
      if (extender) { extendiendo = true; continue; }
      break;
    }
    if (dt > TIMEOUT_CARGA_US) { modoDescarga(); return hayT1 ? RES_NO_LLEGA : RES_LENTO; }
    pT = sT; pA = sA; pCnt = vCnt;
  }
  modoDescarga();
  if (t2 <= t1) return RES_RAPIDO;

  float tauS, P;
  ajustarCurva(t1, t2, tauS, P);
  tauSeg = tauS / 1000000.0;
  meseta = P;
  t1Sal = t1;
  t2Sal = t2;
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

void mostrarError(uint8_t codigo, const char* msg) {
  estado = ERROR_ESTADO;
  setLeds(false, false, true);
  lcdLinea(0, "ERROR");
  lcdLinea(1, msg);
  Serial.print(F("#ERROR,"));
  Serial.print(codigo);
  Serial.print(',');
  Serial.println(msg);
  Serial.print(F("ERROR: "));
  Serial.println(msg);
  Serial.println(F("#LISTO"));
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

  Serial.print(F("#INICIO,"));
  Serial.println(N_MAX);
  imprimirRango(rango);
  Serial.println(F("prueba,R,meseta,tau_ms,C_uF"));
  for (uint8_t i = 0; i < nPruebas; i++) {
    snprintf(l, sizeof(l), "Midiendo %d/%d", i + 1, nPruebas);
    lcdLinea(0, l);
    lcdLinea(1, R_ETIQ[rango]);

    bool ultima = (i > 0) && (i == nPruebas - 1);
    float P = 0;
    float t1 = 0, t2 = 0;
    bool extendida = false;
    uint8_t res = RES_OK;
    for (uint8_t intento = 0; intento < N_RANGOS + 1; intento++) {
      res = medirUnaVez(i + 1, rango, ultima, tau[i], P, t1, t2, extendida);
      if (res == RES_RAPIDO && USAR_AUTORANGO && rango < N_RANGOS - 1) { rango++; imprimirRango(rango); continue; }
      if (res == RES_LENTO  && USAR_AUTORANGO && rango > 0)            { rango--; imprimirRango(rango); continue; }
      break;
    }
    if (res != RES_OK) {
      mostrarError(res, textoError(res));
      descartarBotones();
      return;
    }
    c[i] = tau[i] / (R_REAL[rango] + R_PIN_ON) * 1000000.0 * K_CAL;
    if (c[i] < C_MIN_UF) {
      mostrarError(ERR_SIN_CAPACITOR, "Sin capacitor");
      descartarBotones();
      return;
    }
    sumaP += P;

    // Ya termino la parte sensible al tiempo: ahora si se envia todo.
    volcarMuestras();
    Serial.print(F("#PRUEBA,"));
    Serial.print(i + 1);              Serial.print(',');
    Serial.print(rango);              Serial.print(',');
    Serial.print(t1, 1);              Serial.print(',');
    Serial.print(t2, 1);              Serial.print(',');
    Serial.print(P, 1);               Serial.print(',');
    Serial.print(tau[i] * 1000.0, 3); Serial.print(',');
    Serial.print(c[i], 3);            Serial.print(',');
    Serial.println(extendida ? 1 : 0);

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

  Serial.print(F("#RESULTADO,"));
  Serial.print(nPruebas);                   Serial.print(',');
  Serial.print(R_REAL[rango] + R_PIN_ON, 1); Serial.print(',');
  Serial.print(V_ENTRADA, 2);               Serial.print(',');
  Serial.print(tauPromMs, 3);               Serial.print(',');
  Serial.print(cProm, 3);                   Serial.print(',');
  Serial.print(incPct, 2);                  Serial.print(',');
  Serial.print(cMin, 3);                    Serial.print(',');
  Serial.print(cMax, 3);                    Serial.print(',');
  Serial.print(qUC, 3);                     Serial.print(',');
  Serial.print(eUJ, 3);                     Serial.print(',');
  Serial.println(mesetaPct, 1);

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
  Serial.println(F("#FIN"));
  Serial.println(F("#LISTO"));
  Serial.println();

  idxPantalla = 0;
  autoCiclo = true;
  tPantalla = millis();
  estado = REPORTE;
  setLeds(true, false, false);
  mostrarPantalla();
  pitido(120);
  descartarBotones();
  while (Serial.available()) Serial.read();   // descarta comandos que llegaron mientras se media
}

// ---------- comandos desde el PC ----------
// 'M' = medir (como START), 'V' = version y configuracion. Se ignora el resto (\r, \n, basura).
bool comandoMedir() {
  bool medirAhora = false;
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == 'M' || ch == 'm') {
      medirAhora = true;
    } else if (ch == 'V' || ch == 'v') {
      imprimirConfig();
      Serial.println(F("#LISTO"));
    }
  }
  return medirAhora;
}

void setup() {
  Serial.begin(115200);
  pinMode(LED_VERDE, OUTPUT);
  pinMode(LED_AMARILLO, OUTPUT);
  pinMode(LED_ROJO, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  for (uint8_t i = 0; i < 3; i++) pinMode(BTN[i], INPUT_PULLUP);
  soltarCargas();
  modoDescarga();

  lcd.begin(16, 2);
  lcdLinea(0, "CapSense Lab 2.3");
  lcdLinea(1, "Iniciando...");
  setLeds(true, true, true);          // prueba de LEDs
  delay(1200);
  imprimirConfig();
  Serial.println(F("=== CapSense Lab v" VERSION_FW " ==="));
  Serial.println(F("Rango: 1 uF a 1000 uF. Pulsa START o envia M para medir."));
  Serial.println(F("#LISTO"));
  descartarBotones();
  entrarListo();
}

void loop() {
  bool start = pulsado(0);
  bool sig   = pulsado(1);
  bool atras = pulsado(2);
  if (comandoMedir()) start = true;

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
