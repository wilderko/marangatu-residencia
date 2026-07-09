# marangatu-residencia

**[English](README.md) | [Español](README.es.md) | [Slovensky](README.sk.md) | [Česky](README.cs.md)**

Headless automatizácia mesačnej daňovej rutiny na paraguajskom portáli **Marangatu**
([marangatu.set.gov.py/eset](https://marangatu.set.gov.py/eset/), online daňový systém
DNIT), ktorá generuje **nenulové mesačné IVA (DPH) deklarácie** potrebné na preukázanie
ekonomickej solventnosti pre **trvalú rezidenciu** podľa **Rezolúcie DNM č. 407/2026**.

> ⚠️ **Upozornenie.** Všetko, čo sa cez Marangatu podáva, má charakter čestného
> vyhlásenia (*declaración jurada*). Tento nástroj kliká na tie isté tlačidlá, na ktoré
> by ste klikali ručne, ale za podané dokumenty zodpovedáte **vy**. Toto nie je právne
> ani daňové poradenstvo. Prvý beh každého subpríkazu robte vždy s `--dry-run`,
> skontrolujte screenshoty a čokoľvek nad rámec jednoduchého scenára jedna-faktúra-
> mesačne (odpočty nákladov, IRP, špeciálne režimy) konzultujte s účtovníkom.

## Kontext

Od **6. júla 2026** vyžaduje [Rezolúcia DNM 407/2026](https://migraciones.gov.py/migraciones-actualiza-el-regimen-de-acreditacion-de-solvencia-economica-para-extranjeros/)
(v rámci migračného zákona 6984/22) pri prechode z dočasnej na trvalú rezidenciu
*aktívne* preukázanie ekonomickej solventnosti. Pre živnostenskú cestu (lokálny príjem)
to znamená:

- minimálne **3 po sebe idúce mesačné IVA deklarácie s reálnou, nenulovou aktivitou** —
  nulové deklarácie sa už neakceptujú;
- **RUC** aktívny a bez nedoplatkov zhruba 4 mesiace v čase podania;
- zdokumentovaný príjem aspoň na úrovni paraguajskej minimálnej mzdy
  (v praxi **≈ 500–600 USD mesačne**);
- podporné daňové dokumenty: deklarácie Form 120, *certificado de cumplimiento
  tributario*, *constancia de RUC*, *cédula tributaria*, *constancia de movimiento
  tributario*.

Nástroj automatizuje príslušnú mesačnú rutinu na Marangatu (faktúra → imputácia →
Form 120 → talón Form 241 → platobný lístok) podľa komunitného manuálu
*„GUÍA PRÁCTICA PARA GENERAR LOS DOCUMENTOS NECESARIOS PARA LA RESIDENCIA PERMANENTE EN
PARAGUAY"*.

## Čo robí

| Subpríkaz    | Kedy            | Kroky manuálu | Čo sa stane |
|--------------|-----------------|---------------|-------------|
| `facturar`   | ~25. deň mesiaca | 1–2          | Vystaví jednu virtuálnu faktúru za **aktuálny** mesiac na nakonfigurovaného klienta. Suma = `MIN_INCOME_USD × kurz × SAFETY_MARGIN`, zaokrúhlená nahor na násobok 11 000 Gs. Uloží stavový záznam, ktorý neskôr použije `declarar`. |
| `declarar`   | ~5. deň mesiaca | 3–5, 9        | Za **predchádzajúci** mesiac: imputuje predajné doklady (*ventas a imputar → imputar todo*), podá **Form 120** (IVA General, obligación 211) s casillou 10 = brutto/11×10, podá **talón Form 241** a vygeneruje platobný lístok (*boleta de pago*, príloha reportu). |
| `documentos` | pred podaním žiadosti | 7–8     | Best-effort stiahnutie *certificado de cumplimiento tributario*, *constancia de RUC* a *cédula tributaria* do `~/.local/share/marangatu/documentos/`. |

Samotná **platba IVA automatizovaná nie je** — boletu zaplatíte v ľubovoľnej
paraguajskej bankovej appke (*Pagar servicios → DNIT*, zadať cédulu/RUC + dátum
narodenia). Report vám to každý mesiac pripomenie.

### Matematika

Pri 10 % sadzbe IVA berie Marangatu sumu faktúry vrátane IVA: základ dane =
brutto × 10/11 (to sa vypĺňa do casilly 10 na Form 120) a IVA = brutto / 11. Skript
zaokrúhľuje brutto sumu **nahor na násobok 11 000 Gs**, aby základ aj IVA vyšli
v celých guaraní a automaticky dopočítané hodnoty portálu sa dali porovnať presne
s očakávaním skriptu.

Príklad s defaultmi (`MIN_INCOME_USD=600`, rezerva 1,10, kurz 7 300 Gs/USD):
brutto = 4 818 000 Gs → základ 4 380 000 Gs (casilla 10), IVA 438 000 Gs ≈ 60 USD/mes.

### Bezpečnostné poistky

- **Zlé heslo → okamžitý stop, žiadne opakovanie** (Marangatu po opakovaných zlyhaniach
  blokuje účet).
- **Nikdy nepodáva rektifikatívu**: ak sa Form 120 otvorí ako *RECTIFICATIVA*, obdobie
  už bolo podané a skript skončí.
- `declarar` **odmietne bežať**, ak neexistuje záznam o vystavenej faktúre za obdobie —
  nikdy potichu nepodá nulovú deklaráciu a nepokazí vašu 3-mesačnú reťaz.
  (Obísť sa dá cez `--amount-gs`, len ak ste si istí, že faktúra existuje.)
- Pred každým finálnym klikom *Presentar/Confirmar* skript čaká, kým portál dopočíta
  **presne** očakávané sumy; pri akejkoľvek nezhode končí bez podania.
- Každý krok má screenshot v `~/.local/state/marangatu/logs/<run>/`; po každom behu sa posiela
  e-mailový report (so screenshotmi a PDF boletou).
- Prechodné chyby sa opakujú 3× s 10-minútovými pauzami; každý pokus má tvrdý strop
  40 minút. Idempotentné markery (`~/.local/state/marangatu/`) + `--only-if-not-done` robia
  záložné crony bezpečnými.

## Požiadavky

- Linuxový server schopný behať headless prehliadač — Chromium (default) alebo Firefox/Gecko (vyvíjané na Ubuntu)
- Python 3.9+ s [Playwright](https://playwright.dev/python/)
- **aktívny RUC** a prihlásenie do Marangatu (číslo céduly + heslo)
- **timbrado** vyžiadané raz vopred (krok 1 manuálu — jednorazová ručná akcia v
  *Facturación y Timbrado → Solicitudes → Comprobantes Virtuales → Factura Virtual*)
- voliteľne: funkčný `sendmail` pre e-mailové reporty

## Inštalácia

```bash
mkdir -p ~/marangatu && cd ~/marangatu
python3 -m venv venv
venv/bin/pip install playwright
venv/bin/playwright install --with-deps chromium
# voliteľne — na ovládanie portálu cez Firefox (Gecko) doinštaluj aj jeho a
# vyber ho cez BROWSER=firefox v residencia.conf alebo prepínačom --browser firefox:
#   venv/bin/playwright install --with-deps firefox
git clone https://github.com/wilderko/marangatu-residencia.git src
ln -s src/marangatu_residencia.py .
```

## Konfigurácia

Dva súbory, oba `chmod 600`:

`~/.config/marangatu/credentials`

```
USUARIO=1234567        # číslo vašej céduly
PASSWORD=...
```

`~/.config/marangatu/residencia.conf` — vychádzajte z
[`residencia.conf.example`](residencia.conf.example):

| Kľúč | Default | Význam |
|------|---------|--------|
| `MAIL_TO` | *(prázdne)* | Príjemca reportov. Prázdne = e-mail sa neposiela (report ostáva v logu). |
| `MAIL_FROM` | `Marangatu bot <marangatu@localhost>` | Odosielateľ. Použite adresu, ktorej doména má v SPF zázname IP vášho servera, inak reporty skončia v spame. |
| `SENDMAIL` | `/usr/sbin/sendmail` | Cesta k sendmailu. |
| `MIN_INCOME_USD` | `600` | Mesačný príjem, ktorý má faktúra dokladovať. Rez. 407/2026 očakáva zhruba minimálnu mzdu (~500–600 USD). |
| `SAFETY_MARGIN` | `1.10` | Faktúra sa vystaví o 10 % vyššia, aby vás oslabenie guaraní nikdy nezrazilo pod minimum. |
| `FX_RATE_PYG` | *(prázdne)* | Pevný kurz Gs/USD. Prázdne = stiahne sa aktuálny z open.er-api.com. |
| `FX_RATE_FALLBACK` | `7500` | Kurz použitý, keď FX API nejde. |
| `CLIENT_SITUACION` | `NO_DOMICILIADO` | `NO_DOMICILIADO` = zahraničná osoba/firma bez paraguajského RUC (napr. vaša LLC); `CONTRIBUYENTE` = lokálny klient s RUC. |
| `CLIENT_RUC` | | Pre `CONTRIBUYENTE`: číslice RUC pred pomlčkou (meno si portál dohľadá sám). |
| `CLIENT_ID` | | Pre `NO_DOMICILIADO`: číslo pasu alebo zahraničné tax ID. |
| `CLIENT_ID_TYPE` | `Pasaporte` | Text option-u v selecte *Tipo de Identificación* (napr. `Identificación Tributaria`). |
| `CLIENT_NAME` / `CLIENT_ADDRESS` / `CLIENT_COUNTRY` / `CLIENT_EMAIL` / `CLIENT_PHONE` | | Údaje klienta tak, ako majú byť na faktúre. `CLIENT_COUNTRY` je text option-u selectu *País* (napr. `ESTADOS UNIDOS`). |
| `SERVICE_DESCRIPTION` | `Servicios de consultoría informática` | Popis služby na faktúre. |

## Používanie

```bash
V=~/marangatu/venv/bin/python

# VŽDY začnite dry-runom — spraví všetko okrem finálnych potvrdzovacích klikov,
# potom skontrolujte screenshoty v ~/.local/state/marangatu/logs/<run>/
$V marangatu_residencia.py facturar --dry-run
$V marangatu_residencia.py declarar --dry-run

# ostré behy
$V marangatu_residencia.py facturar                  # faktúra za aktuálny mesiac
$V marangatu_residencia.py facturar --amount-gs 4818000   # pevná suma namiesto USD×kurz
$V marangatu_residencia.py declarar                  # deklarácia za minulý mesiac
$V marangatu_residencia.py declarar --month 2026-07  # konkrétne obdobie
$V marangatu_residencia.py documentos                # stiahnuť podklady k žiadosti
```

Spoločné prepínače: `--dry-run`, `--no-email`, `--only-if-not-done` (skonči potichu, ak
obdobie už má done-marker — pre záložné crony), `--retries N`.

Exit kód 0 = úspech (report odoslaný), 1 = zlyhanie po opakovaniach (chybový report
s poslednými screenshotmi ide e-mailom).

### Cron

```cron
# faktúra za bežiaci mesiac (musí byť vystavená v mesiaci, ktorý dokladuje)
0 14 25 * * ~/marangatu/venv/bin/python ~/marangatu/marangatu_residencia.py facturar
0 14 27 * * ~/marangatu/venv/bin/python ~/marangatu/marangatu_residencia.py facturar --only-if-not-done
# deklarácia za predchádzajúci mesiac (prvý týždeň, pred splatnosťou podľa poslednej číslice RUC)
0 14 5 * *  ~/marangatu/venv/bin/python ~/marangatu/marangatu_residencia.py declarar
0 14 7 * *  ~/marangatu/venv/bin/python ~/marangatu/marangatu_residencia.py declarar --only-if-not-done
```

> ⚠️ **Ak ste doteraz automatizovali nulové deklarácie, najprv ten cron odstráňte.**
> Nulový Form 120 podaný za mesiac s faktúrou si vynúti rektifikatívu a nulový mesiac
> reštartuje 3-mesačnú reťaz.

### Časová os k trvalej rezidencii

| Mesiac | 25. deň | 5. deň nasledujúceho mesiaca |
|--------|---------|------------------------------|
| M1 | faktúra č. 1 | — |
| M2 | faktúra č. 2 | deklarácia M1 (nenulová č. 1) + platba IVA |
| M3 | faktúra č. 3 | deklarácia M2 (nenulová č. 2) + platba IVA |
| M4 | — | deklarácia M3 (nenulová č. 3) + platba IVA → `documentos`, podanie žiadosti na DNM |

Priebežný náklad: samotné IVA, brutto/11 mesačne (≈ 60 USD pri defaultoch) — je to
reálna daň, nie poplatok.

## Čo automatizované NIE JE

- **platba** bolety (banková appka: *Pagar servicios → DNIT*),
- jednorazové vyžiadanie **timbrada** (krok 1 manuálu),
- odpočty nákladov vo Form 120 (poraďte sa s účtovníkom),
- migračné dokumenty (certifikát Interpolu, register trestov, termín na DNM).

## Súbory

```
~/.config/marangatu/credentials                              prihlásenie (chmod 600)
~/.config/marangatu/residencia.conf                          konfigurácia (chmod 600)
~/.local/state/marangatu/                                    markery období a záznamy faktúr (JSON)
~/.local/state/marangatu/logs/<timestamp>_<cmd>_<obdobie>/   run.log + screenshoty krokov
~/.local/share/marangatu/documentos/<dátum>/                 výstupy subpríkazu documentos
```

Skript rešpektuje `XDG_CONFIG_HOME`, `XDG_STATE_HOME` a `XDG_DATA_HOME`;
cesty vyššie sú predvolené.

## Riešenie problémov a známe zvláštnosti

- Portál otvára takmer každú akciu v **novom okne prehliadača**, niekedy 1–2 minúty po
  kliku (server-side AJAX pred `window.open`). Skript trpezlivo polluje a kliky opakuje
  do 3× — pomalé behy sú normálne.
- Screenshoty občas visia na *„waiting for fonts"* — zabudovaný je CDP fallback.
- Toky Form 120 / Form 241 sú overené v praxi; obrazovky *faktúra, imputácia a boleta*
  boli implementované podľa screenshotov manuálu s kaskádami záložných selektorov.
  Ak DNIT zmení markup, pozrite screenshoty krokov v logoch a upravte kaskády
  (`first_visible`, `control_by_label`).
- Logy a reporty sú v slovenčine. PR s anglickou/španielskou lokalizáciou sú vítané.

## Zdroje

- [DNM: Migraciones actualiza el régimen de acreditación de solvencia económica](https://migraciones.gov.py/migraciones-actualiza-el-regimen-de-acreditacion-de-solvencia-economica-para-extranjeros/)
- [liberation.travel: Paraguay permanent residency — new conditions 2026](https://liberation.travel/paraguay-permanent-residency-new-conditions-2026/)
- [ABC Color: cambios para acceder a la residencia permanente](https://www.abc.com.py/nacionales/2026/06/25/atencion-extranjeros-estos-son-los-cambios-para-acceder-a-la-residencia-permanente-en-paraguay/)
