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
- doložený příjem o něco vyšší než paraguayská minimální mzda
  (**3 044 000 Gs měsíčně** v roce 2026, ≈ 510 USD);
- podpůrné daňové dokumenty: přiznání Form 120, *certificado de cumplimiento
  tributario*, *constancia de RUC*, *cédula tributaria*, *constancia de movimiento
  tributario*.

Nástroj automatizuje příslušnou měsíční rutinu na Marangatu (faktura → imputace včetně
kroku *Obligaciones* → Form 120 včetně Rubro 2 → talón Form 241 → platební lístek) podle
klientského návodu
[*Paraguay_navod_pobyt_SK.pdf*](https://liberation.travel/wp-content/uploads/2026/06/Paraguay_navod_pobyt_SK.pdf)
(aktualizovaný září 2026), který vychází z komunitního manuálu *„GUÍA PRÁCTICA PARA
GENERAR LOS DOCUMENTOS NECESARIOS PARA LA RESIDENCIA PERMANENTE EN PARAGUAY"*.

## Co dělá

| Subpříkaz    | Kdy             | Kroky manuálu | Co se stane |
|--------------|-----------------|---------------|-------------|
| `facturar`   | ~25. den měsíce | 1–2           | Vystaví jednu virtuální fakturu za **aktuální** měsíc na nakonfigurovaného klienta. Částka = `max(MIN_INCOME_GS × 11/10, MIN_INCOME_USD × kurz) × SAFETY_MARGIN`, zaokrouhlená nahoru na násobek 11 000 Gs, takže základ daně je vždy o něco nad minimální mzdou. Uloží stavový záznam, který později použije `declarar`. |
| `declarar`   | ~5. den měsíce (před termínem) | 3–5, 9 | Za **předchozí** měsíc: imputuje prodejní doklady (*ventas a imputar → imputar todo → siguiente → imputar comprobantes*), nastaví přepínače **Obligaciones asociadas** (zeleně jen `IMPUTAR_OBLIGACIONES`, typicky IVA GENERAL; IRP–RSP a IRE červeně) a klikne *Procesar Imputación*; podá **Form 120** (IVA General, obligación 211) s Rubro 1 políčkem 10 = brutto/11×10 **a Rubro 2** (políčko 160 = kumulativ za 6 období, 27 = 31 = 160, zbytek 0); podá **talón Form 241**; vygeneruje platební lístek (*boleta de pago*, příloha reportu). Zaloguje termín podání **i platby** podle vašeho RUC. |
| `documentos` | před podáním žádosti | 6–8      | Best-effort stažení posledních Form 120, *certificado de cumplimiento tributario*, *constancia de RUC* a *cédula tributaria* do `~/.local/share/marangatu/documentos/`. |
| `vencimiento`| kdykoli         | 4             | Offline (bez přihlášení): vypíše termín podání + platby za období podle poslední číslice RUC. |

Samotná **platba IVA automatizovaná není** — boletu zaplatíte v libovolné paraguayské
bankovní aplikaci (*Pagar servicios → DNIT*, zadat cédulu/RUC + datum narození)
**do stejného termínu jako přiznání**. Report vám to každý měsíc připomene i s datem.

### Matematika

Při 10% sazbě IVA bere Marangatu částku faktury včetně IVA: základ daně =
brutto × 10/11 (to se vyplňuje do políčka 10 na Form 120) a IVA = brutto / 11. Skript
zaokrouhluje brutto částku **nahoru na násobek 11 000 Gs**, aby základ i IVA vyšly
v celých guaraních a automaticky dopočítané hodnoty portálu šly porovnat přesně
s očekáváním skriptu.

Návod žádá fakturu „o něco vyšší než minimální mzda (₲3 044 000 měsíčně)". Skript
porovnává minimální mzdu se **základem daně** (políčko 10 — příjem, který vidí DNM), takže
brutto musí být alespoň `MIN_INCOME_GS × 11/10`; `MIN_INCOME_USD × kurz` zůstává jako
druhé minimum a platí vyšší z obou.

Příklad s defaulty (`MIN_INCOME_GS=3044000`, `MIN_INCOME_USD=600`, rezerva 1,10,
kurz 5 990 Gs/USD): max(3 348 400; 3 594 000) × 1,10 → brutto 3 960 000 Gs → základ
3 600 000 Gs (políčko 10), IVA 360 000 Gs ≈ 60 USD/měs. — tedy „řádově ₲360 000 měsíčně
na dani", jak uvádí návod.

### Form 120 Rubro 2

Rubro 2 (*„Enajenación de bienes y/o prestación de servicios de los últimos seis (6)
meses, incluido el periodo que se declara"*) vyplňuje poplatník — Marangatu ho nespočítá.
Skript zadá políčko **160** = součet políčka 10 za posledních šest měsíčních období
**včetně** přiznávaného, **161, 26, 162, 163, 29** nechá na 0 a ověří (nebo doplní, pokud
je formulář nedopočítá) **27** = 160+161+26, **30** = 162+163+29 = 0 a **31** = 27+30.
V prvním přiznání 160 = 10; od sedmého měsíce jde o klouzavé okno šesti období. Při
faktuře ₲6 000 000 měsíčně: 160 = 5 454 545 v prvním měsíci, 16 363 635 ve třetím.

Historie se bere z vlastních záznamů skriptu (podané Form 120, pak záznamy faktur).
Období v okně **bez** záznamu se v ostrém běhu nikdy neodhadne jako nula — nastavte
`RUC_START` (starší období = 0) a/nebo `PRIOR_SALES_10` pro období podaná ručně.
V `--dry-run` jde jen o varování.

### Termín (calendario perpetuo)

Přiznání **i platba** jsou splatné ve stejný den následujícího měsíce podle **poslední
číslice RUC před pomlčkou** (kontrolní číslice za pomlčkou se nepočítá): 0→7., 1→9.,
2→11., 3→13., 4→15., 5→17., 6→19., 7→21., 8→23., 9→25.; víkend nebo svátek ho posouvá na
nejbližší pracovní den. Příklad: RUC 1234567-8 končí na 7, přiznání za září se tedy
podává do 21. října. Manželé mají každý vlastní RUC, a tedy i vlastní termín. Skript zná
paraguayské svátky s pevným datem a Zelený čtvrtek/Velký pátek; přesouvané svátky
(1. 3., 12. 6., 29. 9.) patří do `HOLIDAYS` — chybějící svátek dá vždy jen *dřívější*
termín, nikdy pozdější. `declarar` termín zaloguje, v poslední den varuje a opožděné
podání označí.

### Bezpečnostní pojistky

- **Špatné heslo → okamžitý stop, žádné opakování** (Marangatu po opakovaných selháních
  blokuje účet).
- **Nikdy nepodává rektifikaci**: pokud se Form 120 otevře jako *RECTIFICATIVA*, období
  už bylo podáno a skript skončí.
- `declarar` **odmítne běžet**, pokud neexistuje záznam o vystavené faktuře za období —
  nikdy potichu nepodá nulové přiznání a nezničí vaši 3měsíční řadu.
  (Obejít lze přes `--amount-gs`, jen pokud jste si jistí, že faktura existuje.)
- **Obligaciones**: zeleně se přepnou jen povinnosti z `IMPUTAR_OBLIGACIONES`, všechny
  ostatní červeně, a stav každého přepínače se před *Procesar Imputación* znovu přečte
  (imputace k dani, kterou RUC nemá, skončí jako *inconsistencia* a v *Ventas a imputar*
  možnost „no imputar" není). Pokud požadovaná povinnost v nabídce není nebo přepínač
  nejde přečíst, nic se neimputuje.
- **Rubro 2** se počítá před přihlášením; chybějící období v 6měsíčním okně zastaví
  ostrý běh dřív, než se čehokoli dotkne. Políčka 10, 160, 27 a 31 se před *Presentar*
  zpětně přečtou.
- `--interactive` otevře viditelný prohlížeč, před každým nevratným klikem (faktura,
  *Procesar Imputación*, Form 120, Form 241) se ptá y/N a na obrazovce, kterou skript
  neumí spolehlivě obsloužit, počká na ruční zásah. Bez něj taková obrazovka běh ukončí
  (bez opakování) a nic nepotvrdí.
- Před každým finálním klikem *Presentar/Confirmar* skript čeká, dokud portál nedopočítá
  **přesně** očekávané částky; při jakékoli neshodě končí bez podání.
- Každý krok má screenshot v `~/.local/state/marangatu/logs/<run>/`; po každém běhu se posílá
  e-mailový report (se screenshoty a PDF boletou).
- Přechodné chyby se opakují 3× s 10minutovými pauzami; každý pokus má tvrdý strop
  40 minut. Idempotentní markery (`~/.local/state/marangatu/`) + `--only-if-not-done` dělají
  záložní crony bezpečnými.

## Požadavky

- Linuxový server schopný provozovat headless prohlížeč — Chromium (výchozí) nebo Firefox/Gecko (vyvíjeno na Ubuntu)
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
# volitelně — pro ovládání portálu přes Firefox (Gecko) doinstaluj i jej a
# vyber ho přes BROWSER=firefox v residencia.conf nebo přepínačem --browser firefox:
#   venv/bin/playwright install --with-deps firefox
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
| `MIN_INCOME_GS` | `3044000` | Paraguayská minimální mzda (Gs/měs.). Základ daně faktury (políčko 10) se drží nad ní. |
| `MIN_INCOME_USD` | `600` | Volitelné druhé minimum v USD (× kurz, porovnává se s brutto); platí vyšší minimum. `0` = nepoužít. |
| `SAFETY_MARGIN` | `1.10` | Faktura se vystaví o 10 % nad minimem („o něco nad minimální mzdou"; pokryje i pohyb kurzu). |
| `FX_RATE_PYG` | *(prázdné)* | Pevný kurz Gs/USD. Prázdné = stáhne se aktuální z open.er-api.com. |
| `FX_RATE_FALLBACK` | `6000` | Kurz použitý, když FX API nefunguje. |
| `CLIENT_SITUACION` | `NO_DOMICILIADO` | `NO_DOMICILIADO` = zahraniční osoba/firma bez paraguayského RUC (např. vaše LLC); `CONTRIBUYENTE` = lokální klient s RUC. |
| `CLIENT_RUC` | | Pro `CONTRIBUYENTE`: číslice RUC před pomlčkou (jméno si portál dohledá sám). |
| `CLIENT_ID` | | Pro `NO_DOMICILIADO`: číslo pasu nebo zahraniční tax ID. |
| `CLIENT_ID_TYPE` | `Pasaporte` | Text option-u v selectu *Tipo de Identificación* (např. `Identificación Tributaria`). |
| `CLIENT_NAME` / `CLIENT_ADDRESS` / `CLIENT_COUNTRY` / `CLIENT_EMAIL` / `CLIENT_PHONE` | | Údaje klienta tak, jak mají být na faktuře. `CLIENT_COUNTRY` je text option-u selectu *País* (např. `ESTADOS UNIDOS`). |
| `SERVICE_DESCRIPTION` | `Servicios de consultoría informática` | Popis služby na faktuře. |
| `IMPUTAR_OBLIGACIONES` | `IVA GENERAL` | Čárkou oddělené povinnosti, které se v kroku *Obligaciones asociadas* přepnou **zeleně**; ostatní červeně. `IRP - RSP` přidejte, jen pokud je na něj RUC skutečně registrované (povinné nad 80 000 000 Gs příjmu ze služeb ročně, čl. 62 zákona 6380/2019). |
| `RUC` | *(prázdné)* | Vaše RUC (např. `1234567-8`) pro výpočet termínu. Prázdné = vezme se `USUARIO` (u fyzické osoby je RUC číslo cédula). |
| `HOLIDAYS` | *(prázdné)* | Další dny volna `YYYY-MM-DD,…` (přesunuté svátky, bankovní volno), které posouvají termín. |
| `RUC_START` | *(prázdné)* | `YYYY-MM` prvního období s IVA; starší období se v Rubro 2 počítají jako 0. |
| `PRIOR_SALES_10` | *(prázdné)* | Políčko 10 období, o kterých skript nemá záznam, `YYYY-MM:základ,…` (např. `2026-05:0,2026-06:3600000`). |

## Používání

```bash
V=~/marangatu/venv/bin/python

# VŽDY začněte dry-runem — provede vše kromě finálních potvrzovacích kliků,
# poté zkontrolujte screenshoty v ~/.local/state/marangatu/logs/<run>/
$V marangatu_residencia.py facturar --dry-run
$V marangatu_residencia.py declarar --dry-run

# ostré běhy
$V marangatu_residencia.py facturar                  # faktura za aktuální měsíc
$V marangatu_residencia.py facturar --amount-gs 3960000   # pevná částka místo vypočtené
$V marangatu_residencia.py declarar                  # přiznání za minulý měsíc
$V marangatu_residencia.py declarar --month 2026-07  # konkrétní období
$V marangatu_residencia.py documentos                # stáhnout podklady k žádosti
$V marangatu_residencia.py vencimiento --month 2026-09   # termín (offline, bez přihlášení)

# první ostrý běh nových obrazovek imputace / Rubro 2: viditelný prohlížeč,
# y/N před každým nevratným klikem, ruční zásah, kde je potřeba
$V marangatu_residencia.py declarar --interactive
```

Společné přepínače: `--dry-run`, `--no-email`, `--only-if-not-done` (skonči tiše, pokud
období už má done-marker — pro záložní crony), `--retries N`, `--interactive`
(potřebuje terminál a displej; ne pro cron).

`--dry-run` u `declarar` projde až k přepínačům *Obligaciones* (klikne na krok průvodce
*Imputar comprobantes*, který jen přepne obrazovku) a vyplní Rubro 1 i Rubro 2, ale
**neklikne** *Procesar Imputación* ani *Presentar*.

Exit kód 0 = úspěch (report odeslán), 1 = selhání po opakováních (chybový report
s posledními screenshoty jde e-mailem).

### Cron

```cron
# faktura za běžící měsíc (musí být vystavena v měsíci, který dokládá)
0 14 25 * * ~/marangatu/venv/bin/python ~/marangatu/marangatu_residencia.py facturar
0 14 27 * * ~/marangatu/venv/bin/python ~/marangatu/marangatu_residencia.py facturar --only-if-not-done
# přiznání za předchozí měsíc — 5. a 6. den jsou před každým možným termínem
# (nejdřívější je 7. den u RUC končícího na 0); svůj ověřte přes `vencimiento`
0 14 5 * *  ~/marangatu/venv/bin/python ~/marangatu/marangatu_residencia.py declarar
0 14 6 * *  ~/marangatu/venv/bin/python ~/marangatu/marangatu_residencia.py declarar --only-if-not-done
```

Boletu zaplaťte v bankovní aplikaci **do stejného termínu** — opožděné přiznání nebo
platba znamená pokutu a přirážky za prodlení.

> ⚠️ **Pokud jste dosud automatizovali nulová přiznání, nejprve ten cron odstraňte.**
> Nulový Form 120 podaný za měsíc s fakturou si vynutí rektifikaci a nulový měsíc
> restartuje 3měsíční řadu.

### Časová osa k trvalé rezidenci

| Měsíc | 25. den | 5. den následujícího měsíce (termín: podle číslice RUC, 7.–25.) |
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
- odpočty nákladů ve Form 120 (Rubro 3, *Compras locales e importaciones*; poraďte se s účetním),
- migrační dokumenty (certifikát Interpolu, výpis z rejstříku trestů, termín na DNM).

## Soubory

```
~/.config/marangatu/credentials                              přihlášení (chmod 600)
~/.config/marangatu/residencia.conf                          konfigurace (chmod 600)
~/.local/state/marangatu/                                    markery období a záznamy faktur (JSON)
~/.local/state/marangatu/logs/<timestamp>_<cmd>_<období>/    run.log + screenshoty kroků
~/.local/share/marangatu/documentos/<datum>/                 výstupy subpříkazu documentos
```

Skript respektuje `XDG_CONFIG_HOME`, `XDG_STATE_HOME` a `XDG_DATA_HOME`;
cesty výše jsou výchozí.

## Řešení problémů a známé zvláštnosti

- Portál otevírá téměř každou akci v **novém okně prohlížeče**, někdy 1–2 minuty po
  kliknutí (server-side AJAX před `window.open`). Skript trpělivě polluje a kliky
  opakuje až 3× — pomalé běhy jsou normální.
- Screenshoty občas visí na *„waiting for fonts"* — vestavěný je CDP fallback.
- Toky Form 120 Rubro 1 / Form 241 jsou ověřené v praxi; obrazovky *faktura, imputace
  a boleta* byly implementovány podle screenshotů manuálu s kaskádami záložních
  selektorů. Pokud DNIT změní markup, podívejte se na screenshoty kroků v lozích
  a upravte kaskády (`first_visible`, `control_by_label`).
- **Zatím neověřené na živém portálu** (doplněno v říjnu 2026 podle aktualizovaného
  návodu): obrazovky *Imputar comprobantes → Obligaciones asociadas → Procesar
  Imputación* (stav přepínačů se čte přes checkbox / `aria-checked` / CSS třídu),
  políčka Rubro 2 (hledají se podle názvů typu `name='c160'` jako políčko 10, pak podle
  čísla políčka za nadpisem „RUBRO 2") a odkazy na stažení Form 120 na úvodní stránce.
  První běh udělejte s `--dry-run`, pak s `--interactive` a zkontrolujte screenshoty
  `24_obligaciones_*`, `25_obligaciones_nastavene` a `32_form120_vyplneny`.
- Nesrovnalosti po imputaci (např. přiřazení k dani, kterou RUC nemá) najdete
  v *Herramientas → Consulta de Estado de Procesos de Imputación*.
- Logy a reporty jsou ve slovenštině. PR s anglickou/španělskou lokalizací jsou vítány.

## Zdroje

- [Klientský návod, slovensky (září 2026)](https://liberation.travel/wp-content/uploads/2026/06/Paraguay_navod_pobyt_SK.pdf)
- DNIT: *Cómo obtener comprobantes electrónicos y virtuales* (RG 90/2021), *Instructivo del Formulario N° 120 v4*, calendario perpetuo (RG 38/2020)
- [DNM: Migraciones actualiza el régimen de acreditación de solvencia económica](https://migraciones.gov.py/migraciones-actualiza-el-regimen-de-acreditacion-de-solvencia-economica-para-extranjeros/)
- [liberation.travel: Paraguay permanent residency — new conditions 2026](https://liberation.travel/paraguay-permanent-residency-new-conditions-2026/)
- [ABC Color: cambios para acceder a la residencia permanente](https://www.abc.com.py/nacionales/2026/06/25/atencion-extranjeros-estos-son-los-cambios-para-acceder-a-la-residencia-permanente-en-paraguay/)
