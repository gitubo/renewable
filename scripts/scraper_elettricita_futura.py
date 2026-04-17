import requests
from bs4 import BeautifulSoup
import csv
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

URL = "https://www.elettricitafutura.it/s/Chi-siamo/Gli-associati_2.html"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )
}

OUTPUT_FILE = "associati.csv"


def scrape_associati() -> list[dict]:
    print(f"Fetching {URL} ...")
    response = requests.get(URL, headers=HEADERS, timeout=15, verify=False)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    divs = soup.find_all("div", class_="item_associato")
    print(f"Trovati {len(divs)} associati.")

    rows = []
    for idx, div in enumerate(divs, start=1):
        nome      = div.get("data-nome", "").strip()
        provincia = div.get("data-nomeprovincia", "").strip()
        regione   = div.get("data-nomeregione", "").strip()

        rows.append({
            "id":       idx,
            "nome":     nome,
            "provincia": provincia,
            "regione":  regione,
        })

    return rows


def write_csv(rows: list[dict], path: str) -> None:
    fieldnames = ["id", "nome", "provincia", "regione"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"CSV salvato in: {path}")


if __name__ == "__main__":
    data = scrape_associati()
    write_csv(data, OUTPUT_FILE)