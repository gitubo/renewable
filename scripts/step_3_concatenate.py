#!/usr/bin/env python3
"""
Processa file CSV con naming convention xx_yy_step_2.csv
e scrive in append su un file di output consolidato.

Uso:
    python process_ateco.py input1.csv input2.csv ...
    python process_ateco.py *.csv
    python process_ateco.py --dir ./cartella_input
"""

import csv
import os
import re
import sys
import argparse
from pathlib import Path

OUTPUT_FILE = "output_aziende.csv"
OUTPUT_FIELDS = [
    "id",
    "piva",
    "ragione_sociale",
    "codice_ateco",
    "regione",
    "provincia",
    "citta",
    "indirizzo",
    "dipendenti",
]


def extract_ateco_from_filename(filename: str) -> str | None:
    """
    Estrae il codice ATECO dal nome file.
    Es: '35_21_step_2.csv' -> '35.21'
    """
    name = Path(filename).stem  # rimuove estensione
    match = re.match(r"^(\d+)_(\d+)", name)
    if match:
        return f"{match.group(1)}.{match.group(2)}"
    return None


def load_existing_pivas(output_file: str) -> set:
    """Carica le P.IVA già presenti nel file di output per evitare duplicati."""
    pivas = set()
    if not os.path.exists(output_file):
        return pivas
    with open(output_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("piva"):
                pivas.add(row["piva"].strip())
    return pivas


def get_last_id(output_file: str) -> int:
    """Restituisce l'ultimo ID presente nel file di output."""
    last_id = 0
    if not os.path.exists(output_file):
        return last_id
    with open(output_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                row_id = int(row.get("id", 0))
                if row_id > last_id:
                    last_id = row_id
            except (ValueError, TypeError):
                pass
    return last_id


def process_file(csv_path: str, output_file: str, existing_pivas: set, current_id: int) -> tuple[int, int, int]:
    """
    Processa un singolo file CSV e scrive le righe valide in append sull'output.
    Restituisce (righe_scritte, duplicati_saltati, id_corrente).
    """
    filename = os.path.basename(csv_path)
    codice_ateco = extract_ateco_from_filename(filename)

    if codice_ateco is None:
        print(f"  ⚠️  Nome file non riconosciuto (atteso: xx_yy_...csv): {filename}")
        return 0, 0, current_id

    written = 0
    skipped = 0

    write_header = not os.path.exists(output_file)

    with open(csv_path, newline="", encoding="utf-8") as infile, \
         open(output_file, "a", newline="", encoding="utf-8") as outfile:

        reader = csv.DictReader(infile)
        writer = csv.DictWriter(outfile, fieldnames=OUTPUT_FIELDS, quoting=csv.QUOTE_ALL)

        if write_header:
            writer.writeheader()

        for row in reader:
            piva = row.get("piva", "").strip()

            # Salta righe senza P.IVA
            if not piva:
                skipped += 1
                continue

            # Salta duplicati
            if piva in existing_pivas:
                skipped += 1
                continue

            current_id += 1
            existing_pivas.add(piva)

            writer.writerow({
                "id":             current_id,
                "piva":           piva,
                "ragione_sociale": row.get("ragione_sociale", "").strip(),
                "codice_ateco":   codice_ateco,
                "regione":        row.get("regione", "").strip(),
                "provincia":      row.get("provincia", "").strip(),
                "citta":          row.get("citta", "").strip(),
                "indirizzo":      row.get("indirizzo", "").strip(),
                "dipendenti":     row.get("dipendenti", "").strip(),
            })
            written += 1

    return written, skipped, current_id


def main():
    parser = argparse.ArgumentParser(description="Processa file CSV ATECO e consolida in output.")
    parser.add_argument("files", nargs="*", help="File CSV da processare")
    parser.add_argument("--dir", help="Cartella da cui leggere tutti i file *_step_2.csv")
    parser.add_argument("--output", default=OUTPUT_FILE, help=f"File di output (default: {OUTPUT_FILE})")
    args = parser.parse_args()

    output_file = args.output

    # Raccolta file da processare
    input_files = list(args.files)
    if args.dir:
        dir_path = Path(args.dir)
        found = sorted(dir_path.glob("*_step_2.csv"))
        input_files.extend(str(p) for p in found)

    if not input_files:
        print("Nessun file specificato. Usa: python process_ateco.py file1.csv file2.csv")
        print("Oppure: python process_ateco.py --dir ./cartella")
        sys.exit(1)

    print(f"📂 File di output: {output_file}")
    print(f"📋 File da processare: {len(input_files)}\n")

    existing_pivas = load_existing_pivas(output_file)
    current_id = get_last_id(output_file)
    print(f"   Ultimo ID trovato nell'output: {current_id}")
    print(f"   P.IVA già presenti:            {len(existing_pivas)}\n")

    total_written = 0
    total_skipped = 0

    for csv_path in input_files:
        if not os.path.exists(csv_path):
            print(f"  ❌ File non trovato: {csv_path}")
            continue

        print(f"  ▶ {os.path.basename(csv_path)}")
        written, skipped, current_id = process_file(
            csv_path, output_file, existing_pivas, current_id
        )
        print(f"     ✅ Scritte: {written}  |  ⏭  Saltate (duplicati/no-piva): {skipped}")
        total_written += written
        total_skipped += skipped

    print(f"\n{'─'*45}")
    print(f"  Totale righe scritte:  {total_written}")
    print(f"  Totale righe saltate:  {total_skipped}")
    print(f"  Ultimo ID assegnato:   {current_id}")
    print(f"  Output:                {output_file}")


if __name__ == "__main__":
    main()