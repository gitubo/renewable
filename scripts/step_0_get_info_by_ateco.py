import requests
from bs4 import BeautifulSoup
import sys
import time
import csv
import os
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def scrape_aziende(codice_ateco: str, min_page: int, max_page: int, output_file: str = "aziende.csv"):
    base_url    = "https://registroaziende.it/ateco/{ateco}?page={page}&ordering=-ultimo_fatturato"
    base_domain = "https://registroaziende.it"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    # Apri in append, scrivi header solo se il file non esiste ancora
    file_exists = os.path.exists(output_file)
    out_file    = open(output_file, "a", encoding="utf-8", newline="")
    writer      = csv.writer(out_file, quoting=csv.QUOTE_NONNUMERIC)
    if not file_exists:
        writer.writerow(["id", "nome", "link"])
        out_file.flush()

    # Determina il prossimo ID leggendo l'ultima riga del file
    record_id = 1
    if file_exists:
        with open(output_file, "r", encoding="utf-8") as f:
            rows = list(csv.reader(f))
            if len(rows) > 1:
                try:
                    record_id = int(rows[-1][0]) + 1
                    print(f"File esistente: riprendo da ID {record_id}")
                except ValueError:
                    pass

    total_written = 0

    try:
        for page in range(min_page, max_page + 1):
            url = base_url.format(ateco=codice_ateco, page=page)
            print(f"[Page {page}/{max_page}] Fetching: {url}")

            try:
                response = requests.get(url, headers=headers, timeout=10, verify=False)
                response.raise_for_status()
            except requests.RequestException as e:
                print(f"  ERRORE: {e}")
                break

            soup  = BeautifulSoup(response.text, "html.parser")
            table = soup.find("table", {"id": "t2"})

            if not table:
                print(f"  WARNING: Tabella non trovata a pagina {page}. Stop.")
                break

            rows = table.find("tbody").find_all("tr")

            if not rows:
                print(f"  WARNING: Nessuna riga a pagina {page}. Stop.")
                break

            page_written = 0
            for row in rows:
                cols = row.find_all("td")
                if len(cols) < 4:
                    continue

                nome_tag = cols[0].find("b")
                nome     = nome_tag.get_text(strip=True) if nome_tag else cols[0].get_text(strip=True)

                link_tag = cols[-1].find("a", class_="table-link")
                link     = (base_domain + link_tag["href"]) if link_tag and link_tag.get("href") else "N/A"

                writer.writerow([record_id, nome, link])
                out_file.flush()
                record_id    += 1
                page_written += 1
                total_written += 1

            print(f"  Scritti {page_written} record (totale sessione: {total_written})")
            time.sleep(0.5)

    finally:
        out_file.close()

    print(f"\nDone. Record scritti in questa sessione: {total_written} -> '{output_file}'")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python scraper.py <CODICE_ATECO> <MIN_PAGE> <MAX_PAGE> [output_file]")
        print("Example: python scraper.py 35.11 5 15 output.csv")
        sys.exit(1)

    codice_ateco = sys.argv[1]
    min_page     = int(sys.argv[2])
    max_page     = int(sys.argv[3])
    output_file  = sys.argv[4] if len(sys.argv) > 4 else "aziende.csv"

    if min_page > max_page:
        print(f"ERRORE: MIN_PAGE ({min_page}) > MAX_PAGE ({max_page})")
        sys.exit(1)

    scrape_aziende(codice_ateco, min_page, max_page, output_file)