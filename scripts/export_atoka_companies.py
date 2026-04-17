import sqlite3
import csv

conn = sqlite3.connect('biogas.db')
cursor = conn.cursor()

cursor.execute("""
    SELECT c.vat_number, c.name, cd.source_url
    FROM company_data cd
    JOIN companies c ON cd.company_id = c.id
    WHERE cd.source = 'atoka'
    ORDER BY c.name
""")

rows = cursor.fetchall()

with open('atoka_companies.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f, quoting=csv.QUOTE_ALL)
    writer.writerow(['vat_number', 'name', 'source_url'])
    writer.writerows(rows)

print(f"Esportate {len(rows)} aziende in atoka_companies.csv")
conn.close()
