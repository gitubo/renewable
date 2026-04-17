import csv
import sys
import os

def deduplicate(input_file: str, output_file: str):
    with open(input_file, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows   = list(reader)

    print(f"Record totali letti: {len(rows)}")

    seen      = set()
    unique    = []
    duplicate = 0

    for row in rows:
        if len(row) < 3:
            continue
        link = row[-1]  # ultimo campo
        if link not in seen:
            seen.add(link)
            unique.append(row)
        else:
            duplicate += 1

    print(f"Duplicati rimossi:   {duplicate}")
    print(f"Record unici:        {len(unique)}")

    with open(output_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_NONNUMERIC)
        writer.writerow(header)
        for new_id, row in enumerate(unique, start=1):
            row[0] = new_id   # rigenera ID
            writer.writerow(row)

    print(f"Output scritto in:   '{output_file}'")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python dedup.py <input.csv> <output.csv>")
        print("Example: python dedup.py aziende.csv aziende_dedup.csv")
        sys.exit(1)

    input_file  = sys.argv[1]
    output_file = sys.argv[2]

    if not os.path.exists(input_file):
        print(f"ERRORE: file '{input_file}' non trovato.")
        sys.exit(1)

    if input_file == output_file:
        print("ERRORE: input e output devono essere file diversi.")
        sys.exit(1)

    deduplicate(input_file, output_file)