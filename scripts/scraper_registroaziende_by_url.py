import requests
from bs4 import BeautifulSoup
import csv
import time
import argparse
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )
}

DELAY = 0.5

FIELD_MAP = {
    "P.IVA":                "partita_iva",
    "Ragione sociale":      "ragione_sociale",
    "Codice ATECO Primario":"codice_ateco",
    "Regione":              "regione",
    "Provincia":            "provincia",
    "Città":                "citta",
    "Indirizzo":            "indirizzo",
    "Dipendenti":           "dipendenti",
}

EMPTY_ROW = {v: "" for v in FIELD_MAP.values()}


def scrape_azienda(url: str) -> dict:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15, verify=False)
        resp.raise_for_status()
    except Exception as e:
        print(f"  ERRORE fetch {url}: {e}")
        return EMPTY_ROW.copy()

    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table", class_="azienda-table-det")
    if not table:
        print(f"  WARN: tabella non trovata su {url}")
        return EMPTY_ROW.copy()

    result = EMPTY_ROW.copy()

    for row in table.find_all("tr"):
        th = row.find("th")
        td = row.find("td")
        if not th or not td:
            continue

        label = th.get_text(strip=True)
        if label not in FIELD_MAP:
            continue

        # Salta celle che contengono solo il pulsante "Accedi"
        if td.find("button", class_="btn-sblocca"):
            continue

        value = td.get_text(separator=" ", strip=True)
        # Pulizia spazi multipli
        value = " ".join(value.split())

        # Per il codice ATECO tieni solo la parte prima dei due punti (es. "70.1")
        if FIELD_MAP[label] == "codice_ateco" and ":" in value:
            value = value.split(":")[0].strip()

        result[FIELD_MAP[label]] = value

    return result


def parse_args():
    parser = argparse.ArgumentParser(
        description="Scraper registroaziende.it — legge URL da file di testo, salva CSV."
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="File di testo con un URL per riga"
    )
    parser.add_argument(
        "--output", "-o",
        default="registro_aziende.csv",
        help="Path del CSV di output (default: registro_aziende.csv)"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    with open(args.input, encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    print(f"Elaboro {len(urls)} aziende ...\n")

    fieldnames = ["id", "partita_iva", "ragione_sociale", "codice_ateco",
                  "regione", "provincia", "citta", "indirizzo", "dipendenti"]

    with open(args.output, "w", newline="", encoding="utf-8") as out_f:
        writer = csv.DictWriter(out_f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()

        for idx, url in enumerate(urls, start=1):
            print(f"[{idx}/{len(urls)}] {url}")
            data = scrape_azienda(url)
            writer.writerow({"id": idx, **data})
            out_f.flush()          # scrive subito su disco, utile per liste lunghe
            time.sleep(DELAY)

    print(f"\nCSV salvato in: {args.output}")


if __name__ == "__main__":
    main()