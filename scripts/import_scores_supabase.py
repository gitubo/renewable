"""
Import scores CSV into Supabase company_scores table.
Matches by vat_number, upserts scores.

Usage:
    python scripts/import_scores_supabase.py scores.csv

Requires: pip install supabase
"""
import csv
import sys
from pathlib import Path

from supabase import create_client

# ── Config — same as frontend/src/config.js ──
SUPABASE_URL = "https://mlkgobmhauwnqdnjizte.supabase.co"
SUPABASE_KEY = "sb_publishable_1ZgIHPgnfTSZgX5wdw_RNQ_AgwXLsk4"


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/import_scores_supabase.py scores.csv")
        sys.exit(1)

    csv_file = sys.argv[1]
    if not Path(csv_file).exists():
        print(f"❌ File non trovato: {csv_file}")
        sys.exit(1)

    with open(csv_file, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    print(f"📂 {len(rows)} righe in {csv_file}")

    sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Build VAT → company_id lookup
    print("Caricamento aziende da Supabase...")
    all_companies = sb.table("companies").select("id,vat_number").execute().data
    vat_map = {c["vat_number"]: c["id"] for c in all_companies}
    print(f"  {len(vat_map)} aziende trovate")

    inserted = 0
    updated = 0
    skipped = 0

    for row in rows:
        vat = row.get("vat_number", "").strip()
        score = row.get("score", "").strip()
        confidence = row.get("confidence", "").strip()
        reasoning = row.get("reasoning", "").strip()
        model = row.get("model_used", "").strip()

        if not vat or not score:
            skipped += 1
            continue

        company_id = vat_map.get(vat)
        if not company_id:
            print(f"  ⚠  VAT {vat} non trovato")
            skipped += 1
            continue

        payload = {
            "company_id": company_id,
            "score": int(float(score)),
            "confidence": float(confidence) if confidence else None,
            "reasoning": reasoning or None,
            "model_used": model or None,
        }

        # Check if exists
        existing = sb.table("company_scores").select("id").eq("company_id", company_id).execute().data
        if existing:
            sb.table("company_scores").update(payload).eq("company_id", company_id).execute()
            updated += 1
        else:
            sb.table("company_scores").insert(payload).execute()
            inserted += 1

    print(f"\n✅ Completato:")
    print(f"   Inseriti: {inserted}")
    print(f"   Aggiornati: {updated}")
    print(f"   Saltati: {skipped}")


if __name__ == "__main__":
    main()
