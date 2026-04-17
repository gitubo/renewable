"""
Esporta le aziende che non hanno entry in company_data con source='homepage'.

Crea un CSV con: vat_number, name, address, city
"""

import sqlite3
import csv
import sys

def get_companies_without_homepage_data(db_path: str = "biogas.db") -> list:
    """
    Trova tutte le aziende che non hanno entry in company_data con source='homepage'.
    
    Returns:
        Lista di tuple (vat_number, name, address, city)
    """
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    query = """
    SELECT DISTINCT
        c.vat_number,
        c.name,
        c.address,
        c.city
    FROM companies c
    WHERE c.id NOT IN (
        SELECT DISTINCT cd.company_id
        FROM company_data cd
        WHERE cd.source = 'homepage'
        AND cd.company_id IS NOT NULL
    )
    ORDER BY c.name
    """
    
    cursor.execute(query)
    results = cursor.fetchall()
    
    conn.close()
    
    return results


def main():
    print("Esportazione aziende senza dati homepage\n")
    print("=" * 60)
    
    # Ottieni aziende
    companies = get_companies_without_homepage_data()
    
    if not companies:
        print("\nNessuna azienda trovata senza dati homepage")
        sys.exit(0)
    
    print(f"\nTrovate {len(companies)} aziende senza dati homepage")
    
    # Crea CSV
    output_file = "companies_missing_homepage_data.csv"
    
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        
        # Header
        writer.writerow(["vat_number", "name", "address", "city"])
        
        # Dati
        for row in companies:
            writer.writerow(row)
    
    print(f"\nCSV salvato: {output_file}")
    print(f"Righe esportate: {len(companies)}")
    
    # Mostra prime 5 righe come esempio
    if companies:
        print("\nPrime 5 aziende:")
        for i, (vat, name, address, city) in enumerate(companies[:5], 1):
            print(f"  {i}. {name} (P.IVA: {vat})")
            print(f"     {address}, {city}")


if __name__ == "__main__":
    main()
