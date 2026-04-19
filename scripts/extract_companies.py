"""Estrae i dati della tabella 'companies' da un backup SQL PostgreSQL e li salva in CSV."""

import csv
import re
import sys

SQL_FILE = "backup_20260419_025008.sql"
OUTPUT_CSV = "csv/companies.csv"

COPY_RE = re.compile(r"^COPY public\.companies \((.+?)\) FROM stdin;$")

# Mapping: nome colonna SQL -> nome colonna output CSV
# L'ordine qui definisce l'ordine delle colonne nel CSV
OUTPUT_COLUMNS = [
    "vat_number",
    "name",
    "state",      # non esiste nel dump, sarà sempre vuoto
    "city",
    "address",
    "county",
    "region",
    "ateco_code",
    "employees",
]


def clean_utf8(value: str) -> str:
    """Rimuove caratteri non-UTF8 / surrogati."""
    return value.encode("utf-8", errors="replace").decode("utf-8")


def extract_companies(sql_path: str, csv_path: str) -> int:
    sql_columns = None
    rows = []
    inside_copy = False

    with open(sql_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")

            if not inside_copy:
                m = COPY_RE.match(line)
                if m:
                    sql_columns = [c.strip() for c in m.group(1).split(",")]
                    inside_copy = True
                continue

            if line == "\\.":
                break

            values = line.split("\t")
            row_dict = {}
            for i, col in enumerate(sql_columns):
                raw = values[i] if i < len(values) else ""
                row_dict[col] = "" if raw == "\\N" else clean_utf8(raw)

            out_row = []
            for col in OUTPUT_COLUMNS:
                out_row.append(row_dict.get(col, ""))
            rows.append(out_row)

    if not sql_columns:
        print("Tabella 'companies' non trovata nel file SQL.", file=sys.stderr)
        sys.exit(1)

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow(OUTPUT_COLUMNS)
        writer.writerows(rows)

    print(f"Estratte {len(rows)} righe -> {csv_path}")
    return len(rows)


if __name__ == "__main__":
    extract_companies(SQL_FILE, OUTPUT_CSV)
