# marangatu-residencia

**[English](README.md) | [Español](README.es.md) | [Slovensky](README.sk.md) | [Česky](README.cs.md)**

Automatización headless de la rutina tributaria mensual en el portal **Marangatu** de
Paraguay ([marangatu.set.gov.py/eset](https://marangatu.set.gov.py/eset/), el sistema
tributario en línea de la DNIT), que genera las **declaraciones mensuales de IVA con
movimiento (no en cero)** exigidas para acreditar solvencia económica para la
**residencia permanente** según la **Resolución DNM N° 407/2026**.

> ⚠️ **Aviso.** Todo lo que se presenta a través de Marangatu tiene carácter de
> **declaración jurada**. Esta herramienta hace clic en los mismos botones que usted
> presionaría a mano, pero **usted** es responsable de lo que se presenta. Esto no es
> asesoramiento legal ni tributario. Ejecute siempre la primera corrida de cada
> subcomando con `--dry-run`, revise las capturas de pantalla y consulte a un contador
> para cualquier caso más allá del escenario simple de una-factura-por-mes
> (deducción de gastos, IRP, regímenes especiales).

## Contexto

Desde el **6 de julio de 2026**, la [Resolución DNM 407/2026](https://migraciones.gov.py/migraciones-actualiza-el-regimen-de-acreditacion-de-solvencia-economica-para-extranjeros/)
(en el marco de la Ley de Migraciones 6984/22) exige a quienes convierten la residencia
temporal en permanente acreditar *activamente* su solvencia económica. Para la vía del
trabajador independiente con ingresos locales, esto significa:

- al menos **3 declaraciones mensuales de IVA consecutivas con actividad real, no en
  cero** — las declaraciones en cero ya no se aceptan;
- **RUC** activo y al día durante aproximadamente 4 meses al momento de la presentación;
- ingresos documentados algo por encima del salario mínimo paraguayo
  (**₲3.044.000 por mes** en 2026, ≈ USD 510);
- documentos tributarios de respaldo: declaraciones Form 120, *certificado de
  cumplimiento tributario*, *constancia de RUC*, *cédula tributaria*, *constancia de
  movimiento tributario*.

La herramienta automatiza la rutina mensual correspondiente en Marangatu (factura →
imputación incl. el paso *Obligaciones* → Form 120 incl. Rubro 2 → talón Form 241 →
boleta de pago), tal como se describe en el manual eslovaco para clientes
[*Paraguay_navod_pobyt_SK.pdf*](https://liberation.travel/wp-content/uploads/2026/06/Paraguay_navod_pobyt_SK.pdf)
(actualizado en septiembre de 2026), basado a su vez en la guía comunitaria *«GUÍA
PRÁCTICA PARA GENERAR LOS DOCUMENTOS NECESARIOS PARA LA RESIDENCIA PERMANENTE EN
PARAGUAY»*.

## Qué hace

| Subcomando   | Cuándo          | Pasos de la guía | Qué sucede |
|--------------|-----------------|------------------|------------|
| `facturar`   | ~día 25 del mes | 1–2              | Emite una factura virtual del mes **en curso** al cliente configurado. Monto = `max(MIN_INCOME_GS × 11/10, MIN_INCOME_USD × tipo de cambio) × SAFETY_MARGIN`, redondeado hacia arriba a un múltiplo de 11.000 Gs, de modo que la base imponible quede siempre algo por encima del salario mínimo. Guarda un registro de estado que luego usa `declarar`. |
| `declarar`   | ~día 5 del mes (antes del vencimiento) | 3–5, 9 | Para el mes **anterior**: imputa los comprobantes de venta (*ventas a imputar → imputar todo → siguiente → imputar comprobantes*), ajusta los interruptores de **Obligaciones asociadas** (en verde solo `IMPUTAR_OBLIGACIONES`, normalmente IVA GENERAL; IRP–RSP e IRE en rojo) y hace clic en *Procesar Imputación*; presenta el **Form 120** (IVA General, obligación 211) con Rubro 1 casilla 10 = monto/11×10 **y Rubro 2** (casilla 160 = acumulado de 6 períodos, 27 = 31 = 160, el resto 0); presenta el **talón Form 241**; genera la **boleta de pago** (adjunta al correo de reporte). Registra el vencimiento de la presentación **y del pago** según su RUC. |
| `documentos` | antes de la solicitud | 6–8        | Descarga best-effort de los últimos Form 120, el *certificado de cumplimiento tributario*, la *constancia de RUC* y la *cédula tributaria* en `~/.local/share/marangatu/documentos/`. |
| `vencimiento`| en cualquier momento | 4           | Sin conexión (sin login): muestra el vencimiento de presentación + pago de un período según el último dígito del RUC. |

El **pago del IVA no está automatizado** — la boleta generada se paga en cualquier
aplicación bancaria paraguaya (*Pagar servicios → DNIT*, ingresando cédula/RUC + fecha
de nacimiento) **hasta el mismo vencimiento que la declaración**. El correo de reporte
se lo recuerda cada mes, con la fecha.

### La aritmética

Con la tasa del 10 % de IVA, Marangatu trata el total de la factura como IVA incluido:
base imponible = monto × 10/11 (eso es lo que va en la casilla 10 del Form 120) e
IVA = monto / 11. El script redondea el monto bruto **hacia arriba a un múltiplo de
11.000 Gs** para que tanto la base como el IVA resulten en guaraníes enteros y las
cifras autocalculadas por el portal puedan compararse exactamente con lo que espera el
script.

La guía pide facturar «algo por encima del salario mínimo (₲3.044.000 mensuales)». El
script compara el salario mínimo con la **base imponible** (casilla 10 — el ingreso que
ve la DNM), así que el monto bruto debe ser al menos `MIN_INCOME_GS × 11/10`;
`MIN_INCOME_USD × cambio` se mantiene como segundo mínimo y gana el mayor de los dos.

Ejemplo con los valores por defecto (`MIN_INCOME_GS=3044000`, `MIN_INCOME_USD=600`,
margen 1,10, cambio 5.990 Gs/USD): max(3.348.400; 3.594.000) × 1,10 → monto 3.960.000 Gs
→ base 3.600.000 Gs (casilla 10), IVA 360.000 Gs ≈ USD 60/mes — los «≈ ₲360.000 de
impuesto al mes» que menciona la guía.

### Form 120 Rubro 2

El Rubro 2 (*«Enajenación de bienes y/o prestación de servicios de los últimos seis (6)
meses, incluido el periodo que se declara»*) lo completa el contribuyente — Marangatu no
lo calcula. El script ingresa la casilla **160** = suma de la casilla 10 de los últimos
seis períodos mensuales **incluido** el que se declara, deja **161, 26, 162, 163, 29**
en 0 y verifica (o completa, si el formulario no los calcula) **27** = 160+161+26,
**30** = 162+163+29 = 0 y **31** = 27+30. En la primera declaración 160 = 10; desde el
séptimo mes es una ventana móvil de seis períodos. Con una factura de ₲6.000.000 al mes:
160 = 5.454.545 en el mes 1, 16.363.635 en el mes 3.

El historial sale de los registros propios del script (Form 120 presentados, luego
registros de facturas). Un período de la ventana **sin** registro nunca se supone en cero
en una corrida real — configure `RUC_START` (los períodos anteriores cuentan 0) y/o
`PRIOR_SALES_10` para los períodos presentados a mano. En `--dry-run` solo se advierte.

### Vencimiento (calendario perpetuo)

La declaración **y el pago** vencen el mismo día del mes siguiente, según el **último
dígito del RUC antes del guion** (el dígito verificador no cuenta): 0→7, 1→9, 2→11,
3→13, 4→15, 5→17, 6→19, 7→21, 8→23, 9→25; si cae en fin de semana o feriado pasa al
siguiente día hábil. Ejemplo: el RUC 1234567-8 termina en 7, así que la declaración de
septiembre vence el 21 de octubre. Cada cónyuge tiene su propio RUC y su propio
vencimiento. El script conoce los feriados paraguayos de fecha fija y el Jueves/Viernes
Santo; los feriados trasladables (1/3, 12/6, 29/9) van en `HOLIDAYS` — un feriado
faltante solo puede adelantar la fecha calculada, nunca atrasarla. `declarar` registra
la fecha, avisa el último día y marca una presentación tardía.

### Salvaguardas

- **Contraseña incorrecta → detención inmediata, sin reintentos** (Marangatu bloquea la
  cuenta tras fallos repetidos).
- **Nunca presenta una rectificativa**: si el Form 120 se abre como *RECTIFICATIVA*, el
  período ya fue presentado y el script aborta.
- `declarar` **se niega a ejecutarse** si no existe registro de una factura emitida para
  el período — nunca presentará silenciosamente una declaración en cero que rompa su
  cadena de 3 meses. (Se puede forzar con `--amount-gs` solo si está seguro de que la
  factura existe.)
- **Obligaciones**: solo las obligaciones de `IMPUTAR_OBLIGACIONES` se ponen en verde,
  todas las demás en rojo, y el estado de cada interruptor se vuelve a leer antes de
  *Procesar Imputación* (imputar a un impuesto que el RUC no tiene termina como
  *inconsistencia*, y en *Ventas a imputar* no existe «no imputar»). Si una obligación
  deseada no aparece o un interruptor no se puede leer, no se imputa nada.
- El **Rubro 2** se calcula antes de iniciar sesión; un período faltante en la ventana
  de seis meses detiene una corrida real antes de tocar nada. Las casillas 10, 160, 27
  y 31 se releen antes de *Presentar*.
- `--interactive` abre un navegador visible, pregunta y/N antes de cada clic
  irreversible (factura, *Procesar Imputación*, Form 120, Form 241) y espera una
  corrección manual en cualquier pantalla que el script no pueda manejar con fiabilidad.
  Sin él, esa pantalla aborta la corrida (sin reintentos) sin confirmar nada.
- Antes de cada clic final en *Presentar/Confirmar*, el script espera hasta que el
  portal haya calculado **exactamente** los montos esperados; ante cualquier
  discrepancia aborta sin presentar nada.
- Cada paso se captura en pantalla en `~/.local/state/marangatu/logs/<run>/`; tras cada corrida se
  envía un reporte por correo (con capturas y el PDF de la boleta).
- Los fallos transitorios se reintentan 3× con pausas de 10 minutos; cada intento tiene
  un tope duro de 40 minutos. Los marcadores idempotentes (`~/.local/state/marangatu/`) más
  `--only-if-not-done` hacen seguros los cron de respaldo.

## Requisitos

- Servidor Linux capaz de ejecutar un navegador headless — Chromium (por defecto) o Firefox/Gecko (desarrollado en Ubuntu)
- Python 3.9+ con [Playwright](https://playwright.dev/python/)
- un **RUC activo** y acceso a Marangatu (número de cédula + contraseña)
- **timbrado** ya solicitado una vez (paso 1 de la guía — acción manual única en
  *Facturación y Timbrado → Solicitudes → Comprobantes Virtuales → Factura Virtual*)
- opcional: un `sendmail` funcional para los reportes por correo

## Instalación

```bash
mkdir -p ~/marangatu && cd ~/marangatu
python3 -m venv venv
venv/bin/pip install playwright
venv/bin/playwright install --with-deps chromium
# opcional — para controlar el portal con Firefox (Gecko), instálalo también y
# selecciónalo con BROWSER=firefox en residencia.conf o con la opción --browser firefox:
#   venv/bin/playwright install --with-deps firefox
git clone https://github.com/wilderko/marangatu-residencia.git src
ln -s src/marangatu_residencia.py .
```

## Configuración

Dos archivos, ambos con `chmod 600`:

`~/.config/marangatu/credentials`

```
USUARIO=1234567        # su número de cédula
PASSWORD=...
```

`~/.config/marangatu/residencia.conf` — parta de
[`residencia.conf.example`](residencia.conf.example):

| Clave | Default | Significado |
|-------|---------|-------------|
| `MAIL_TO` | *(vacío)* | Destinatario de los reportes. Vacío = no se envía correo (el reporte queda en el log). |
| `MAIL_FROM` | `Marangatu bot <marangatu@localhost>` | Remitente. Use una dirección cuyo dominio tenga la IP de su servidor en el registro SPF, o los reportes caerán en spam. |
| `SENDMAIL` | `/usr/sbin/sendmail` | Binario de sendmail. |
| `MIN_INCOME_GS` | `3044000` | Salario mínimo paraguayo (Gs/mes). La base imponible de la factura (casilla 10) se mantiene por encima. |
| `MIN_INCOME_USD` | `600` | Segundo mínimo opcional en USD (× cambio, se compara con el monto bruto); gana el mínimo mayor. `0` = no usar. |
| `SAFETY_MARGIN` | `1.10` | La factura se emite un 10 % por encima del mínimo («algo por encima del salario mínimo»; absorbe también movimientos del cambio). |
| `FX_RATE_PYG` | *(vacío)* | Tipo de cambio fijo Gs/USD. Vacío = se obtiene el actual de open.er-api.com. |
| `FX_RATE_FALLBACK` | `6000` | Cambio usado cuando la API de cotizaciones no responde. |
| `CLIENT_SITUACION` | `NO_DOMICILIADO` | `NO_DOMICILIADO` = persona/empresa extranjera sin RUC paraguayo (p. ej. su LLC); `CONTRIBUYENTE` = cliente local con RUC. |
| `CLIENT_RUC` | | Para `CONTRIBUYENTE`: dígitos del RUC antes del guion (el portal completa el nombre automáticamente). |
| `CLIENT_ID` | | Para `NO_DOMICILIADO`: número de pasaporte o tax ID extranjero. |
| `CLIENT_ID_TYPE` | `Pasaporte` | Texto de la opción en el select *Tipo de Identificación* (p. ej. `Identificación Tributaria`). |
| `CLIENT_NAME` / `CLIENT_ADDRESS` / `CLIENT_COUNTRY` / `CLIENT_EMAIL` / `CLIENT_PHONE` | | Datos del cliente tal como deben figurar en la factura. `CLIENT_COUNTRY` es el texto de la opción del select *País* (p. ej. `ESTADOS UNIDOS`). |
| `SERVICE_DESCRIPTION` | `Servicios de consultoría informática` | Descripción del servicio en la factura. |
| `IMPUTAR_OBLIGACIONES` | `IVA GENERAL` | Obligaciones separadas por comas que se ponen en **verde** en el paso *Obligaciones asociadas*; las demás en rojo. Agregue `IRP - RSP` solo si su RUC realmente está inscripto (obligatorio por encima de ₲80.000.000 de ingresos por servicios al año, art. 62 Ley 6380/2019). |
| `RUC` | *(vacío)* | Su RUC (p. ej. `1234567-8`) para calcular el vencimiento. Vacío = se toma `USUARIO` (para una persona física el RUC es el número de cédula). |
| `HOLIDAYS` | *(vacío)* | Días no hábiles adicionales `YYYY-MM-DD,…` (feriados trasladados, asuetos bancarios) que corren el vencimiento. |
| `RUC_START` | *(vacío)* | `YYYY-MM` del primer período con IVA; los anteriores cuentan como 0 en el Rubro 2. |
| `PRIOR_SALES_10` | *(vacío)* | Casilla 10 de los períodos de los que el script no tiene registro, `YYYY-MM:base,…` (p. ej. `2026-05:0,2026-06:3600000`). |

## Uso

```bash
V=~/marangatu/venv/bin/python

# empiece SIEMPRE con un dry-run — hace todo salvo los clics finales de confirmación;
# luego revise las capturas en ~/.local/state/marangatu/logs/<run>/
$V marangatu_residencia.py facturar --dry-run
$V marangatu_residencia.py declarar --dry-run

# corridas reales
$V marangatu_residencia.py facturar                  # factura del mes en curso
$V marangatu_residencia.py facturar --amount-gs 3960000   # monto fijo en vez del calculado
$V marangatu_residencia.py declarar                  # declarar el mes anterior
$V marangatu_residencia.py declarar --month 2026-07  # declarar un período específico
$V marangatu_residencia.py documentos                # descargar documentos para la solicitud
$V marangatu_residencia.py vencimiento --month 2026-09   # vencimiento (sin conexión, sin login)

# primera corrida real de las nuevas pantallas de imputación / Rubro 2: navegador
# visible, y/N antes de cada clic irreversible, intervención manual donde haga falta
$V marangatu_residencia.py declarar --interactive
```

Opciones comunes: `--dry-run`, `--no-email`, `--only-if-not-done` (termina en silencio
si el período ya tiene marcador — para cron de respaldo), `--retries N`, `--interactive`
(requiere terminal y pantalla; no para cron).

El `--dry-run` de `declarar` llega hasta los interruptores de *Obligaciones* (hace clic
en el paso del asistente *Imputar comprobantes*, que solo cambia de pantalla) y completa
Rubro 1 y Rubro 2, pero **no** hace clic en *Procesar Imputación* ni en *Presentar*.

Código de salida 0 = éxito (reporte enviado), 1 = fallo tras los reintentos (se envía
un reporte de error con las últimas capturas).

### Cron

```cron
# factura del mes en curso (debe emitirse dentro del mes que documenta)
0 14 25 * * ~/marangatu/venv/bin/python ~/marangatu/marangatu_residencia.py facturar
0 14 27 * * ~/marangatu/venv/bin/python ~/marangatu/marangatu_residencia.py facturar --only-if-not-done
# declaración del mes anterior — los días 5 y 6 son anteriores a cualquier vencimiento
# posible (el más temprano es el 7, para RUC terminado en 0); verifique el suyo con `vencimiento`
0 14 5 * *  ~/marangatu/venv/bin/python ~/marangatu/marangatu_residencia.py declarar
0 14 6 * *  ~/marangatu/venv/bin/python ~/marangatu/marangatu_residencia.py declarar --only-if-not-done
```

Pague la boleta en su aplicación bancaria **hasta el mismo vencimiento** — una
declaración o un pago tardío implican multa y recargos por mora.

> ⚠️ **Si antes automatizaba declaraciones en cero, elimine primero ese cron.** Un
> Form 120 en cero presentado para un mes con factura obliga a una rectificativa, y un
> mes en cero reinicia su cadena de 3 meses.

### Cronograma hacia la residencia permanente

| Mes | Día 25 | Día 5 del mes siguiente (vencimiento: según dígito del RUC, 7–25) |
|-----|--------|--------------------------|
| M1 | factura n.º 1 | — |
| M2 | factura n.º 2 | declarar M1 (no en cero n.º 1) + pagar IVA |
| M3 | factura n.º 3 | declarar M2 (no en cero n.º 2) + pagar IVA |
| M4 | — | declarar M3 (no en cero n.º 3) + pagar IVA → `documentos`, presentar la solicitud ante la DNM |

Costo recurrente: el propio IVA, monto/11 por mes (≈ USD 60 con la configuración por
defecto) — es un impuesto real, no una comisión.

## Qué NO está automatizado

- el **pago** de la boleta (aplicación bancaria: *Pagar servicios → DNIT*),
- la solicitud única del **timbrado** (paso 1 de la guía),
- las deducciones de gastos en el Form 120 (Rubro 3, *Compras locales e importaciones*; consulte a un contador),
- los documentos migratorios (certificado de Interpol, antecedentes policiales, turno
  en la DNM).

## Archivos

```
~/.config/marangatu/credentials                              acceso (chmod 600)
~/.config/marangatu/residencia.conf                          configuración (chmod 600)
~/.local/state/marangatu/                                    marcadores por período y registros de facturas (JSON)
~/.local/state/marangatu/logs/<timestamp>_<cmd>_<período>/   run.log + capturas de cada paso
~/.local/share/marangatu/documentos/<fecha>/                 descargas del subcomando documentos
```

El script respeta `XDG_CONFIG_HOME`, `XDG_STATE_HOME` y `XDG_DATA_HOME`;
las rutas anteriores son las predeterminadas.

## Solución de problemas y particularidades conocidas

- El portal abre casi cada acción en una **ventana nueva del navegador**, a veces 1–2
  minutos después del clic (AJAX del lado servidor antes de `window.open`). El script
  espera con paciencia y reintenta los clics hasta 3× — las corridas lentas son
  normales.
- Las capturas de pantalla a veces se cuelgan en *«waiting for fonts»* — hay un
  fallback vía CDP incorporado.
- Los flujos de Form 120 Rubro 1 / Form 241 están probados en producción; las pantallas
  de *factura, imputación y boleta* se implementaron a partir de las capturas de la guía
  con cascadas de selectores de respaldo. Si la DNIT cambia el marcado, revise las
  capturas de los pasos en los logs y ajuste las cascadas (`first_visible`,
  `control_by_label`).
- **Aún no verificado contra el portal real** (agregado en octubre de 2026 según la guía
  actualizada): las pantallas *Imputar comprobantes → Obligaciones asociadas → Procesar
  Imputación* (el estado de los interruptores se lee vía checkbox / `aria-checked` /
  clase CSS), las casillas del Rubro 2 (se buscan por nombres tipo `name='c160'` como la
  casilla 10, luego por el número de casilla tras el título «RUBRO 2») y los enlaces de
  descarga de Form 120 en la página de inicio. Haga la primera corrida con `--dry-run`,
  luego con `--interactive`, y revise las capturas `24_obligaciones_*`,
  `25_obligaciones_nastavene` y `32_form120_vyplneny`.
- Las inconsistencias tras imputar (p. ej. imputar a un impuesto que el RUC no tiene)
  aparecen en *Herramientas → Consulta de Estado de Procesos de Imputación*.
- Los mensajes de log y de los reportes están en eslovaco (el idioma del operador
  original). Se agradecen PRs que agreguen localización al español o inglés.

## Fuentes

- [Manual para clientes, en eslovaco (septiembre de 2026)](https://liberation.travel/wp-content/uploads/2026/06/Paraguay_navod_pobyt_SK.pdf)
- DNIT: *Cómo obtener comprobantes electrónicos y virtuales* (RG 90/2021), *Instructivo del Formulario N° 120 v4*, calendario perpetuo (RG 38/2020)
- [DNM: Migraciones actualiza el régimen de acreditación de solvencia económica](https://migraciones.gov.py/migraciones-actualiza-el-regimen-de-acreditacion-de-solvencia-economica-para-extranjeros/)
- [liberation.travel: Paraguay permanent residency — new conditions 2026](https://liberation.travel/paraguay-permanent-residency-new-conditions-2026/)
- [ABC Color: cambios para acceder a la residencia permanente](https://www.abc.com.py/nacionales/2026/06/25/atencion-extranjeros-estos-son-los-cambios-para-acceder-a-la-residencia-permanente-en-paraguay/)
