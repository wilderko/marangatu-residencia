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
- documented income just above the Paraguayan minimum wage
  (**₲3,044,000 per month** in 2026, ≈ USD 510);
- supporting tax documents: Form 120 declarations, tax compliance certificate
  (*certificado de cumplimiento tributario*), RUC registration
  (*constancia de RUC*), *cédula tributaria*, *constancia de movimiento tributario*.

This tool automates the corresponding monthly Marangatu routine (invoice → imputation incl.
the *Obligaciones* step → Form 120 incl. Rubro 2 → Form 241 talón → payment slip), as
described in the Slovak client manual
[*Paraguay_navod_pobyt_SK.pdf*](https://liberation.travel/wp-content/uploads/2026/06/Paraguay_navod_pobyt_SK.pdf)
(updated September 2026), itself based on the community guide *"GUÍA PRÁCTICA PARA GENERAR
LOS DOCUMENTOS NECESARIOS PARA LA RESIDENCIA PERMANENTE EN PARAGUAY"*.

## What it does

| Subcommand   | When            | Guide steps | What happens |
|--------------|-----------------|-------------|--------------|
| `facturar`   | ~25th of month  | 1–2         | Issues one virtual invoice for the **current** month to your configured client. Amount = `max(MIN_INCOME_GS × 11/10, MIN_INCOME_USD × FX rate) × SAFETY_MARGIN`, rounded up to a multiple of 11,000 Gs, so the taxable base always sits just above the minimum wage. Saves a state record used later by `declarar`. |
| `declarar`   | ~5th of month (before your due date) | 3–5, 9 | For the **previous** month: imputes the sales vouchers (*ventas a imputar → imputar todo → siguiente → imputar comprobantes*), sets the **Obligaciones asociadas** switches (only `IMPUTAR_OBLIGACIONES` green, typically IVA GENERAL; IRP–RSP and IRE red) and clicks *Procesar Imputación*; files **Form 120** (IVA General, obligation 211) with Rubro 1 box 10 = gross/11×10 **and Rubro 2** (box 160 = 6-period accumulated sales, 27 = 31 = 160, rest 0); presents the **Form 241 talón**; generates the payment slip (*boleta de pago*, attached to the report e-mail). Logs the filing **and payment** due date for your RUC. |
| `documentos` | before applying | 6–8         | Best-effort download of the latest Form 120 PDFs, the *certificado de cumplimiento tributario*, *constancia de RUC* and *cédula tributaria* into `~/.local/share/marangatu/documentos/`. |
| `vencimiento`| any time        | 4           | Offline (no login): prints the filing + payment due date for a period from the last digit of your RUC. |

Paying the IVA itself is **not** automated — you pay the generated boleta in any
Paraguayan banking app (*Pagar servicios → DNIT*, enter cédula/RUC + date of birth)
**by the same due date as the declaration**. The report e-mail reminds you every month,
with the date.

### The arithmetic

At the 10 % IVA rate, Marangatu treats the invoice total as IVA-inclusive:
taxable base = gross × 10/11 (that is what goes into Form 120 box 10) and
IVA = gross / 11. The script rounds the gross amount **up to a multiple of 11,000 Gs**
so that both the base and the IVA come out in whole guaraníes and the portal's
auto-computed figures can be compared byte-for-byte against the script's expectations.

The guide asks for an invoice "just above the minimum wage (₲3,044,000 a month)". The
script compares the minimum wage with the **taxable base** (box 10 — the income DNM
sees), so the gross must be at least `MIN_INCOME_GS × 11/10`; `MIN_INCOME_USD × rate`
is kept as a second floor and the higher of the two wins.

Example with the defaults (`MIN_INCOME_GS=3044000`, `MIN_INCOME_USD=600`, margin 1.10,
rate 5,990 Gs/USD): max(3,348,400; 3,594,000) × 1.10 → gross 3,960,000 Gs → base
3,600,000 Gs (box 10), IVA 360,000 Gs ≈ USD 60/month — the "≈ ₲360,000 of tax a month"
the guide mentions.

### Form 120 Rubro 2

Rubro 2 (*"Enajenación de bienes y/o prestación de servicios de los últimos seis (6)
meses, incluido el periodo que se declara"*) is filled by the taxpayer — Marangatu does
not compute it. The script enters box **160** = sum of box 10 over the last six monthly
periods **including** the one being declared, leaves **161, 26, 162, 163, 29** at 0,
and checks (or fills, if the form does not compute them) **27** = 160+161+26,
**30** = 162+163+29 = 0 and **31** = 27+30. In the first return 160 = 10; from the
seventh month it is a rolling six-period window. With a ₲6,000,000 invoice a month:
160 = 5,454,545 in month 1, 16,363,635 in month 3.

The history comes from the script's own records (filed Form 120s, then invoice records).
A period inside the window that has **no** record is never guessed as zero on a live run —
set `RUC_START` (periods before it count as 0) and/or `PRIOR_SALES_10` for periods you
filed by hand. In `--dry-run` the gap is only warned about.

### Due date (calendario perpetuo)

Declaration **and payment** are due on the same day of the following month, set by the
**last digit of your RUC before the hyphen** (the check digit after it does not count):
0→7th, 1→9th, 2→11th, 3→13th, 4→15th, 5→17th, 6→19th, 7→21st, 8→23rd, 9→25th; a weekend
or holiday moves it to the next business day. Example: RUC 1234567-8 ends in 7, so the
September return is due on 21 October. Spouses each have their own RUC and their own
date. The script knows fixed-date Paraguayan holidays and Holy Thursday/Good Friday;
holidays that get moved each year (1 Mar, 12 Jun, 29 Sep) go into `HOLIDAYS` — a missing
holiday only ever makes the computed date *earlier*, never later. `declarar` logs the
date, warns on the last day, and flags a late filing.

### Safety guards

- **Wrong password → immediate stop, no retry** (Marangatu locks accounts after
  repeated failures).
- **Never files a rectification**: if Form 120 opens as *RECTIFICATIVA*, the period was
  already filed and the script aborts.
- `declarar` **refuses to run** if there is no record of an issued invoice for the
  period — it will never silently file a zero declaration and break your 3-month chain.
  (Override with `--amount-gs` only if you are sure the invoice exists.)
- **Obligaciones**: only the obligations in `IMPUTAR_OBLIGACIONES` are switched green,
  every other one red, and the state of every switch is re-read before *Procesar
  Imputación* (an imputation to a tax your RUC does not hold ends up as an
  *inconsistencia*, and *Ventas a imputar* has no "no imputar" option). If a wanted
  obligation is not offered, or a switch cannot be read, nothing is imputed.
- **Rubro 2** is computed before logging in; a missing period in the six-month window
  stops a live run before anything is touched. Boxes 10, 160, 27 and 31 are read back
  before *Presentar*.
- `--interactive` opens a visible browser, asks y/N before every irreversible click
  (invoice, *Procesar Imputación*, Form 120, Form 241) and pauses for a manual fix on any
  screen the script cannot handle reliably. Without it, such a screen aborts the run
  (no retry) without confirming anything.
- Before every final *Presentar/Confirmar* click the script waits until the portal has
  computed **exactly** the expected amounts; on any mismatch it aborts without filing.
- Every step is screenshotted to `~/.local/state/marangatu/logs/<run>/`; a report (with screenshots
  and the boleta PDF) is e-mailed after every run.
- Transient failures are retried 3× with 10-minute pauses; each attempt has a hard
  40-minute cap. Idempotent state markers (`~/.local/state/marangatu/`) plus
  `--only-if-not-done` make backup cron runs safe.

## Requirements

- Linux host that can run a headless browser — Chromium (default) or Firefox/Gecko (developed on Ubuntu)
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
# optional — to drive the portal with Firefox (Gecko) instead, install it too and
# select it via BROWSER=firefox in residencia.conf or the --browser firefox flag:
#   venv/bin/playwright install --with-deps firefox
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
| `MIN_INCOME_GS` | `3044000` | Paraguayan minimum wage (Gs/month). The invoice's taxable base (box 10) is kept above it. |
| `MIN_INCOME_USD` | `600` | Optional second floor in USD (× FX rate, compared with the gross); the higher floor wins. `0` = ignore. |
| `SAFETY_MARGIN` | `1.10` | Invoice is issued 10 % above the floor ("something above the minimum wage"; also absorbs FX moves). |
| `FX_RATE_PYG` | *(empty)* | Fixed Gs/USD rate. Empty = fetch the current rate from open.er-api.com. |
| `FX_RATE_FALLBACK` | `6000` | Rate used when the FX API is unreachable. |
| `CLIENT_SITUACION` | `NO_DOMICILIADO` | `NO_DOMICILIADO` = foreign person/company without a Paraguayan RUC (e.g. your LLC); `CONTRIBUYENTE` = local client with RUC. |
| `CLIENT_RUC` | | For `CONTRIBUYENTE`: RUC digits before the dash (the portal auto-fills the name). |
| `CLIENT_ID` | | For `NO_DOMICILIADO`: passport number or foreign tax ID. |
| `CLIENT_ID_TYPE` | `Pasaporte` | Text of the option in the *Tipo de Identificación* select (e.g. `Identificación Tributaria`). |
| `CLIENT_NAME` / `CLIENT_ADDRESS` / `CLIENT_COUNTRY` / `CLIENT_EMAIL` / `CLIENT_PHONE` | | Client data as it should appear on the invoice. `CLIENT_COUNTRY` is the option text of the *País* select (e.g. `ESTADOS UNIDOS`). |
| `SERVICE_DESCRIPTION` | `Servicios de consultoría informática` | Invoice line description. |
| `IMPUTAR_OBLIGACIONES` | `IVA GENERAL` | Comma-separated obligations switched **green** in the *Obligaciones asociadas* step; all others red. Add `IRP - RSP` only if your RUC is actually registered for it (mandatory above ₲80,000,000 of service income a year, art. 62 Ley 6380/2019). |
| `RUC` | *(empty)* | Your RUC (e.g. `1234567-8`) for the due-date calculation. Empty = taken from `USUARIO` (for an individual the RUC is the cédula number). |
| `HOLIDAYS` | *(empty)* | Extra non-working days `YYYY-MM-DD,…` (moved holidays, bank holidays) that push the due date. |
| `RUC_START` | *(empty)* | `YYYY-MM` of your first IVA period; earlier periods count as 0 in Rubro 2. |
| `PRIOR_SALES_10` | *(empty)* | Box 10 of periods the script has no record of, `YYYY-MM:base,…` (e.g. `2026-05:0,2026-06:3600000`). |

## Usage

```bash
V=~/marangatu/venv/bin/python

# ALWAYS start with a dry run — does everything except the final confirm clicks,
# then check the screenshots in ~/.local/state/marangatu/logs/<run>/
$V marangatu_residencia.py facturar --dry-run
$V marangatu_residencia.py declarar --dry-run

# real runs
$V marangatu_residencia.py facturar                  # invoice for the current month
$V marangatu_residencia.py facturar --amount-gs 3960000   # fixed amount instead of the computed one
$V marangatu_residencia.py declarar                  # declare the previous month
$V marangatu_residencia.py declarar --month 2026-07  # declare a specific period
$V marangatu_residencia.py documentos                # download residency paperwork
$V marangatu_residencia.py vencimiento --month 2026-09   # due date (offline, no login)

# first live run of the new imputation / Rubro 2 screens: visible browser,
# y/N before every irreversible click, manual fallback where needed
$V marangatu_residencia.py declarar --interactive
```

Common flags: `--dry-run`, `--no-email`, `--only-if-not-done` (exit silently when the
period already has a done-marker — for backup crons), `--retries N`, `--interactive`
(needs a terminal and a display; not for cron).

`--dry-run` of `declarar` goes as far as the *Obligaciones* switches (it clicks the
wizard's *Imputar comprobantes* step, which only moves to the next screen) and fills
Rubro 1 + Rubro 2, but does **not** click *Procesar Imputación* or *Presentar*.

Exit code 0 = success (report e-mailed), 1 = failed after retries (error report with the
last screenshots is e-mailed).

### Cron

```cron
# invoice for the running month (must be issued inside the month it documents)
0 14 25 * * ~/marangatu/venv/bin/python ~/marangatu/marangatu_residencia.py facturar
0 14 27 * * ~/marangatu/venv/bin/python ~/marangatu/marangatu_residencia.py facturar --only-if-not-done
# declaration of the previous month — the 5th/6th are before every possible due date
# (earliest is the 7th, for RUCs ending in 0); check yours with `vencimiento`
0 14 5 * *  ~/marangatu/venv/bin/python ~/marangatu/marangatu_residencia.py declarar
0 14 6 * *  ~/marangatu/venv/bin/python ~/marangatu/marangatu_residencia.py declarar --only-if-not-done
```

Pay the boleta in your banking app **by the same due date** — a late declaration or
payment means a fine plus late-payment surcharges.

> ⚠️ **If you previously automated zero declarations, remove that cron first.** A zero
> Form 120 filed for a month with an invoice forces a rectification and a zero month
> restarts your 3-month chain.

### Timeline to permanent residency

| Month | 25th | 5th of next month (due date: by RUC digit, 7th–25th) |
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
- expense deductions on Form 120 (Rubro 3, *Compras locales e importaciones*; talk to an accountant),
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
- The Form 120 Rubro 1 / Form 241 flows are battle-tested; the *invoice, imputation and
  boleta* screens were implemented from the guide's screenshots with cascading selector
  fallbacks. If DNIT changes the markup, check the step screenshots in the logs and
  adjust the selector cascades (`first_visible`, `control_by_label`).
- **Not yet verified against the live portal** (added October 2026 from the updated
  guide): the *Imputar comprobantes → Obligaciones asociadas → Procesar Imputación*
  screens (switch widgets are read via checkbox / `aria-checked` / CSS class), the
  Rubro 2 boxes (located by `name='c160'`-style names like box 10, then by the box
  number after the "RUBRO 2" heading) and the Form 120 download links on the dashboard.
  Do the first run with `--dry-run`, then `--interactive`, and check screenshots
  `24_obligaciones_*`, `25_obligaciones_nastavene` and `32_form120_vyplneny`.
- After imputing, inconsistencies (e.g. an imputation to a tax the RUC does not hold)
  show up in *Herramientas → Consulta de Estado de Procesos de Imputación*.
- Log and report messages are in Slovak (the original operator's language). PRs adding
  English/Spanish message localisation are welcome.

## Sources

- [Slovak client manual (September 2026)](https://liberation.travel/wp-content/uploads/2026/06/Paraguay_navod_pobyt_SK.pdf)
- DNIT: *Cómo obtener comprobantes electrónicos y virtuales* (RG 90/2021), *Instructivo del Formulario N° 120 v4*, calendario perpetuo (RG 38/2020)
- [DNM: Migraciones actualiza el régimen de acreditación de solvencia económica](https://migraciones.gov.py/migraciones-actualiza-el-regimen-de-acreditacion-de-solvencia-economica-para-extranjeros/)
- [liberation.travel: Paraguay permanent residency — new conditions 2026](https://liberation.travel/paraguay-permanent-residency-new-conditions-2026/)
- [ABC Color: cambios para acceder a la residencia permanente](https://www.abc.com.py/nacionales/2026/06/25/atencion-extranjeros-estos-son-los-cambios-para-acceder-a-la-residencia-permanente-en-paraguay/)
