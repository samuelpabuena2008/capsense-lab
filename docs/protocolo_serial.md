# Protocolo serie Arduino → PC

## Firmware v2.2 (115200 baud)

Cada línea de máquina empieza con `#`, un tipo y campos separados por coma. El firmware **también** imprime el texto legible de la v2.1 para el Monitor Serie. El dashboard ignora ese texto cuando ya vio líneas `#`.

| Línea | Campos | Cuándo |
|---|---|---|
| `#VERSION,2.2` | versión | al arrancar y con el comando `V` |
| `#CONFIG,V,R10k,R1M,R_pin,K,N1,N2` | calibración del firmware | igual que `#VERSION` |
| `#LISTO` | | listo para medir (también después de un error) |
| `#INICIO,n_max` | pruebas máximas (5) | al empezar una medición |
| `#RANGO,idx,etiqueta,R_ohm` | rango (0 = 10k, 1 = 1M) y R total con el pin | al empezar y cada vez que el autorango cambia |
| `#PRUEBA_INI,i,rango` | número de prueba (1..n) y rango | justo antes de cargar (ya descargado) |
| `#MUESTRA,t_us,adc` | tiempo desde el inicio de la carga y lectura | después de la prueba, hasta 100 líneas |
| `#PRUEBA,i,rango,t1_us,t2_us,P,tau_ms,C_uF,ext` | cruces, meseta, τ, C; `ext` = 1 si la curva siguió tras t2 | al terminar cada prueba |
| `#RESULTADO,n,R_ohm,V,tau_ms,C_uF,inc_pct,Cmin,Cmax,Q_uC,E_uJ,meseta_pct` | resumen | al terminar la medición |
| `#FIN` | | después del resultado |
| `#ERROR,codigo,mensaje` | ver tabla | si la medición falla |

Códigos de error: `1` No descarga · `2` Sin capacitor / Muy chico · `3` Muy grande · `4` Fuga muy alta (no llega a ADC 700) · `5` Sin capacitor (C < 0.5 µF).

### Ejemplo (recortado)

```
#VERSION,2.2
#CONFIG,4.92,9790,996000,25.0,1.000,250,700
=== CapSense Lab v2.2 ===
#LISTO
#INICIO,5
#RANGO,0,10k,9815
prueba,R,meseta,tau_ms,C_uF
#PRUEBA_INI,1,0
#MUESTRA,500,4
#MUESTRA,616,5
...
#PRUEBA,1,0,290360,1221590,993.3,1001.524,102.040,0
1,10k,993.3,1001.524,102.040
...
#RESULTADO,5,9815.0,4.92,1001.512,102.039,0.06,101.978,102.099,502.032,1234.999,97.1
---------- RESULTADO ----------
...
#FIN
#LISTO
```

### Comandos PC → Arduino

| Comando | Efecto |
|---|---|
| `M` | medir (igual que el botón START) |
| `V` | reenviar `#VERSION`, `#CONFIG` y `#LISTO` |

Los comandos que llegan durante una medición se descartan al terminar.

## Captura de la curva sin dañar la medición

- **Nada de `Serial.print` mientras se mide.** Antes de cargar se hace `Serial.flush()` para que no quede nada saliendo (las interrupciones de transmisión moverían t1 y t2).
- Las muestras se guardan en RAM: `uint32_t muestraT[100]` + `uint16_t muestraADC[100]` = 600 bytes. El sketch completo usa 1204 de 2048 bytes.
- El instante de la próxima muestra es un `unsigned long`; en cada vuelta solo hay una comparación de enteros. La multiplicación por 1.1147 ocurre solo al guardar una muestra.
- **Espaciado geométrico:** primera muestra a 0.5 ms y cada una ~11 % después de la anterior: 100 muestras cubren de 0.5 ms a ~23 s, con la misma densidad relativa para un capacitor de 1 µF que para uno de 1000 µF.
- La **última prueba** sigue cargando después de t2 hasta ADC ≥ 1015, 8 s extra o 100 muestras. Así se ve la meseta. t1 y t2 se capturan exactamente igual que en las demás pruebas.
- El volcado de ~100 líneas (~2 200 caracteres) tarda ~0.2 s a 115200 baud. A 9600 tardaría ~2.3 s; por eso se subió la velocidad.

## Firmware v2.1 (9600 baud)

Solo texto legible. El dashboard lo entiende igual:

| Texto | Evento |
|---|---|
| `=== CapSense Lab v2.1 ===` | versión |
| `prueba,R,meseta,tau_ms,C_uF` | inicio de medición |
| `1,10k,993.3,1001.524,102.040` | prueba (R es la **etiqueta**, no el valor) |
| bloque `RESULTADO` + línea tras `CSV (...)` | resultado (`R_ohm` ya incluye los 25 Ω del pin) |
| `ERROR: mensaje` | error |

Como la v2.1 no manda t1 ni t2, el dashboard los **reconstruye** desde τ y P: `t = τ·(−ln(1 − N/P))`. Es exacto cuando la bisección convergió (τ₁ = τ₂); si P saturó en 1023 es una aproximación. El panel lo indica.
