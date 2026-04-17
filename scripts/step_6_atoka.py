#!/usr/bin/env python3
"""
atoka_scraper.py
----------------
Per ogni record del CSV di input:
  1. Cerca su Google 'site:atoka.io <ragione_sociale_normalizzata>' via Playwright
  2. Prende i primi N risultati atoka.io
  3. Per ogni risultato (in ordine):
       a. Carica la pagina e legge la P.IVA dal blocco col-company-desc
       b. Se P.IVA == vat_number del record → match trovato
       c. Se no → entra nei link "Aziende Simili" e controlla P.IVA uno ad uno
       d. Se ancora nessun match → passa al risultato Google successivo
  4. Se tutti i risultati sono esauriti → found=N

Output CSV: id, vat_number, found (Y/N), description, source

Uso:
    python atoka_scraper.py input.csv output.csv
    python atoka_scraper.py input.csv output.csv --debug

Al riavvio salta automaticamente i record già elaborati (checkpoint).
"""

import csv
import re
import sys
import time
import random
import argparse
import logging
from pathlib import Path
from urllib.parse import unquote

import urllib3
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------------------------------------------------------------------
# Cache globale P.IVA → {url, description}
# Ogni pagina atoka visitata viene indicizzata per P.IVA, anche se non è
# il match cercato in quel momento. Così se la stessa P.IVA serve dopo,
# la troviamo senza passare da Google.
# ---------------------------------------------------------------------------
import json

_vat_cache: dict[str, dict] = {}  # piva → {"url": ..., "description": ...}


def load_vat_cache():
    global _vat_cache
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            _vat_cache = json.load(f)
        log.info("Cache P.IVA caricata: %d voci.", len(_vat_cache))
    except (FileNotFoundError, json.JSONDecodeError):
        _vat_cache = {}


def save_vat_cache():
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(_vat_cache, f, ensure_ascii=False)


def cache_put(piva: str, url: str, description: str | None):
    """Salva una P.IVA nella cache (sovrascrive se già presente)."""
    if piva:
        _vat_cache[piva.strip()] = {"url": url, "description": description or ""}


def cache_get(piva: str) -> dict | None:
    """Cerca una P.IVA nella cache. Restituisce {"url", "description"} o None."""
    return _vat_cache.get(piva.strip()) if piva else None

# ---------------------------------------------------------------------------
# Configurazione
# ---------------------------------------------------------------------------
WAIT_BETWEEN_REQUESTS = 30      # secondi tra un record e il successivo
CAPTCHA_WAIT          = 120     # secondi di attesa se Google mostra CAPTCHA
MAX_CAPTCHA_RETRIES   = 3       # tentativi Google prima di arrendersi
MAX_SEARCH_RESULTS    = 5       # max risultati Google da considerare
MAX_FETCH_RETRIES     = 3       # tentativi fetch atoka.io prima di arrendersi
REQUEST_TIMEOUT       = 20      # timeout HTTP per fetch diretti
GOOGLE_SEARCH_URL     = "https://www.google.com/search"
CACHE_FILE            = "atoka_vat_cache.json"  # cache P.IVA → {url, description}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) "
    "Gecko/20100101 Firefox/125.0",
]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("atoka_scraper.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Playwright — browser condiviso per tutta la sessione
# ---------------------------------------------------------------------------
_pw_ctx: dict = {}


def get_page():
    if "page" not in _pw_ctx:
        pw      = sync_playwright().start()
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="it-IT",
            viewport={"width": 1280, "height": 800},
        )
        ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = ctx.new_page()
        _pw_ctx.update({"pw": pw, "browser": browser, "ctx": ctx, "page": page})
        log.info("Browser Playwright avviato.")
    return _pw_ctx["page"]


def close_browser():
    if "browser" in _pw_ctx:
        try:
            _pw_ctx["browser"].close()
            _pw_ctx["pw"].stop()
        except Exception:
            pass
        _pw_ctx.clear()
        log.info("Browser Playwright chiuso.")


# ---------------------------------------------------------------------------
# HTTP helpers (fetch diretti atoka.io — URL già noti, no JS necessario)
# ---------------------------------------------------------------------------
def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent":      random.choice(USER_AGENTS),
        "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
        "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer":         "https://www.google.com/",
        "DNT":             "1",
    })
    return s


def is_captcha(html: str) -> bool:
    lower = html.lower()
    return (
        "/sorry/index" in lower
        or "unusual traffic" in lower
        or "captcha" in lower
        or "g-recaptcha" in lower
        or "our systems have detected" in lower
    )


def fetch_html_requests(session: requests.Session, url: str) -> str | None:
    """GET leggero via requests (no JS). Per P.IVA e descrizione."""
    for attempt in range(1, MAX_FETCH_RETRIES + 1):
        try:
            resp = session.get(url, timeout=REQUEST_TIMEOUT,
                               allow_redirects=True, verify=False)
            if resp.status_code == 403:
                wait = 30 * attempt
                log.warning("    403 su %s (t%d/%d) — attendo %ds...",
                            url, attempt, MAX_FETCH_RETRIES, wait)
                time.sleep(wait)
                session.headers["User-Agent"] = random.choice(USER_AGENTS)
                continue
            if resp.status_code == 429:
                wait = 60 * attempt
                log.warning("    429 su %s (t%d/%d) — attendo %ds...",
                            url, attempt, MAX_FETCH_RETRIES, wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
        except requests.RequestException as exc:
            wait = 10 * attempt
            log.warning("    fetch %s errore (t%d/%d): %s", url, attempt, MAX_FETCH_RETRIES, exc)
            time.sleep(wait)
            continue
        if is_captcha(resp.text):
            wait = CAPTCHA_WAIT * attempt
            log.warning("    CAPTCHA su %s (t%d/%d) — attendo %ds...",
                        url, attempt, MAX_FETCH_RETRIES, wait)
            time.sleep(wait)
            session.headers["User-Agent"] = random.choice(USER_AGENTS)
            continue
        return resp.text
    log.error("    Tutti i %d tentativi requests falliti per %s", MAX_FETCH_RETRIES, url)
    return None


def fetch_html_playwright(url: str) -> str | None:
    """Carica pagina atoka via Playwright (JS rendering).
    Necessario per il blocco 'Aziende Simili' renderizzato client-side."""
    page = get_page()
    for attempt in range(1, MAX_FETCH_RETRIES + 1):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(3000)
            html = page.content()
            if is_captcha(html):
                wait = CAPTCHA_WAIT * attempt
                log.warning("    CAPTCHA Playwright %s (t%d/%d) — attendo %ds...",
                            url, attempt, MAX_FETCH_RETRIES, wait)
                time.sleep(wait)
                continue
            return html
        except PlaywrightTimeout:
            log.warning("    Timeout Playwright %s (t%d/%d)", url, attempt, MAX_FETCH_RETRIES)
            time.sleep(10 * attempt)
        except Exception as exc:
            log.warning("    Errore Playwright %s (t%d/%d): %s", url, attempt, MAX_FETCH_RETRIES, exc)
            time.sleep(10 * attempt)
    log.error("    Tutti i %d tentativi Playwright falliti per %s", MAX_FETCH_RETRIES, url)
    return None


# ---------------------------------------------------------------------------
# Normalizzazione ragione sociale
# ---------------------------------------------------------------------------
def normalize_ragione_sociale(name: str) -> str:
    name = name.lower()
    legal = [
        r"societa[\'']?\s*a\s*responsabilita[\'']?\s*limitata\s*semplificata",
        r"societa[\'']?\s*a\s*responsabilita[\'']?\s*limitata",
        r"societa[\'']?\s*per\s*azioni",
        r"societa[\'']?\s*semplice\s*agricola",
        r"societa[\'']?\s*semplice",
        r"societa[\'']?\s*cooperativa\s*agricola",
        r"societa[\'']?\s*cooperativa",
        r"societa[\'']?\s*agricola",
        r"s\.r\.l\.?\s*s\.b\.",
        r"s\.r\.l\.?", r"s\.p\.a\.?", r"s\.n\.c\.?", r"s\.a\.s\.?",
        r"s\.s\.?", r"s\.c\.?",
        r"\bsrls\b", r"\bsrl\b", r"\bspa\b", r"\bsnc\b", r"\bsas\b",
        r"\bscpa\b", r"\bscrl\b", r"\bsoc\b", r"\bsoc\.?\s*coop\.?",
        r"\bcooperativa\b", r"\bin\s+breve\b", r"\bcoop\.?",
        r"\bagricola\b", r"\bsocieta\b", r"\bsociet[aà]\b",
        r"\bin\s+liquidazione?\b", r"\bin\s+sigla\b",
        r"\bin\s+forma\s+abbreviata\b", r"\be\s+c\b",
        r"\bgmbh\b", r"\bag\b", r"\bltd\.?\b", r"\bllc\b", r"\bgroup\b",
    ]
    for pattern in legal:
        name = re.sub(pattern, " ", name)
    name = re.sub(r"[^\w\s]", " ", name)
    name = re.sub(r"\b\w\b", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


# ---------------------------------------------------------------------------
# Google search via Playwright
# ---------------------------------------------------------------------------
def search_atoka(nome: str) -> list[str]:
    """
    Cerca 'site:atoka.io <nome>' su Google tramite Playwright.
    Restituisce fino a MAX_SEARCH_RESULTS URL atoka.io.
    """
    import urllib.parse
    query   = f"site:atoka.io {nome}"
    encoded = urllib.parse.quote(query)
    gurl    = f"{GOOGLE_SEARCH_URL}?hl=it&gl=it&num=10&q={encoded}"

    page = get_page()
    log.info("  Google: %s", query)

    for attempt in range(1, MAX_CAPTCHA_RETRIES + 1):
        try:
            page.goto(gurl, wait_until="domcontentloaded", timeout=25000)
            for selector in [
                "button:has-text('Accetta tutto')",
                "button:has-text('Accept all')",
                "button:has-text('Acconsento')",
            ]:
                try:
                    btn = page.locator(selector)
                    if btn.count() > 0:
                        btn.first.click()
                        page.wait_for_timeout(1500)
                        break
                except Exception:
                    pass
            page.wait_for_timeout(2500)
            html = page.content()
        except PlaywrightTimeout:
            log.warning("  Timeout Google (tentativo %d).", attempt)
            time.sleep(10)
            continue
        except Exception as exc:
            log.warning("  Errore Playwright (tentativo %d): %s", attempt, exc)
            time.sleep(10)
            continue

        n_chars     = len(html)
        has_results = "<h3" in html and "google.com" in html
        log.debug("  Google risposta: %d chars | risultati: %s", n_chars, has_results)

        if n_chars < 3000 or not has_results:
            wait = CAPTCHA_WAIT * attempt
            log.warning("  Pagina Google anomala/CAPTCHA (t%d/%d). Attendo %ds...",
                        attempt, MAX_CAPTCHA_RETRIES, wait)
            time.sleep(wait)
            continue

        soup = BeautifulSoup(html, "html.parser")
        urls = []
        for block in soup.select("div.g, div.tF2Cxc, div.MjjYud > div"):
            a = block.find("a", href=True)
            if not a:
                continue
            href = unquote(a["href"])
            if href.startswith("https://atoka.io/") and href not in urls:
                urls.append(href)
                if len(urls) >= MAX_SEARCH_RESULTS:
                    break

        if not urls:
            for a in soup.find_all("a", href=True):
                href = unquote(a["href"])
                if href.startswith("https://atoka.io/") and href not in urls:
                    urls.append(href)
                if len(urls) >= MAX_SEARCH_RESULTS:
                    break

        log.info("  Google: %d URL atoka.io trovati.", len(urls))
        if not urls:
            log.debug("  HTML snippet: %s", html[:2000].replace("\n", " "))
        return urls

    log.error("  Google: superati %d tentativi.", MAX_CAPTCHA_RETRIES)
    return []


# ---------------------------------------------------------------------------
# Estrazione dati da una pagina atoka.io
# ---------------------------------------------------------------------------
def extract_vat_from_page(html: str) -> str | None:
    """
    Estrae la P.IVA dal blocco col-company-desc.
    Restituisce la stringa numerica o None se non trovata.
    """
    soup  = BeautifulSoup(html, "html.parser")
    block = soup.find("div", class_="col-company-desc")
    if not block:
        return None

    # Cerca lo span/div che contiene il testo "P.IVA:"
    for tag in block.find_all(string=re.compile(r"P\.IVA", re.I)):
        parent = tag.find_parent()
        if parent:
            # Il valore è nel testo del nodo contenitore, dopo "P.IVA:"
            full_text = parent.get_text(" ", strip=True)
            m = re.search(r"P\.IVA[:\s]+(\d{11})", full_text, re.I)
            if m:
                return m.group(1)

    # Fallback: cerca il pattern direttamente in tutto il blocco
    m = re.search(r"P\.IVA[:\s]+(\d{11})", block.get_text(" ", strip=True), re.I)
    return m.group(1) if m else None


def extract_description(html: str) -> str | None:
    """Estrae il testo pulito del div.detail-descrizione.
    Rimuove tag HTML, newline, e fa escape di caratteri speciali."""
    soup = BeautifulSoup(html, "html.parser")
    div  = soup.find("div", class_="detail-descrizione")
    if not div:
        return None
    # Estrai solo il testo, rimuovi tag HTML
    text = div.get_text(" ", strip=True)
    # Rimuovi newline, tab, carriage return
    text = re.sub(r"[\r\n\t]+", " ", text)
    # Collassa spazi multipli
    text = re.sub(r"\s{2,}", " ", text).strip()
    # Escape di virgolette doppie per sicurezza CSV
    text = text.replace('"', '""')
    return text if text else None


def extract_similar_links(html: str) -> list[str]:
    """Estrae i link /azienda/ dal blocco 'Aziende Simili'.
    La struttura è: <div class="card p-3"><ul class="list-unstyled"><li><a href="...">
    """
    soup = BeautifulSoup(html, "html.parser")
    urls = []

    # Strategia 1: cerca tutti i link atoka /azienda/ dentro card con list-unstyled
    for ul in soup.find_all("ul", class_=re.compile(r"list-unstyled")):
        for a in ul.find_all("a", href=True):
            href = a["href"]
            if href.startswith("/"):
                href = "https://atoka.io" + href
            if re.match(r"https://atoka\.io/public/it/azienda/", href) and href not in urls:
                urls.append(href)

    # Strategia 2 (fallback): qualsiasi link /azienda/ nella pagina
    if not urls:
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("/"):
                href = "https://atoka.io" + href
            if re.match(r"https://atoka\.io/public/it/azienda/", href) and href not in urls:
                urls.append(href)
                if len(urls) >= 15:
                    break

    return urls


# ---------------------------------------------------------------------------
# Risoluzione: scorre i risultati Google e cerca il match sulla P.IVA
# ---------------------------------------------------------------------------
def resolve_atoka(session: requests.Session,
                  vat_number: str,
                  google_urls: list[str]) -> tuple[str | None, str | None]:
    """
    Per ogni URL Google (in ordine):
      1. Carica la pagina (requests) e controlla la P.IVA
      2. Se match → restituisce (url, description)
      3. Cachea la P.IVA trovata (anche se non è il match cercato)
      4. Se no match → carica con Playwright per ottenere 'Aziende Simili'
      5. Controlla ogni link simile
      6. Se ancora nessun match → passa all'URL Google successivo

    Restituisce (url_matched, html_description) oppure (None, None).
    """
    visited = set()

    def check_page_requests(url: str) -> tuple[str | None, str | None]:
        """Fetch via requests, estrai P.IVA, cachea. Restituisce (url, desc) se match."""
        if url in visited:
            return None, None
        visited.add(url)

        html = fetch_html_requests(session, url)
        if not html:
            return None, None

        page_vat = extract_vat_from_page(html)
        log.debug("    %s → P.IVA estratta: %s", url, page_vat)

        if page_vat:
            desc = extract_description(html)
            cache_put(page_vat, url, desc)

            if page_vat.strip() == vat_number.strip():
                log.info("    ✓ Match P.IVA su: %s", url)
                return url, desc

        return None, None

    for gurl in google_urls:
        log.info("  Controllo risultato Google: %s", gurl)

        # Passo A: check P.IVA via requests (veloce)
        matched_url, desc = check_page_requests(gurl)
        if matched_url:
            return matched_url, desc

        # Passo B: carica con Playwright per ottenere Aziende Simili (JS-rendered)
        log.info("    Carico con Playwright per Aziende Simili...")
        pw_html = fetch_html_playwright(gurl)
        if pw_html:
            similar_urls = extract_similar_links(pw_html)
            # Filtra via il link della pagina stessa
            similar_urls = [u for u in similar_urls if u != gurl]
            log.info("    'Aziende Simili': %d link trovati.", len(similar_urls))

            for surl in similar_urls:
                matched_url, desc = check_page_requests(surl)
                if matched_url:
                    return matched_url, desc
        else:
            log.warning("    Playwright fallito, nessun link simile disponibile.")

        log.info("    Nessun match in questo risultato Google, passo al successivo.")

    return None, None


# ---------------------------------------------------------------------------
# Checkpoint
# ---------------------------------------------------------------------------
def load_done_pivas(output_path: Path) -> set:
    done = set()
    if not output_path.exists():
        return done
    try:
        with output_path.open(encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                piva = row.get("vat_number", "").strip()
                if piva:
                    done.add(piva)
        log.info("Checkpoint: %d record già elaborati in '%s'.", len(done), output_path)
    except Exception as exc:
        log.warning("Impossibile leggere il checkpoint: %s — si riparte da zero.", exc)
    return done


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Scraper atoka.io via Google (Playwright)")
    parser.add_argument("input_csv",  help="CSV di input (id, vat_number/piva, ragione_sociale, ...)")
    parser.add_argument("output_csv", help="CSV di output")
    parser.add_argument("--debug", action="store_true", help="Abilita log DEBUG")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        log.debug("Modalità DEBUG attivata.")

    input_path  = Path(args.input_csv)
    output_path = Path(args.output_csv)

    if not input_path.exists():
        log.error("File di input non trovato: %s", input_path)
        sys.exit(1)

    with input_path.open(encoding="utf-8-sig") as f:
        records = list(csv.DictReader(f))

    total      = len(records)
    done_pivas = load_done_pivas(output_path)
    skip_count = sum(1 for r in records
                     if r.get("vat_number", r.get("piva", "")).strip() in done_pivas)
    todo_count = total - skip_count

    log.info("Record totali: %d  |  Già elaborati: %d  |  Da elaborare: %d",
             total, skip_count, todo_count)

    if todo_count == 0:
        log.info("Tutti i record sono già stati elaborati.")
        return

    file_exists = output_path.exists() and output_path.stat().st_size > 0
    out_file    = output_path.open("a", encoding="utf-8-sig", newline="")
    writer      = csv.DictWriter(
        out_file,
        fieldnames=["id", "vat_number", "found", "description", "source"],
        quoting=csv.QUOTE_ALL,
    )
    if not file_exists:
        writer.writeheader()

    session            = make_session()
    processed_this_run = 0
    load_vat_cache()

    try:
        for idx, record in enumerate(records):
            piva = record.get("vat_number", record.get("piva", "")).strip()

            if piva in done_pivas:
                continue

            row_id             = record.get("id", str(idx))
            processed_this_run += 1
            remaining          = todo_count - processed_this_run

            log.info("[%d/%d | fatto:%d rimasto:%d] id=%s  piva=%s  (%s)",
                     idx + 1, total,
                     len(done_pivas) + processed_this_run, remaining,
                     row_id, piva, record.get("ragione_sociale", ""))

            if not piva:
                log.warning("  Partita IVA mancante, salto.")
                writer.writerow({"id": row_id, "vat_number": piva,
                                 "found": "N", "description": "", "source": ""})
                out_file.flush()
                done_pivas.add(piva)
                continue

            # 0. Controlla la cache prima di andare su Google
            cached = cache_get(piva)
            if cached:
                log.info("  ✓ Cache HIT per P.IVA %s → %s", piva, cached["url"])
                writer.writerow({"id": row_id, "vat_number": piva,
                                 "found": "Y", "description": cached["description"],
                                 "source": cached["url"]})
                out_file.flush()
                done_pivas.add(piva)
                continue

            ragione_sociale   = record.get("ragione_sociale", "").strip()
            nome_normalizzato = normalize_ragione_sociale(ragione_sociale)

            # 1. Ricerca Google via Playwright (prima per nome, poi per P.IVA)
            google_urls = search_atoka(nome_normalizzato)

            # Se nessun match con il nome, prova cercando direttamente la P.IVA
            matched_url, description = None, None
            if google_urls:
                matched_url, description = resolve_atoka(session, piva, google_urls)

            if matched_url is None:
                # Fallback: cerca per P.IVA direttamente
                log.info("  Nessun match per nome, provo ricerca per P.IVA...")
                piva_urls = search_atoka(piva)
                if piva_urls:
                    matched_url, description = resolve_atoka(session, piva, piva_urls)

            if matched_url is None and not google_urls and not piva_urls:
                log.info("  Nessun risultato Google → found=N")
                writer.writerow({"id": row_id, "vat_number": piva,
                                 "found": "N", "description": "", "source": ""})
            elif matched_url is None:
                log.info("  Nessun match P.IVA trovato → found=N")
                writer.writerow({"id": row_id, "vat_number": piva,
                                     "found": "N", "description": "", "source": ""})
            elif description:
                log.info("  Match trovato con descrizione (%d car).", len(description))
                writer.writerow({"id": row_id, "vat_number": piva,
                                     "found": "Y", "description": description,
                                     "source": matched_url})
            else:
                log.warning("  Match trovato ma div.detail-descrizione assente.")
                writer.writerow({"id": row_id, "vat_number": piva,
                                     "found": "Y", "description": "",
                                     "source": matched_url})

            out_file.flush()
            done_pivas.add(piva)

            # Salva cache periodicamente (ogni 5 record)
            if processed_this_run % 5 == 0:
                save_vat_cache()

            if remaining > 0:
                wait = WAIT_BETWEEN_REQUESTS + random.uniform(-5, 5)
                log.info("  Attesa %.1f secondi...", wait)
                time.sleep(wait)

    finally:
        save_vat_cache()
        out_file.close()
        close_browser()

    log.info("Sessione completata. Elaborati: %d. Output: %s",
             processed_this_run, output_path)


if __name__ == "__main__":
    main()