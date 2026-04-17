import requests
from bs4 import BeautifulSoup
import sys
import time
import csv
import json
import os
import logging
import urllib3
from datetime import datetime, timedelta

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- Config ---
MAX_CONSECUTIVE_ERRORS  = 5
REQUEST_TIMEOUT         = 10
DELAY_BETWEEN_CALLS     = 1

# Retry su 429: primo retry dopo 60s, poi raddoppia ogni volta
RETRY_429_BASE_DELAY    = 60       # secondi
RETRY_429_MAX_ATTEMPTS  = 5        # tentativi massimi prima di rinunciare sul record

FIELDS = ["id", "nome", "link", "stato", "ragione_sociale", "piva",
          "citta", "indirizzo", "provincia", "regione", "ateco_primario", "dipendenti"]


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def setup_logger(input_file: str) -> logging.Logger:
    base      = os.path.splitext(input_file)[0]
    log_path  = base + "_errors.log"

    logger = logging.getLogger("scraper")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    # File handler – tutto da WARNING in su
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.WARNING)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    ))

    # Console handler – INFO e superiori
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(message)s"))

    logger.addHandler(fh)
    logger.addHandler(ch)

    logger.info(f"Log errori su: {log_path}")
    return logger


# ---------------------------------------------------------------------------
# Checkpoint
# ---------------------------------------------------------------------------

def checkpoint_path(input_file: str) -> str:
    return os.path.splitext(input_file)[0] + "_checkpoint.json"

def load_checkpoint(ckpt_path: str) -> dict:
    if os.path.exists(ckpt_path):
        with open(ckpt_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_completed_id": None, "errors": []}

def save_checkpoint(ckpt_path: str, data: dict):
    with open(ckpt_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Progress / ETA
# ---------------------------------------------------------------------------

class ProgressTracker:
    def __init__(self, total: int):
        self.total      = total
        self.done       = 0
        self.start_time = time.monotonic()

    def tick(self):
        self.done += 1

    def eta_str(self) -> str:
        if self.done == 0:
            return "N/A"
        elapsed   = time.monotonic() - self.start_time
        avg       = elapsed / self.done
        remaining = avg * (self.total - self.done)
        eta_dt    = datetime.now() + timedelta(seconds=remaining)
        return (f"{int(remaining // 60)}m {int(remaining % 60)}s"
                f"  (finisce ~{eta_dt.strftime('%H:%M:%S')})")

    def bar(self, width: int = 30) -> str:
        frac   = self.done / self.total if self.total else 0
        filled = int(width * frac)
        return f"[{'█' * filled}{'░' * (width - filled)}]"

    def print_progress(self, record_id, record_nome):
        pct = 100 * self.done / self.total if self.total else 0
        print(
            f"\r{self.bar()} {self.done}/{self.total} ({pct:.1f}%) "
            f"| ETA {self.eta_str()} "
            f"| [{record_id}] {record_nome[:40]}",
            end="", flush=True
        )


# ---------------------------------------------------------------------------
# Scraping con retry 429
# ---------------------------------------------------------------------------

def extract_table_value(soup, label: str) -> str:
    for row in soup.select("table.azienda-table-det tr"):
        th = row.find("th")
        td = row.find("td")
        if th and td and label.lower() in th.get_text(strip=True).lower():
            if td.find("button"):
                return "N/D (locked)"
            return td.get_text(separator=" ", strip=True)
    return ""


def scrape_detail(url: str, session: requests.Session, logger: logging.Logger) -> dict:
    """GET con retry esponenziale su HTTP 429. Primo retry dopo RETRY_429_BASE_DELAY secondi."""
    delay = RETRY_429_BASE_DELAY

    for attempt in range(1, RETRY_429_MAX_ATTEMPTS + 1):
        response = session.get(url, timeout=REQUEST_TIMEOUT, verify=False)

        if response.status_code == 429:
            if attempt == RETRY_429_MAX_ATTEMPTS:
                logger.error(
                    f"429 su {url} – esauriti {RETRY_429_MAX_ATTEMPTS} tentativi"
                )
                response.raise_for_status()   # solleva HTTPError

            # calcola il delay: usa Retry-After se presente, altrimenti esponenziale
            retry_after = response.headers.get("Retry-After")
            wait = int(retry_after) if retry_after and retry_after.isdigit() else delay

            logger.warning(
                f"429 su {url} | tentativo {attempt}/{RETRY_429_MAX_ATTEMPTS} "
                f"– attendo {wait}s prima di riprovare"
            )
            print(f"\n  ⏳ 429 ricevuto – retry {attempt}/{RETRY_429_MAX_ATTEMPTS} "
                  f"tra {wait}s ...", flush=True)

            time.sleep(wait)
            delay *= 2   # backoff esponenziale per il prossimo eventuale retry
            continue

        response.raise_for_status()
        break

    soup = BeautifulSoup(response.text, "html.parser")
    return {
        "stato":           extract_table_value(soup, "Stato"),
        "ragione_sociale": extract_table_value(soup, "Ragione sociale"),
        "piva":            extract_table_value(soup, "P.IVA"),
        "citta":           extract_table_value(soup, "Città"),
        "indirizzo":       extract_table_value(soup, "Indirizzo"),
        "provincia":       extract_table_value(soup, "Provincia"),
        "regione":         extract_table_value(soup, "Regione"),
        "ateco_primario":  extract_table_value(soup, "Codice ATECO Primario"),
        "dipendenti":      extract_table_value(soup, "Dipendenti"),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(input_csv: str, output_csv: str):
    logger    = setup_logger(input_csv)
    ckpt_path = checkpoint_path(input_csv)
    checkpoint = load_checkpoint(ckpt_path)
    last_completed_id = checkpoint.get("last_completed_id")
    errors_log        = checkpoint.get("errors", [])

    with open(input_csv, "r", encoding="utf-8") as f:
        records = list(csv.DictReader(f))

    if not records:
        print("Input CSV vuoto.")
        return

    # Calcola quanti record rimangono da elaborare per l'ETA
    remaining_records = records
    if last_completed_id is not None:
        ids = [r.get("id", "") for r in records]
        try:
            idx = ids.index(str(last_completed_id))
            remaining_records = records[idx + 1:]
        except ValueError:
            pass

    total_remaining = len(remaining_records)
    print(f"Totale record nel CSV : {len(records)}")
    print(f"Da elaborare          : {total_remaining}")
    if last_completed_id:
        print(f"Checkpoint            : ultimo ID completato = {last_completed_id}")

    progress = ProgressTracker(total_remaining)

    # Output CSV
    file_exists = os.path.exists(output_csv)
    out_file    = open(output_csv, "a", encoding="utf-8", newline="")
    writer      = csv.writer(out_file, quoting=csv.QUOTE_NONNUMERIC)
    if not file_exists:
        writer.writerow(FIELDS)
        out_file.flush()

    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    })

    skip               = last_completed_id is not None
    consecutive_errors = 0
    processed          = 0
    skipped_count      = 0

    for record in records:
        record_id   = record.get("id", "")
        record_nome = record.get("nome", "")
        record_link = record.get("link", "")

        if skip:
            if str(record_id) == str(last_completed_id):
                skip = False
            else:
                skipped_count += 1
            continue

        progress.print_progress(record_id, record_nome)

        try:
            detail = scrape_detail(record_link, session, logger)
            consecutive_errors = 0

            writer.writerow([
                record_id, record_nome, record_link,
                detail["stato"], detail["ragione_sociale"], detail["piva"],
                detail["citta"], detail["indirizzo"], detail["provincia"],
                detail["regione"], detail["ateco_primario"], detail["dipendenti"],
            ])
            out_file.flush()

            checkpoint["last_completed_id"] = record_id
            checkpoint["errors"]            = errors_log
            save_checkpoint(ckpt_path, checkpoint)

            progress.tick()
            processed += 1

        except Exception as e:
            consecutive_errors += 1
            error_entry = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "id":        record_id,
                "nome":      record_nome,
                "url":       record_link,
                "error":     str(e),
            }
            errors_log.append(error_entry)
            checkpoint["errors"] = errors_log
            save_checkpoint(ckpt_path, checkpoint)

            logger.error(
                f"ID={record_id} | {record_nome} | {record_link} | {e}"
            )
            print(
                f"\n  ❌ ERRORE [{consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}]: {e}",
                flush=True
            )

            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                print(
                    f"\n!!! Troppi errori consecutivi ({MAX_CONSECUTIVE_ERRORS}). "
                    f"Interruzione. Ultimo ID OK: {checkpoint.get('last_completed_id')}."
                )
                logger.critical(
                    f"Interruzione per {MAX_CONSECUTIVE_ERRORS} errori consecutivi. "
                    f"Ultimo ID OK: {checkpoint.get('last_completed_id')}"
                )
                break

        time.sleep(DELAY_BETWEEN_CALLS)

    out_file.close()
    print()  # newline dopo la barra di progresso

    elapsed = time.monotonic() - progress.start_time
    print(f"\n{'─' * 60}")
    print(f"  Completato in        : {int(elapsed // 60)}m {int(elapsed % 60)}s")
    print(f"  Processati           : {processed}")
    print(f"  Saltati (checkpoint) : {skipped_count}")
    print(f"  Errori registrati    : {len(errors_log)}")
    print(f"  Output CSV           : {output_csv}")
    print(f"  Checkpoint           : {ckpt_path}")
    print(f"{'─' * 60}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python scraper_step_2.py <input.csv> <output.csv>")
        print("Example: python scraper_step_2.py aziende.csv dettagli.csv")
        sys.exit(1)

    main(sys.argv[1], sys.argv[2])