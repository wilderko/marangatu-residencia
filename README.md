# marangatu-residencia

**[English](README.md) | [Español](README.es.md) | [Slovensky](README.sk.md) | [Česky](README.cs.md)**

Headless automation of the monthly tax workflow on Paraguay's **Marangatu** portal
([marangatu.set.gov.py/eset](https://marangatu.set.gov.py/eset/), the online tax system
of DNIT) that produces the **non-zero monthly VAT (IVA) declarations** required to prove
economic solvency for **permanent residency** under **DNM Resolution No. 407/2026**.

> ⚠️ **Disclaimer.** Everything submitted through Marangatu has the character of a sworn
> declaration (*declaración jurada*). This tool clicks the same buttons you would click by
> hand, but **you** are responsible for what gets filed. This is not legal or tax advice.
> Always do the first run of each subcommand with `--dry-run`, inspect the screenshots,
> and consult an accountant for anything beyond the simple one-invoice-per-month case
> (expense deductions, IRP, special regimes).

## Background

Since **6 July 2026**, [DNM Resolution 407/2026](https://migraciones.gov.py/migraciones-actualiza-el-regimen-de-acreditacion-de-solvencia-economica-para-extranjeros/)
(under Migration Law 6984/22) requires applicants converting temporary → permanent
residency to *actively* prove economic solvency. For the self-employed / local-income
route this means:

- at least **3 consecutive monthly IVA declarations with real, non-zero activity** —
  zero declarations are no longer accepted;
- **RUC** active and in good standing for roughly 4 months at filing time;
- documented income at least around the Paraguayan minimum wage
  (in practice **≈ USD 500–600 per month**);
- supporting tax documents: Form 120 declarations, tax compliance certificate
  (*certificado de cumplimiento tributario*), RUC registration
  (*constancia de RUC*), *cédula tributaria*, *constancia de movimiento tributario*.

This tool automates the corresponding monthly Marangatu routine (invoice → imputation →
Form 120 → Form 241 talón → payment slip), as described in the community guide
*"GUÍA PRÁCTICA PARA GENERAR LOS DOCUMENTOS NECESARIOS PARA LA RESIDENCIA PERMANENTE EN
PARAGUAY"*.

## What it does

| Subcommand   | When            | Guide steps | What happens |
|--------------|-----------------|-------------|--------------|
| `facturar`   | ~25th of month  | 1–2         | Issues one virtual invoice for the **current** month to your configured client. Amount = `MIN_INCOME_USD × FX rate × SAFETY_MARGIN`, rounded up to a multiple of 11,000 Gs. Saves a state record used later by `declarar`. |
| `declarar`   | ~5th of month   | 3–5, 9      | For the **previous** month: imputes the sales vouchers (*ventas a imputar → imputar todo*), files **Form 120** (IVA General, obligation 211) with box 10 = gross/11×10, presents the **Form 241 talón**, and generates the payment slip (*boleta de pago*, attached to the report e-mail). |
| `documentos` | before applying | 7–8         | Best-effort download of the *certificado de cumplimiento tributario*, *constancia de RUC* and *cédula tributaria* into `~/.local/share/marangatu/documentos/`. |

Paying the IVA itself is **not** automated — you pay the generated boleta in any
Paraguayan banking app (*Pagar servicios → DNIT*, enter cédula/RUC + date of birth).
The report e-mail reminds you every month.

### The arithmetic

At the 10 % IVA rate, Marangatu treats the invoice total as IVA-inclusive:
taxable base = gross × 10/11 (that is what goes into Form 120 box 10) and
IVA = gross / 11. The script rounds the gross amount **up to a multiple of 11,000 Gs**
so that both the base and the IVA come out in whole guaraníes and the portal's
auto-computed figures can be compared byte-for-byte against the script's expectations.

Example with the defaults (`MIN_INCOME_USD=600`, margin 1.10, rate 7,300 Gs/USD):
gross = 4,818,000 Gs → base 4,380,000 Gs (box 10), IVA 438,000 Gs ≈ USD 60/month.

### Safety guards

- **Wrong password → immediate stop, no retry** (Marangatu locks accounts after
  repeated failures).
- **Never files a rectification**: if Form 120 opens as *RECTIFICATIVA*, the period was
  already filed and the script aborts.
- `declarar` **refuses to run** if there is no record of an issued invoice for the
  period — it will never silently file a zero declaration and break your 3-month chain.
  (Override with `--amount-gs` only if you are sure the invoice exists.)
- Before every final *Presentar/Confirmar* click the script waits until the portal has
  computed **exactly** the expected amounts; on any mismatch it aborts without filing.
- Every step is screenshotted to `~/.local/state/marangatu/logs/<run>/`; a report (with screenshots
  and the boleta PDF) is e-mailed after every run.
- Transient failures are retried 3× with 10-minute pauses; each attempt has a hard
  40-minute cap. Idempotent state markers (`~/.local/state/marangatu/`) plus
  `--only-if-not-done` make backup cron runs safe.

## Requirements

- Linux host that can run headless Chromium (developed on Ubuntu)
- Python 3.9+ with [Playwright](https://playwright.dev/python/)
- an **active RUC** and a Marangatu login (cédula number + password)
- **timbrado** already requested once (guide step 1 — a one-time manual action in
  *Facturación y Timbrado → Solicitudes → Comprobantes Virtuales → Factura Virtual*)
- optional: a working `sendmail` for e-mail reports

## Installation

```bash
mkdir -p ~/marangatu && cd ~/marangatu
python3 -m venv venv
venv/bin/pip install playwright
venv/bin/playwright install --with-deps chromium
git clone https://github.com/wilderko/marangatu-residencia.git src
ln -s src/marangatu_residencia.py .
```

## Configuration

Two files, both `chmod 600`:

`~/.config/marangatu/credentials`

```
USUARIO=1234567        # your cédula number
PASSWORD=...
```

`~/.config/marangatu/residencia.conf` — start from
[`residencia.conf.example`](residencia.conf.example):

| Key | Default | Meaning |
|-----|---------|---------|
| `MAIL_TO` | *(empty)* | Report recipient. Empty = no e-mail (report stays in the log). |
| `MAIL_FROM` | `Marangatu bot <marangatu@localhost>` | Sender. Use an address whose domain's SPF record covers your server, or reports land in spam. |
| `SENDMAIL` | `/usr/sbin/sendmail` | Sendmail binary. |
| `MIN_INCOME_USD` | `600` | Monthly income the invoice must document. Res. 407/2026 expects roughly the minimum wage (~USD 500–600). |
| `SAFETY_MARGIN` | `1.10` | Invoice is issued 10 % above the minimum so a weakening guaraní never drops you below the threshold. |
| `FX_RATE_PYG` | *(empty)* | Fixed Gs/USD rate. Empty = fetch the current rate from open.er-api.com. |
| `FX_RATE_FALLBACK` | `7500` | Rate used when the FX API is unreachable. |
| `CLIENT_SITUACION` | `NO_DOMICILIADO` | `NO_DOMICILIADO` = foreign person/company without a Paraguayan RUC (e.g. your LLC); `CONTRIBUYENTE` = local client with RUC. |
| `CLIENT_RUC` | | For `CONTRIBUYENTE`: RUC digits before the dash (the portal auto-fills the name). |
| `CLIENT_ID` | | For `NO_DOMICILIADO`: passport number or foreign tax ID. |
| `CLIENT_ID_TYPE` | `Pasaporte` | Text of the option in the *Tipo de Identificación* select (e.g. `Identificación Tributaria`). |
| `CLIENT_NAME` / `CLIENT_ADDRESS` / `CLIENT_COUNTRY` / `CLIENT_EMAIL` / `CLIENT_PHONE` | | Client data as it should appear on the invoice. `CLIENT_COUNTRY` is the option text of the *País* select (e.g. `ESTADOS UNIDOS`). |
| `SERVICE_DESCRIPTION` | `Servicios de consultoría informática` | Invoice line description. |

## Usage

```bash
V=~/marangatu/venv/bin/python

# ALWAYS start with a dry run — does everything except the final confirm clicks,
# then check the screenshots in ~/.local/state/marangatu/logs/<run>/
$V marangatu_residencia.py facturar --dry-run
$V marangatu_residencia.py declarar --dry-run

# real runs
$V marangatu_residencia.py facturar                  # invoice for the current month
$V marangatu_residencia.py facturar --amount-gs 4818000   # fixed amount instead of USD×FX
$V marangatu_residencia.py declarar                  # declare the previous month
$V marangatu_residencia.py declarar --month 2026-07  # declare a specific period
$V marangatu_residencia.py documentos                # download residency paperwork
```

Common flags: `--dry-run`, `--no-email`, `--only-if-not-done` (exit silently when the
period already has a done-marker — for backup crons), `--retries N`.

Exit code 0 = success (report e-mailed), 1 = failed after retries (error report with the
last screenshots is e-mailed).

### Cron

```cron
# invoice for the running month (must be issued inside the month it documents)
0 14 25 * * ~/marangatu/venv/bin/python ~/marangatu/marangatu_residencia.py facturar
0 14 27 * * ~/marangatu/venv/bin/python ~/marangatu/marangatu_residencia.py facturar --only-if-not-done
# declaration of the previous month (first week, before the due date driven by your RUC's last digit)
0 14 5 * *  ~/marangatu/venv/bin/python ~/marangatu/marangatu_residencia.py declarar
0 14 7 * *  ~/marangatu/venv/bin/python ~/marangatu/marangatu_residencia.py declarar --only-if-not-done
```

> ⚠️ **If you previously automated zero declarations, remove that cron first.** A zero
> Form 120 filed for a month with an invoice forces a rectification and a zero month
> restarts your 3-month chain.

### Timeline to permanent residency

| Month | 25th | 5th of next month |
|-------|------|-------------------|
| M1 | invoice #1 | — |
| M2 | invoice #2 | declare M1 (non-zero #1) + pay IVA |
| M3 | invoice #3 | declare M2 (non-zero #2) + pay IVA |
| M4 | — | declare M3 (non-zero #3) + pay IVA → run `documentos`, file the DNM application |

Recurring cost: the IVA itself, gross/11 per month (≈ USD 60 at the default settings) —
that is a real tax payment, not a fee.

## What is NOT automated

- **paying** the boleta (banking app: *Pagar servicios → DNIT*),
- the one-time **timbrado** request (guide step 1),
- expense deductions on Form 120 (talk to an accountant),
- migration-side documents (Interpol certificate, police records, DNM appointment).

## Files

```
~/.config/marangatu/credentials                             login (chmod 600)
~/.config/marangatu/residencia.conf                         configuration (chmod 600)
~/.local/state/marangatu/                                   per-period markers & invoice records (JSON)
~/.local/state/marangatu/logs/<timestamp>_<cmd>_<period>/   run.log + step screenshots
~/.local/share/marangatu/documentos/<date>/                 downloads from the `documentos` subcommand
```

The script honours `XDG_CONFIG_HOME`, `XDG_STATE_HOME` and `XDG_DATA_HOME`;
the paths above are the defaults.

## Troubleshooting & known quirks

- The portal opens almost every action in a **new browser window**, sometimes 1–2
  minutes after the click (server-side AJAX before `window.open`). The script polls
  patiently and retries clicks up to 3×; don't panic at slow runs.
- Screenshots occasionally hang on *"waiting for fonts"* — a CDP fallback is built in.
- The Form 120 / Form 241 flows are battle-tested; the *invoice, imputation and boleta*
  screens were implemented from the guide's screenshots with cascading selector
  fallbacks. If DNIT changes the markup, check the step screenshots in the logs and
  adjust the selector cascades (`first_visible`, `control_by_label`).
- Log and report messages are in Slovak (the original operator's language). PRs adding
  English/Spanish message localisation are welcome.

## Sources

- [DNM: Migraciones actualiza el régimen de acreditación de solvencia económica](https://migraciones.gov.py/migraciones-actualiza-el-regimen-de-acreditacion-de-solvencia-economica-para-extranjeros/)
- [liberation.travel: Paraguay permanent residency — new conditions 2026](https://liberation.travel/paraguay-permanent-residency-new-conditions-2026/)
- [ABC Color: cambios para acceder a la residencia permanente](https://www.abc.com.py/nacionales/2026/06/25/atencion-extranjeros-estos-son-los-cambios-para-acceder-a-la-residencia-permanente-en-paraguay/)
