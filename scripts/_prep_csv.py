import csv

with open('homepages.csv', 'r', encoding='utf-8') as f:
    rows = list(csv.DictReader(f))

with open('_homepages_scrape.csv', 'w', encoding='utf-8', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['vat_number', 'source_url'])
    writer.writeheader()
    for r in rows:
        writer.writerow({
            'vat_number': r.get('va_number', ''),
            'source_url': r.get('source_url', '')
        })

print(f"Created _homepages_scrape.csv with {len(rows)} rows")
