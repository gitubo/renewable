import csv

with open("missing_atoka_output.csv", newline="", encoding="utf-8-sig") as f:
    rows = list(csv.DictReader(f))

found = 0
missing = 0

with open("atoka_to_import.csv", "w", newline="", encoding="utf-8") as out_ok, \
     open("atoka_still_missing.csv", "w", newline="", encoding="utf-8") as out_miss:

    w_ok = csv.writer(out_ok, quoting=csv.QUOTE_ALL)
    w_ok.writerow(["vat_number", "source", "content", "source_url", "note"])

    w_miss = csv.writer(out_miss, quoting=csv.QUOTE_ALL)
    w_miss.writerow(["id", "vat_number", "ragione_sociale"])

    for row in rows:
        contenuto = row.get("contenuto", "").strip()
        if contenuto:
            w_ok.writerow([
                row["vat_number"],
                "atoka",
                contenuto,
                row.get("source_url", ""),
                "",
            ])
            found += 1
        else:
            w_miss.writerow([
                row["id"],
                row["vat_number"],
                row["ragione_sociale"],
            ])
            missing += 1

print(f"With content: {found} → atoka_to_import.csv")
print(f"Without content: {missing} → atoka_still_missing.csv")
