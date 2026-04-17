"""
Import scores.csv into company_scores table.
Replaces existing scores for the same company.

Usage:
    python import_scores.py scores.csv
"""

import csv
import sqlite3
import sys
from pathlib import Path

def main():
    if len(sys.argv) < 2:
        print("Usage: python import_scores.py scores.csv")
        sys.exit(1)

    csv_file = sys.argv[1]
    db_file = "biogas.db"

    if not Path(csv_file).exists():
        print(f"❌ File non trovato: {csv_file}")
        sys.exit(1)

    # Leggi CSV
    with open(csv_file, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    print(f"📂 Trovate {len(rows)} righe in {csv_file}")

    # Connetti al DB
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row

    inserted = 0
    updated = 0
    skipped = 0

    for row in rows:
        vat = row.get("vat_number", "").strip()
        score = row.get("score", "").strip()
        confidence = row.get("confidence", "").strip()
        reasoning = row.get("reasoning", "").strip()
        model = row.get("model_used", "").strip()

        if not vat:
            skipped += 1
            continue

        # Trova company_id
        company = conn.execute(
            "SELECT id FROM companies WHERE vat_number = ?", (vat,)
        ).fetchone()

        if not company:
            print(f"  ⚠  VAT {vat} non trovato nel DB")
            skipped += 1
            continue

        company_id = company["id"]

        # Controlla se esiste già uno score
        existing = conn.execute(
            "SELECT id FROM company_scores WHERE company_id = ?", (company_id,)
        ).fetchone()

        if existing:
            # Update
            conn.execute("""
                UPDATE company_scores
                SET score = ?, confidence = ?, reasoning = ?, model_used = ?, scored_at = datetime('now')
                WHERE company_id = ?
            """, (score, confidence, reasoning, model, company_id))
            updated += 1
        else:
            # Insert
            conn.execute("""
                INSERT INTO company_scores (company_id, score, confidence, reasoning, model_used, scored_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
            """, (company_id, score, confidence, reasoning, model))
            inserted += 1

    conn.commit()
    conn.close()

    print(f"\n✅ Completato:")
    print(f"   Inseriti: {inserted}")
    print(f"   Aggiornati: {updated}")
    print(f"   Saltati: {skipped}")


if __name__ == "__main__":
    main()
