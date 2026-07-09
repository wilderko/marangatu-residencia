#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Marangatu — mesačný cyklus NENULOVÝCH deklarácií pre trvalú rezidenciu v Paraguaji.

Automatizuje kroky z "GUÍA PRACTICA PARA GENERAR LOS DOCUMENTOS NECESARIOS PARA
LA RESIDENCIA PERMANENTE EN PARAGUAY" tak, aby výstup spĺňal Rezolúciu DNM
č. 407/2026 (účinná pre podania od 6. 7. 2026): nenulová ekonomická aktivita,
minimálne 3 po sebe idúce mesačné IVA deklarácie, nulové deklarácie sa už
neakceptujú.

Subpríkazy (poradie v mesačnom cykle):
  facturar    vystaví virtuálnu faktúru za AKTUÁLNY mesiac (krok 1-2 manuálu);
              suma = MIN_INCOME_USD × kurz × SAFETY_MARGIN, zaokrúhlená nahor
              na násobok 11 000 Gs (aby báza aj IVA vyšli v celých guaraní)
  declarar    za PREDCHÁDZAJÚCI mesiac: imputácia predajov (krok 3) → Form 120
              s casillou 10 = suma/11×10 (krok 4) → talón Form 241 (krok 5) →
              boleta de pago (krok 9, best-effort; platba ostáva ručná v banke)
  documentos  stiahne certificado de cumplimiento, constancia de RUC a cédulu
              tributaria (kroky 7-8, best-effort) do
              $XDG_DATA_HOME/marangatu/documentos/ (~/.local/share/…)

Bezpečnostné zásady (zdedené z marangatu_declaracion.py):
  - pri zlom hesle sa login NEopakuje (ochrana pred zablokovaním účtu),
  - Form 120 sa NIKDY nepodáva ako rektifikatíva,
  - declarar odmietne bežať, ak neexistuje záznam o vystavenej faktúre za
    obdobie — radšej deklaráciu nepodať a kričať e-mailom, než podať nulovú
    a pokaziť 3-mesačnú reťaz pre rezidenciu,
  - pred každým finálnym "Presentar/Confirmar" sa overí, že portál dopočítal
    očakávané sumy; pri nezhode sa NIČ nepodáva,
  - každý krok má screenshot v $XDG_STATE_HOME/marangatu/logs/<run>/
    (~/.local/state/…).

Použitie:
  marangatu_residencia.py facturar                 # faktúra za aktuálny mesiac
  marangatu_residencia.py facturar --amount-gs 4818000   # pevná suma v Gs
  marangatu_residencia.py declarar                 # deklarácia za minulý mesiac
  marangatu_residencia.py declarar --month 2026-07
  marangatu_residencia.py documentos               # stiahnuť podklady k žiadosti
  spoločné: --dry-run --no-email --only-if-not-done --retries N
            --browser chromium|firefox   (engine prehliadača; gecko = firefox)

Konfigurácia (rešpektuje XDG_CONFIG_HOME, default ~/.config):
  ~/.config/marangatu/credentials       USUARIO= a PASSWORD= (chmod 600)
  ~/.config/marangatu/residencia.conf   klient, suma, kurz, e-mail reporty —
                                        viď residencia.conf.example

Stav a logy (XDG_STATE_HOME, default ~/.local/state):
  ~/.local/state/marangatu/             markery období + záznamy faktúr (JSON)
  ~/.local/state/marangatu/logs/        run.log + screenshoty jednotlivých behov
"""

import argparse
import base64
import datetime
import getpass
import json
import math
import os
import re
import signal
import socket
import subprocess
import sys
import time
import traceback
import urllib.request
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

def _xdg_dir(env_var: str, default: Path) -> Path:
    val = os.environ.get(env_var, "")
    return (Path(val) if val else default) / "marangatu"

CONFIG_DIR = _xdg_dir("XDG_CONFIG_HOME", Path.home() / ".config")
STATE_DIR = _xdg_dir("XDG_STATE_HOME", Path.home() / ".local" / "state")
DATA_DIR = _xdg_dir("XDG_DATA_HOME", Path.home() / ".local" / "share")
LOGS_DIR = STATE_DIR / "logs"
DOCS_DIR = DATA_DIR / "documentos"
CRED_FILE = CONFIG_DIR / "credentials"
CONF_FILE = CONFIG_DIR / "residencia.conf"

PORTAL = "https://marangatu.set.gov.py/eset/"

FX_URL = "https://open.er-api.com/v6/latest/USD"

ATTEMPT_TIMEOUT_S = 40 * 60   # tvrdý strop na jeden pokus
RETRIES = 3                   # pokusy pri prechodných chybách
RETRY_PAUSE_S = 10 * 60

CONF_DEFAULTS = {
    "MAIL_TO": "",              # kam poslať report; prázdne = e-mail sa neposiela
    "MAIL_FROM": "Marangatu bot <marangatu@localhost>",
    "SENDMAIL": "/usr/sbin/sendmail",
    "MIN_INCOME_USD": "600",
    "SAFETY_MARGIN": "1.10",
    "FX_RATE_PYG": "",          # pevný kurz Gs/USD; prázdne = stiahnuť z API
    "FX_RATE_FALLBACK": "7500",
    "CLIENT_SITUACION": "NO_DOMICILIADO",   # alebo CONTRIBUYENTE
    "CLIENT_RUC": "",           # pre CONTRIBUYENTE: číslice pred pomlčkou
    "CLIENT_ID": "",            # pre NO_DOMICILIADO: pas alebo tax ID
    "CLIENT_ID_TYPE": "Pasaporte",
    "CLIENT_NAME": "",
    "CLIENT_ADDRESS": "",
    "CLIENT_COUNTRY": "",
    "CLIENT_EMAIL": "",
    "CLIENT_PHONE": "",
    "SERVICE_DESCRIPTION": "Servicios de consultoría informática",
    "BROWSER": "chromium",      # engine prehliadača: chromium (Blink) | firefox (Gecko)
}


class FatalError(Exception):
    """Chyba, pri ktorej nemá zmysel opakovať (zlé heslo, chýbajúca faktúra…)."""


# ---------------------------------------------------------------- infra

class Reporter:
    def __init__(self, run_dir: Path):
        self.run_dir = run_dir
        self.lines = []
        self.attachments = []
        self.logf = open(run_dir / "run.log", "a", encoding="utf-8")

    def log(self, msg, report=False):
        stamp = datetime.datetime.now().strftime("%H:%M:%S")
        line = f"[{stamp}] {msg}"
        print(line, flush=True)
        self.logf.write(line + "\n")
        self.logf.flush()
        if report:
            self.lines.append(msg)

    def attach(self, path):
        if path and Path(path).exists():
            self.attachments.append(Path(path))


def load_kv_file(path: Path):
    data = {}
    if path.exists():
        for raw in path.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if raw and not raw.startswith("#") and "=" in raw:
                k, v = raw.split("=", 1)
                data[k.strip().upper()] = v.strip()
    return data


def load_credentials():
    creds = load_kv_file(CRED_FILE)
    if "USUARIO" not in creds or "PASSWORD" not in creds:
        raise FatalError(f"{CRED_FILE} musí obsahovať USUARIO= a PASSWORD=")
    return creds


def load_config():
    cfg = dict(CONF_DEFAULTS)
    cfg.update(load_kv_file(CONF_FILE))
    return cfg


def previous_month(today=None):
    today = today or datetime.date.today()
    first = today.replace(day=1)
    prev = first - datetime.timedelta(days=1)
    return prev.year, prev.month


def format_gs(n: int) -> str:
    """5454545 → '5.454.545' (formát, v akom portál zobrazuje sumy)."""
    return f"{int(n):,}".replace(",", ".")


def factura_state_file(period: str) -> Path:
    return STATE_DIR / f"residencia_factura_{period}.json"


# ---------------------------------------------------------------- výber prehliadača

# Portál je čistý web bez CDP-špecifík, takže funguje pod oboma enginmi. Chromium
# (Blink) ostáva default; Firefox (Gecko) je dobrovoľná alternatíva pre tých, čo
# nechcú/nemôžu behať Chrome. Jediné Chromium-only miesto je CDP fallback pre
# screenshoty v shot() — na Firefoxe ticho preskočí a použije page.screenshot().
BROWSER_ALIASES = {
    "chromium": "chromium", "chrome": "chromium", "blink": "chromium",
    "firefox": "firefox", "gecko": "firefox", "ff": "firefox",
}


def resolve_browser(name):
    """Normalizuje názov engine z konfigurácie/CLI na 'chromium' alebo 'firefox'."""
    key = (name or "chromium").strip().lower()
    if key not in BROWSER_ALIASES:
        raise FatalError(
            f"neznámy prehliadač '{name}' v BROWSER= / --browser — "
            "povolené: chromium (Blink) alebo firefox (Gecko)")
    return BROWSER_ALIASES[key]


def launch_context(p, cfg, rep):
    """Spustí headless prehliadač podľa cfg['BROWSER'] a vráti (browser, context).

    Predtým sa spúšťanie Chromia opakovalo v každom subpríkaze; teraz je na
    jednom mieste, aby voľba enginu (Chromium/Firefox) platila rovnako pre
    facturar, declarar aj documentos."""
    engine = resolve_browser(cfg.get("BROWSER"))
    if engine == "firefox":
        rep.log("prehliadač: Firefox (Gecko), headless")
        # Firefox nemá Chromium sandbox prepínače; --no-sandbox by neprijal
        browser = p.firefox.launch(headless=True)
    else:
        rep.log("prehliadač: Chromium (Blink), headless")
        browser = p.chromium.launch(
            headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
    ctx = browser.new_context(viewport={"width": 1400, "height": 1000},
                              locale="es-PY", accept_downloads=True)
    return browser, ctx


# ---------------------------------------------------------------- playwright helpers

def shot(ctx, page, rep: Reporter, name):
    """Screenshot s CDP fallbackom (portál občas visí na 'waiting for fonts')."""
    path = rep.run_dir / f"{name}.png"
    try:
        page.screenshot(path=str(path), timeout=15000)
    except Exception:
        try:
            cdp = ctx.new_cdp_session(page)
            data = cdp.send("Page.captureScreenshot")["data"]
            path.write_bytes(base64.b64decode(data))
        except Exception as e:
            rep.log(f"screenshot {name} zlyhal: {e}")
            return None
    return path


def find_page(ctx, url_substr, timeout_s=30, exclude=None):
    """Nájde okno podľa časti URL — akcie na portáli otvárajú nové okná."""
    deadline = time.time() + timeout_s
    exclude = exclude or []
    while time.time() < deadline:
        for p in ctx.pages:
            if url_substr in p.url and p not in exclude:
                try:
                    p.wait_for_load_state("domcontentloaded", timeout=5000)
                except Exception:
                    pass
                return p
        time.sleep(0.5)
    raise RuntimeError(f"Nenašlo sa okno s URL obsahujúcou '{url_substr}'. "
                       f"Otvorené: {[p.url for p in ctx.pages]}")


def body_text(page):
    try:
        return page.inner_text("body", timeout=10000)
    except Exception:
        return page.content()


def dismiss_pico_modal(page, rep, button_text="ACEPTAR"):
    """Zavrie pico modal, ak nejaký visí. Vráti text modalu alebo None."""
    try:
        modal = page.locator("div[class*='pico']").last
        if modal.is_visible(timeout=1500):
            text = modal.inner_text(timeout=3000)
            btn = modal.locator(f"button:has-text('{button_text}')").last
            if btn.is_visible(timeout=1500):
                btn.click()
                time.sleep(1)
            rep.log(f"zavretý modal: {' '.join(text.split())[:150]}")
            return text
    except Exception:
        pass
    return None


def select_option_containing(page, selector_locator, text, rep, label):
    """Vyberie option, ktorej text alebo value obsahuje `text`."""
    loc = selector_locator
    loc.wait_for(state="visible", timeout=20000)
    options = loc.evaluate(
        "el => Array.from(el.options).map(o => ({value: o.value, text: o.textContent.trim()}))")
    for o in options:
        if text in o["text"] or text == o["value"]:
            loc.select_option(value=o["value"])
            rep.log(f"{label}: vybraté '{o['text']}' (value={o['value']})")
            return
    raise RuntimeError(f"{label}: option obsahujúca '{text}' neexistuje. Možnosti: {options}")


def click_any(page, selectors, timeout=15000):
    last = None
    for sel in selectors:
        try:
            page.click(sel, timeout=timeout)
            return sel
        except Exception as e:
            last = e
    raise RuntimeError(f"Nekliknuteľné: {selectors} ({last})")


def first_visible(page, selectors, timeout_each=4000):
    """Prvý viditeľný prvok z kaskády selektorov (obrazovky, ktorých presné
    názvy polí nepoznáme vopred — struts názvy najprv, pozičné xpath potom)."""
    for sel in selectors:
        loc = page.locator(sel).first
        try:
            loc.wait_for(state="visible", timeout=timeout_each)
            return loc, sel
        except Exception:
            continue
    return None, None


def control_by_label(page, labels, control="input", timeout_each=4000):
    """Ovládací prvok nasledujúci za textovým labelom — portál nepoužíva
    <label for=>, polia sú hneď pod textom. Exact match má prednosť, aby
    'Identificación' nechytil 'Tipo de Identificación'."""
    if isinstance(labels, str):
        labels = [labels]
    tried = []
    for lab in labels:
        for xp in (f"xpath=(//*[normalize-space(text())='{lab}']/following::{control})[1]",
                   f"xpath=(//*[contains(normalize-space(text()), '{lab}')]/following::{control})[1]"):
            loc = page.locator(xp)
            try:
                loc.wait_for(state="visible", timeout=timeout_each)
                return loc
            except Exception:
                tried.append(xp)
    raise RuntimeError(f"Nenašiel som {control} pri labeli {labels}")


def fill_by_label(page, labels, value, rep, name):
    loc = control_by_label(page, labels, "input")
    loc.click()
    loc.fill(str(value))
    rep.log(f"{name}: vyplnené")
    return loc


def wait_for_text(page, needles, timeout_s=20):
    """Čaká, kým sa v body objaví niektorý z reťazcov. Vráti nájdený alebo None."""
    if isinstance(needles, str):
        needles = [needles]
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        b = body_text(page)
        for n in needles:
            if n in b:
                return n
        time.sleep(1)
    return None


def open_window_via_menu(ctx, page, query, item_text, url_substr, rep, attempts=3):
    """Portál otvára okná pomaly (server-side AJAX pred window.open) a občas
    vôbec — preto trpezlivé čakanie a opakovanie celej sekvencie."""
    last = None
    for i in range(1, attempts + 1):
        search = page.locator("input[placeholder*='squeda']").first
        search.wait_for(state="visible", timeout=30000)
        search.click()
        search.fill("")
        search.type(query, delay=40)
        item = page.locator(f"text={item_text} >> visible=true").first
        item.wait_for(state="visible", timeout=20000)
        item.click()
        try:
            return find_page(ctx, url_substr, timeout_s=60)
        except RuntimeError as e:
            last = e
            rep.log(f"okno '{url_substr}' sa neotvorilo (pokus {i}/{attempts}), reload a znova")
            page.goto(PORTAL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(4)
    raise RuntimeError(f"Menu '{item_text}' neotvorilo okno '{url_substr}': {last}")


def open_menu_window_any(ctx, page, query, item_text, rep, attempts=3):
    """Ako open_window_via_menu, ale bez znalosti URL nového okna: berie
    hociktoré NOVÉ okno, ktoré sa po kliku objaví (fallback pre obrazovky,
    ktorých URL nepoznáme — emitir factura, boleta…)."""
    last = None
    for i in range(1, attempts + 1):
        before = set(ctx.pages)
        search = page.locator("input[placeholder*='squeda']").first
        search.wait_for(state="visible", timeout=30000)
        search.click()
        search.fill("")
        search.type(query, delay=40)
        try:
            item = page.locator(f"text={item_text} >> visible=true").first
            item.wait_for(state="visible", timeout=20000)
            item.click()
        except Exception as e:
            last = e
            page.goto(PORTAL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(4)
            continue
        deadline = time.time() + 60
        while time.time() < deadline:
            for p in ctx.pages:
                if p not in before and p.url and p.url != "about:blank":
                    try:
                        p.wait_for_load_state("domcontentloaded", timeout=10000)
                    except Exception:
                        pass
                    return p
            time.sleep(0.5)
        last = RuntimeError("žiadne nové okno")
        rep.log(f"'{item_text}' neotvorilo nové okno (pokus {i}/{attempts}), reload a znova")
        page.goto(PORTAL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(4)
    raise RuntimeError(f"Menu '{item_text}' neotvorilo žiadne nové okno: {last}")


def newest_page_or(ctx, before, default_page, timeout_s=15):
    """Po kliku na dlaždicu: ak sa otvorilo nové okno, vráti ho, inak default."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        for p in ctx.pages:
            if p not in before and p.url and p.url != "about:blank":
                try:
                    p.wait_for_load_state("domcontentloaded", timeout=10000)
                except Exception:
                    pass
                return p
        time.sleep(0.5)
    return default_page


def try_download(win, click_selectors, dest: Path, rep, timeout=45000):
    """Klikne a uloží download; vráti Path alebo None (portál niekedy PDF
    otvára v novom tabe namiesto downloadu — to rieši volajúci screenshotom)."""
    for sel in click_selectors:
        try:
            with win.expect_download(timeout=timeout) as dl_info:
                win.click(sel, timeout=15000)
            dl = dl_info.value
            dest.parent.mkdir(parents=True, exist_ok=True)
            dl.save_as(str(dest))
            rep.log(f"stiahnuté: {dest}")
            return dest
        except Exception:
            continue
    return None


# ---------------------------------------------------------------- login

def login(ctx, page, creds, rep):
    rep.log("otváram portál a prihlasujem…")
    page.goto(PORTAL, wait_until="domcontentloaded", timeout=90000)
    page.fill("input[placeholder='Usuario']", creds["USUARIO"], timeout=30000)
    page.fill("input[placeholder='Contraseña']", creds["PASSWORD"])
    shot(ctx, page, rep, "01_login")
    click_any(page, ["button:has-text('ACCEDER')", "input[value='ACCEDER']",
                     "text=ACCEDER"])
    time.sleep(5)
    try:
        page.wait_for_load_state("networkidle", timeout=30000)
    except Exception:
        pass
    text = body_text(page)
    shot(ctx, page, rep, "02_dashboard")
    low = text.lower()
    if "contraseña" in low and ("incorrect" in low or "inválid" in low or "no válid" in low):
        raise FatalError("Portál hlási nesprávne prihlasovacie údaje — NEopakujem, "
                         f"aby sa účet nezablokoval. Skontroluj {CRED_FILE}.")
    if page.locator("input[placeholder='Usuario']").count() > 0 \
            and page.locator("input[placeholder='Usuario']").first.is_visible():
        raise RuntimeError(f"Prihlásenie sa nepodarilo (stále login stránka). Text: {text[:300]}")
    rep.log("prihlásenie OK")
    return text


def get_vencimientos(dash_text):
    m = re.search(r"Próximos Vencimientos(.{0,600})", dash_text, re.S | re.I)
    if not m:
        return ""
    return " ".join(m.group(1).split())


# ---------------------------------------------------------------- suma faktúry

def get_fx_rate(cfg, rep):
    if cfg.get("FX_RATE_PYG"):
        return float(cfg["FX_RATE_PYG"]), "pevný kurz z residencia.conf"
    try:
        with urllib.request.urlopen(FX_URL, timeout=30) as r:
            data = json.load(r)
        rate = float(data["rates"]["PYG"])
        if not (3000 < rate < 30000):
            raise ValueError(f"nezmyselný kurz {rate}")
        return rate, FX_URL
    except Exception as e:
        rep.log(f"kurz sa nepodarilo stiahnuť ({e}) — používam FX_RATE_FALLBACK")
        return float(cfg.get("FX_RATE_FALLBACK", "7500")), "FX_RATE_FALLBACK"


def compute_gross_gs(cfg, rep, override=None):
    """Hrubá suma faktúry (vrátane IVA) v Gs, násobok 11 000 → báza (casilla 10)
    aj IVA débito vyjdú v celých guaraní bez zaokrúhľovacích rozdielov."""
    if override:
        gross = int(override)
        if gross % 11:
            gross = (gross // 11 + 1) * 11
        rep.log(f"suma faktúry zadaná ručne: {format_gs(gross)} Gs", report=True)
        return gross
    usd = float(cfg.get("MIN_INCOME_USD", "600"))
    margin = float(cfg.get("SAFETY_MARGIN", "1.10"))
    rate, src = get_fx_rate(cfg, rep)
    raw = usd * rate * margin
    gross = int(math.ceil(raw / 11000) * 11000)
    rep.log(f"suma faktúry: {usd:.0f} USD × {rate:,.0f} Gs/USD × {margin} rezerva "
            f"= {raw:,.0f} → {format_gs(gross)} Gs (kurz: {src})", report=True)
    return gross


# ---------------------------------------------------------------- FACTURAR

def emitir_factura(ctx, page, cfg, gross, rep, dry_run):
    """Krok 2 manuálu: EMITIR FACTURA VIRTUAL. Vráti dict s výsledkom."""
    iva = gross // 11
    base = gross - iva
    rep.log(f"faktúra: brutto {format_gs(gross)} Gs = báza {format_gs(base)} + IVA {format_gs(iva)}")

    win = open_menu_window_any(ctx, page, "EMITIR FACTURA", "EMITIR FACTURA VIRTUAL", rep)
    time.sleep(3)
    shot(ctx, win, rep, "10_factura_formular")

    situ = cfg["CLIENT_SITUACION"].upper()
    sel_situ = control_by_label(win, "Situación", "select", timeout_each=15000)
    if situ.startswith("NO"):
        select_option_containing(win, sel_situ, "No Domiciliado", rep, "situación")
        time.sleep(2)
        if not cfg["CLIENT_ID"] or not cfg["CLIENT_NAME"]:
            raise FatalError("residencia.conf: pre NO_DOMICILIADO vyplň CLIENT_ID a CLIENT_NAME")
        fill_by_label(win, ["Identificación"], cfg["CLIENT_ID"], rep, "identificación")
        select_option_containing(win, control_by_label(win, "Tipo de Identificación", "select"),
                                 cfg["CLIENT_ID_TYPE"], rep, "tipo de identificación")
        fill_by_label(win, ["Nombre"], cfg["CLIENT_NAME"], rep, "nombre")
        fill_by_label(win, ["Dirección", "Direccion"], cfg["CLIENT_ADDRESS"], rep, "dirección")
        fill_by_label(win, ["Correo Electrónico", "Correo Electronico"],
                      cfg["CLIENT_EMAIL"], rep, "correo")
        if cfg["CLIENT_COUNTRY"]:
            select_option_containing(win, control_by_label(win, "País", "select"),
                                     cfg["CLIENT_COUNTRY"], rep, "país")
        if cfg["CLIENT_PHONE"]:
            try:
                fill_by_label(win, ["Teléfono", "Telefono"], cfg["CLIENT_PHONE"], rep, "teléfono")
            except Exception:
                pass
    else:
        if not cfg["CLIENT_RUC"]:
            raise FatalError("residencia.conf: pre CONTRIBUYENTE vyplň CLIENT_RUC")
        select_option_containing(win, sel_situ, "Contribuyente", rep, "situación")
        time.sleep(2)
        ruc_inp = fill_by_label(win, ["RUC"], cfg["CLIENT_RUC"], rep, "RUC klienta")
        ruc_inp.press("Tab")
        # systém sám dohľadá meno — čakáme, kým sa Nombre/Razón Social naplní
        nombre = control_by_label(win, ["Nombre / Razón Social", "Nombre"], "input")
        for _ in range(20):
            if (nombre.input_value() or "").strip():
                rep.log(f"klient dohľadaný: {nombre.input_value().strip()}")
                break
            time.sleep(1)
        else:
            raise RuntimeError(f"Portál nedohľadal klienta k RUC {cfg['CLIENT_RUC']}")

    # Condición de Venta — CONTADO býva default; ak select existuje, poistíme sa
    try:
        select_option_containing(win, control_by_label(win, ["Condición de Venta", "Condicion de Venta"],
                                                       "select", timeout_each=3000),
                                  "CONTADO", rep, "condición de venta")
    except Exception:
        rep.log("condición de venta: nechávam default (CONTADO)")

    # detail faktúry: precio unitario + descripción; cantidad=1 a tasa=IVA 10% sú default
    precio, sel = first_visible(win, [
        "input[name*='precio' i]",
        "input[id*='precio' i]",
        "xpath=(//*[contains(text(),'DETALLES DE FACTURACION')]/following::input[not(@readonly) and not(@disabled)])[2]",
    ])
    if precio is None:
        shot(ctx, win, rep, "10x_precio_nenajdene")
        raise RuntimeError("Nenašiel som pole 'Precio Unitario' — over screenshot 10x")
    precio.click()
    precio.fill(str(gross))
    rep.log(f"precio unitario: {gross} (selector: {sel})")

    desc, _ = first_visible(win, [
        "textarea[name*='descripcion' i]", "input[name*='descripcion' i]",
        "xpath=(//*[normalize-space(text())='Descripción']/following::input[1])",
        "xpath=(//*[normalize-space(text())='Descripción']/following::textarea[1])",
    ])
    if desc is None:
        raise RuntimeError("Nenašiel som pole 'Descripción'")
    desc.click()
    desc.fill(cfg["SERVICE_DESCRIPTION"])
    win.keyboard.press("Tab")

    # tasa IVA 10% — default, ale poistíme sa
    try:
        tasa, _ = first_visible(win, [
            "select[name*='tasa' i]",
            "xpath=(//*[contains(text(),'DETALLES DE FACTURACION')]/following::select)[1]",
        ], timeout_each=3000)
        if tasa is not None and "10" not in (tasa.input_value() or ""):
            select_option_containing(win, tasa, "10", rep, "tasa")
    except Exception:
        pass

    # KONTROLA pred odoslaním: portál musí dopočítať presne našu liquidación IVA
    found = wait_for_text(win, [format_gs(iva), format_gs(base)], timeout_s=20)
    shot(ctx, win, rep, "11_factura_vyplnena")
    if not found:
        raise RuntimeError(f"Portál nedopočítal očakávané sumy (báza {format_gs(base)}, "
                           f"IVA {format_gs(iva)}) — NIČ neodosielam, over screenshot 11.")

    click_any(win, ["button:has-text('Vista Previa')", "text=Vista Previa"])
    time.sleep(4)
    shot(ctx, win, rep, "12_factura_vista_previa")
    if format_gs(gross) not in body_text(win) and format_gs(base) not in body_text(win):
        raise RuntimeError("Vista previa neobsahuje očakávanú sumu — NIČ neodosielam.")

    if dry_run:
        rep.log("DRY-RUN: preskakujem finálne potvrdenie faktúry", report=True)
        return {"status": "DRY-RUN (nevystavená)", "gross_gs": gross,
                "base_gs": base, "iva_gs": iva, "numero": None}

    click_any(win, ["button:has-text('Confirmar')", "button:has-text('Emitir')",
                    "text=Confirmar", "button:has-text('ACEPTAR')"])
    time.sleep(2)
    dismiss_pico_modal(win, rep, "Confirmar")
    dismiss_pico_modal(win, rep, "ACEPTAR")

    ok = wait_for_text(win, ["xitosa", "xito", "generad", "Timbrado"], timeout_s=60)
    rtext = body_text(win)
    rep.attach(shot(ctx, win, rep, "13_factura_vysledok"))
    if not ok:
        raise RuntimeError("Po potvrdení faktúry sa nezobrazil výsledok — over screenshot 13, "
                           "faktúra MOHLA byť vystavená; pred opakovaním skontroluj ručne!")
    m = re.search(r"\b(\d{3}-\d{3}-\d{7})\b", rtext)
    numero = m.group(1) if m else None
    rep.log(f"faktúra vystavená: {numero or '(číslo sa nepodarilo prečítať)'}", report=True)
    return {"status": "vystavená", "gross_gs": gross, "base_gs": base,
            "iva_gs": iva, "numero": numero}


def cmd_facturar(creds, cfg, rep, args, period):
    from playwright.sync_api import sync_playwright
    gross = compute_gross_gs(cfg, rep, args.amount_gs)
    results = {}
    with sync_playwright() as p:
        browser, ctx = launch_context(p, cfg, rep)
        page = ctx.new_page()
        page.set_default_timeout(45000)
        try:
            login(ctx, page, creds, rep)
            results["factura"] = emitir_factura(ctx, page, cfg, gross, rep, args.dry_run)
        finally:
            try:
                page.goto(PORTAL + "logout", timeout=30000)
                rep.log("odhlásené")
            except Exception:
                pass
            browser.close()

    if not args.dry_run and results["factura"]["status"] == "vystavená":
        sf = factura_state_file(period)
        payload = dict(results["factura"])
        payload["period"] = period
        payload["issued"] = datetime.date.today().isoformat()
        sf.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        rep.log(f"stav uložený: {sf}")
    return results


# ---------------------------------------------------------------- DECLARAR

def imputar_ventas(ctx, page, year, month, gross, rep, dry_run):
    """Krok 3 manuálu: Ventas a Imputar → imputar todo → siguiente → confirmar."""
    rep.log(f"imputácia predajov: obdobie {month:02d}/{year}")
    marker = STATE_DIR / f"residencia_imputado_{year}-{month:02d}.done"

    gcv = open_window_via_menu(ctx, page, "comprobante",
                               "GESTION DE COMPROBANTES INFORMATIVOS",
                               "gestionComprobantesVirtuales", rep)
    time.sleep(3)
    shot(ctx, gcv, rep, "20_gestion_comprobantes")

    before = set(ctx.pages)
    click_any(gcv, ["text=Obtener Comprob. Elect. y Virtuales", "text=Obtener Comprob",
                    "text=Obtener"])
    win = newest_page_or(ctx, before, gcv)
    time.sleep(3)
    click_any(win, ["text=Ventas a Imputar", "text=Ventas a imputar"])
    time.sleep(3)
    shot(ctx, win, rep, "21_ventas_a_imputar")

    # výber roka a mesiaca — názvy selectov skúšame ako pri talóne (anho/mes)
    sel_year, _ = first_visible(win, ["select[name='anho']", "select[name='anio']",
                                      "select[name*='anho' i]", "select[name*='anio' i]"])
    sel_month, _ = first_visible(win, ["select[name='mes']", "select[name*='mes' i]"])
    if sel_year is None or sel_month is None:
        selects = win.locator("select")
        if selects.count() >= 2:
            sel_year, sel_month = selects.nth(0), selects.nth(1)
        else:
            raise RuntimeError("Nenašiel som selecty rok/mesiac na 'Ventas a Imputar'")
    select_option_containing(win, sel_year, str(year), rep, "rok(imputácia)")
    time.sleep(1.5)
    select_option_containing(win, sel_month, str(month), rep, "mesiac(imputácia)")
    time.sleep(3)
    ttext = body_text(win)
    shot(ctx, win, rep, "22_imputacia_zoznam")

    if re.search(r"[Nn]o (existen|hay|se encontraron)", ttext):
        if marker.exists():
            rep.log("imputácia: nič na imputovanie a marker existuje — už imputované, pokračujem")
            return "už imputované skôr"
        raise FatalError(f"Imputácia {month:02d}/{year}: portál nenašiel ŽIADNE predajné "
                         "doklady a imputácia neprebehla ani skôr. Faktúra za obdobie chýba? "
                         "NIČ nepodávam — over ručne (kroky 2-3 manuálu).")

    click_any(win, ["button:has-text('Imputar todo')", "text=Imputar todo",
                    "text=Imputar Todo"])
    time.sleep(2)
    click_any(win, ["button:has-text('Siguiente')", "text=Siguiente"])
    time.sleep(3)
    ttext = body_text(win)
    shot(ctx, win, rep, "23_imputacia_suhrn")

    # kontrola súčtu: v súhrne musí figurovať suma >= naša faktúra
    nums = [int(x.replace(".", "")) for x in re.findall(r"\b\d{1,3}(?:\.\d{3})+\b", ttext)]
    if not nums or max(nums) < gross:
        raise RuntimeError(f"Súhrn imputácie neobsahuje očakávanú sumu {format_gs(gross)} Gs "
                           f"(nájdené: {[format_gs(n) for n in sorted(set(nums))[-5:]]}) — "
                           "NIČ nepotvrdzujem, over screenshot 23.")
    if dry_run:
        rep.log("DRY-RUN: preskakujem potvrdenie imputácie", report=True)
        return "DRY-RUN (nepotvrdené)"

    click_any(win, ["button:has-text('Confirmar')", "button:has-text('Finalizar')",
                    "text=Confirmar", "button:has-text('ACEPTAR')"])
    time.sleep(2)
    dismiss_pico_modal(win, rep, "ACEPTAR")
    rep.attach(shot(ctx, win, rep, "24_imputacia_vysledok"))
    marker.write_text(datetime.datetime.now().isoformat(), encoding="utf-8")
    return f"imputované, súčet {format_gs(max(nums))} Gs"


def submit_form_120(ctx, page, year, month, base, iva, rep, dry_run):
    """Krok 4 manuálu: Form 120 s NENULOVOU casillou 10 (rubro 1 inciso a).
    Pred podaním sa overí, že portál dopočítal IVA débito = base × 10 %."""
    rep.log(f"Form 120: obdobie {month:02d}/{year}, casilla 10 = {format_gs(base)}")
    href = page.locator("a[href*='recibirDDJJContribuyente.do']").first.get_attribute("href")
    if not href:
        raise RuntimeError("Na dashboarde nie je odkaz recibirDDJJContribuyente.do")
    from urllib.parse import urljoin
    page.goto(urljoin(page.url, href), wait_until="domcontentloaded", timeout=60000)
    time.sleep(2)

    select_option_containing(page, page.locator("select[name='obligacion']"), "211",
                             rep, "obligación")
    time.sleep(2.5)

    anio_selects = page.locator("select[name='anio']")
    if anio_selects.count() < 2:
        time.sleep(3)
    if anio_selects.count() < 2:
        raise RuntimeError(f"Čakal som 2 selecty name='anio', je ich {anio_selects.count()}")
    select_option_containing(page, anio_selects.nth(0), str(year), rep, "rok")
    time.sleep(1.5)
    select_option_containing(page, anio_selects.nth(1), str(month), rep, "mesiac")

    for _ in range(20):
        if "IVA GENERAL" in body_text(page):
            break
        time.sleep(1)
    else:
        raise RuntimeError("Pole Formulario sa nenaplnilo na '120 - IVA GENERAL'")
    shot(ctx, page, rep, "30_ddjj_vyber")

    dismiss_pico_modal(page, rep)
    click_any(page, ["button:has-text('Abrir Declaración')", "text=Abrir Declaración"])
    form = find_page(ctx, "/eset/crear", timeout_s=90)
    time.sleep(4)
    ftext = body_text(form)
    shot(ctx, form, rep, "31_form120_otvoreny")

    if "RECTIFICATIVA" in ftext.upper():
        shot(ctx, form, rep, "31b_rectificativa_STOP")
        try:
            form.close()
        except Exception:
            pass
        raise FatalError(f"Formulár 120 pre {month:02d}/{year} sa otvoril ako RECTIFICATIVA — "
                         "obdobie je už podané. NIČ nepodávam.")

    # rubro 1 inciso a) casilla 10 — riadok 'gravados con tasa del 10%'
    casilla, sel = first_visible(form, [
        "input[name='c10']", "input[id='c10']", "input[name='casilla10']",
        "xpath=(//tr[contains(., 'tasa del 10%')]//input[not(@readonly) and not(@disabled)])[1]",
        "xpath=(//*[contains(text(), 'gravados con tasa del 10%')]/ancestor::tr[1]"
        "//input[not(@readonly) and not(@disabled)])[1]",
    ])
    if casilla is None:
        shot(ctx, form, rep, "31c_casilla10_nenajdena")
        raise RuntimeError("Nenašiel som casillu 10 vo Form 120 — over screenshot 31c")
    casilla.click()
    casilla.fill(str(base))
    form.keyboard.press("Tab")
    rep.log(f"casilla 10 vyplnená: {base} (selector: {sel})")

    # portál musí sám dopočítať IVA débito (casilla 22) = base × 10 %
    expected = {format_gs(iva), str(iva)}
    if not wait_for_text(form, list(expected), timeout_s=20):
        shot(ctx, form, rep, "31d_iva_nedopocitane")
        raise RuntimeError(f"Form 120 nedopočítal IVA débito {format_gs(iva)} — zle vyplnená "
                           "casilla? NIČ nepodávam, over screenshot 31d.")
    shot(ctx, form, rep, "32_form120_vyplneny")

    form.keyboard.press("End")
    form.mouse.wheel(0, 30000)
    time.sleep(1)
    if dry_run:
        rep.log("DRY-RUN: preskakujem klik 'Presentar Declaración' vo Form 120", report=True)
        try:
            form.close()
        except Exception:
            pass
        return "DRY-RUN (nepodané)"

    form.click("button:has-text('Presentar Declaración')")
    time.sleep(2)
    form.locator("div[class*='pico'] button:has-text('Presentar Declaración')").last.click(timeout=20000)
    for _ in range(30):
        rtext = body_text(form)
        if "Declaración Exitosa" in rtext or "Exitosa" in rtext:
            break
        time.sleep(2)
    else:
        shot(ctx, form, rep, "33_form120_vysledok_TIMEOUT")
        raise RuntimeError("Po podaní Form 120 sa nezobrazilo 'Declaración Exitosa'")
    rep.attach(shot(ctx, form, rep, "33_form120_vysledok"))

    m = re.search(r"Declaración Exitosa.{0,400}", rtext, re.S)
    detail = " ".join(m.group(0).split()) if m else "Declaración Exitosa"
    nums = re.findall(r"\b\d{8,}\b", rtext)
    ctrl = re.findall(r"\b[0-9a-f]{8}\b", rtext)
    if nums:
        detail += f" | doc: {nums[0]}"
    if ctrl:
        detail += f" | control: {ctrl[0]}"
    try:
        form.close()
    except Exception:
        pass
    return detail


def submit_form_241(ctx, page, year, month, rep, dry_run):
    """Krok 5 manuálu: talón (Registro Mensual de Comprobantes)."""
    rep.log(f"Form 241: obdobie {month:02d}/{year}")
    page.goto(PORTAL, wait_until="domcontentloaded", timeout=60000)
    time.sleep(3)

    gcv = open_window_via_menu(ctx, page, "comprobante",
                               "GESTION DE COMPROBANTES INFORMATIVOS",
                               "gestionComprobantesVirtuales", rep)
    time.sleep(3)
    shot(ctx, gcv, rep, "40_gestion_comprobantes")

    talon = None
    for i in range(1, 4):
        gcv.click("text=Confirmar Presentación", timeout=30000)
        try:
            talon = find_page(ctx, "presentacionTalon", timeout_s=60)
            break
        except RuntimeError as e:
            rep.log(f"okno presentacionTalon sa neotvorilo (pokus {i}/3): {e}")
            gcv.reload(wait_until="domcontentloaded")
            time.sleep(4)
    if talon is None:
        raise RuntimeError("Dlaždica 'Confirmar Presentación' neotvorila okno presentacionTalon")
    time.sleep(3)

    select_option_containing(talon, talon.locator("select[name='anho']"), str(year), rep, "rok(241)")
    time.sleep(1.5)
    select_option_containing(talon, talon.locator("select[name='mes']"), str(month), rep, "mesiac(241)")
    time.sleep(3)
    ttext = body_text(talon)
    shot(ctx, talon, rep, "41_talon_vyber")

    if "No existen talones pendientes" in ttext:
        rep.log("Form 241: žiadny čakajúci talón (už podané) — nepodávam")
        return "žiadny čakajúci talón — už bolo podané skôr"
    if "241" not in ttext:
        raise RuntimeError(f"Nevidím čakajúci Formulario 241 pre {month:02d}/{year}. "
                           f"Text: {' '.join(ttext.split())[:300]}")
    if dry_run:
        rep.log("DRY-RUN: preskakujem klik 'Presentar declaración' vo Form 241", report=True)
        return "DRY-RUN (nepodané)"

    click_any(talon, ["button:has-text('Presentar declaración')",
                      "text=Presentar declaración"])
    time.sleep(2)
    talon.locator("div[class*='pico'] button:has-text('ACEPTAR')").last.click(timeout=20000)
    for _ in range(30):
        rtext = body_text(talon)
        if "generado satisfactoriamente" in rtext:
            break
        time.sleep(2)
    else:
        shot(ctx, talon, rep, "42_talon_vysledok_TIMEOUT")
        raise RuntimeError("Po podaní Form 241 sa nezobrazilo 'generado satisfactoriamente'")
    rep.attach(shot(ctx, talon, rep, "42_talon_vysledok"))
    return "Talón de Presentación generado satisfactoriamente"


def generar_boleta(ctx, page, rep, dry_run):
    """Krok 9 manuálu: boleta de pago. Best-effort — pri zlyhaní sa deklarácia
    nezhadzuje, boletu vieš vygenerovať ručne a zaplatiť v bankovej appke."""
    try:
        page.goto(PORTAL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)
        win = open_menu_window_any(ctx, page, "BOLETA", "GENERAR BOLETA PAGO", rep)
        time.sleep(3)
        shot(ctx, win, rep, "50_boleta")
        if dry_run:
            return "DRY-RUN — boletu negenerujem"
        # ak obrazovka ponúka pendientes s checkboxom, zaškrtni prvý
        try:
            cb = win.locator("input[type='checkbox']").first
            if cb.is_visible(timeout=3000):
                cb.check()
        except Exception:
            pass
        dest = rep.run_dir / "boleta_de_pago.pdf"
        got = try_download(win, ["button:has-text('Generar')", "text=Generar",
                                 "button:has-text('GENERAR')"], dest, rep)
        if got:
            rep.attach(got)
            return f"boleta vygenerovaná a v prílohe ({got.name})"
        # portál mohol PDF otvoriť v novom tabe — aspoň screenshot
        time.sleep(4)
        rep.attach(shot(ctx, ctx.pages[-1], rep, "51_boleta_vysledok"))
        return "boleta pravdepodobne vygenerovaná (bez downloadu) — over screenshot 51"
    except Exception as e:
        rep.log(f"boleta zlyhala: {e}")
        return ("NEPODARILO sa vygenerovať automaticky — vygeneruj ručne "
                "(manuál krok 9: hľadaj BOLETA → Generar Boleta Pago) a zaplať v bankovej appke")


def cmd_declarar(creds, cfg, rep, args, year, month):
    from playwright.sync_api import sync_playwright
    period = f"{year}-{month:02d}"

    # tvrdá poistka: bez záznamu o faktúre NIKDY nepodávať (nulová deklarácia
    # by pokazila 3-mesačnú reťaz vyžadovanú Rezolúciou DNM 407/2026)
    sf = factura_state_file(period)
    if sf.exists():
        st = json.loads(sf.read_text(encoding="utf-8"))
        gross = int(st["gross_gs"])
        rep.log(f"faktúra za {period}: {format_gs(gross)} Gs "
                f"(č. {st.get('numero') or '?'}, vystavená {st.get('issued')})", report=True)
    elif args.amount_gs:
        gross = int(args.amount_gs)
        rep.log(f"POZOR: marker faktúry za {period} neexistuje, beriem --amount-gs "
                f"{format_gs(gross)} Gs — over, že faktúra bola naozaj vystavená!", report=True)
    else:
        raise FatalError(
            f"Neexistuje záznam o vystavenej faktúre za {period} ({sf}).\n"
            "Podľa Rezolúcie DNM 407/2026 sa nulové deklarácie pre rezidenciu neakceptujú, "
            "preto NIČ nepodávam. Najprv spusti 'facturar' (v mesiaci, za ktorý deklaruješ), "
            "alebo ak faktúra existuje, zopakuj s --amount-gs <brutto v Gs>.")
    iva = gross // 11
    base = gross - iva

    results = {"suma": f"brutto {format_gs(gross)} Gs = báza {format_gs(base)} + IVA {format_gs(iva)}"}
    with sync_playwright() as p:
        browser, ctx = launch_context(p, cfg, rep)
        page = ctx.new_page()
        page.set_default_timeout(45000)
        try:
            dash_text = login(ctx, page, creds, rep)
            venc = get_vencimientos(dash_text)
            rep.log(f"Próximos Vencimientos: {venc[:250] or '(prázdne)'}")
            results["vencimientos_pred"] = venc[:250] or "(prázdne)"

            results["imputacion"] = imputar_ventas(ctx, page, year, month, gross,
                                                   rep, args.dry_run)

            page.goto(PORTAL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(3)
            iva_pending = ("IVA" in venc.upper()) or ("211" in venc)
            if iva_pending:
                results["form120"] = submit_form_120(ctx, page, year, month, base, iva,
                                                     rep, args.dry_run)
            else:
                results["form120"] = ("nepodávané — IVA nie je v Próximos Vencimientos "
                                      "(pravdepodobne už podané)")
                rep.log("Form 120: nič pending, preskakujem")

            results["form241"] = submit_form_241(ctx, page, year, month, rep, args.dry_run)
            results["boleta"] = generar_boleta(ctx, page, rep, args.dry_run)

            page.goto(PORTAL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(4)
            venc_after = get_vencimientos(body_text(page))
            results["vencimientos_po"] = venc_after[:250] or "(prázdne)"
            rep.attach(shot(ctx, page, rep, "60_final_dashboard"))
        finally:
            try:
                page.goto(PORTAL + "logout", timeout=30000)
                rep.log("odhlásené")
            except Exception:
                pass
            browser.close()
    return results


# ---------------------------------------------------------------- DOCUMENTOS

def cmd_documentos(creds, cfg, rep, args):
    """Kroky 7-8 manuálu — podklady k žiadosti o rezidenciu. Všetko best-effort:
    každý dokument sa skúsi, zlyhanie jedného nezhodí ostatné."""
    from playwright.sync_api import sync_playwright
    outdir = DOCS_DIR / datetime.date.today().isoformat()
    outdir.mkdir(parents=True, exist_ok=True)
    results = {}
    with sync_playwright() as p:
        browser, ctx = launch_context(p, cfg, rep)
        page = ctx.new_page()
        page.set_default_timeout(45000)
        try:
            login(ctx, page, creds, rep)

            # 7. certificado de cumplimiento tributario (len ak nič nedlhuješ)
            try:
                win = open_menu_window_any(ctx, page, "CUMP",
                                           "SOLICITAR CERTIFICADO CUMPLIMIENTO", rep)
                time.sleep(3)
                shot(ctx, win, rep, "70_cumplimiento")
                got = try_download(win, ["button:has-text('Generar')",
                                         "button:has-text('Solicitar')",
                                         "text=Generar", "text=Solicitar"],
                                   outdir / "certificado_cumplimiento.pdf", rep)
                if not got:
                    time.sleep(4)
                    rep.attach(shot(ctx, ctx.pages[-1], rep, "71_cumplimiento_vysledok"))
                results["cumplimiento"] = str(got) if got else \
                    "vyžiadaný, ale PDF sa nestiahol — over screenshot (pozor: nejde vygenerovať, ak sú nedoplatky)"
            except Exception as e:
                results["cumplimiento"] = f"ZLYHALO: {e}"

            # 8. constancia de RUC a cédula tributaria (mi perfil → herramientas)
            try:
                page.goto(PORTAL, wait_until="domcontentloaded", timeout=60000)
                time.sleep(3)
                click_any(page, ["text=Mi Perfil", "a:has-text('Perfil')",
                                 "text=MI PERFIL"], timeout=10000)
                time.sleep(3)
                click_any(page, ["text=Herramientas", "text=HERRAMIENTAS"], timeout=15000)
                time.sleep(2)
                shot(ctx, page, rep, "72_perfil_herramientas")
                for label, fname in (("Constancia de RUC", "constancia_ruc.pdf"),
                                     ("Cédula Tributaria", "cedula_tributaria.pdf")):
                    got = try_download(page, [f"text={label}", f"a:has-text('{label}')"],
                                       outdir / fname, rep)
                    results[fname] = str(got) if got else "nestiahnuté — over screenshot 72"
            except Exception as e:
                results["perfil"] = f"ZLYHALO: {e}"
        finally:
            try:
                page.goto(PORTAL + "logout", timeout=30000)
            except Exception:
                pass
            browser.close()
    results["adresar"] = str(outdir)
    return results


# ---------------------------------------------------------------- e-mail + main

def send_email(cfg, subject, body, attachments, rep):
    if not cfg.get("MAIL_TO"):
        rep.log("MAIL_TO nie je nastavené v residencia.conf — report neposielam e-mailom")
        return False
    m = re.search(r"<([^>]+)>", cfg["MAIL_FROM"])
    from_addr = m.group(1) if m else cfg["MAIL_FROM"].strip()
    domain = from_addr.split("@")[-1] or "localhost"
    msg = EmailMessage()
    msg["From"] = cfg["MAIL_FROM"]
    msg["To"] = cfg["MAIL_TO"]
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=domain)
    msg.set_content(body)
    total = 0
    for path in attachments:
        try:
            data = path.read_bytes()
            if total + len(data) > 8_000_000:
                continue
            total += len(data)
            if path.suffix.lower() == ".pdf":
                msg.add_attachment(data, maintype="application", subtype="pdf",
                                   filename=path.name)
            else:
                msg.add_attachment(data, maintype="image", subtype="png",
                                   filename=path.name)
        except Exception as e:
            rep.log(f"príloha {path} zlyhala: {e}")
    proc = subprocess.run([cfg["SENDMAIL"], "-t", "-oi", "-f", from_addr],
                          input=msg.as_bytes(), capture_output=True, timeout=120)
    if proc.returncode != 0:
        rep.log(f"sendmail zlyhal: rc={proc.returncode} {proc.stderr.decode()[:200]}")
        return False
    rep.log(f"e-mail odoslaný na {cfg['MAIL_TO']}: {subject}")
    return True


def build_body(cmd, period, results, rep, dry_run, run_dir):
    host_hint = f"{getpass.getuser()}@{socket.gethostname()}:{run_dir}"
    lines = [f"Marangatu residencia — {cmd}, obdobie {period}"
             f"{' (DRY-RUN)' if dry_run else ''}", ""]
    for line in rep.lines:
        lines.append(f"- {line}")
    lines.append("")
    for k, v in results.items():
        if isinstance(v, dict):
            v = ", ".join(f"{a}={b}" for a, b in v.items())
        lines.append(f"{k}: {v}")
    if cmd == "declarar" and not dry_run:
        lines += ["", "!!! NEZABUDNI: IVA treba ZAPLATIŤ cez bankovú appku "
                      "(Pagar servicios → DNIT, cédula/RUC + dátum narodenia) — "
                      "certificado de cumplimiento sa bez zaplatenia nedá vygenerovať."]
    lines += ["", f"Log + screenshoty: {host_hint}"]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["facturar", "declarar", "documentos"])
    ap.add_argument("--month", help="obdobie YYYY-MM (len declarar; default: minulý mesiac)")
    ap.add_argument("--amount-gs", type=int,
                    help="brutto suma faktúry v Gs (facturar: namiesto výpočtu z USD; "
                         "declarar: fallback, ak chýba marker faktúry)")
    ap.add_argument("--browser", choices=["chromium", "firefox", "gecko"],
                    help="engine prehliadača; prebije BROWSER z residencia.conf "
                         "(default chromium). gecko = firefox")
    ap.add_argument("--dry-run", action="store_true",
                    help="všetko okrem finálnych Presentar/Confirmar klikov")
    ap.add_argument("--no-email", action="store_true")
    ap.add_argument("--only-if-not-done", action="store_true",
                    help="skonči potichu, ak už obdobie má marker (záložný cron)")
    ap.add_argument("--retries", type=int, default=RETRIES)
    args = ap.parse_args()

    today = datetime.date.today()
    if args.cmd == "facturar":
        # faktúru nemožno antedatovať — vždy patrí do aktuálneho mesiaca
        period = f"{today.year}-{today.month:02d}"
        year, month = today.year, today.month
        done_marker = factura_state_file(period)
    elif args.cmd == "declarar":
        if args.month:
            year, month = (int(x) for x in args.month.split("-"))
        else:
            year, month = previous_month(today)
        period = f"{year}-{month:02d}"
        done_marker = STATE_DIR / f"residencia_declarado_{period}.done"
    else:
        period = today.isoformat()
        year = month = None
        done_marker = None

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    if args.only_if_not_done and done_marker and done_marker.exists():
        print(f"{period} už má marker ({done_marker}), končím.")
        return 0

    run_dir = LOGS_DIR / f"{datetime.datetime.now():%Y-%m-%d_%H%M%S}_{args.cmd}_{period}"
    run_dir.mkdir(parents=True, exist_ok=True)
    rep = Reporter(run_dir)
    rep.log(f"=== Marangatu residencia: {args.cmd}, obdobie {period}, dry_run={args.dry_run} ===")

    def _alarm(signum, frame):
        raise RuntimeError(f"pokus prekročil tvrdý limit {ATTEMPT_TIMEOUT_S//60} min")
    signal.signal(signal.SIGALRM, _alarm)

    try:
        creds = load_credentials()
        cfg = load_config()
        if args.browser:
            cfg["BROWSER"] = args.browser
        resolve_browser(cfg.get("BROWSER"))   # over voľbu enginu pred behom
    except FatalError as e:
        print(f"CHYBA: {e}", file=sys.stderr)
        return 1

    last_err = None
    results = None
    for attempt in range(1, args.retries + 1):
        try:
            signal.alarm(ATTEMPT_TIMEOUT_S)
            rep.log(f"pokus {attempt}/{args.retries}")
            if args.cmd == "facturar":
                results = cmd_facturar(creds, cfg, rep, args, period)
            elif args.cmd == "declarar":
                results = cmd_declarar(creds, cfg, rep, args, year, month)
            else:
                results = cmd_documentos(creds, cfg, rep, args)
            signal.alarm(0)
            break
        except FatalError as e:
            signal.alarm(0)
            last_err = e
            rep.log(f"FATÁLNA chyba (neopakujem): {e}")
            break
        except Exception as e:
            signal.alarm(0)
            last_err = e
            rep.log(f"pokus {attempt} zlyhal: {e}\n{traceback.format_exc()}")
            if attempt < args.retries:
                rep.log(f"pauza {RETRY_PAUSE_S//60} min pred ďalším pokusom…")
                time.sleep(RETRY_PAUSE_S)

    if results is not None:
        ok = True
        body = build_body(args.cmd, period, results, rep, args.dry_run, run_dir)
        subject = f"Marangatu residencia {period}: {args.cmd} OK"
        if args.cmd == "declarar" and not args.dry_run:
            done_marker.write_text(body, encoding="utf-8")
    else:
        ok = False
        host = f"{getpass.getuser()}@{socket.gethostname()}"
        body = (f"Marangatu residencia — CHYBA pri '{args.cmd}' za obdobie {period}\n\n"
                f"Posledná chyba: {last_err}\n\n"
                f"Log + screenshoty: {host}:{run_dir}\n\n"
                f"Ručné spustenie:\n"
                f"  python {Path(__file__).resolve()} "
                f"{args.cmd}{' --month ' + period if args.cmd == 'declarar' else ''}\n")
        subject = f"Marangatu residencia {period}: {args.cmd} CHYBA — treba zásah"
        for png in sorted(run_dir.glob("*.png"))[-3:]:
            rep.attach(png)

    rep.log("--- REPORT ---\n" + body)
    if not args.no_email:
        send_email(cfg, subject, body, rep.attachments, rep)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
