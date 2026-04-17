#!/usr/bin/env python3
"""
Filtra il file CSV consolidato mantenendo solo le aziende il cui nome
contiene almeno una delle parole chiave definite.
Aggiunge un campo 'score' con il numero di keyword distinte trovate.

Uso:
    python filter_keywords.py input.csv
    python filter_keywords.py input.csv --output filtered.csv
    python filter_keywords.py input.csv --keywords bio gas energia  # sovrascrive le keyword
"""

import csv
import os
import sys
import argparse

# ── Parole chiave (modifica qui per aggiungerne/togliere) ──────────────────────
DEFAULT_KEYWORDS = [
    "bio",
    "gas",
    "metano",
    "power",
    "energy",
    "energia",
    "methane",
    "anaerobic",
    "anaerobico",
]
# ──────────────────────────────────────────────────────────────────────────────


def count_matches(name: str, keywords: list[str]) -> tuple[int, list[str]]:
    """
    Ritorna (numero di keyword distinte trovate, lista delle keyword trovate).
    Il confronto è case-insensitive.
    """
    name_lower = name.lower()
    found = [kw for kw in keywords if kw in name_lower]
    return len(found), found


def filter_file(input_file: str, output_file: str, keywords: list[str]) -> None:
    if not os.path.exists(input_file):
        print(f"❌ File non trovato: {input_file}")
        sys.exit(1)

    # Ordina per lunghezza decrescente così "biomethane" viene prima di "bio"
    # (utile per il log, non influisce sul conteggio che usa set distinte)
    keywords_sorted = sorted(keywords, key=len, reverse=True)

    written = 0
    skipped = 0

    with open(input_file, newline="", encoding="utf-8") as infile:
        reader = csv.DictReader(infile)
        input_fields = reader.fieldnames or []
        output_fields = input_fields + ["score"]

        with open(output_file, "w", newline="", encoding="utf-8") as outfile:
            writer = csv.DictWriter(outfile, fieldnames=output_fields, quoting=csv.QUOTE_ALL)
            writer.writeheader()

            for row in reader:
                name = row.get("ragione_sociale", "")
                score, found = count_matches(name, keywords_sorted)

                if score == 0:
                    skipped += 1
                    continue

                row["score"] = score
                writer.writerow(row)
                written += 1

    print(f"\n📂 Input:   {input_file}")
    print(f"📄 Output:  {output_file}")
    print(f"\n   ✅ Righe mantenute:  {written}")
    print(f"   ⏭  Righe scartate:   {skipped}")
    print(f"\n   Keyword usate ({len(keywords)}):")
    for kw in sorted(keywords):
        print(f"      • {kw}")


def main():
    parser = argparse.ArgumentParser(
        description="Filtra aziende per keyword nel nome e aggiunge score."
    )
    parser.add_argument("input", help="File CSV di input (es. output_aziende.csv)")
    parser.add_argument(
        "--output",
        help="File CSV di output (default: <input>_filtered.csv)",
    )
    parser.add_argument(
        "--keywords",
        nargs="+",
        help="Sovrascrive le keyword di default (es. --keywords bio gas energia)",
    )
    args = parser.parse_args()

    keywords = [kw.lower() for kw in args.keywords] if args.keywords else DEFAULT_KEYWORDS

    if args.output:
        output_file = args.output
    else:
        base, ext = os.path.splitext(args.input)
        output_file = f"{base}_filtered{ext}"

    filter_file(args.input, output_file, keywords)


if __name__ == "__main__":
    main()