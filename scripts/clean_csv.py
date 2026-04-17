import csv
import sys

INPUT_FILE = "output_intelligence.csv"
OUTPUT_FILE = "output_intelligence_cleaned.csv"

with open(INPUT_FILE, "r", encoding="utf-8") as infile, \
     open(OUTPUT_FILE, "w", encoding="utf-8", newline="") as outfile:

    reader = csv.DictReader(infile)
    writer = csv.DictWriter(outfile, fieldnames=reader.fieldnames, quoting=csv.QUOTE_ALL)
    writer.writeheader()

    total = 0
    kept = 0
    skipped_empty = 0
    skipped_pdf = 0

    for row in reader:
        total += 1
        content = row["content"].strip()

        if content == "":
            skipped_empty += 1
            continue

        if content.startswith("%PDF"):
            skipped_pdf += 1
            continue

        writer.writerow(row)
        kept += 1

print(f"Totale righe lette: {total}")
print(f"Righe mantenute:    {kept}")
print(f"Scartate (vuote):   {skipped_empty}")
print(f"Scartate (PDF):     {skipped_pdf}")
