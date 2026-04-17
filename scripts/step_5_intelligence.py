#!/usr/bin/env python3
"""
score_bioenergy.py

Uso:
  python score_bioenergy.py --input file.csv
  python score_bioenergy.py --input file.csv --debug        # 1 azienda, dump testo, poi esce
  python score_bioenergy.py --input file.csv --limit 20
  python score_bioenergy.py --input file.csv --skip-ollama  # solo scraping
  python score_bioenergy.py --input file.csv --reset-cache
"""

import argparse
import csv
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path
from urllib.parse import urlparse, unquote, parse_qs

import pandas as pd
import requests
import urllib3
from bs4 import BeautifulSoup
from requests.exceptions import RequestException
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ═══════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════
INPUT_FILE   = "input.csv"
OUTPUT_FILE  = "output_scored.csv"
CACHE_FILE   = "cache_scored.json"
OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3"

BRAVE_API_KEY   = ""
SEARCH_KEYWORDS = "biogas OR biometano OR biomassa OR impianto bioenerg"
MAX_PAGES       = 3
MAX_TEXT_CHARS  = 2000
DELAY_SEARCH    = 10.0
DELAY_FETCH     = 2.0
CACHE_EVERY     = 5

# ── Batch / rate-limit ─────────────────────────────────
BATCH_SIZE            = 4     # record per batch
DELAY_BETWEEN_RECORDS = 30    # secondi tra un record e il successivo
DELAY_BETWEEN_BATCHES = 120   # secondi di pausa tra un batch e il prossimo
# ──────────────────────────────────────────────────────

SKIP_DOMAINS = [
    "linkedin", "facebook", "instagram", "twitter", "youtube",
    "paginegialle", "kompass", "europages", "trustpilot",
    "registroaziende", "infocamere", "atoka", "opencorporates",
    "wikipedia", "wikidata", "duckduckgo",
]

LEGAL_SUFFIXES = [
    r"\bs\.r\.l\.?\b", r"\bs\.p\.a\.?\b", r"\bsrl\b", r"\bspa\b",
    r"\bsas\b", r"\bsnc\b", r"\bltd\b", r"\bsoc\b",
    r"\bsocieta'?\b", r"\barl\b", r"\bsrls\b", r"\bgeie\b",
    r"\bcooperativa\b", r"\bagricola\b", r"\bconsortile\b",
    r"\bin\b", r"\bforma\b", r"\babbreviata\b",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0 Safari/537.36"
    ),
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
}

NEW_COLS = [
    "sources",
    "confidence",
    "settore_principale",
    "motivazione",
    "come_approcciarla",
]

# ═══════════════════════════════════════════════════════
#  CACHE
# ═══════════════════════════════════════════════════════
def load_cache(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_cache(cache, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)

# ═══════════════════════════════════════════════════════
#  OUTPUT CSV
# ═══════════════════════════════════════════════════════
def normalize_piva(piva):
    """Normalizza la PIVA per confronti affidabili: strip + uppercase."""
    return str(piva).strip().upper() if piva else ""

def init_output(output_path, input_df):
    """
    Crea il file di output con header se non esiste.
    Restituisce l'insieme delle PIVA già presenti (normalizzate) per il resume.
    """
    all_cols = list(input_df.columns) + NEW_COLS
    already_done = set()

    if os.path.exists(output_path):
        try:
            existing = pd.read_csv(output_path, dtype=str)
            if "piva" in existing.columns:
                already_done = {
                    normalize_piva(p)
                    for p in existing["piva"].dropna().tolist()
                    if normalize_piva(p)  # esclude stringhe vuote
                }
            print(f"   Output esistente: {len(already_done)} righe già presenti — riprendo da lì")
        except Exception as e:
            print(f"   ⚠️  Impossibile leggere output esistente ({e}) — ricomincio da capo")
    else:
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=all_cols, quoting=csv.QUOTE_ALL)
            writer.writeheader()
        print(f"   Creato nuovo output: {output_path}")

    return already_done, all_cols

def append_row(output_path, row_dict, all_cols):
    with open(output_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=all_cols, quoting=csv.QUOTE_ALL,
                                extrasaction="ignore")
        writer.writerow(row_dict)

# ═══════════════════════════════════════════════════════
#  UTILS
# ═══════════════════════════════════════════════════════
def strip_accents(text):
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )

NOISE_WORDS = [
    "societa per azioni", "societa a responsabilita limitata",
    "societa agricola", "societa consortile", "societa cooperativa",
    "in forma abbreviata", "in breve",
    "italia", "italian", "italiane", "italiani",
    "gruppo", "group", "holding", "international", "invest",
    "service", "services", "solutions", "management",
    "consulting", "enterprise", "ventures",
    "spa", "srl", "srls", "sas", "snc", "arl",
    "geie", "scrl", "scarl",
]

def normalize_name(name):
    name = strip_accents(name.lower())
    for p in LEGAL_SUFFIXES:
        name = re.sub(p, " ", name, flags=re.IGNORECASE)
    for w in NOISE_WORDS:
        name = re.sub(r"\b" + re.escape(w) + r"\b", " ", name)
    name = re.sub(r"[^\w\s]", " ", name)
    name = re.sub(r"\s+", " ", name)
    return name.strip()

def domain_from_url(url):
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""

def should_skip(url):
    domain = domain_from_url(url)
    return any(bad in domain for bad in SKIP_DOMAINS)

def clean_text(html):
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    text = soup.get_text(separator=" ")
    return re.sub(r"\s+", " ", text).strip()

# ═══════════════════════════════════════════════════════
#  PLAYWRIGHT
# ═══════════════════════════════════════════════════════
_pw_ctx = {}

def get_page():
    if "page" not in _pw_ctx:
        pw      = sync_playwright().start()
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            locale="it-IT",
            viewport={"width": 1280, "height": 800},
        )
        ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = ctx.new_page()
        _pw_ctx.update({"pw": pw, "browser": browser, "ctx": ctx, "page": page})
        print("        🌐 Browser Playwright avviato")
    return _pw_ctx["page"]

def close_browser():
    if "browser" in _pw_ctx:
        try:
            _pw_ctx["browser"].close()
            _pw_ctx["pw"].stop()
        except Exception:
            pass
        _pw_ctx.clear()

# ═══════════════════════════════════════════════════════
#  GOOGLE SEARCH
# ═══════════════════════════════════════════════════════
def google_search(query, n=6):
    import random, urllib.parse
    time.sleep(DELAY_SEARCH + random.uniform(2.0, 5.0))

    encoded = urllib.parse.quote(query)
    gurl    = f"https://www.google.com/search?hl=it&gl=it&num=10&q={encoded}"
    page    = get_page()
    print(f"        🔍 Google: {query}")

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
        print("        ⚠️  timeout Google")
        return []
    except Exception as e:
        print(f"        ⚠️  errore Google: {e}")
        return []

    n_chars     = len(html)
    has_results = "<h3" in html and ("google.com" in html)
    print(f"        📡 Google risposta: {n_chars} chars | risultati presenti: {has_results}")

    if n_chars < 3000 or not has_results:
        print("        ⚠️  pagina anomala — possibile CAPTCHA")
        return []

    soup    = BeautifulSoup(html, "html.parser")
    results = []

    for block in soup.select("div.g, div.tF2Cxc, div.MjjYud > div"):
        a   = block.find("a", href=True)
        h3  = block.find("h3")
        raw_snippet = " ".join(
            s.get_text(" ", strip=True)
            for s in block.find_all("span")
            if len(s.get_text(strip=True)) > 25
        )
        if not a:
            continue
        href = a["href"]
        if not href.startswith("http") or "google.com" in href:
            continue
        results.append({
            "url":     href,
            "title":   h3.get_text(strip=True) if h3 else "",
            "snippet": raw_snippet[:500],
        })
        if len(results) >= n:
            break

    if not results:
        for a in soup.find_all("a", href=True):
            h = a["href"]
            if h.startswith("http") and "google.com" not in h:
                results.append({"url": h, "title": "", "snippet": ""})
            if len(results) >= n:
                break

    print(f"        → {len(results)} risultati: {[r['url'][:55] for r in results]}")
    return results

# ═══════════════════════════════════════════════════════
#  FETCH PAGE
# ═══════════════════════════════════════════════════════
def fetch_page_text(url, max_chars=MAX_TEXT_CHARS):
    try:
        res = requests.get(
            url, headers=HEADERS,
            timeout=10, allow_redirects=True, verify=False
        )
        print(f"        📄 {url[:60]}... → HTTP {res.status_code}")
        if res.status_code != 200:
            return ""
        text = clean_text(res.text)[:max_chars]
        return text
    except RequestException as e:
        print(f"        ⚠️  fetch error {url[:50]}: {e}")
        return ""

# ═══════════════════════════════════════════════════════
#  SCRAPING
# ═══════════════════════════════════════════════════════
def scrape_company(raw_name, norm_name):
    query   = f'"{norm_name}" {SEARCH_KEYWORDS}'
    results = google_search(query, n=6)

    if not results:
        return [], ""

    collected_urls, collected_texts = [], []
    name_tokens = [t for t in norm_name.split() if len(t) > 3]
    bio_kw = [
        "biogas", "biometano", "biomass", "impianto", "bioenerg",
        "digestione", "anaerobica", "rinnovabil", "energia",
    ]

    for r in results:
        url     = r["url"]
        snippet = r.get("snippet", "")
        title   = r.get("title", "")

        if should_skip(url):
            print(f"        ⏭  skip: {url[:60]}")
            continue

        context   = f"Titolo: {title}\nSnippet: {snippet}".strip()
        page_text = ""

        if len(collected_urls) < MAX_PAGES:
            page_text = fetch_page_text(url)
            time.sleep(DELAY_FETCH)

        full = (context + "\n" + page_text).strip()

        if len(full) < 50:
            continue

        has_name = any(t in full.lower() for t in name_tokens)
        has_kw   = any(k in full.lower() for k in bio_kw)

        if has_name or has_kw or snippet:
            collected_urls.append(url)
            collected_texts.append(f"--- FONTE: {url} ---\n{full}")
            print(f"        ✅ {url[:60]} ({len(full)} chars)")

    return collected_urls, "\n\n".join(collected_texts)

# ═══════════════════════════════════════════════════════
#  OLLAMA
# ═══════════════════════════════════════════════════════
PROMPT_TEMPLATE = """Sei un analista di mercato specializzato nel settore delle bioenergie italiano.

Testo raccolto da fonti web sull'azienda "{company_name}":
---
{text}
---

Dati strutturati:
- Codice ATECO: {ateco}
- Città: {city}
- Dipendenti: {employees}

Valuta quanto questa azienda sia attiva nel settore bioenergie (biogas, biometano, biomasse, digestione anaerobica, impianti energia da fonti biologiche).

Rispondi SOLO con JSON, nessun altro testo:
{{
  "confidence": <0.0-1.0>,
  "settore_principale": "<stringa breve>",
  "motivazione": "<2-3 frasi>",
  "come_approcciarla": "<1-2 frasi>"
}}

Scala confidence:
0.9-1.0 = chiaramente focalizzata su biogas/biometano/biomasse
0.7-0.8 = attività bioenergetica confermata ma non esclusiva
0.5-0.6 = probabile coinvolgimento, non confermato
0.3-0.4 = settore energetico generico, bioenergie marginali
0.0-0.2 = nessuna evidenza — assegna questo se non hai testo reale
"""

def ask_ollama(prompt, model):
    try:
        res = requests.post(
            OLLAMA_URL,
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=120
        )
        if res.status_code == 200:
            return res.json().get("response", "")
        print(f"        ⚠️  Ollama HTTP {res.status_code}")
        return ""
    except RequestException as e:
        print(f"        ⚠️  Ollama: {e}")
        return ""

def parse_ollama_response(raw):
    if not raw:
        return None
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return None

def score_with_ollama(company_name, text, ateco, city, employees, model):
    if not text.strip():
        text = "(Nessun testo trovato. Se non hai evidenze reali, assegna confidence 0.1)"

    prompt = PROMPT_TEMPLATE.format(
        company_name=company_name,
        text=text[:4000],
        ateco=ateco,
        city=city,
        employees=employees,
    )

    print(f"        🤖 Ollama ({model})...", end=" ", flush=True)
    raw    = ask_ollama(prompt, model)
    parsed = parse_ollama_response(raw)

    if parsed:
        c = float(parsed.get("confidence", 0.0))
        print(f"confidence={c:.2f}")
        return {
            "confidence":         c,
            "settore_principale": parsed.get("settore_principale", ""),
            "motivazione":        parsed.get("motivazione", ""),
            "come_approcciarla":  parsed.get("come_approcciarla", ""),
        }
    else:
        print(f"⚠️  parsing JSON fallito")
        return {
            "confidence":         -1.0,
            "settore_principale": "",
            "motivazione":        f"Parsing fallito: {raw[:200]}",
            "come_approcciarla":  "",
        }

# ═══════════════════════════════════════════════════════
#  CORE — processa una singola azienda
# ═══════════════════════════════════════════════════════
def process_company(row, cache, skip_ollama, model):
    piva      = str(row.get("piva", "")).strip()
    raw_name  = str(row.get("ragione_sociale", "")).strip()
    norm_name = normalize_name(raw_name)
    city      = str(row.get("citta", "")).strip()
    ateco     = str(row.get("codice_ateco", "")).strip()
    employees = str(row.get("dipendenti", "")).strip()
    cache_key = piva if piva else f"{norm_name}_{city}"

    if cache_key in cache:
        print(f"        📦 da cache")
        return cache[cache_key]

    urls, text = scrape_company(raw_name, norm_name)

    result = {
        "sources":            " | ".join(urls),
        "confidence":         "",
        "settore_principale": "",
        "motivazione":        "",
        "come_approcciarla":  "",
    }

    if not skip_ollama:
        scores = score_with_ollama(raw_name, text, ateco, city, employees, model)
        result.update(scores)

    cache[cache_key] = result
    return result

# ═══════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",          default=INPUT_FILE)
    parser.add_argument("--output",         default=OUTPUT_FILE)
    parser.add_argument("--cache",          default=CACHE_FILE)
    parser.add_argument("--limit",          type=int, default=0)
    parser.add_argument("--reset-cache",    action="store_true")
    parser.add_argument("--skip-ollama",    action="store_true")
    parser.add_argument("--ollama-model",   default=OLLAMA_MODEL)
    parser.add_argument("--min-confidence", type=float, default=0.0)
    args = parser.parse_args()

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("❌ pip install beautifulsoup4 lxml")
        sys.exit(1)

    if not args.skip_ollama:
        try:
            requests.get("http://localhost:11434", timeout=3)
            print(f"✅ Ollama ok (model: {args.ollama_model})")
        except Exception:
            print("⚠️  Ollama non raggiungibile — usa --skip-ollama o avvia Ollama")
            sys.exit(1)

    cache = {} if args.reset_cache else load_cache(args.cache)
    print(f"📦 Cache: {len(cache)} voci\n")

    if not Path(args.input).exists():
        print(f"❌ File non trovato: {args.input}")
        sys.exit(1)

    df = pd.read_csv(args.input, dtype=str).fillna("")

    if args.limit:
        df = df.head(args.limit)

    # ── Resume: filtra le righe già presenti nell'output ──────────────────
    already_done, all_cols = init_output(args.output, df)

    pending = []
    for i, row in df.iterrows():
        piva_norm = normalize_piva(row.get("piva", ""))
        if piva_norm and piva_norm in already_done:
            print(f"  ⏭  già presente, skip: {row.get('ragione_sociale', '—')} ({piva_norm})")
            continue
        pending.append((i, row))

    total_input   = len(df)
    total_pending = len(pending)
    total_skipped = total_input - total_pending

    print(f"\n📋 Totale input: {total_input} | Già processate: {total_skipped} | Da fare: {total_pending}\n")

    if not pending:
        print("✅ Nessuna azienda da processare — tutto già fatto.")
        return

    # ── Loop a batch ──────────────────────────────────────────────────────
    processed = 0

    for batch_start in range(0, total_pending, BATCH_SIZE):
        batch       = pending[batch_start : batch_start + BATCH_SIZE]
        batch_num   = batch_start // BATCH_SIZE + 1
        total_batch = (total_pending + BATCH_SIZE - 1) // BATCH_SIZE

        print(f"\n{'─'*50}")
        print(f"  📦 BATCH {batch_num}/{total_batch}  "
              f"(record {batch_start+1}–{min(batch_start+BATCH_SIZE, total_pending)} di {total_pending})")
        print(f"{'─'*50}")

        for record_idx, (i, row) in enumerate(batch):
            name      = row.get("ragione_sociale", "—")
            piva_disp = normalize_piva(row.get("piva", ""))
            global_n  = batch_start + record_idx + 1

            print(f"\n  [{global_n}/{total_pending}] {name}  (PIVA: {piva_disp})")

            result = process_company(
                row, cache,
                skip_ollama=args.skip_ollama,
                model=args.ollama_model,
            )

            out_row = dict(row)
            for col in NEW_COLS:
                out_row[col] = result.get(col, "")
            append_row(args.output, out_row, all_cols)
            processed += 1

            save_cache(cache, args.cache)

            # pausa tra record (non dopo l'ultimo del batch)
            if record_idx < len(batch) - 1:
                print(f"  ⏳ pausa {DELAY_BETWEEN_RECORDS}s tra record...")
                time.sleep(DELAY_BETWEEN_RECORDS)

        # pausa tra batch (non dopo l'ultimo batch)
        is_last_batch = (batch_start + BATCH_SIZE) >= total_pending
        if not is_last_batch:
            print(f"\n  ☕ Fine batch {batch_num} — pausa {DELAY_BETWEEN_BATCHES}s "
                  f"({DELAY_BETWEEN_BATCHES//60} min) prima del prossimo batch...")
            time.sleep(DELAY_BETWEEN_BATCHES)

    # ── Riepilogo ─────────────────────────────────────────────────────────
    print(f"\n{'═'*50}")
    print(f"  Output:     {args.output}")
    print(f"  Processate: {processed}  |  Saltate (già presenti): {total_skipped}")

    if not args.skip_ollama:
        try:
            out_df = pd.read_csv(args.output, dtype=str)
            c = pd.to_numeric(out_df["confidence"], errors="coerce")
            print(f"\n  Distribuzione confidence:")
            print(f"    🔥 0.8-1.0 : {((c>=0.8)&(c<=1.0)).sum()}")
            print(f"    🟡 0.5-0.79: {((c>=0.5)&(c<0.8)).sum()}")
            print(f"    ⚠️  0.3-0.49: {((c>=0.3)&(c<0.5)).sum()}")
            print(f"    ❌ <0.3    : {(c<0.3).sum()}")
        except Exception:
            pass

    close_browser()

if __name__ == "__main__":
    main()