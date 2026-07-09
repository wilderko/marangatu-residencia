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
- ingresos documentados de al menos el salario mínimo paraguayo
  (en la práctica **≈ USD 500–600 por mes**);
- documentos tributarios de respaldo: declaraciones Form 120, *certificado de
  cumplimiento tributario*, *constancia de RUC*, *cédula tributaria*, *constancia de
  movimiento tributario*.

La herramienta automatiza la rutina mensual correspondiente en Marangatu (factura →
imputación → Form 120 → talón Form 241 → boleta de pago), tal como se describe en la
guía comunitaria *«GUÍA PRÁCTICA PARA GENERAR LOS DOCUMENTOS NECESARIOS PARA LA
RESIDENCIA PERMANENTE EN PARAGUAY»*.

## Qué hace

| Subcomando   | Cuándo          | Pasos de la guía | Qué sucede |
|--------------|-----------------|------------------|------------|
| `facturar`   | ~día 25 del mes | 1–2              | Emite una factura virtual del mes **en curso** al cliente configurado. Monto = `MIN_INCOME_USD × tipo de cambio × SAFETY_MARGIN`, redondeado hacia arriba a un múltiplo de 11.000 Gs. Guarda un registro de estado que luego usa `declarar`. |
| `declarar`   | ~día 5 del mes  | 3–5, 9           | Para el mes **anterior**: imputa los comprobantes de venta (*ventas a imputar → imputar todo*), presenta el **Form 120** (IVA General, obligación 211) con la casilla 10 = monto/11×10, presenta el **talón Form 241** y genera la **boleta de pago** (adjunta al correo de reporte). |
| `documentos` | antes de la solicitud | 7–8        | Descarga best-effort del *certificado de cumplimiento tributario*, la *constancia de RUC* y la *cédula tributaria* en `~/.local/share/marangatu/documentos/`. |

El **pago del IVA no está automatizado** — la boleta generada se paga en cualquier
aplicación bancaria paraguaya (*Pagar servicios → DNIT*, ingresando cédula/RUC + fecha
de nacimiento). El correo de reporte se lo recuerda cada mes.

### La aritmética

Con la tasa del 10 % de IVA, Marangatu trata el total de la factura como IVA incluido:
base imponible = monto × 10/11 (eso es lo que va en la casilla 10 del Form 120) e
IVA = monto / 11. El script redondea el monto bruto **hacia arriba a un múltiplo de
11.000 Gs** para que tanto la base como el IVA resulten en guaraníes enteros y las
cifras autocalculadas por el portal puedan compararse exactamente con lo que espera el
script.

Ejemplo con los valores por defecto (`MIN_INCOME_USD=600`, margen 1,10, cambio
7.300 Gs/USD): monto = 4.818.000 Gs → base 4.380.000 Gs (casilla 10),
IVA 438.000 Gs ≈ USD 60/mes.

### Salvaguardas

- **Contraseña incorrecta → detención inmediata, sin reintentos** (Marangatu bloquea la
  cuenta tras fallos repetidos).
- **Nunca presenta una rectificativa**: si el Form 120 se abre como *RECTIFICATIVA*, el
  período ya fue presentado y el script aborta.
- `declarar` **se niega a ejecutarse** si no existe registro de una factura emitida para
  el período — nunca presentará silenciosamente una declaración en cero que rompa su
  cadena de 3 meses. (Se puede forzar con `--amount-gs` solo si está seguro de que la
  factura existe.)
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
| `MIN_INCOME_USD` | `600` | Ingreso mensual que la factura debe documentar. La Res. 407/2026 espera aproximadamente el salario mínimo (~USD 500–600). |
| `SAFETY_MARGIN` | `1.10` | La factura se emite un 10 % por encima del mínimo para que una depreciación del guaraní nunca lo deje por debajo del umbral. |
| `FX_RATE_PYG` | *(vacío)* | Tipo de cambio fijo Gs/USD. Vacío = se obtiene el actual de open.er-api.com. |
| `FX_RATE_FALLBACK` | `7500` | Cambio usado cuando la API de cotizaciones no responde. |
| `CLIENT_SITUACION` | `NO_DOMICILIADO` | `NO_DOMICILIADO` = persona/empresa extranjera sin RUC paraguayo (p. ej. su LLC); `CONTRIBUYENTE` = cliente local con RUC. |
| `CLIENT_RUC` | | Para `CONTRIBUYENTE`: dígitos del RUC antes del guion (el portal completa el nombre automáticamente). |
| `CLIENT_ID` | | Para `NO_DOMICILIADO`: número de pasaporte o tax ID extranjero. |
| `CLIENT_ID_TYPE` | `Pasaporte` | Texto de la opción en el select *Tipo de Identificación* (p. ej. `Identificación Tributaria`). |
| `CLIENT_NAME` / `CLIENT_ADDRESS` / `CLIENT_COUNTRY` / `CLIENT_EMAIL` / `CLIENT_PHONE` | | Datos del cliente tal como deben figurar en la factura. `CLIENT_COUNTRY` es el texto de la opción del select *País* (p. ej. `ESTADOS UNIDOS`). |
| `SERVICE_DESCRIPTION` | `Servicios de consultoría informática` | Descripción del servicio en la factura. |

## Uso

```bash
V=~/marangatu/venv/bin/python

# empiece SIEMPRE con un dry-run — hace todo salvo los clics finales de confirmación;
# luego revise las capturas en ~/.local/state/marangatu/logs/<run>/
$V marangatu_residencia.py facturar --dry-run
$V marangatu_residencia.py declarar --dry-run

# corridas reales
$V marangatu_residencia.py facturar                  # factura del mes en curso
$V marangatu_residencia.py facturar --amount-gs 4818000   # monto fijo en vez de USD×cambio
$V marangatu_residencia.py declarar                  # declarar el mes anterior
$V marangatu_residencia.py declarar --month 2026-07  # declarar un período específico
$V marangatu_residencia.py documentos                # descargar documentos para la solicitud
```

Opciones comunes: `--dry-run`, `--no-email`, `--only-if-not-done` (termina en silencio
si el período ya tiene marcador — para cron de respaldo), `--retries N`.

Código de salida 0 = éxito (reporte enviado), 1 = fallo tras los reintentos (se envía
un reporte de error con las últimas capturas).

### Cron

```cron
# factura del mes en curso (debe emitirse dentro del mes que documenta)
0 14 25 * * ~/marangatu/venv/bin/python ~/marangatu/marangatu_residencia.py facturar
0 14 27 * * ~/marangatu/venv/bin/python ~/marangatu/marangatu_residencia.py facturar --only-if-not-done
# declaración del mes anterior (primera semana, antes del vencimiento según el último dígito del RUC)
0 14 5 * *  ~/marangatu/venv/bin/python ~/marangatu/marangatu_residencia.py declarar
0 14 7 * *  ~/marangatu/venv/bin/python ~/marangatu/marangatu_residencia.py declarar --only-if-not-done
```

> ⚠️ **Si antes automatizaba declaraciones en cero, elimine primero ese cron.** Un
> Form 120 en cero presentado para un mes con factura obliga a una rectificativa, y un
> mes en cero reinicia su cadena de 3 meses.

### Cronograma hacia la residencia permanente

| Mes | Día 25 | Día 5 del mes siguiente |
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
- las deducciones de gastos en el Form 120 (consulte a un contador),
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
- Los flujos de Form 120 / Form 241 están probados en producción; las pantallas de
  *factura, imputación y boleta* se implementaron a partir de las capturas de la guía
  con cascadas de selectores de respaldo. Si la DNIT cambia el marcado, revise las
  capturas de los pasos en los logs y ajuste las cascadas (`first_visible`,
  `control_by_label`).
- Los mensajes de log y de los reportes están en eslovaco (el idioma del operador
  original). Se agradecen PRs que agreguen localización al español o inglés.

## Fuentes

- [DNM: Migraciones actualiza el régimen de acreditación de solvencia económica](https://migraciones.gov.py/migraciones-actualiza-el-regimen-de-acreditacion-de-solvencia-economica-para-extranjeros/)
- [liberation.travel: Paraguay permanent residency — new conditions 2026](https://liberation.travel/paraguay-permanent-residency-new-conditions-2026/)
- [ABC Color: cambios para acceder a la residencia permanente](https://www.abc.com.py/nacionales/2026/06/25/atencion-extranjeros-estos-son-los-cambios-para-acceder-a-la-residencia-permanente-en-paraguay/)
