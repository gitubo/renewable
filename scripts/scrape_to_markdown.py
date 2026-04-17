"""
Company Website Scraper to Markdown - Scrapa siti aziendali e genera Markdown ottimizzato per LLM.

Usa requests + BeautifulSoup per evitare problemi con cookie consent.
Estrae contenuto da homepage, about, contact, history pages.
Cerca automaticamente la P.IVA nel sito.

Utilizzo:
    # Singolo URL
    python scrape_to_markdown.py https://example.com
    python scrape_to_markdown.py https://example.com --vat 12345678901
    
    # Batch da CSV
    python scrape_to_markdown.py --csv input.csv
    
CSV format: vat_number (optional), source_url
Output: file .md nella directory markdown_output/
"""

import csv
import re
import argparse
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
import urllib3

# Disabilita warning SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Pattern per trovare pagine rilevanti (italiano + inglese)
PAGE_PATTERNS = {
    "about": [
        r"/about", r"/chi-siamo", r"/azienda", r"/company", r"/about-us",
        r"/chi_siamo", r"/about_us", r"/la-nostra-azienda", r"/our-company",
        r"/societa", r"/società"
    ],
    "history": [
        r"/storia", r"/history", r"/our-story", r"/la-nostra-storia"
    ],
    "contact": [
        r"/contatti", r"/contact", r"/contacts", r"/contattaci", r"/contact-us"
    ],
}

# Pattern per social links
SOCIAL_PATTERNS = {
    "linkedin": r"linkedin\.com/company/[^/\s\"']+",
    "facebook": r"facebook\.com/[^/\s\"']+",
    "instagram": r"instagram\.com/[^/\s\"']+",
}

# Pattern per P.IVA italiana (11 cifre)
VAT_PATTERN = re.compile(r"(?:P\.?\s*I\.?(?:\s*V\.?\s*A\.?)?|Partita\s+[Ii]va|VAT)\s*[:\s]?\s*(\d{11})", re.IGNORECASE)

# Headers per requests
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
}


def extract_vat_from_text(text: str) -> str | None:
    """Estrae P.IVA dal testo."""
    match = VAT_PATTERN.search(text)
    return match.group(1) if match else None


def clean_text(text: str) -> str:
    """Pulisce il testo: rimuove newline multipli, spazi extra."""
    if not text:
        return ""
    text = " ".join(text.split())
    return text.strip()


def fetch_page(url: str, timeout: int = 15) -> tuple[str, str]:
    """
    Scarica una pagina web.
    
    Returns:
        (html_content, text_content)
    """
    try:
        response = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True, verify=False)
        response.raise_for_status()
        response.encoding = response.apparent_encoding
        return response.text, response.text
    except Exception as e:
        print(f"  Errore download: {e}")
        return "", ""


def extract_text_from_html(html: str) -> str:
    """Estrae testo pulito da HTML usando BeautifulSoup."""
    if not html:
        return ""
    
    try:
        soup = BeautifulSoup(html, "html.parser")
        
        # Rimuovi script, style, e elementi non necessari
        for tag in soup(["script", "style", "noscript", "iframe"]):
            tag.decompose()
        
        # Estrai testo
        text = soup.get_text(separator=" ", strip=True)
        return clean_text(text)
    except Exception:
        return ""


def find_page_links(soup: BeautifulSoup, base_url: str, patterns: list[str]) -> list[str]:
    """Trova link che matchano i pattern forniti."""
    found = []
    
    try:
        base_domain = urlparse(base_url).netloc
        
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            if not href:
                continue
            
            # Normalizza URL
            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)
            
            # Solo link interni
            if parsed.netloc != base_domain:
                continue
            
            path_lower = parsed.path.lower()
            text_lower = link.get_text(strip=True).lower()
            
            # Match pattern
            for pattern in patterns:
                pattern_clean = pattern.strip('/')
                if (re.search(pattern, path_lower) or 
                    pattern_clean in path_lower or
                    pattern_clean in text_lower):
                    if full_url not in found:
                        found.append(full_url)
                        break
    except Exception:
        pass
    
    return found


def find_social_links(html: str) -> dict:
    """Trova link social nella pagina."""
    social = {}
    
    for platform, pattern in SOCIAL_PATTERNS.items():
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            social[platform] = f"https://{match.group(0)}"
    
    return social


def url_to_filename(url: str) -> str:
    """Converte URL in nome file valido."""
    parsed = urlparse(url)
    domain = parsed.netloc.replace("www.", "").replace(".", "_")
    return f"{domain}.md"


def scrape_to_markdown(url: str, expected_vat: str | None = None) -> tuple[str, dict]:
    """
    Scrapa il sito e genera Markdown.
    
    Returns:
        (markdown_content, metadata)
    """
    
    metadata = {
        "url": url,
        "scraped_at": datetime.now().isoformat(),
        "vat_number": "",
        "error": None
    }
    
    lines = []
    
    # Header
    lines.append(f"# Company Website Analysis")
    lines.append(f"\n**URL**: {url}")
    lines.append(f"**Scraped**: {metadata['scraped_at']}")
    
    print(f"Caricamento homepage: {url}")
    
    # Scarica homepage
    html, _ = fetch_page(url)
    if not html:
        metadata["error"] = "Failed to load homepage"
        lines.append(f"**Status**: Error loading page")
        return "\n".join(lines), metadata
    
    soup = BeautifulSoup(html, "html.parser")
    homepage_text = extract_text_from_html(html)
    
    # Cerca P.IVA
    found_vat = extract_vat_from_text(homepage_text)
    
    if expected_vat:
        if found_vat:
            if found_vat != expected_vat:
                metadata["error"] = f"VAT mismatch: expected {expected_vat}, found {found_vat}"
                lines.append(f"**VAT Number**: Mismatch (expected: {expected_vat}, found: {found_vat})")
                print(f"P.IVA mismatch!")
                return "\n".join(lines), metadata
            else:
                metadata["vat_number"] = expected_vat
                lines.append(f"**VAT Number**: {expected_vat}")
                print(f"P.IVA verificata: {expected_vat}")
        else:
            metadata["vat_number"] = expected_vat
            lines.append(f"**VAT Number**: {expected_vat} (not found on site)")
            print(f"P.IVA non trovata sul sito")
    else:
        if found_vat:
            metadata["vat_number"] = found_vat
            lines.append(f"**VAT Number**: {found_vat}")
            print(f"P.IVA trovata: {found_vat}")
        else:
            lines.append(f"**VAT Number**: Not found")
            print("P.IVA non trovata")
    
    lines.append("")
    
    # Social links
    social = find_social_links(html)
    if social:
        lines.append("**Social Media**:")
        for platform, link in social.items():
            lines.append(f"- {platform.capitalize()}: {link}")
        lines.append("")
        print(f"Social trovati: {', '.join(social.keys())}")
    
    lines.append("---")
    lines.append("")
    
    # Homepage content
    lines.append("## Homepage Content")
    lines.append("")
    lines.append(homepage_text)
    lines.append("")
    
    # Cerca pagine specifiche
    for page_type, patterns in PAGE_PATTERNS.items():
        print(f"Cerco pagina: {page_type}...")
        links = find_page_links(soup, url, patterns)
        
        if links:
            target_url = links[0]
            print(f"  Trovata: {target_url}")
            
            time.sleep(1)  # Pausa tra richieste
            
            page_html, _ = fetch_page(target_url)
            if page_html:
                page_text = extract_text_from_html(page_html)
                
                # Cerca P.IVA anche qui se non ancora trovata
                if not metadata["vat_number"]:
                    page_vat = extract_vat_from_text(page_text)
                    if page_vat:
                        if expected_vat and page_vat != expected_vat:
                            print(f"  P.IVA mismatch in {page_type}")
                        else:
                            metadata["vat_number"] = page_vat
                            print(f"  P.IVA trovata in {page_type}: {page_vat}")
                
                lines.append(f"## {page_type.capitalize()} Page")
                lines.append("")
                lines.append(f"**URL**: {target_url}")
                lines.append("")
                lines.append(page_text)
                lines.append("")
        else:
            print(f"  Pagina {page_type} non trovata")
    
    return "\n".join(lines), metadata


def main():
    parser = argparse.ArgumentParser(description="Scrape company website(s) to Markdown")
    parser.add_argument("url", nargs="?", help="Homepage URL (for single site)")
    parser.add_argument("--vat", help="Expected VAT number (for single site)")
    parser.add_argument("--csv", help="CSV file with vat_number (optional) and source_url columns")
    args = parser.parse_args()
    
    # Crea directory output
    output_dir = Path("markdown_output")
    output_dir.mkdir(exist_ok=True)
    
    # Batch mode: CSV input
    if args.csv:
        print(f"\nModalita batch: {args.csv}\n")
        
        # Leggi CSV
        with open(args.csv, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        
        if not rows:
            print("CSV vuoto")
            sys.exit(1)
        
        print(f"Trovate {len(rows)} righe\n")
        
        success_count = 0
        
        for idx, row in enumerate(rows, 1):
            url = row.get("source_url", "").strip()
            vat = row.get("vat_number", "").strip() or None
            
            if not url:
                print(f"[{idx}/{len(rows)}] Riga senza source_url, salto\n")
                continue
            
            print(f"[{idx}/{len(rows)}] Scraping: {url}")
            if vat:
                print(f"            P.IVA attesa: {vat}")
            
            try:
                markdown, metadata = scrape_to_markdown(url, vat)
                
                # Salva file
                filename = url_to_filename(url)
                output_path = output_dir / filename
                
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(markdown)
                
                if metadata.get("error"):
                    print(f"            Completato con warning: {metadata['error']}")
                else:
                    print(f"            Salvato: {filename}")
                    success_count += 1
                
                print()
                
            except Exception as e:
                print(f"            Errore: {e}\n")
        
        print(f"\nConversione completata!")
        print(f"File salvati in: {output_dir.absolute()}")
        print(f"Successi: {success_count}/{len(rows)}")
        
    # Single mode: URL from command line
    elif args.url:
        print(f"\nAvvio scraping: {args.url}")
        if args.vat:
            print(f"P.IVA attesa: {args.vat}\n")
        
        try:
            markdown, metadata = scrape_to_markdown(args.url, args.vat)
            
            # Salva file
            filename = url_to_filename(args.url)
            output_path = output_dir / filename
            
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(markdown)
            
            print(f"\nMarkdown salvato: {output_path}")
            print(f"P.IVA: {metadata['vat_number'] or 'non trovata'}")
            
            if metadata.get("error"):
                print(f"Warning: {metadata['error']}")
                
        except Exception as e:
            print(f"\nErrore: {e}")
            sys.exit(1)
    
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
