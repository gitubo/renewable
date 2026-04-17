"""
Export all tables from biogas.db into separate CSV files in supabase/data/.
Read-only access to the database — never modifies biogas.db.

Usage:
    python scripts/export_sqlite.py
"""

import csv
import os
import sqlite3
import sys

DB_PATH = os.environ.get("BIOGAS_DB", "biogas.db")
OUTPUT_DIR = os.path.join("supabase", "data")

# Tables to export (excludes sqlite_sequence which is internal)
TABLES = [
    "companies",
    "company_data",
    "company_scores",
    "contacts",
    "activities",
    "statuses",
    "company_statuses",
    "tags",
    "company_tags",
]


def get_readonly_connection(db_path: str) -> sqlite3.Connection:
    """Open a read-only connection to the SQLite database."""
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def export_table(conn: sqlite3.Connection, table: str, output_dir: str) -> int:
    """Export a single table to CSV. Returns the number of rows written."""
    cursor = conn.execute(f"SELECT * FROM [{table}]")
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()

    csv_path = os.path.join(output_dir, f"{table}.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        for row in rows:
            writer.writerow(list(row))

    return len(rows)


def main() -> None:
    if not os.path.exists(DB_PATH):
        print(f"ERROR: database not found at '{DB_PATH}'")
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    conn = get_readonly_connection(DB_PATH)

    print(f"Exporting tables from '{DB_PATH}' → '{OUTPUT_DIR}/'\n")

    counts: dict[str, int] = {}
    for table in TABLES:
        row_count = export_table(conn, table, OUTPUT_DIR)
        counts[table] = row_count
        print(f"  ✓ {table}: {row_count} rows")

    conn.close()

    # Verification: re-read CSVs and compare row counts
    print("\n--- Verification ---")
    all_ok = True
    for table in TABLES:
        csv_path = os.path.join(OUTPUT_DIR, f"{table}.csv")
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            header = next(reader)  # skip header
            csv_rows = sum(1 for _ in reader)
        match = "OK" if csv_rows == counts[table] else "MISMATCH"
        if csv_rows != counts[table]:
            all_ok = False
        print(f"  {table}: DB={counts[table]}  CSV={csv_rows}  [{match}]")

    total = sum(counts.values())
    print(f"\nTotal rows exported: {total}")

    if all_ok:
        print("All counts verified ✓")
    else:
        print("WARNING: some counts do not match!")
        sys.exit(1)


if __name__ == "__main__":
    main()
