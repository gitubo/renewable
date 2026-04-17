import json
import sqlite3
from datetime import datetime

INPUT_FILE = 'atoka_companies_content_to_markdown.json'
DB_FILE = 'biogas.db'

with open(INPUT_FILE, 'r', encoding='utf-8') as f:
    data = json.load(f)

conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

inserted = 0
skipped = 0

for record in data['records']:
    vat = record['vat_number'].strip()
    # Try exact match, then with leading zeros up to 11 digits
    cursor.execute("SELECT id FROM companies WHERE vat_number = ?", (vat,))
    row = cursor.fetchone()
    if not row:
        padded = vat.zfill(11)
        cursor.execute("SELECT id FROM companies WHERE vat_number = ?", (padded,))
        row = cursor.fetchone()

    if not row:
        print(f"  Azienda non trovata per VAT {vat} - {record['name']}")
        skipped += 1
        continue

    company_id = row[0]
    cursor.execute("""
        INSERT INTO company_data (company_id, source, source_url, content, note, created_at)
        VALUES (?, 'atoka2', ?, ?, 'Generated markdown from html', ?)
    """, (company_id, record['source_url'], record['markdown_content'], datetime.now().isoformat()))
    inserted += 1

conn.commit()
conn.close()

print(f"\nCompletato. Inseriti: {inserted}, Saltati: {skipped}")
