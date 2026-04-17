"""
Scraper Atoka by URL — estrae contenuto dalle pagine Atoka già note.
Input: CSV con colonne vat_number, source, source_url
Output: stesso file con colonne content e note aggiunte.

Utilizzo:
    python scrape_atoka_by_url.py unknown_to_atoka.csv
    python scrape_atoka_by_url.py unknown_to_atoka.csv --visible
"""

import csv
import re
import time
import random
import argparse
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

CAMPI = [
    "Descrizione",
    "Area di Business",
    "altri Nomi",
    "Categoria di Impresa",
    "Aziende simili",
    "Ricavi",
]

DELAY_MIN = 3
DELAY_MAX = 6

# ─── Estrazione dati ──────────────────────────────────────────────────────────

def estrai_testo_sezione(page, titolo: str) -> str:
    titolo_lower = titolo.lower()
    for tag in ["h2", "h3", "h4", "h5", "strong", "b", "span", "div"]:
        try:
            headings = page.locator(tag).all()
            for heading in headings:
                testo = heading.inner_text(timeout=2000).strip()
                if titolo_lower in testo.lower():
                    try:
                        sibling = heading.locator("xpath=following-sibling::*[1]")
                        contenuto = sibling.inner_text(timeout=2000).strip()
                        if contenuto:
                            return contenuto
                    except Exception:
                        pass
                    try:
                        parent = heading.locator("xpath=..")
                        full = parent.inner_text(timeout=2000).strip()
                        contenuto = full.replace(testo, "").strip(" :\n")
                        if contenuto:
                            return contenuto
                    except Exception:
                        pass
        except Exception:
            continue

    try:
        body = page.locator("body").inner_text(timeout=5000)
        lines = body.splitlines()
        for i, line in enumerate(lines):
            if titolo_lower in line.lower():
                result_lines = []
                for j in range(i + 1, min(i + 6, len(lines))):
                    next_line = lines[j].strip()
                    if next_line and not any(
                        c.lower() in next_line.lower()
                        for c in CAMPI if c.lower() != titolo_lower
                    ):
                        result_lines.append(next_line)
                    elif next_line:
                        break
                if result_lines:
                    return " ".join(result_lines)
    except Exception:
        pass
    return "N/D"


def estrai_ricavi(page) -> str:
    keywords = ["ricavi", "revenue", "fatturato"]
    try:
        body = page.locator("body").inner_text(timeout=5000)
        lines = body.splitlines()
        for i, line in enumerate(lines):
            if any(k in line.lower() for k in keywords):
                for j in range(i, min(i + 4, len(lines))):
                    candidate = lines[j].strip()
                    if any(c.isdigit() for c in candidate) and len(candidate) < 80:
                        return candidate
    except Exception:
        pass
    return "N/D"


def costruisci_contenuto(dati: dict[str, str]) -> str:
    parti = []
    for campo in CAMPI:
        valore = dati.get(campo, "").strip()
        if valore and valore != "N/D":
            valore = re.sub(r"[\r\n\t]+", " ", valore)
            valore = re.sub(r" {2,}", " ", valore)
            parti.append(valore)
    return " | ".join(parti) if parti else ""


def scrapa_pagina(page, url: str) -> str:
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_load_state("networkidle", timeout=15_000)
    except PlaywrightTimeoutError:
        print(f"  ⚠  Timeout: {url}")
        return ""
    except Exception as e:
        print(f"  ⚠  Errore: {e}")
        return ""

    dati = {}
    for campo in ["Descrizione", "Area di Business", "altri Nomi",
                   "Categoria di Impresa", "Aziende simili"]:
        dati[campo] = estrai_testo_sezione(page, campo)
    dati["Ricavi"] = estrai_ricavi(page)

    for campo in CAMPI:
        preview = dati[campo][:80] + ("..." if len(dati[campo]) > 80 else "")
        print(f"     {campo}: {preview}")

    return costruisci_contenuto(dati)

# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Scrape Atoka pages by URL")
    parser.add_argument("csv_file", help="CSV con vat_number, source, source_url")
    parser.add_argument("--visible", action="store_true", help="Mostra browser")
    args = parser.parse_args()

    csv_path = Path(args.csv_file)

    # Leggi input
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    print(f"📂 {len(rows)} righe da processare\n")

    # Identifica righe già processate (hanno content non vuoto)
    todo = [(i, r) for i, r in enumerate(rows)
            if not r.get("content", "").strip()]
    done_count = len(rows) - len(todo)

    if done_count:
        print(f"⏩ Già completate: {done_count} — riprendo dalle restanti {len(todo)}\n")

    if not todo:
        print("🎉 Tutte le righe hanno già content. Niente da fare.")
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
            url = row["source_url"]
            print(f"[{idx}/{len(todo)}] VAT={vat}")
            print(f"  🔗 {url}")

            content = scrapa_pagina(page, url)
            rows[row_idx]["content"] = content
            rows[row_idx].setdefault("note", "")

            print(f"  💾 {content[:120]}{'...' if len(content) > 120 else ''}\n")

            # Salva dopo ogni riga (resume-safe)
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f, quoting=csv.QUOTE_ALL)
                w.writerow(["vat_number", "source", "content", "source_url", "note"])
                for r in rows:
                    w.writerow([
                        r["vat_number"], r["source"],
                        r.get("content", ""), r["source_url"],
                        r.get("note", ""),
                    ])

            if idx < len(todo):
                delay = random.uniform(DELAY_MIN, DELAY_MAX)
                time.sleep(delay)

        context.close()
        browser.close()

    filled = sum(1 for r in rows if r.get("content", "").strip())
    print(f"✅ Completato. {filled}/{len(rows)} righe con content.")


if __name__ == "__main__":
    main()
