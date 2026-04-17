"""
Atoka.io scraper via Google Search
Legge id/vat_number/ragione_sociale da un CSV, normalizza la ragione sociale
(rimuove forme giuridiche tipo SRL, SPA, ecc.), cerca su Google con
  site:atoka.io "RAGIONE SOCIALE NORMALIZZATA"
e produce UN'UNICA riga di output per ogni entry con tutti i campi estratti
concatenati in un singolo campo `contenuto`, racchiuso tra doppi apici con
i caratteri interni opportunamente escaped.

Dipendenze:
    pip install playwright
    playwright install chromium

Utilizzo:
    python atoka_scraper.py input.csv output.csv
    python atoka_scraper.py input.csv output.csv --visible        # mostra browser
    python atoka_scraper.py input.csv output.csv --colonna P.IVA  # colonna VAT custom

Funzionalità:
    - Scrive l'output dopo ogni voce elaborata (nessun dato perso in caso di stop)
    - Riprende automaticamente dall'ultimo punto in caso di interruzione
"""

import csv
import json
import re
import time
import random
import argparse
import sys
from pathlib import Path
from urllib.parse import quote
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ─── Configurazione ────────────────────────────────────────────────────────────

CAMPI = [
    "Descrizione",
    "Area di Business",
    "altri Nomi",
    "Categoria di Impresa",
    "Aziende simili",
    "Ricavi",
]

# Output: una riga per entry
FIELDNAMES_OUT = ["id", "vat_number", "ragione_sociale", "ragione_sociale_normalizzata", "contenuto", "source_url"]

# La query Google usa la ragione sociale normalizzata SENZA virgolette
GOOGLE_SEARCH_URL = "https://www.google.com/search?q=site%3Aatoka.io+{rs_enc}&hl=it&gl=it"

# Massimo numero di link Google da provare per ogni azienda
MAX_GOOGLE_LINKS = 4

# File cache P.IVA → URL Atoka (persistente su disco)
CACHE_FILE = "atoka_cache.json"

# Delay tra una ricerca e l'altra (~30 sec) per non fare rate-limit
DELAY_MIN = 10
DELAY_MAX = 15

# ─── Normalizzazione ragione sociale ──────────────────────────────────────────

# Forme giuridiche da rimuovere — dalla più lunga alla più corta per evitare
# match parziali (es. "s.r.l." prima di "s.r." ecc.)
_FORME_GIURIDICHE = [
    r"societ[àa]\s+a\s+responsabilit[àa]\s+limitata",
    r"societ[àa]\s+per\s+azioni",
    r"societ[àa]\s+in\s+accomandita\s+per\s+azioni",
    r"societ[àa]\s+in\s+accomandita\s+semplice",
    r"societ[àa]\s+in\s+nome\s+collettivo",
    r"impresa\s+individuale",
    r"ditta\s+individuale",
    r"s\.?\s*c\.?\s*a\.?\s*r\.?\s*l\.?",   # scarl / s.c.a.r.l.
    r"s\.?\s*c\.?\s*r\.?\s*l\.?",            # scrl  / s.c.r.l.
    r"s\.?\s*a\.?\s*p\.?\s*a\.?",            # sapa  / s.a.p.a.
    r"s\.?\s*c\.?\s*s\.?",                   # scs   / s.c.s.
    r"s\.?\s*r\.?\s*l\.?",                   # srl   / s.r.l.
    r"s\.?\s*p\.?\s*a\.?",                   # spa   / s.p.a.
    r"s\.?\s*n\.?\s*c\.?",                   # snc   / s.n.c.
    r"s\.?\s*a\.?\s*s\.?",                   # sas   / s.a.s.
    r"s\.?\s*s\.?",                           # ss    / s.s.
    r"\bsrl\b",
    r"\bspa\b",
    r"\bsnc\b",
    r"\bsas\b",
    r"\bscrl\b",
    r"\bscarl\b",
    r"\bsapa\b",
    r"\bonlus\b",
    r"\baps\b",
    r"\bodi\b",
    r"\bets\b",
    r"\bltd\.?\b",
    r"\bgmbh\.?\b",
]

_RE_FORME = re.compile(
    r"(?:(?<=\s)|(?<=,)|(?<=-)|^)(?:" + "|".join(_FORME_GIURIDICHE) + r")(?=\s|,|-|$|\.)",
    flags=re.IGNORECASE | re.UNICODE,
)

_RE_TRAILING_PUNCT = re.compile(r"[\s,.\-–—/\\]+$")
_RE_LEADING_PUNCT  = re.compile(r"^[\s,.\-–—/\\]+")
_RE_SPACES         = re.compile(r"\s{2,}")


def normalizza_ragione_sociale(nome: str) -> str:
    """
    Rimuove forme giuridiche, punteggiatura residua e spazi multipli.
    Restituisce la stringa in MAIUSCOLO pronta per la query Google.
    """
    risultato = nome.strip()

    # Rimozione iterativa: alcune RS hanno più sigle (es. "SRL ONLUS")
    precedente = None
    while precedente != risultato:
        precedente = risultato
        risultato = _RE_FORME.sub(" ", risultato)
        risultato = _RE_SPACES.sub(" ", risultato).strip()

    risultato = _RE_TRAILING_PUNCT.sub("", risultato)
    risultato = _RE_LEADING_PUNCT.sub("", risultato)
    risultato = _RE_SPACES.sub(" ", risultato).strip()

    return risultato.upper()

# ─── Lettura input ─────────────────────────────────────────────────────────────

def leggi_input(path_csv: str, col_vat: str = "vat_number") -> list[dict]:
    """
    Legge il CSV e restituisce lista di dict con id, vat, rs, rs_norm.
    Campi obbligatori nel CSV: col_vat, ragione_sociale.
    Il campo 'id' è opzionale — se assente usa l'indice di riga.
    """
    righe = []
    with open(path_csv, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("CSV vuoto o senza intestazione.")

        campi = list(reader.fieldnames)

        if col_vat not in campi:
            raise ValueError(
                f"Colonna VAT '{col_vat}' non trovata. "
                f"Colonne disponibili: {campi}"
            )
        if "ragione_sociale" not in campi:
            raise ValueError(
                f"Colonna 'ragione_sociale' non trovata. "
                f"Colonne disponibili: {campi}"
            )

        has_id = "id" in campi
        for i, row in enumerate(reader, 1):
            vat = row[col_vat].strip()
            rs  = row["ragione_sociale"].strip()
            if vat and rs:
                righe.append({
                    "id":      row["id"].strip() if has_id else str(i),
                    "vat":     vat,
                    "rs":      rs,
                    "rs_norm": normalizza_ragione_sociale(rs),
                })
    return righe

# ─── Resume: leggi ID già processati ──────────────────────────────────────────

def leggi_id_completati(output_csv: str) -> set[str]:
    """
    Legge il CSV di output esistente e restituisce gli id già presenti
    (qualsiasi riga scritta, con o senza contenuto).
    """
    path = Path(output_csv)
    if not path.exists():
        return set()

    completati: set[str] = set()
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None or "id" not in reader.fieldnames:
                return set()
            for row in reader:
                row_id = row.get("id", "").strip()
                if row_id:
                    completati.add(row_id)
    except Exception:
        return set()

    return completati

# ─── Scrittura incrementale ────────────────────────────────────────────────────

def apri_output(output_csv: str, id_completati: set[str]):
    """
    Apre il file di output in append (resume) o lo crea da zero.
    Restituisce (file_handle, csv_writer).
    """
    path = Path(output_csv)
    if path.exists() and id_completati:
        f = open(path, "a", newline="", encoding="utf-8-sig")
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES_OUT, quoting=csv.QUOTE_ALL)
        print(f"📎 Riprendendo output esistente: {output_csv}")
    else:
        f = open(path, "w", newline="", encoding="utf-8-sig")
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES_OUT, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        f.flush()

    return f, writer


def scrivi_e_flush(writer, f, row: dict):
    """Scrive una singola riga e forza il flush su disco immediatamente."""
    writer.writerow(row)
    f.flush()

# ─── Formattazione contenuto output ───────────────────────────────────────────

def costruisci_contenuto(dati: dict[str, str]) -> str:
    """
    Concatena tutti i valori estratti separati da ' | '.
    Restituisce una stringa semplice — la quotatura CSV è gestita dal DictWriter.
    """
    parti = []
    for campo in CAMPI:
        valore = dati.get(campo, "").strip()
        if valore and valore != "N/D":
            # Collassa newline interni
            valore = re.sub(r"[\r\n\t]+", " ", valore)
            valore = re.sub(r" {2,}", " ", valore)
            parti.append(valore)

    return " | ".join(parti) if parti else ""

# ─── Cache P.IVA → URL Atoka ──────────────────────────────────────────────────

def carica_cache() -> dict[str, str]:
    """Carica la cache da disco. Restituisce dict vuoto se non esiste."""
    path = Path(CACHE_FILE)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def salva_cache(cache: dict[str, str]):
    """Salva la cache su disco (sovrascrive)."""
    Path(CACHE_FILE).write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


# ─── Google Search ─────────────────────────────────────────────────────────────

def cerca_link_google(page, rs_norm: str) -> list[str]:
    """
    Cerca su Google:  site:atoka.io RAGIONE SOCIALE NORMALIZZATA
    (senza virgolette attorno alla ragione sociale)
    Restituisce fino a MAX_GOOGLE_LINKS link atoka.io trovati nei risultati organici.
    """
    from urllib.parse import urlparse, parse_qs

    rs_enc = quote(rs_norm)
    url = GOOGLE_SEARCH_URL.format(rs_enc=rs_enc)
    page.goto(url, wait_until="domcontentloaded", timeout=30_000)

    # Accetta cookie Google se compaiono
    try:
        for testo_btn in ["Accetta tutto", "Accept all", "Accetto", "I agree"]:
            btn = page.locator("button", has_text=testo_btn).first
            if btn.is_visible(timeout=2000):
                btn.click()
                page.wait_for_load_state("domcontentloaded")
                break
    except Exception:
        pass

    # Attendi che i risultati si carichino
    try:
        page.wait_for_selector("div#search", timeout=10_000)
    except Exception:
        pass

    # Pausa breve per rendering completo
    page.wait_for_timeout(2000)

    # Controlla CAPTCHA / blocco
    try:
        body_text = page.locator("body").inner_text(timeout=5000)
        if any(kw in body_text.lower() for kw in ["captcha", "unusual traffic", "not a robot", "traffico insolito"]):
            print("  ⚠  Google CAPTCHA rilevato! Attendo 60s...")
            page.wait_for_timeout(60_000)
            # Riprova
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(3000)
    except Exception:
        pass

    links: list[str] = []
    seen: set[str] = set()

    # Selettori multipli per catturare i link in vari layout Google
    selectors = [
        "div#search a[href*='atoka.io']",
        "div#rso a[href*='atoka.io']",
        "div.g a[href*='atoka.io']",
        "a[href*='atoka.io/public']",
        "a[href*='atoka.io']",
    ]
    for sel in selectors:
        for el in page.locator(sel).all():
            if len(links) >= MAX_GOOGLE_LINKS:
                break
            try:
                href = el.get_attribute("href", timeout=3000)
                if not href or "atoka.io" not in href:
                    continue
                # Google a volte wrappa i link in /url?q=...
                if href.startswith("/url?"):
                    qs = parse_qs(urlparse(href).query)
                    href = qs.get("q", [href])[0]
                # Ignora link a pagine non-azienda (es. homepage, blog)
                if "/public/" not in href and "/azienda/" not in href:
                    continue
                if href not in seen:
                    seen.add(href)
                    links.append(href)
            except Exception:
                continue
        if len(links) >= MAX_GOOGLE_LINKS:
            break

    # Debug: se nessun link trovato, logga un pezzo della pagina
    if not links:
        try:
            snippet = page.locator("body").inner_text(timeout=3000)[:500]
            print(f"  🔍 Debug pagina Google (primi 500 char): {snippet[:200]}...")
        except Exception:
            pass

    return links

# ─── Estrazione dati dalla pagina atoka ───────────────────────────────────────

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


def estrai_piva_da_pagina(page) -> str | None:
    """
    Estrae la P.IVA dal div .wrapper della pagina Atoka.
    Cerca il testo 'P.IVA:' e restituisce il valore numerico trovato.
    """
    try:
        # Cerca nel div wrapper il campo P.IVA
        piva_el = page.locator("text=P.IVA:").first
        parent = piva_el.locator("xpath=..")
        testo = parent.inner_text(timeout=3000)
        # Estrai solo le cifre dopo "P.IVA:"
        match = re.search(r"P\.?IVA:?\s*(\d{11})", testo)
        if match:
            return match.group(1)
    except Exception:
        pass

    # Fallback: cerca nel body intero
    try:
        body = page.locator("body").inner_text(timeout=5000)
        match = re.search(r"P\.?IVA:?\s*(\d{11})", body)
        if match:
            return match.group(1)
    except Exception:
        pass

    return None


def scrapa_pagina_atoka(page, url: str) -> dict[str, str]:
    dati = {campo: "N/D" for campo in CAMPI}

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_load_state("networkidle", timeout=15_000)
    except PlaywrightTimeoutError:
        print(f"  ⚠  Timeout caricando {url}")
        return dati
    except Exception as e:
        print(f"  ⚠  Errore navigando {url}: {e}")
        return dati

    for campo in ["Descrizione", "Area di Business", "altri Nomi", "Categoria di Impresa", "Aziende simili"]:
        dati[campo] = estrai_testo_sezione(page, campo)

    dati["Ricavi"] = estrai_ricavi(page)

    return dati

# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Scraper Atoka.io via Google Search")
    parser.add_argument("input_csv",  help="CSV di input (colonne: id, vat_number, ragione_sociale)")
    parser.add_argument("output_csv", help="CSV di output con una riga per entry")
    parser.add_argument(
        "--colonna", default="vat_number",
        help="Nome colonna partita IVA (default: vat_number)"
    )
    parser.add_argument(
        "--visible", action="store_true",
        help="Mostra il browser (utile per debug)"
    )
    args = parser.parse_args()

    print(f"📂 Lettura da: {args.input_csv}  (colonna VAT: {args.colonna})")
    try:
        righe = leggi_input(args.input_csv, args.colonna)
    except Exception as e:
        print(f"❌ Errore lettura CSV: {e}")
        sys.exit(1)

    print(f"✅ Trovate {len(righe)} righe valide\n")
    print("Esempi normalizzazione ragione sociale:")
    for r in righe[:5]:
        print(f"   {r['rs']!r:40s}  →  {r['rs_norm']!r}")
    if len(righe) > 5:
        print(f"   ... (altri {len(righe)-5})")
    print()

    # ── Resume ──
    id_completati = leggi_id_completati(args.output_csv)
    righe_da_fare = [r for r in righe if r["id"] not in id_completati]

    if id_completati:
        print(f"⏩ Già completate: {len(id_completati)} — riprendo dalle restanti {len(righe_da_fare)}\n")
    else:
        print(f"🆕 Nessun output precedente — parto dall'inizio\n")

    if not righe_da_fare:
        print("🎉 Tutte le voci sono già state elaborate. Niente da fare.")
        sys.exit(0)

    out_file, writer = apri_output(args.output_csv, id_completati)

    # ── Cache P.IVA → URL ──
    cache = carica_cache()
    print(f"📦 Cache: {len(cache)} P.IVA già note\n")

    try:
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

            for idx, riga in enumerate(righe_da_fare, 1):
                row_id  = riga["id"]
                piva    = riga["vat"]
                rs_orig = riga["rs"]
                rs_norm = riga["rs_norm"]

                print(f"[{idx}/{len(righe_da_fare)}] id={row_id}  VAT={piva}")

                contenuto = ""
                source_url = ""

                # ── 1. Controlla cache ──
                if piva in cache:
                    cached_url = cache[piva]
                    print(f"  📦 Cache hit! URL: {cached_url}")
                    print(f"  📄 Estrazione dati da cache...")

                    try:
                        page.goto(cached_url, wait_until="domcontentloaded", timeout=30_000)
                        page.wait_for_load_state("networkidle", timeout=15_000)

                        dati = {campo: "N/D" for campo in CAMPI}
                        for campo in ["Descrizione", "Area di Business", "altri Nomi", "Categoria di Impresa", "Aziende simili"]:
                            dati[campo] = estrai_testo_sezione(page, campo)
                        dati["Ricavi"] = estrai_ricavi(page)

                        for campo in CAMPI:
                            preview = dati[campo][:80] + ("..." if len(dati[campo]) > 80 else "")
                            print(f"     {campo}: {preview}")

                        contenuto = costruisci_contenuto(dati)
                        source_url = cached_url
                    except Exception as e:
                        print(f"  ⚠  Errore accesso cache URL: {e}, provo Google...")
                        contenuto = ""

                # ── 2. Se cache miss o errore, cerca su Google ──
                if not contenuto:
                    print(f"  🏢 Query Google: site:atoka.io {rs_norm}")

                    try:
                        links = cerca_link_google(page, rs_norm)
                    except Exception as e:
                        print(f"  ❌ Errore ricerca: {e}")
                        links = []

                    if not links:
                        print(f"  ⚠  Nessun risultato atoka.io trovato")
                    else:
                        print(f"  🔗 Trovati {len(links)} link, verifico P.IVA...")
                        for li, link in enumerate(links, 1):
                            print(f"  [{li}/{len(links)}] {link}")

                            try:
                                page.goto(link, wait_until="domcontentloaded", timeout=30_000)
                                page.wait_for_load_state("networkidle", timeout=15_000)
                            except Exception as e:
                                print(f"    ⚠  Errore caricamento: {e}")
                                continue

                            piva_pagina = estrai_piva_da_pagina(page)
                            print(f"    P.IVA pagina: {piva_pagina or 'non trovata'}")

                            # Salva in cache qualunque P.IVA trovata
                            if piva_pagina and piva_pagina not in cache:
                                cache[piva_pagina] = link
                                salva_cache(cache)

                            if piva_pagina and piva_pagina == piva:
                                print(f"    ✅ P.IVA corrisponde! Estrazione dati...")
                                dati = {campo: "N/D" for campo in CAMPI}
                                for campo in ["Descrizione", "Area di Business", "altri Nomi", "Categoria di Impresa", "Aziende simili"]:
                                    dati[campo] = estrai_testo_sezione(page, campo)
                                dati["Ricavi"] = estrai_ricavi(page)

                                for campo in CAMPI:
                                    preview = dati[campo][:80] + ("..." if len(dati[campo]) > 80 else "")
                                    print(f"       {campo}: {preview}")

                                contenuto = costruisci_contenuto(dati)
                                source_url = link
                                break
                            else:
                                print(f"    ❌ P.IVA non corrisponde, provo il prossimo...")
                        else:
                            print(f"  ⚠  Nessun link con P.IVA corrispondente")

                row_out = {
                    "id":                           row_id,
                    "vat_number":                   piva,
                    "ragione_sociale":              rs_orig,
                    "ragione_sociale_normalizzata": rs_norm,
                    "contenuto":                    contenuto,
                    "source_url":                   source_url,
                }
                scrivi_e_flush(writer, out_file, row_out)
                print(f"  💾 Scritto  →  {contenuto[:120]}{'...' if len(contenuto)>120 else ''}\n")

                if idx < len(righe_da_fare):
                    # Niente delay se era cache hit
                    if piva not in cache or not source_url or source_url != cache.get(piva):
                        delay = random.uniform(DELAY_MIN, DELAY_MAX)
                        print(f"  ⏳ Attesa {delay:.0f}s...\n")
                        time.sleep(delay)

            context.close()
            browser.close()

    finally:
        out_file.close()

    print(f"✅ Completato. Output in: {args.output_csv}  ({len(righe_da_fare)} nuove righe)")


if __name__ == "__main__":
    main()