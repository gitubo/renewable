"""
Import markdown files from markdown_output/ into company_data table.

For each .md file:
- Extract VAT number and URL from the file header
- Find the company_id by vat_number
- Insert a company_data record with source='homepage'
"""
import os
import re
import sqlite3
from datetime import datetime

MD_DIR = 'markdown_output'
DB_FILE = 'biogas.db'

conn = sqlite3.connect(DB_FILE)
conn.row_factory = sqlite3.Row

# First, delete existing homepage records to avoid duplicates
deleted = conn.execute("DELETE FROM company_data WHERE source = 'homepage'").rowcount
conn.commit()
print(f"Deleted {deleted} existing 'homepage' records\n")

inserted = 0
skipped = 0

for filename in sorted(os.listdir(MD_DIR)):
    if not filename.endswith('.md'):
        continue

    filepath = os.path.join(MD_DIR, filename)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Extract VAT number
    vat_match = re.search(r'\*\*VAT Number\*\*:\s*(\d{11})', content)
    if not vat_match:
        print(f"  SKIP {filename} - no VAT number found")
        skipped += 1
        continue
    vat = vat_match.group(1)

    # Extract URL
    url_match = re.search(r'\*\*URL\*\*:\s*(.+)', content)
    source_url = url_match.group(1).strip() if url_match else ''

    # Find company_id
    row = conn.execute("SELECT id FROM companies WHERE vat_number = ?", (vat,)).fetchone()
    if not row:
        print(f"  SKIP {filename} - company not found for VAT {vat}")
        skipped += 1
        continue

    company_id = row['id']

    conn.execute("""
        INSERT INTO company_data (company_id, source, content, source_url, note, created_at)
        VALUES (?, 'homepage', ?, ?, '', ?)
    """, (company_id, content, source_url, datetime.now().isoformat()))
    inserted += 1
    print(f"  OK {filename} -> company_id={company_id} (VAT {vat})")

conn.commit()
conn.close()

print(f"\nDone. Inserted: {inserted}, Skipped: {skipped}")
