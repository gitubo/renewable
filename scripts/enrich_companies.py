#!/usr/bin/env python3
"""
enrich_companies.py
-------------------
Parte da un CSV con dati parziali (tipicamente esportato dal DB) e arricchisce
con dati finanziari da fatturatoitalia.it, poi riconcilia employees.

Input CSV atteso (colonne minime: vat_number):
  vat_number, name, state, city, address, county, region, ateco_code, employees

Output CSV (stesso formato di pipeline_ateco.py):
  vat_number, name, state, city, address, county, region, ateco_code,
  employees_min, employees_max, latest_revenue, latest_profit,
  latest_personnel_cost, founding_year

Fasi:
  1. Legge CSV input
  2. Lookup + scrape fatturatoitalia.it per dati finanziari (parallelo)
  3. Riconciliazione: merge employees ranges
  4. Scrive CSV finale

Usage:
    python scripts/enrich_companies.py csv/companies_partial.csv csv/companies_enriched.csv
    python scripts/enrich_companies.py csv/companies_partial.csv csv/companies_enriched.csv -w 20
"""

import csv
import os
import re
import sys
import time
import logging
import threading
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup

# ── Config ────────────────────────────────────────────────────────────────
DEFAULT_WORKERS = 10
REQUEST_TIMEOUT = 30
# Minimum seconds between ANY request (enforced globally across all threads)
MIN_REQUEST_INTERVAL = 0.3

FINAL_FIELDS = [
    "vat_number", "name",
    "state", "city", "address", "county", "region",
    "ateco_code", "employees_min", "employees_max",
    "latest_revenue", "latest_profit", "latest_personnel_cost",
    "founding_year",
]

HEADERS_FI = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8,it;q=0.7",
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": "https://www.fatturatoitalia.it",
    "Referer": "https://www.fatturatoitalia.it/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
}
FI_SEARCH_URL = "https://www.fatturatoitalia.it/cerca/risultato-di-ricerca"
FI_FIELD_MAP = {
    "fatturato": "latest_revenue",
    "utile": "latest_profit",
    "costo del personale": "latest_personnel_cost",
    "n. dipendenti": "n_dipendenti",
    "anno fondazione": "founding_year",
}
FI_EXTRA = ["latest_revenue", "latest_profit", "latest_personnel_cost",
            "n_dipendenti", "founding_year"]


# ── Logging & Progress ────────────────────────────────────────────────────
class CountingHandler(logging.Handler):
    def __init__(self):
        super().__init__(logging.WARNING)
        self.warnings = 0
        self.errors = 0

    def emit(self, record):
        if record.levelno >= logging.ERROR:
            self.errors += 1
        elif record.levelno >= logging.WARNING:
            self.warnings += 1


def setup_logger(output_file):
    log_path = os.path.splitext(output_file)[0] + "_errors.log"
    logger = logging.getLogger("enrich")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.WARNING)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.addFilter(lambda record: record.levelno < logging.WARNING)
    ch.setFormatter(logging.Formatter("%(message)s"))
    counter = CountingHandler()
    logger.addHandler(fh)
    logger.addHandler(ch)
    logger.addHandler(counter)
    return logger, counter


class Progress:
    def __init__(self, total, label=""):
        self.total = total
        self.done = 0
        self.label = label
        self.start = time.monotonic()
        self._lock = threading.Lock()

    def tick(self):
        with self._lock:
            self.done += 1

    def eta(self):
        if not self.done:
            return "N/A"
        elapsed = time.monotonic() - self.start
        remaining = (elapsed / self.done) * (self.total - self.done)
        return f"{int(remaining // 60)}m{int(remaining % 60)}s"

    def show(self, detail=""):
        with self._lock:
            pct = 100 * self.done / self.total if self.total else 0
            frac = self.done / self.total if self.total else 0
        w = 30
        bar = '█' * int(w * frac) + '░' * (w - int(w * frac))
        print(f"\r[{self.label}] [{bar}] {self.done}/{self.total} ({pct:.1f}%) "
              f"ETA {self.eta()} | {detail[:50]}", end="", flush=True)


# ── Global rate limiter ────────────────────────────────────────────────────
class RateLimiter:
    """Ensures a minimum interval between calls across all threads."""
    def __init__(self, min_interval):
        self._min_interval = min_interval
        self._lock = threading.Lock()
        self._last_call = 0.0

    def wait(self):
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_call
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
            self._last_call = time.monotonic()


_rate_limiter = RateLimiter(MIN_REQUEST_INTERVAL)


# ── CSV helpers ───────────────────────────────────────────────────────────
def read_csv(path):
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        return fields, list(reader)


def write_csv(path, fields, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, quoting=csv.QUOTE_ALL,
                                extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: str(v) if v is not None else "" for k, v in row.items()})


# ── Fatturatoitalia scraping ──────────────────────────────────────────────
def _fi_search_piva(piva):
    _rate_limiter.wait()
    try:
        resp = requests.post(FI_SEARCH_URL, data={"piva": piva},
                             headers=HEADERS_FI, timeout=REQUEST_TIMEOUT,
                             allow_redirects=True)
        resp.raise_for_status()
    except Exception:
        return ""

    # If redirected directly to a detail page, return that URL
    if "/azienda/" in resp.url or "/dettaglio/" in resp.url:
        return resp.url

    soup = BeautifulSoup(resp.text, "html.parser")
    tbody = soup.find("tbody")
    if not tbody:
        return ""
    first_row = tbody.find("tr")
    if not first_row:
        return ""
    first_link = first_row.find("a", href=True)
    if not first_link:
        return ""
    href = first_link["href"]
    if href.startswith("/"):
        href = "https://www.fatturatoitalia.it" + href
    return href


def _fi_match_label(label_text):
    lt = label_text.lower().strip()
    for key in FI_FIELD_MAP:
        if lt.startswith(key):
            return FI_FIELD_MAP[key]
    return None


def _fi_scrape_detail(url, expected_piva, logger):
    result = {f: "" for f in FI_EXTRA}
    if not url:
        return result
    _rate_limiter.wait()
    try:
        resp = requests.get(url, headers={"User-Agent": HEADERS_FI["User-Agent"]},
                            timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"  FI request error for {url}: {e}")
        return result

    soup = BeautifulSoup(resp.text, "html.parser")
    labels = soup.find_all("div", class_="col-xs-5")
    piva_verified = False
    for label_div in labels:
        b_tag = label_div.find("b")
        if not b_tag:
            continue
        label_text = b_tag.get_text(strip=True)
        value_div = label_div.find_next_sibling("div", class_="col-xs-7")
        if not value_div:
            continue
        value_p = value_div.find("p")
        if not value_p:
            continue
        value_text = value_p.get_text(strip=True)

        if label_text.lower().strip() == "partita iva":
            if value_text.strip() != expected_piva.strip():
                logger.warning(f"  FI PIVA mismatch: expected {expected_piva}, got {value_text}")
                return result
            piva_verified = True
            continue

        field_name = _fi_match_label(label_text)
        if field_name:
            result[field_name] = value_text

    if not piva_verified:
        logger.warning(f"  FI PIVA not found on {url} for {expected_piva}")
    return result


# ── Employee range reconciliation ─────────────────────────────────────────
_EMPLOYEE_RANGES = {
    "più di 1000": (1000, 99999), "piu di 1000": (1000, 99999),
    "500-1000": (500, 1000), "200-499": (200, 499), "100-199": (100, 199),
    "50-99": (50, 99), "25-49": (25, 49), "10-24": (10, 24), "0-9": (0, 9),
    "da 1000 in su": (1000, 99999), "da 500 a 999": (500, 999),
    "da 250 a 499": (250, 499), "da 200 a 249": (200, 249),
    "da 100 a 199": (100, 199), "da 50 a 99": (50, 99),
    "da 20 a 49": (20, 49), "da 15 a 19": (15, 19),
    "da 10 a 14": (10, 14), "da 6 a 9": (6, 9),
    "da 3 a 5": (3, 5), "da 1 a 2": (1, 2), "0": (0, 0),
}


def _parse_employee_range(text):
    if not text:
        return None
    t = text.strip().lower()
    if t in _EMPLOYEE_RANGES:
        return _EMPLOYEE_RANGES[t]
    m = re.match(r"da\s+(\d+)\s+a\s+(\d+)", t)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.match(r"(\d+)\s*[-–]\s*(\d+)", t)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.match(r"(?:da\s+|più di\s+|piu di\s+)(\d+)", t)
    if m:
        return int(m.group(1)), 99999
    m = re.match(r"^(\d+)$", t)
    if m:
        v = int(m.group(1))
        return v, v
    return None


def _reconcile_employees(employees_ra, n_dipendenti_fi, logger, vat=""):
    range_ra = _parse_employee_range(employees_ra)
    range_fi = _parse_employee_range(n_dipendenti_fi)
    if range_ra and range_fi:
        lo = max(range_ra[0], range_fi[0])
        hi = min(range_ra[1], range_fi[1])
        if lo > hi:
            logger.warning(
                f"  vat {vat}: no employee overlap between "
                f"'{employees_ra}' ({range_ra}) and '{n_dipendenti_fi}' ({range_fi})"
                f" — using input CSV value"
            )
            lo, hi = range_ra[0], range_ra[1]
        return str(lo), str(hi)
    elif range_ra:
        return str(range_ra[0]), str(range_ra[1])
    elif range_fi:
        return str(range_fi[0]), str(range_fi[1])
    else:
        return "", ""


# ── Phase 1: Financial data from fatturatoitalia.it (parallel) ────────────
def enrich_financial(rows, logger, workers=10):
    logger.info(f"═══ PHASE 1: Financial data from fatturatoitalia.it ({workers} workers) ═══")

    todo = [r for r in rows if r.get("vat_number", "").strip()]
    logger.info(f"  Total: {len(rows)} | With VAT: {len(todo)}")

    progress = Progress(len(todo), "Enrich")

    def worker(row):
        vat = row.get("vat_number", "").strip()
        try:
            fi_url = _fi_search_piva(vat)
            if fi_url:
                extra = _fi_scrape_detail(fi_url, vat, logger)
            else:
                extra = {f: "" for f in FI_EXTRA}
                logger.warning(f"  FI no URL found for vat {vat}")
            merged = dict(row)
            merged.update(extra)
            progress.tick()
            fat = extra.get("latest_revenue", "")[:20]
            progress.show(f"{vat} {fat}")
            return merged
        except Exception as e:
            logger.warning(f"  FI error for vat {vat}: {e}")
            merged = dict(row)
            for f in FI_EXTRA:
                merged.setdefault(f, "")
            progress.tick()
            progress.show(f"ERROR {vat}")
            return merged

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {executor.submit(worker, r): i for i, r in enumerate(todo)}
        indexed_results = [None] * len(todo)
        for future in as_completed(future_map):
            idx = future_map[future]
            indexed_results[idx] = future.result()

    print()

    # Rebuild preserving original order; use index-based matching
    # (handles duplicate VAT numbers correctly)
    enriched_by_idx = {i: r for i, r in enumerate(indexed_results) if r}

    enriched = []
    todo_idx = 0
    for r in rows:
        vat = r.get("vat_number", "").strip()
        if vat and todo_idx < len(todo) and todo[todo_idx] is r:
            enriched.append(enriched_by_idx.get(todo_idx, r))
            todo_idx += 1
        else:
            merged = dict(r)
            for f in FI_EXTRA:
                merged.setdefault(f, "")
            enriched.append(merged)

    logger.info(f"  Phase 1 complete: {len(todo)} companies enriched")
    return enriched


# ── Phase 2: Reconciliation ──────────────────────────────────────────────
def reconcile(rows, logger):
    logger.info("═══ PHASE 2: Reconciliation ═══")
    final_rows = []
    for r in rows:
        try:
            vat = r.get("vat_number", "?")
            min_emp, max_emp = _reconcile_employees(
                r.get("employees", ""), r.get("n_dipendenti", ""),
                logger, vat
            )
            final = {
                "vat_number": r.get("vat_number", ""),
                "name": r.get("name", ""),
                "state": r.get("state", ""),
                "city": r.get("city", ""),
                "address": r.get("address", ""),
                "county": r.get("county", ""),
                "region": r.get("region", ""),
                "ateco_code": r.get("ateco_code", ""),
                "employees_min": min_emp,
                "employees_max": max_emp,
                "latest_revenue": r.get("latest_revenue", ""),
                "latest_profit": r.get("latest_profit", ""),
                "latest_personnel_cost": r.get("latest_personnel_cost", ""),
                "founding_year": r.get("founding_year", ""),
            }
            final_rows.append(final)
        except Exception as e:
            logger.warning(f"  Reconciliation error on vat {r.get('vat_number', '?')}: {e}")
            continue
    logger.info(f"  Phase 2 complete: {len(final_rows)} rows")
    return final_rows


# ── Main ──────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Enrich company CSV with financial data from fatturatoitalia.it"
    )
    parser.add_argument("input_csv", help="Input CSV (must have 'vat_number' column)")
    parser.add_argument("output_csv", help="Output CSV path")
    parser.add_argument("--workers", "-w", type=int, default=DEFAULT_WORKERS,
                        help=f"Parallel workers (default: {DEFAULT_WORKERS})")
    args = parser.parse_args()

    logger, counter = setup_logger(args.output_csv)
    logger.info(f"Enrich: {args.input_csv} → {args.output_csv} | Workers={args.workers}")
    t0 = time.monotonic()

    fields, rows = read_csv(args.input_csv)
    if "vat_number" not in fields:
        logger.error("Input CSV must have a 'vat_number' column")
        sys.exit(1)

    logger.info(f"  Loaded {len(rows)} rows from {args.input_csv}")

    # Phase 1: financial data
    rows = enrich_financial(rows, logger, workers=args.workers)

    # Phase 2: reconciliation
    final = reconcile(rows, logger)

    # Write output
    write_csv(args.output_csv, FINAL_FIELDS, final)

    elapsed = time.monotonic() - t0
    n = len(final)
    avg = elapsed / n if n else 0
    mins, secs = divmod(int(elapsed), 60)
    total_issues = counter.warnings + counter.errors
    summary = f"Done. {n} companies in {mins}m{secs}s ({avg:.2f}s/company)"
    if total_issues:
        log_path = os.path.splitext(args.output_csv)[0] + "_errors.log"
        summary += f" | {counter.warnings} warnings, {counter.errors} errors → {log_path}"
    logger.info(summary)

    # Cleanup empty log
    log_path = os.path.splitext(args.output_csv)[0] + "_errors.log"
    for h in logger.handlers:
        h.flush()
        if isinstance(h, logging.FileHandler):
            h.close()
    if os.path.exists(log_path) and os.path.getsize(log_path) == 0:
        os.remove(log_path)


if __name__ == "__main__":
    main()
