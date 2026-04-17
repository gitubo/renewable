import csv
import argparse
import os
import asyncio
from playwright.async_api import async_playwright

INPUT_FILE = 'atoka_companies.csv'
OUTPUT_FILE = 'atoka_companies_content.csv'
MAX_CONCURRENT = 5


def load_done():
    done = set()
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                done.add(row['source_url'])
    return done


def write_row(row):
    write_header = not os.path.exists(OUTPUT_FILE)
    with open(OUTPUT_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['vat_number', 'name', 'source_url', 'content'],
                                quoting=csv.QUOTE_ALL)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


async def fetch_content(page, url):
    try:
        await page.goto(url, wait_until='networkidle', timeout=60000)
        container = await page.query_selector('section.azienda')
        if container:
            text = await container.inner_text()
            text = text.strip().replace('\r\n', '\\n').replace('\n', '\\n').replace('\r', '\\n').replace('\t', '\\t').replace('"', "'")
            return text
        return ''
    except Exception as e:
        print(f"  Errore {url}: {e}")
        return ''


async def process_batch(browser, rows, semaphore, counter, total):
    async def process_one(row):
        async with semaphore:
            url = row['source_url']
            print(f"  [{counter['done']+1}/{total}] Scaricando: {url}")
            page = await browser.new_page()
            try:
                content = await fetch_content(page, url)
                result = {**row, 'content': content}
                write_row(result)
                counter['done'] += 1
            finally:
                await page.close()

    tasks = [process_one(row) for row in rows]
    await asyncio.gather(*tasks)


async def main():
    parser = argparse.ArgumentParser(description='Scrape Atoka pages con Playwright')
    parser.add_argument('--start', type=int, default=0)
    parser.add_argument('--end', type=int, default=None)
    args = parser.parse_args()

    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        all_rows = list(csv.DictReader(f))

    subset = all_rows[args.start:args.end]
    print(f"Totale righe input: {len(all_rows)}")
    print(f"Range: [{args.start}:{args.end or len(all_rows)}] -> {len(subset)} righe")

    done = load_done()
    to_process = [r for r in subset if r['source_url'] not in done]
    print(f"Gia processate: {len(subset) - len(to_process)}")
    print(f"Da processare: {len(to_process)}")

    if not to_process:
        print("Niente da fare.")
        return

    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    counter = {'done': 0}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        await process_batch(browser, to_process, semaphore, counter, len(to_process))
        await browser.close()

    print(f"\nCompletato. {counter['done']} righe scritte in {OUTPUT_FILE}")


if __name__ == '__main__':
    asyncio.run(main())
