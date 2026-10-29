# Los cálculos, paso a paso

Esta es la matemática que hace el Arduino y que el dashboard repite en Python para comprobarla. Los números de ejemplo son de una medición real de un capacitor de 100 µF.

## 1. El modelo

Al cargar un capacitor a través de una resistencia R, el voltaje sube como

$$V(t) = P\,\left(1 - e^{-t/\tau}\right), \qquad \tau = R\,C$$

**P** es la meseta: el voltaje al que llegaría después de mucho tiempo, en cuentas del ADC (0 a 1023). Sin fuga, P = 1023. Un capacitor con fuga pierde carga mientras se carga y P queda más abajo.

## 2. Lo que mide el Arduino

No guarda toda la curva: anota dos instantes.

- $t_1$: cuando el ADC llega a **250**. Ejemplo: $t_1 = 290.36$ ms.
- $t_2$: cuando el ADC llega a **700**. Ejemplo: $t_2 = 1221.59$ ms.

## 3. La meseta P

De la ecuación, $t = \tau\,(-\ln(1 - N/P))$ para cada nivel N. Al dividir $t_2$ entre $t_1$, τ se cancela:

$$r = \frac{t_2}{t_1} = \frac{\ln(1 - 700/P)}{\ln(1 - 250/P)}$$

Ejemplo: $r = 1221.59 / 290.36 = 4.20716$.

Esta ecuación no se puede despejar, así que el firmware usa **bisección**: prueba P en la mitad del intervalo [702, 1023]. Si la razón con ese P es mayor que r, la meseta está más arriba; si no, más abajo. Después de 30 mitades el intervalo mide 321/2³⁰ ≈ 3·10⁻⁷ cuentas.

Ejemplo: **P = 993.344 cuentas = 97.10 % de 1023**.

Casos límite:
- Si $r \leq$ la razón con P = 1023 (4.1141), no hay fuga apreciable y se fija **P = 1023**.
- Si r es tan grande que P quedaría bajo 702, se fija **P = 702** (fuga extrema).

## 4. τ desde cada cruce

$$\tau_1 = \frac{t_1}{-\ln(1 - 250/P)} \qquad \tau_2 = \frac{t_2}{-\ln(1 - 700/P)} \qquad \tau = \frac{\tau_1 + \tau_2}{2}$$

Cuando la bisección converge, τ₁ y τ₂ salen **iguales** (es lo que se le pidió a P). El promedio solo importa cuando P saturó.

Ejemplo: **τ = 1001.524 ms**.

## 5. La capacitancia

La resistencia total es la de carga más la resistencia interna del pin (25 Ω):

$$C = \frac{\tau}{R + R_{pin}}\cdot K_{cal} = \frac{1.001524\ \text{s}}{9790 + 25\ \Omega} = 102.040\ \mu\text{F}$$

## 6. Varias pruebas

El firmware repite la medición 5 veces (3 si τ > 1 s, 2 si τ > 4 s, decidido tras la primera) y promedia:

$$\bar C = \frac{1}{n}\sum C_i$$

### La incertidumbre es el semi-rango

El firmware **no usa desviación estándar**:

$$\Delta C = \frac{C_{max} - C_{min}}{2} \qquad \text{incertidumbre} = \frac{\Delta C}{\bar C}\cdot 100\ \%$$

El dashboard usa exactamente la misma fórmula. Con 2 a 5 pruebas, el semi-rango es una medida simple y honesta de la dispersión; la desviación estándar de tan pocas muestras es muy inestable.

## 7. Carga y energía

Con V = 4.92 V (el voltaje real del pin de 5 V):

$$Q = \bar C\,V \qquad E = \tfrac12\,\bar C\,V^2$$

µF·V da µC, y µF·V² da µJ.

## 8. La meseta y la fuga

La pantalla del LCD y el dashboard clasifican la meseta promedio:

| Meseta | Fuga |
|---|---|
| > 98 % | baja |
| 93 % a 98 % | media |
| ≤ 93 % | alta (banner rojo) |

**Ojo con el modelo:** una fuga real (una resistencia R_f en paralelo con C) también acorta la constante de tiempo: τ = C·(R‖R_f), con P = 1023·R_f/(R+R_f). El firmware calcula C = τ/R, así que con fuga subestima C en el factor P/1023 (≈ 3 % si la meseta es 97 %). Ajustar P sí evita el error mucho mayor del método simple del 63 %, pero no corrige este factor. El simulador usa el mismo modelo que el firmware (τ = R·C y P < 1023).

## 9. Exactitud del firmware (medida con el simulador)

El simulador reproduce el bucle real del Uno: `micros()` con resolución de 4 µs, `analogRead()` de ~112 µs (la muestra se toma ~12 µs después de empezar), ruido gaussiano del ADC y truncamiento. Peor error de la medición completa (autorango, 2 a 5 pruebas, promedio) en 3 repeticiones:

| C | v2.2 · sin fuga, ruido 0.3 | v2.2 · sin fuga, ruido 0.7 | v2.2 · meseta 96 %, ruido 0.7 | **v2.3** · sin fuga, ruido 0.3 | **v2.3** · sin fuga, ruido 0.7 | **v2.3** · meseta 96 %, ruido 0.7 |
|---|---|---|---|---|---|---|
| 1 µF (1 MΩ) | −0.20 % | −0.70 % | −0.40 % | 0.00 % | −0.10 % | +0.80 % |
| 1.5 µF | +0.80 % | +0.87 % | **+5.00 %** | +0.07 % | +0.07 % | +0.80 % |
| 2.2 µF | +0.36 % | −0.18 % | **+2.05 %** | +0.05 % | −0.14 % | +0.50 % |
| 4.7 µF | +0.23 % | −0.49 % | +1.62 % | +0.02 % | +0.04 % | +0.40 % |
| 10–100 µF | < 0.4 % | < 0.9 % | < 0.8 % | < 0.1 % | < 0.1 % | < 0.7 % |
| 220–1000 µF | < 0.7 % | **−1.59 %** | −1.30 % | < 0.1 % | < 0.3 % | < 0.6 % |

### Por qué fallaba la v2.2 (y la v2.1, que mide igual)

1. **Capacitores chicos en 10 kΩ con fuga (1 a 5 µF).** t1 dura pocos ms y el firmware anota el tiempo de la *primera lectura* que pasa el umbral: el cruce real ocurrió hasta una vuelta antes (~116 µs). Eso cambia la razón t2/t1 y, con fuga, el ajuste de P amplifica el error.
2. **Capacitores grandes con ruido (≥ 220 µF).** La curva sube tan lento que pasa miles de lecturas cerca de 250 y de 700; basta una lectura con ruido hacia arriba para "cruzar" antes de tiempo.

### Qué cambia la v2.3

- Los cruces se detectan sobre la **media móvil de las últimas 8 lecturas**, con su tiempo medio. El ruido baja a la mitad y deja de adelantar el cruce. Por vuelta solo se suman y restan enteros (~5 µs); la comparación `suma ≥ N·cantidad` evita dividir.
- El instante se **interpola** entre el punto medio de la vuelta anterior y el de la actual, y se le suman 8 µs: el ADC muestrea ~12 µs después de leer `micros()` y la carga empieza ~4 µs después de `t0`. La cuenta en `float` se hace solo una vez por cruce.
- Lo que queda con fuga (+0.3 a +0.8 %) viene de promediar una curva que se dobla: la media queda un poco por debajo de la curva y el cruce sale un poco tarde.

La tolerancia de un electrolítico típico es ±20 %, así que la diferencia no cambia ninguna conclusión de la exposición. Pero con la v2.3 el valor medido ya refleja el capacitor y no el método.
