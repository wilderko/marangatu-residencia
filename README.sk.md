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
- zdokumentovaný príjem niečo nad paraguajskou minimálnou mzdou
  (**3 044 000 Gs mesačne** v roku 2026, ≈ 510 USD);
- podporné daňové dokumenty: deklarácie Form 120, *certificado de cumplimiento
  tributario*, *constancia de RUC*, *cédula tributaria*, *constancia de movimiento
  tributario*.

Nástroj automatizuje príslušnú mesačnú rutinu na Marangatu (faktúra → imputácia vrátane
kroku *Obligaciones* → Form 120 vrátane Rubro 2 → talón Form 241 → platobný lístok) podľa
klientskeho návodu
[*Paraguay_navod_pobyt_SK.pdf*](https://liberation.travel/wp-content/uploads/2026/06/Paraguay_navod_pobyt_SK.pdf)
(aktualizovaný september 2026), ktorý vychádza z komunitného manuálu *„GUÍA PRÁCTICA PARA
GENERAR LOS DOCUMENTOS NECESARIOS PARA LA RESIDENCIA PERMANENTE EN PARAGUAY"*.

## Čo robí

| Subpríkaz    | Kedy            | Kroky manuálu | Čo sa stane |
|--------------|-----------------|---------------|-------------|
| `facturar`   | ~25. deň mesiaca | 1–2          | Vystaví jednu virtuálnu faktúru za **aktuálny** mesiac na nakonfigurovaného klienta. Suma = `max(MIN_INCOME_GS × 11/10, MIN_INCOME_USD × kurz) × SAFETY_MARGIN`, zaokrúhlená nahor na násobok 11 000 Gs, takže základ dane je vždy niečo nad minimálnou mzdou. Uloží stavový záznam, ktorý neskôr použije `declarar`. |
| `declarar`   | ~5. deň mesiaca (pred termínom) | 3–5, 9 | Za **predchádzajúci** mesiac: imputuje predajné doklady (*ventas a imputar → imputar todo → siguiente → imputar comprobantes*), nastaví prepínače **Obligaciones asociadas** (na zeleno len `IMPUTAR_OBLIGACIONES`, typicky IVA GENERAL; IRP–RSP a IRE červené) a klikne *Procesar Imputación*; podá **Form 120** (IVA General, obligación 211) s Rubro 1 casillou 10 = brutto/11×10 **a Rubro 2** (casilla 160 = kumulatív za 6 období, 27 = 31 = 160, zvyšok 0); podá **talón Form 241**; vygeneruje platobný lístok (*boleta de pago*, príloha reportu). Zaloguje termín podania **aj platby** podľa vášho RUC. |
| `documentos` | pred podaním žiadosti | 6–8     | Best-effort stiahnutie posledných Form 120, *certificado de cumplimiento tributario*, *constancia de RUC* a *cédula tributaria* do `~/.local/share/marangatu/documentos/`. |
| `vencimiento`| kedykoľvek      | 4             | Offline (bez prihlásenia): vypíše termín podania + platby za obdobie podľa poslednej číslice RUC. |

Samotná **platba IVA automatizovaná nie je** — boletu zaplatíte v ľubovoľnej
paraguajskej bankovej appke (*Pagar servicios → DNIT*, zadať cédulu/RUC + dátum
narodenia) **do rovnakého termínu ako priznanie**. Report vám to každý mesiac pripomenie
aj s dátumom.

### Matematika

Pri 10 % sadzbe IVA berie Marangatu sumu faktúry vrátane IVA: základ dane =
brutto × 10/11 (to sa vypĺňa do casilly 10 na Form 120) a IVA = brutto / 11. Skript
zaokrúhľuje brutto sumu **nahor na násobok 11 000 Gs**, aby základ aj IVA vyšli
v celých guaraní a automaticky dopočítané hodnoty portálu sa dali porovnať presne
s očakávaním skriptu.

Návod žiada faktúru „niečo nad minimálnou mzdou (₲3 044 000 mesačne)". Skript porovnáva
minimálnu mzdu so **základom dane** (casilla 10 — príjem, ktorý vidí DNM), takže brutto
musí byť aspoň `MIN_INCOME_GS × 11/10`; `MIN_INCOME_USD × kurz` ostáva ako druhé
minimum a platí vyššie z oboch.

Príklad s defaultmi (`MIN_INCOME_GS=3044000`, `MIN_INCOME_USD=600`, rezerva 1,10,
kurz 5 990 Gs/USD): max(3 348 400; 3 594 000) × 1,10 → brutto 3 960 000 Gs → základ
3 600 000 Gs (casilla 10), IVA 360 000 Gs ≈ 60 USD/mes. — teda „rádovo ₲360 000 mesačne
na dani", ako uvádza návod.

### Form 120 Rubro 2

Rubro 2 (*„Enajenación de bienes y/o prestación de servicios de los últimos seis (6)
meses, incluido el periodo que se declara"*) vypĺňa poplatník — Marangatu ho nespočíta.
Skript zadá casillu **160** = súčet casilly 10 za posledných šesť mesačných období
**vrátane** priznávaného, **161, 26, 162, 163, 29** nechá na 0 a overí (alebo doplní, ak
ich formulár nedopočíta) **27** = 160+161+26, **30** = 162+163+29 = 0 a **31** = 27+30.
V prvom priznaní 160 = 10; od siedmeho mesiaca ide o kĺzavé okno šiestich období. Pri
faktúre ₲6 000 000 mesačne: 160 = 5 454 545 v prvom mesiaci, 16 363 635 v treťom.

História sa berie z vlastných záznamov skriptu (podané Form 120, potom záznamy faktúr).
Obdobie v okne **bez** záznamu sa v ostrom behu nikdy neodhadne ako nula — nastavte
`RUC_START` (staršie obdobia = 0) a/alebo `PRIOR_SALES_10` pre obdobia podané ručne.
V `--dry-run` je to len varovanie.

### Termín (calendario perpetuo)

Priznanie **aj platba** sú splatné v ten istý deň nasledujúceho mesiaca podľa **poslednej
číslice RUC pred pomlčkou** (kontrolná číslica za pomlčkou sa nepočíta): 0→7., 1→9.,
2→11., 3→13., 4→15., 5→17., 6→19., 7→21., 8→23., 9→25.; víkend alebo sviatok ho posúva na
najbližší pracovný deň. Príklad: RUC 1234567-8 končí na 7, priznanie za september sa
teda podáva do 21. októbra. Manželia majú každý vlastné RUC, a teda aj vlastný termín.
Skript pozná paraguajské sviatky s pevným dátumom a Zelený štvrtok/Veľký piatok;
presúvané sviatky (1. 3., 12. 6., 29. 9.) patria do `HOLIDAYS` — chýbajúci sviatok dá
vždy len *skorší* termín, nikdy neskorší. `declarar` termín zaloguje, v posledný deň
varuje a oneskorené podanie označí.

### Bezpečnostné poistky

- **Zlé heslo → okamžitý stop, žiadne opakovanie** (Marangatu po opakovaných zlyhaniach
  blokuje účet).
- **Nikdy nepodáva rektifikatívu**: ak sa Form 120 otvorí ako *RECTIFICATIVA*, obdobie
  už bolo podané a skript skončí.
- `declarar` **odmietne bežať**, ak neexistuje záznam o vystavenej faktúre za obdobie —
  nikdy potichu nepodá nulovú deklaráciu a nepokazí vašu 3-mesačnú reťaz.
  (Obísť sa dá cez `--amount-gs`, len ak ste si istí, že faktúra existuje.)
- **Obligaciones**: na zeleno sa prepnú len povinnosti z `IMPUTAR_OBLIGACIONES`, všetky
  ostatné na červeno, a stav každého prepínača sa pred *Procesar Imputación* znova
  prečíta (imputácia k dani, ktorú RUC nemá, skončí ako *inconsistencia* a v *Ventas a
  imputar* možnosť „no imputar" nie je). Ak želaná povinnosť v ponuke nie je alebo sa
  prepínač nedá prečítať, nič sa neimputuje.
- **Rubro 2** sa počíta pred prihlásením; chýbajúce obdobie v 6-mesačnom okne zastaví
  ostrý beh skôr, než sa čokoľvek dotkne. Casilly 10, 160, 27 a 31 sa pred *Presentar*
  spätne prečítajú.
- `--interactive` otvorí viditeľný prehliadač, pred každým nevratným klikom (faktúra,
  *Procesar Imputación*, Form 120, Form 241) sa pýta y/N a na obrazovke, ktorú skript
  nevie spoľahlivo obslúžiť, počká na ručný zásah. Bez neho taká obrazovka beh ukončí
  (bez opakovania) a nič nepotvrdí.
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
| `MIN_INCOME_GS` | `3044000` | Paraguajská minimálna mzda (Gs/mes.). Základ dane faktúry (casilla 10) sa drží nad ňou. |
| `MIN_INCOME_USD` | `600` | Voliteľné druhé minimum v USD (× kurz, porovnáva sa s brutto); platí vyššie minimum. `0` = nepoužiť. |
| `SAFETY_MARGIN` | `1.10` | Faktúra sa vystaví o 10 % nad minimom („niečo nad minimálnou mzdou"; pokryje aj pohyb kurzu). |
| `FX_RATE_PYG` | *(prázdne)* | Pevný kurz Gs/USD. Prázdne = stiahne sa aktuálny z open.er-api.com. |
| `FX_RATE_FALLBACK` | `6000` | Kurz použitý, keď FX API nejde. |
| `CLIENT_SITUACION` | `NO_DOMICILIADO` | `NO_DOMICILIADO` = zahraničná osoba/firma bez paraguajského RUC (napr. vaša LLC); `CONTRIBUYENTE` = lokálny klient s RUC. |
| `CLIENT_RUC` | | Pre `CONTRIBUYENTE`: číslice RUC pred pomlčkou (meno si portál dohľadá sám). |
| `CLIENT_ID` | | Pre `NO_DOMICILIADO`: číslo pasu alebo zahraničné tax ID. |
| `CLIENT_ID_TYPE` | `Pasaporte` | Text option-u v selecte *Tipo de Identificación* (napr. `Identificación Tributaria`). |
| `CLIENT_NAME` / `CLIENT_ADDRESS` / `CLIENT_COUNTRY` / `CLIENT_EMAIL` / `CLIENT_PHONE` | | Údaje klienta tak, ako majú byť na faktúre. `CLIENT_COUNTRY` je text option-u selectu *País* (napr. `ESTADOS UNIDOS`). |
| `SERVICE_DESCRIPTION` | `Servicios de consultoría informática` | Popis služby na faktúre. |
| `IMPUTAR_OBLIGACIONES` | `IVA GENERAL` | Čiarkou oddelené povinnosti, ktoré sa v kroku *Obligaciones asociadas* prepnú na **zeleno**; ostatné na červeno. `IRP - RSP` pridajte, len ak je na neho RUC naozaj registrované (povinné nad 80 000 000 Gs príjmu zo služieb ročne, čl. 62 zákona 6380/2019). |
| `RUC` | *(prázdne)* | Vaše RUC (napr. `1234567-8`) pre výpočet termínu. Prázdne = vezme sa `USUARIO` (pri fyzickej osobe je RUC číslo cédula). |
| `HOLIDAYS` | *(prázdne)* | Ďalšie dni voľna `YYYY-MM-DD,…` (presunuté sviatky, bankové voľno), ktoré posúvajú termín. |
| `RUC_START` | *(prázdne)* | `YYYY-MM` prvého obdobia s IVA; staršie obdobia sa v Rubro 2 rátajú ako 0. |
| `PRIOR_SALES_10` | *(prázdne)* | Casilla 10 období, o ktorých skript nemá záznam, `YYYY-MM:báza,…` (napr. `2026-05:0,2026-06:3600000`). |

## Používanie

```bash
V=~/marangatu/venv/bin/python

# VŽDY začnite dry-runom — spraví všetko okrem finálnych potvrdzovacích klikov,
# potom skontrolujte screenshoty v ~/.local/state/marangatu/logs/<run>/
$V marangatu_residencia.py facturar --dry-run
$V marangatu_residencia.py declarar --dry-run

# ostré behy
$V marangatu_residencia.py facturar                  # faktúra za aktuálny mesiac
$V marangatu_residencia.py facturar --amount-gs 3960000   # pevná suma namiesto vypočítanej
$V marangatu_residencia.py declarar                  # deklarácia za minulý mesiac
$V marangatu_residencia.py declarar --month 2026-07  # konkrétne obdobie
$V marangatu_residencia.py documentos                # stiahnuť podklady k žiadosti
$V marangatu_residencia.py vencimiento --month 2026-09   # termín (offline, bez prihlásenia)

# prvý ostrý beh nových obrazoviek imputácie / Rubro 2: viditeľný prehliadač,
# y/N pred každým nevratným klikom, ručný zásah, kde treba
$V marangatu_residencia.py declarar --interactive
```

Spoločné prepínače: `--dry-run`, `--no-email`, `--only-if-not-done` (skonči potichu, ak
obdobie už má done-marker — pre záložné crony), `--retries N`, `--interactive`
(potrebuje terminál a displej; nie pre cron).

`--dry-run` pri `declarar` prejde až po prepínače *Obligaciones* (klikne na krok
sprievodcu *Imputar comprobantes*, ktorý len prepne obrazovku) a vyplní Rubro 1 aj
Rubro 2, ale **neklikne** *Procesar Imputación* ani *Presentar*.

Exit kód 0 = úspech (report odoslaný), 1 = zlyhanie po opakovaniach (chybový report
s poslednými screenshotmi ide e-mailom).

### Cron

```cron
# faktúra za bežiaci mesiac (musí byť vystavená v mesiaci, ktorý dokladuje)
0 14 25 * * ~/marangatu/venv/bin/python ~/marangatu/marangatu_residencia.py facturar
0 14 27 * * ~/marangatu/venv/bin/python ~/marangatu/marangatu_residencia.py facturar --only-if-not-done
# deklarácia za predchádzajúci mesiac — 5. a 6. deň sú pred každým možným termínom
# (najskorší je 7. deň pri RUC končiacom na 0); svoj over cez `vencimiento`
0 14 5 * *  ~/marangatu/venv/bin/python ~/marangatu/marangatu_residencia.py declarar
0 14 6 * *  ~/marangatu/venv/bin/python ~/marangatu/marangatu_residencia.py declarar --only-if-not-done
```

Boletu zaplaťte v bankovej appke **do rovnakého termínu** — oneskorené priznanie alebo
platba znamená pokutu a prirážky za omeškanie.

> ⚠️ **Ak ste doteraz automatizovali nulové deklarácie, najprv ten cron odstráňte.**
> Nulový Form 120 podaný za mesiac s faktúrou si vynúti rektifikatívu a nulový mesiac
> reštartuje 3-mesačnú reťaz.

### Časová os k trvalej rezidencii

| Mesiac | 25. deň | 5. deň nasledujúceho mesiaca (termín: podľa číslice RUC, 7.–25.) |
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
- odpočty nákladov vo Form 120 (Rubro 3, *Compras locales e importaciones*; poraďte sa s účtovníkom),
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
- Toky Form 120 Rubro 1 / Form 241 sú overené v praxi; obrazovky *faktúra, imputácia
  a boleta* boli implementované podľa screenshotov manuálu s kaskádami záložných
  selektorov. Ak DNIT zmení markup, pozrite screenshoty krokov v logoch a upravte
  kaskády (`first_visible`, `control_by_label`).
- **Zatiaľ neoverené na živom portáli** (doplnené v októbri 2026 podľa aktualizovaného
  návodu): obrazovky *Imputar comprobantes → Obligaciones asociadas → Procesar
  Imputación* (stav prepínačov sa číta cez checkbox / `aria-checked` / CSS triedu),
  casilly Rubro 2 (hľadajú sa podľa názvov typu `name='c160'` ako casilla 10, potom podľa
  čísla casilly za nadpisom „RUBRO 2") a odkazy na stiahnutie Form 120 na úvodnej
  stránke. Prvý beh spravte s `--dry-run`, potom s `--interactive` a skontrolujte
  screenshoty `24_obligaciones_*`, `25_obligaciones_nastavene` a `32_form120_vyplneny`.
- Nezrovnalosti po imputácii (napr. priradenie k dani, ktorú RUC nemá) nájdete
  v *Herramientas → Consulta de Estado de Procesos de Imputación*.
- Logy a reporty sú v slovenčine. PR s anglickou/španielskou lokalizáciou sú vítané.

## Zdroje

- [Klientsky návod (september 2026)](https://liberation.travel/wp-content/uploads/2026/06/Paraguay_navod_pobyt_SK.pdf)
- DNIT: *Cómo obtener comprobantes electrónicos y virtuales* (RG 90/2021), *Instructivo del Formulario N° 120 v4*, calendario perpetuo (RG 38/2020)
- [DNM: Migraciones actualiza el régimen de acreditación de solvencia económica](https://migraciones.gov.py/migraciones-actualiza-el-regimen-de-acreditacion-de-solvencia-economica-para-extranjeros/)
- [liberation.travel: Paraguay permanent residency — new conditions 2026](https://liberation.travel/paraguay-permanent-residency-new-conditions-2026/)
- [ABC Color: cambios para acceder a la residencia permanente](https://www.abc.com.py/nacionales/2026/06/25/atencion-extranjeros-estos-son-los-cambios-para-acceder-a-la-residencia-permanente-en-paraguay/)
