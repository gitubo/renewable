"""
Estrae lista unica di P.IVA + nome azienda da tutti i file biometano-*.csv
Output: biometano_companies.csv
"""
import csv
import glob

seen = {}  # vat -> name

for path in sorted(glob.glob("biometano-*.csv")):
    print(f"Reading {path}...")
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            vat = row.get("PARTITA_IVA_DEL_SOGGETTO_BENEFICIARIO", "").strip()
            name = row.get("NOMINATIVO_DEL_SOGGETTO_BENEFICIARIO", "").strip()
            if vat and vat not in seen:
                seen[vat] = name

with open("biometano_companies.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f, quoting=csv.QUOTE_ALL)
    w.writerow(["vat_number", "name"])
    for vat, name in sorted(seen.items(), key=lambda x: x[1]):
        w.writerow([vat, name])

print(f"Unique companies: {len(seen)} → biometano_companies.csv")
