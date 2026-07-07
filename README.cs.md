# marangatu-residencia

**[English](README.md) | [Español](README.es.md) | [Slovensky](README.sk.md) | [Česky](README.cs.md)**

Headless automatizace měsíční daňové rutiny na paraguayském portálu **Marangatu**
([marangatu.set.gov.py/eset](https://marangatu.set.gov.py/eset/), online daňový systém
DNIT), která generuje **nenulová měsíční přiznání IVA (DPH)** potřebná k prokázání
ekonomické solventnosti pro **trvalou rezidenci** podle **Rezoluce DNM č. 407/2026**.

> ⚠️ **Upozornění.** Vše, co se přes Marangatu podává, má charakter čestného prohlášení
> (*declaración jurada*). Tento nástroj kliká na stejná tlačítka, na která byste klikali
> ručně, ale za podané dokumenty odpovídáte **vy**. Nejde o právní ani daňové
> poradenství. První běh každého subpříkazu provádějte vždy s `--dry-run`, zkontrolujte
> screenshoty a cokoli nad rámec jednoduchého scénáře jedna-faktura-měsíčně (odpočty
> nákladů, IRP, speciální režimy) konzultujte s účetním.

## Kontext

Od **6. července 2026** vyžaduje [Rezoluce DNM 407/2026](https://migraciones.gov.py/migraciones-actualiza-el-regimen-de-acreditacion-de-solvencia-economica-para-extranjeros/)
(v rámci migračního zákona 6984/22) při přechodu z dočasné na trvalou rezidenci
*aktivní* prokázání ekonomické solventnosti. Pro živnostenskou cestu (lokální příjem)
to znamená:

- minimálně **3 po sobě jdoucí měsíční přiznání IVA s reálnou, nenulovou aktivitou** —
  nulová přiznání se už neakceptují;
- **RUC** aktivní a bez nedoplatků zhruba 4 měsíce v okamžiku podání;
- doložený příjem alespoň na úrovni paraguayské minimální mzdy
  (v praxi **≈ 500–600 USD měsíčně**);
- podpůrné daňové dokumenty: přiznání Form 120, *certificado de cumplimiento
  tributario*, *constancia de RUC*, *cédula tributaria*, *constancia de movimiento
  tributario*.

Nástroj automatizuje příslušnou měsíční rutinu na Marangatu (faktura → imputace →
Form 120 → talón Form 241 → platební lístek) podle komunitního manuálu
*„GUÍA PRÁCTICA PARA GENERAR LOS DOCUMENTOS NECESARIOS PARA LA RESIDENCIA PERMANENTE EN
PARAGUAY"*.

## Co dělá

| Subpříkaz    | Kdy             | Kroky manuálu | Co se stane |
|--------------|-----------------|---------------|-------------|
| `facturar`   | ~25. den měsíce | 1–2           | Vystaví jednu virtuální fakturu za **aktuální** měsíc na nakonfigurovaného klienta. Částka = `MIN_INCOME_USD × kurz × SAFETY_MARGIN`, zaokrouhlená nahoru na násobek 11 000 Gs. Uloží stavový záznam, který později použije `declarar`. |
| `declarar`   | ~5. den měsíce  | 3–5, 9        | Za **předchozí** měsíc: imputuje prodejní doklady (*ventas a imputar → imputar todo*), podá **Form 120** (IVA General, obligación 211) s políčkem 10 = brutto/11×10, podá **talón Form 241** a vygeneruje platební lístek (*boleta de pago*, příloha reportu). |
| `documentos` | před podáním žádosti | 7–8      | Best-effort stažení *certificado de cumplimiento tributario*, *constancia de RUC* a *cédula tributaria* do `~/marangatu/documentos/`. |

Samotná **platba IVA automatizovaná není** — boletu zaplatíte v libovolné paraguayské
bankovní aplikaci (*Pagar servicios → DNIT*, zadat cédulu/RUC + datum narození).
Report vám to každý měsíc připomene.

### Matematika

Při 10% sazbě IVA bere Marangatu částku faktury včetně IVA: základ daně =
brutto × 10/11 (to se vyplňuje do políčka 10 na Form 120) a IVA = brutto / 11. Skript
zaokrouhluje brutto částku **nahoru na násobek 11 000 Gs**, aby základ i IVA vyšly
v celých guaraních a automaticky dopočítané hodnoty portálu šly porovnat přesně
s očekáváním skriptu.

Příklad s defaulty (`MIN_INCOME_USD=600`, rezerva 1,10, kurz 7 300 Gs/USD):
brutto = 4 818 000 Gs → základ 4 380 000 Gs (políčko 10), IVA 438 000 Gs ≈ 60 USD/měs.

### Bezpečnostní pojistky

- **Špatné heslo → okamžitý stop, žádné opakování** (Marangatu po opakovaných selháních
  blokuje účet).
- **Nikdy nepodává rektifikaci**: pokud se Form 120 otevře jako *RECTIFICATIVA*, období
  už bylo podáno a skript skončí.
- `declarar` **odmítne běžet**, pokud neexistuje záznam o vystavené faktuře za období —
  nikdy potichu nepodá nulové přiznání a nezničí vaši 3měsíční řadu.
  (Obejít lze přes `--amount-gs`, jen pokud jste si jistí, že faktura existuje.)
- Před každým finálním klikem *Presentar/Confirmar* skript čeká, dokud portál nedopočítá
  **přesně** očekávané částky; při jakékoli neshodě končí bez podání.
- Každý krok má screenshot v `~/marangatu/logs/<run>/`; po každém běhu se posílá
  e-mailový report (se screenshoty a PDF boletou).
- Přechodné chyby se opakují 3× s 10minutovými pauzami; každý pokus má tvrdý strop
  40 minut. Idempotentní markery (`~/marangatu/state/`) + `--only-if-not-done` dělají
  záložní crony bezpečnými.

## Požadavky

- Linuxový server schopný provozovat headless Chromium (vyvíjeno na Ubuntu)
- Python 3.9+ s [Playwright](https://playwright.dev/python/)
- **aktivní RUC** a přihlášení do Marangatu (číslo céduly + heslo)
- **timbrado** vyžádané jednou předem (krok 1 manuálu — jednorázová ruční akce v
  *Facturación y Timbrado → Solicitudes → Comprobantes Virtuales → Factura Virtual*)
- volitelně: funkční `sendmail` pro e-mailové reporty

## Instalace

```bash
mkdir -p ~/marangatu && cd ~/marangatu
python3 -m venv venv
venv/bin/pip install playwright
venv/bin/playwright install --with-deps chromium
git clone https://github.com/wilderko/marangatu-residencia.git src
ln -s src/marangatu_residencia.py .
```

## Konfigurace

Dva soubory, oba `chmod 600`:

`~/.config/marangatu/credentials`

```
USUARIO=1234567        # číslo vaší céduly
PASSWORD=...
```

`~/.config/marangatu/residencia.conf` — vycházejte z
[`residencia.conf.example`](residencia.conf.example):

| Klíč | Default | Význam |
|------|---------|--------|
| `MAIL_TO` | *(prázdné)* | Příjemce reportů. Prázdné = e-mail se neposílá (report zůstává v logu). |
| `MAIL_FROM` | `Marangatu bot <marangatu@localhost>` | Odesílatel. Použijte adresu, jejíž doména má v SPF záznamu IP vašeho serveru, jinak reporty skončí ve spamu. |
| `SENDMAIL` | `/usr/sbin/sendmail` | Cesta k sendmailu. |
| `MIN_INCOME_USD` | `600` | Měsíční příjem, který má faktura dokládat. Rez. 407/2026 očekává zhruba minimální mzdu (~500–600 USD). |
| `SAFETY_MARGIN` | `1.10` | Faktura se vystaví o 10 % vyšší, aby vás oslabení guaraní nikdy nesrazilo pod minimum. |
| `FX_RATE_PYG` | *(prázdné)* | Pevný kurz Gs/USD. Prázdné = stáhne se aktuální z open.er-api.com. |
| `FX_RATE_FALLBACK` | `7500` | Kurz použitý, když FX API nefunguje. |
| `CLIENT_SITUACION` | `NO_DOMICILIADO` | `NO_DOMICILIADO` = zahraniční osoba/firma bez paraguayského RUC (např. vaše LLC); `CONTRIBUYENTE` = lokální klient s RUC. |
| `CLIENT_RUC` | | Pro `CONTRIBUYENTE`: číslice RUC před pomlčkou (jméno si portál dohledá sám). |
| `CLIENT_ID` | | Pro `NO_DOMICILIADO`: číslo pasu nebo zahraniční tax ID. |
| `CLIENT_ID_TYPE` | `Pasaporte` | Text option-u v selectu *Tipo de Identificación* (např. `Identificación Tributaria`). |
| `CLIENT_NAME` / `CLIENT_ADDRESS` / `CLIENT_COUNTRY` / `CLIENT_EMAIL` / `CLIENT_PHONE` | | Údaje klienta tak, jak mají být na faktuře. `CLIENT_COUNTRY` je text option-u selectu *País* (např. `ESTADOS UNIDOS`). |
| `SERVICE_DESCRIPTION` | `Servicios de consultoría informática` | Popis služby na faktuře. |

## Používání

```bash
V=~/marangatu/venv/bin/python

# VŽDY začněte dry-runem — provede vše kromě finálních potvrzovacích kliků,
# poté zkontrolujte screenshoty v ~/marangatu/logs/<run>/
$V marangatu_residencia.py facturar --dry-run
$V marangatu_residencia.py declarar --dry-run

# ostré běhy
$V marangatu_residencia.py facturar                  # faktura za aktuální měsíc
$V marangatu_residencia.py facturar --amount-gs 4818000   # pevná částka místo USD×kurz
$V marangatu_residencia.py declarar                  # přiznání za minulý měsíc
$V marangatu_residencia.py declarar --month 2026-07  # konkrétní období
$V marangatu_residencia.py documentos                # stáhnout podklady k žádosti
```

Společné přepínače: `--dry-run`, `--no-email`, `--only-if-not-done` (skonči tiše, pokud
období už má done-marker — pro záložní crony), `--retries N`.

Exit kód 0 = úspěch (report odeslán), 1 = selhání po opakováních (chybový report
s posledními screenshoty jde e-mailem).

### Cron

```cron
# faktura za běžící měsíc (musí být vystavena v měsíci, který dokládá)
0 14 25 * * ~/marangatu/venv/bin/python ~/marangatu/marangatu_residencia.py facturar
0 14 27 * * ~/marangatu/venv/bin/python ~/marangatu/marangatu_residencia.py facturar --only-if-not-done
# přiznání za předchozí měsíc (první týden, před splatností podle poslední číslice RUC)
0 14 5 * *  ~/marangatu/venv/bin/python ~/marangatu/marangatu_residencia.py declarar
0 14 7 * *  ~/marangatu/venv/bin/python ~/marangatu/marangatu_residencia.py declarar --only-if-not-done
```

> ⚠️ **Pokud jste dosud automatizovali nulová přiznání, nejprve ten cron odstraňte.**
> Nulový Form 120 podaný za měsíc s fakturou si vynutí rektifikaci a nulový měsíc
> restartuje 3měsíční řadu.

### Časová osa k trvalé rezidenci

| Měsíc | 25. den | 5. den následujícího měsíce |
|-------|---------|------------------------------|
| M1 | faktura č. 1 | — |
| M2 | faktura č. 2 | přiznání M1 (nenulové č. 1) + platba IVA |
| M3 | faktura č. 3 | přiznání M2 (nenulové č. 2) + platba IVA |
| M4 | — | přiznání M3 (nenulové č. 3) + platba IVA → `documentos`, podání žádosti na DNM |

Průběžný náklad: samotné IVA, brutto/11 měsíčně (≈ 60 USD při defaultech) — je to
skutečná daň, ne poplatek.

## Co automatizované NENÍ

- **platba** bolety (bankovní aplikace: *Pagar servicios → DNIT*),
- jednorázové vyžádání **timbrada** (krok 1 manuálu),
- odpočty nákladů ve Form 120 (poraďte se s účetním),
- migrační dokumenty (certifikát Interpolu, výpis z rejstříku trestů, termín na DNM).

## Soubory

```
~/.config/marangatu/credentials       přihlášení (chmod 600)
~/.config/marangatu/residencia.conf   konfigurace (chmod 600)
~/marangatu/state/                    markery období a záznamy faktur (JSON)
~/marangatu/logs/<timestamp>_<cmd>_<období>/   run.log + screenshoty kroků
~/marangatu/documentos/<datum>/       výstupy subpříkazu documentos
```

## Řešení problémů a známé zvláštnosti

- Portál otevírá téměř každou akci v **novém okně prohlížeče**, někdy 1–2 minuty po
  kliknutí (server-side AJAX před `window.open`). Skript trpělivě polluje a kliky
  opakuje až 3× — pomalé běhy jsou normální.
- Screenshoty občas visí na *„waiting for fonts"* — vestavěný je CDP fallback.
- Toky Form 120 / Form 241 jsou ověřené v praxi; obrazovky *faktura, imputace a boleta*
  byly implementovány podle screenshotů manuálu s kaskádami záložních selektorů.
  Pokud DNIT změní markup, podívejte se na screenshoty kroků v lozích a upravte kaskády
  (`first_visible`, `control_by_label`).
- Logy a reporty jsou ve slovenštině. PR s anglickou/španělskou lokalizací jsou vítány.

## Zdroje

- [DNM: Migraciones actualiza el régimen de acreditación de solvencia económica](https://migraciones.gov.py/migraciones-actualiza-el-regimen-de-acreditacion-de-solvencia-economica-para-extranjeros/)
- [liberation.travel: Paraguay permanent residency — new conditions 2026](https://liberation.travel/paraguay-permanent-residency-new-conditions-2026/)
- [ABC Color: cambios para acceder a la residencia permanente](https://www.abc.com.py/nacionales/2026/06/25/atencion-extranjeros-estos-son-los-cambios-para-acceder-a-la-residencia-permanente-en-paraguay/)
