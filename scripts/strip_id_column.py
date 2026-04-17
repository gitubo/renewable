"""
Remove the 'id' column from exported CSVs so Supabase can auto-generate IDs.
Skips 'statuses' table (uses fixed integer PK, not identity).

Usage: python scripts/strip_id_column.py
"""
import csv
import os

DATA_DIR = os.path.join("supabase", "data")
# statuses has a fixed PK, keep its id column
SKIP = {"statuses.csv"}

for fname in os.listdir(DATA_DIR):
    if not fname.endswith(".csv") or fname in SKIP:
        continue
    path = os.path.join(DATA_DIR, fname)
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if "id" not in reader.fieldnames:
            continue
        rows = list(reader)
        cols = [c for c in reader.fieldnames if c != "id"]

    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row[c] for c in cols})

    print(f"  ✓ {fname}: removed 'id' column ({len(rows)} rows)")

print("\nDone. Re-import the CSVs into Supabase.")
