"""Genera UPDATE SQL per Supabase partendo dal CSV enriched."""

import csv
import re
import sys

INPUT_CSV = "csv/companies_enriched.csv"
OUTPUT_SQL = "sql/update_companies.sql"


def parse_euro(val: str) -> str | None:
    """'€ 1.869.369.003' → '1869369003', '€ -210.513.300' → '-210513300', '' o 'N.D.' → None"""
    if not val or val.strip().upper() == "N.D.":
        return None
    cleaned = val.replace("€", "").replace(".", "").replace(" ", "").strip()
    if not cleaned or not re.match(r"^-?\d+$", cleaned):
        return None
    return cleaned


def parse_date(val: str) -> str | None:
    """'19/09/2019' → '2019-09-19', '' → None"""
    if not val or val.strip().upper() == "N.D.":
        return None
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", val.strip())
    if not m:
        return None
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"


def sql_val(v, typ="int"):
    """Ritorna il valore SQL o NULL."""
    if v is None or v == "":
        return "NULL"
    if typ == "int":
        return str(v)
    if typ == "date":
        return f"'{v}'"
    return "NULL"


def main():
    with open(INPUT_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    lines = []
    lines.append("-- Auto-generated UPDATE statements from companies_enriched.csv")
    lines.append("-- Aggiorna employees_min/max, dati finanziari e founding_date")
    lines.append("BEGIN;")
    lines.append("")

    count = 0
    skipped = 0
    for r in rows:
        vat = r.get("vat_number", "").strip()
        if not vat:
            skipped += 1
            continue

        emp_min = r.get("employees_min", "").strip() or None
        emp_max = r.get("employees_max", "").strip() or None
        revenue = parse_euro(r.get("latest_revenue", ""))
        profit = parse_euro(r.get("latest_profit", ""))
        personnel = parse_euro(r.get("latest_personnel_cost", ""))
        # CSV header is "founding_year" but contains a date
        fdate = parse_date(r.get("founding_year", "") or r.get("founding_date", ""))

        sets = []
        sets.append(f"employees_min = {sql_val(emp_min)}")
        sets.append(f"employees_max = {sql_val(emp_max)}")
        sets.append(f"latest_revenue = {sql_val(revenue)}")
        sets.append(f"latest_profit = {sql_val(profit)}")
        sets.append(f"latest_personnel_cost = {sql_val(personnel)}")
        sets.append(f"founding_date = {sql_val(fdate, 'date')}")

        sets.append("updated_at = now()")

        escaped_vat = vat.replace("'", "''")
        sql = f"UPDATE companies SET {', '.join(sets)} WHERE vat_number = '{escaped_vat}';"
        lines.append(sql)
        count += 1

    lines.append("")
    lines.append("COMMIT;")
    lines.append(f"-- {count} UPDATE generati, {skipped} righe saltate (nessun dato)")

    import os
    os.makedirs(os.path.dirname(OUTPUT_SQL), exist_ok=True)
    with open(OUTPUT_SQL, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Generati {count} UPDATE → {OUTPUT_SQL} ({skipped} saltati)")


if __name__ == "__main__":
    main()
