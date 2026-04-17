"""
Google search per trovare homepage aziendali tramite P.IVA.
Cerca varianti di "P.IVA: XXXXXXXXXXX" ed esclude siti di report aziendali.

Utilizzo:
    python find_company_homepage.py top_30_scores.csv
    python find_company_homepage.py top_30_scores.csv --visible
"""

import csv
import re
import time
import random
import argparse
import sys
from pathlib import Path
from urllib.parse import quote, urlparse, parse_qs
from playwright.sync_api import sync_playwright

# Domini da escludere (report aziendali, registri, ecc.)
EXCLUDED_DOMAINS = [
    "fatturatoitalia.it",
    "cameradicommercio",
    "registroaziende.it",
    "companyreports",
    "atoka.io",
    "cerved.com",
    "infocamere.it",
    "paginegialle.it",
    "europages.it",
    "kompass.com",
    "dnb.com",
    "aziende.virgilio.it",
    "italiaonline.it",
    "linkedin.com",
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "ufficiocamerale.it",
    "ufficiocamerale",
    "aziende.it",
    "reportaziende.it",
    "regione.",
    "visura.pro",
    "impresaitalia.info",
]

DELAY_MIN = 15
DELAY_MAX = 15
MAX_RESULTS = 5

def build_google_query(vat: str) -> str:
    """
    Costruisce query Google per cercare homepage con P.IVA.
    Cerca varianti: "P.IVA: XXX", "Partita IVA: XXX", "P.IVA XXX"
    """
    # Usa OR per cercare varianti
    query = f'("P.IVA: {vat}" OR "Partita IVA: {vat}" OR "P.IVA {vat}")'
    
    # Escludi domini indesiderati
    for domain in EXCLUDED_DOMAINS:
        query += f' -site:{domain}'
    
    return query


def cerca_homepage_google(page, vat: str) -> list[str]:
    """Cerca su Google e restituisce lista di URL trovati."""
    query = build_google_query(vat)
    encoded = quote(query)
    url = f"https://www.google.com/search?q={encoded}&hl=it&gl=it"
    
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
    except Exception as e:
        print(f"  ⚠  Errore caricamento Google: {e}")
        return []

    # Accetta cookie
    try:
        for testo in ["Accetta tutto", "Accept all", "Accetto", "I agree"]:
            btn = page.locator("button", has_text=testo).first
            if btn.is_visible(timeout=2000):
                btn.click()
                page.wait_for_load_state("domcontentloaded")
                break
    except Exception:
        pass

    # Attendi risultati
    try:
        page.wait_for_selector("div#search", timeout=10_000)
    except Exception:
        pass

    page.wait_for_timeout(2000)

    # Controlla CAPTCHA
    try:
        body_text = page.locator("body").inner_text(timeout=5000)
        if any(kw in body_text.lower() for kw in ["captcha", "unusual traffic", "not a robot", "traffico insolito"]):
            print("  ⚠  Google CAPTCHA rilevato! Attendo 60s...")
            page.wait_for_timeout(60_000)
            # Riprova dopo il wait
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(3000)
            # Controlla di nuovo se c'è ancora CAPTCHA
            body_text = page.locator("body").inner_text(timeout=5000)
            if any(kw in body_text.lower() for kw in ["captcha", "unusual traffic", "not a robot", "traffico insolito"]):
                print("  ❌ CAPTCHA ancora presente, salto questa ricerca")
                return []
    except Exception:
        pass

    # Estrai link
    links = []
    seen_domains = set()  # Track domains to avoid duplicates
    
    selectors = [
        "div#search a[href]",
        "div#rso a[href]",
        "div.g a[href]",
    ]
    
    for sel in selectors:
        for el in page.locator(sel).all():
            if len(links) >= MAX_RESULTS:
                break
            try:
                href = el.get_attribute("href", timeout=3000)
                if not href:
                    continue
                
                # Unwrap Google redirect
                if href.startswith("/url?"):
                    qs = parse_qs(urlparse(href).query)
                    href = qs.get("q", [href])[0]
                
                # Valida URL
                if not href.startswith("http"):
                    continue
                
                # Estrai dominio
                parsed = urlparse(href)
                domain = parsed.netloc.lower()
                
                # Escludi domini indesiderati
                if any(excl in domain for excl in EXCLUDED_DOMAINS):
                    continue
                
                # Normalizza a dominio base (rimuovi path)
                base_url = f"{parsed.scheme}://{parsed.netloc}"
                
                # Evita duplicati di dominio
                if domain in seen_domains:
                    continue
                
                seen_domains.add(domain)
                links.append(base_url)
                
            except Exception:
                continue
        
        if len(links) >= MAX_RESULTS:
            break
    
    return links


def main():
    parser = argparse.ArgumentParser(description="Find company homepages via Google + VAT")
    parser.add_argument("csv_file", help="CSV con vat_number")
    parser.add_argument("--visible", action="store_true", help="Mostra browser")
    args = parser.parse_args()

    csv_path = Path(args.csv_file)
    
    # Leggi input
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    
    print(f"📂 {len(rows)} righe da processare\n")
    
    # Identifica righe già processate
    todo = [(i, r) for i, r in enumerate(rows)
            if not r.get("results", "").strip()]
    done_count = len(rows) - len(todo)
    
    if done_count:
        print(f"⏩ Già completate: {done_count} — riprendo dalle restanti {len(todo)}\n")
    
    if not todo:
        print("🎉 Tutte le righe hanno già results.")
        sys.exit(0)
    
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.visible)
        context = browser.new_context(
            locale="it-IT",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        
        for idx, (row_idx, row) in enumerate(todo, 1):
            vat = row["vat_number"]
            print(f"[{idx}/{len(todo)}] VAT={vat}")
            
            links = cerca_homepage_google(page, vat)
            
            if links:
                print(f"  ✅ Trovati {len(links)} link:")
                for link in links:
                    print(f"     {link}")
            else:
                print(f"  ⚠  Nessun risultato")
            
            rows[row_idx]["results"] = " | ".join(links)
            
            # Salva dopo ogni riga
            fieldnames = list(rows[0].keys())
            if "results" not in fieldnames:
                fieldnames.append("results")
            
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
                w.writeheader()
                w.writerows(rows)
            
            if idx < len(todo):
                delay = random.uniform(DELAY_MIN, DELAY_MAX)
                print(f"  ⏳ Attesa {delay:.0f}s...\n")
                time.sleep(delay)
        
        context.close()
        browser.close()
    
    filled = sum(1 for r in rows if r.get("results", "").strip())
    print(f"\n✅ Completato. {filled}/{len(rows)} righe con results.")


if __name__ == "__main__":
    main()
