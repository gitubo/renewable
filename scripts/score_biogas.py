"""
score_biogas.py
---------------
Per ogni azienda nel DB legge tutti i testi in company_data,
chiede a un modello Ollama uno score di rilevanza biogas/biometano/biomasse
e salva i risultati nella tabella company_scores.

Uso:
    python score_biogas.py --db aziende.db
    python score_biogas.py --db aziende.db --model qwen3:4b --batch 20
    python score_biogas.py --db aziende.db --export scores.csv
"""

import argparse
import json
import re
import sqlite3
import time
import csv
from datetime import datetime

import requests

# ── Configurazione ────────────────────────────────────────────────────────────

OLLAMA_GENERATE_URL = "http://localhost:11434/api/generate"
OLLAMA_CHAT_URL    = "http://localhost:11434/api/chat"
DEFAULT_MODEL = "qwen3:4b"
DELAY         = 2     # secondi tra una chiamata e l'altra
SOURCE        = "batch_scorer_v1"
LOG_FILE      = "score_debug.log"

SYSTEM_PROMPT = """Sei un analista esperto nel settore energetico italiano, 
specializzato in biogas, biometano e utilizzo di biomasse per la produzione 
di energia. Il tuo compito è valutare la rilevanza di un'azienda rispetto 
a questo settore ed alla possibilità che quella azienda abbia necessità 
di migliorare la matrice della biomassa utilizzata."""

USER_PROMPT_TEMPLATE = """Analizza le seguenti informazioni sull'azienda e valuta 
quanto è rilevante per il settore biometano / biomasse / biogas (impianti di produzione).

=== ANAGRAFICA ===
Ragione sociale : {name}
Codice ATECO    : {ateco_code}
Settore / Note  : {notes}

=== TESTI DISPONIBILI ===
{texts}

=== ISTRUZIONI ===
Restituisci ESCLUSIVAMENTE un oggetto JSON valido, senza testo aggiuntivo, 
con questa struttura esatta:
{{
  "score": <intero da 0 a 10>,
  "confidence": <float da 0.0 a 1.0>,
  "reasoning": "<stringa breve con la motivazione, max 2 frasi>"
}}

Criteri per lo score:
  0-2  : nessuna relazione con biogas/biometano/biomasse
  3-4  : settore energetico generico, possibile interesse indiretto
  5-6  : fornisce tecnologie, servizi o componenti usati nel settore
  7-8  : opera direttamente nel settore (impianti, gestione, O&M)
  9-10 : core business biogas/biometano/biomasse, produttore o sviluppatore di impianti

La confidence indica quanto sei certo della valutazione in base alla quantità
e qualità delle informazioni disponibili.

REGOLA IMPORTANTE: Se non ci sono testi disponibili (solo anagrafica e codice ATECO),
la confidence NON può superare 0.3 e lo score NON può superare 3.
Il codice ATECO da solo non è sufficiente per assegnare punteggi alti."""


# ── Gestione DB ───────────────────────────────────────────────────────────────

DDL_SCORES = """
CREATE TABLE IF NOT EXISTS company_scores (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id      INTEGER NOT NULL UNIQUE REFERENCES companies(id) ON DELETE CASCADE,
    score           INTEGER,
    confidence      REAL,
    reasoning       TEXT,
    model_used      TEXT,
    scored_at       TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_scores_company ON company_scores(company_id);
"""


def init_db(conn: sqlite3.Connection):
    conn.executescript(DDL_SCORES)
    conn.commit()


def get_companies(conn: sqlite3.Connection, only_new: bool) -> list[dict]:
    """Restituisce le aziende da processare."""
    if only_new:
        sql = """
            SELECT c.id, c.name, c.vat_number, c.ateco_code, c.notes
            FROM companies c
            LEFT JOIN company_scores cs ON cs.company_id = c.id
            WHERE cs.id IS NULL
            ORDER BY c.id
        """
    else:
        sql = "SELECT id, name, vat_number, ateco_code, notes FROM companies ORDER BY id"
    cur = conn.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_texts(conn: sqlite3.Connection, company_id: int) -> list[str]:
    """Raccoglie tutti i testi per un'azienda."""
    cur = conn.execute(
        "SELECT source, content FROM company_data WHERE company_id = ? AND content IS NOT NULL",
        (company_id,)
    )
    return [f"[{row[0]}] {row[1]}" for row in cur.fetchall()]


def save_score(conn: sqlite3.Connection, company_id: int, result: dict, model: str):
    conn.execute("""
        INSERT INTO company_scores (company_id, score, confidence, reasoning, model_used, scored_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(company_id) DO UPDATE SET
            score      = excluded.score,
            confidence = excluded.confidence,
            reasoning  = excluded.reasoning,
            model_used = excluded.model_used,
            scored_at  = excluded.scored_at
    """, (
        company_id,
        result.get("score"),
        result.get("confidence"),
        result.get("reasoning"),
        model,
        datetime.now().isoformat(timespec="seconds"),
    ))
    conn.commit()
MAX_TEXT_CHARS = 6000  # Truncate texts to avoid 500 errors from Ollama

# ── Chiamata Ollama ───────────────────────────────────────────────────────────

def call_ollama(prompt: str, model: str, retries: int = 2) -> str:
    for attempt in range(retries + 1):
        start = time.time()
        payload_chat = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 4096,
            }
        }
        try:
            resp = requests.post(OLLAMA_CHAT_URL, json=payload_chat, timeout=300)
            resp.raise_for_status()
            elapsed = time.time() - start
            data = resp.json()
            result = data.get("message", {}).get("content", "")
            print(f"({elapsed:.1f}s, {len(result)} chars) ", end="", flush=True)
            return result
        except requests.exceptions.ReadTimeout:
            elapsed = time.time() - start
            print(f"(TIMEOUT {elapsed:.0f}s) ", end="", flush=True)
            if attempt < retries:
                print(f"retry {attempt+1}... ", end="", flush=True)
                _reset_ollama(model)
                time.sleep(3)
                continue
            raise ValueError(f"Timeout dopo {elapsed:.0f}s")
        except Exception as e:
            elapsed = time.time() - start
            print(f"(ERR {elapsed:.1f}s: {e}) ", end="", flush=True)
            if attempt < retries:
                print(f"retry {attempt+1}... ", end="", flush=True)
                _reset_ollama(model)
                time.sleep(5)
                continue
            raise


def _reset_ollama(model: str):
    """Send a tiny request to reset model state after errors."""
    try:
        requests.post(OLLAMA_GENERATE_URL, json={
            "model": model, "prompt": "hi", "stream": False,
            "options": {"num_predict": 1}
        }, timeout=30)
    except Exception:
        pass


def parse_json_response(raw: str) -> dict:
    """Estrae il JSON dalla risposta del modello, anche se c'è testo intorno."""
    # Rimuovi eventuali blocchi <think>...</think> (qwen3 thinking mode)
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    # Greedy match per gestire correttamente oggetti JSON annidati
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError(f"Nessun JSON trovato nella risposta: {raw[:200]}")
    return json.loads(match.group())

# ── Logging ───────────────────────────────────────────────────────────────────

def write_log(company_name: str, prompt: str, raw_response: str, error: str = ""):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*80}\n")
        f.write(f"AZIENDA  : {company_name}\n")
        f.write(f"TIMESTAMP: {datetime.now().isoformat(timespec='seconds')}\n")
        f.write(f"{'─'*80}\n")
        f.write("PROMPT INVIATO:\n")
        f.write(prompt + "\n")
        f.write(f"{'─'*80}\n")
        f.write("RISPOSTA GREZZA:\n")
        f.write(raw_response + "\n")
        if error:
            f.write(f"{'─'*80}\n")
            f.write(f"ERRORE: {error}\n")
        f.write(f"{'='*80}\n")

def score_company(company: dict, texts: list[str], model: str) -> dict:
    # Check if company name contains biogas/biometano/biomassa keywords
    name_lower = (company.get("name") or "").lower()
    name_keywords = [kw for kw in ["biogas", "biometano", "biomassa", "biomasse", "bioenergia", "bioenergy", "bioenergie"]
                     if kw in name_lower]
    name_hint = ""
    if name_keywords:
        name_hint = f"\nNOTA: Il nome dell'azienda contiene le parole chiave: {', '.join(name_keywords)}. Questo è un forte indicatore di rilevanza per il settore."

    texts_block = "\n\n".join(texts) if texts else "(nessun testo disponibile)"
    if len(texts_block) > MAX_TEXT_CHARS:
        texts_block = texts_block[:MAX_TEXT_CHARS] + "\n\n[... testo troncato per lunghezza ...]"

    prompt = (
        USER_PROMPT_TEMPLATE.format(
            name       = company.get("name", ""),
            ateco_code = company.get("ateco_code") or "-",
            notes      = company.get("notes") or "-",
            texts      = texts_block,
        ) + name_hint
    )

    raw = ""
    try:
        raw = call_ollama(prompt, model)
        result = parse_json_response(raw)
        result["score"]      = max(0, min(10, int(result.get("score", 0))))
        result["confidence"] = max(0.0, min(1.0, float(result.get("confidence", 0.0))))
        write_log(company["name"], prompt, raw)          # ← log anche i successi
        return result
    except Exception as e:
        write_log(company["name"], prompt, raw, str(e))  # ← log con errore
        print(f"    ERRORE LLM: {e}")
        return {"score": None, "confidence": None, "reasoning": f"errore: {e}"}

# ── Export CSV ────────────────────────────────────────────────────────────────

def export_csv(conn: sqlite3.Connection, path: str):
    """
    Produce un CSV pronto per l'import nella tabella company_relevance.
    Colonne: company_id, score (normalizzato 0-1), confidence,
             note, source, created_at, updated_at
    """
    cur = conn.execute("""
        SELECT
            cs.company_id,
            ROUND(cs.score / 10.0, 4)   AS score,
            cs.confidence,
            cs.reasoning                AS note,
            cs.model_used               AS source,
            cs.scored_at                AS created_at,
            cs.scored_at                AS updated_at
        FROM company_scores cs
        ORDER BY score DESC, cs.confidence DESC
    """)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow(cols)
        writer.writerows(rows)

    print(f"CSV esportato: {path}  ({len(rows)} righe)")


# ── Main ──────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Score biogas/biometano via Ollama")
    p.add_argument("--db",      required=True,         help="Path al file SQLite")
    p.add_argument("--model",   default=DEFAULT_MODEL, help=f"Modello Ollama (default: {DEFAULT_MODEL})")
    p.add_argument("--batch",   type=int, default=0,   help="Limita a N aziende (0 = tutte)")
    p.add_argument("--rescore", action="store_true",   help="Ricalcola anche aziende già scorate")
    p.add_argument("--export",  default="",            help="Se specificato, esporta i risultati in questo CSV")
    return p.parse_args()


def main():
    args = parse_args()

    conn = sqlite3.connect(args.db)
    init_db(conn)

    companies = get_companies(conn, only_new=not args.rescore)

    if args.batch > 0:
        companies = companies[: args.batch]

    total = len(companies)
    print(f"Aziende da processare: {total}  |  modello: {args.model}\n")

    # Open incremental CSV output (append if exists)
    csv_path = args.export or "scores_incremental.csv"
    file_exists = False
    already_done = set()
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                file_exists = True
                cid = row.get("company_id", "").strip()
                if cid:
                    already_done.add(int(cid))
    except FileNotFoundError:
        pass

    if already_done:
        before = len(companies)
        companies = [c for c in companies if c["id"] not in already_done]
        print(f"Saltate {before - len(companies)} aziende già nel CSV ({csv_path})")
        total = len(companies)
        print(f"Rimaste da processare: {total}\n")

    csv_file = open(csv_path, "a", newline="", encoding="utf-8")
    csv_writer = csv.writer(csv_file, quoting=csv.QUOTE_ALL)
    if not file_exists:
        csv_writer.writerow(["company_id", "name", "vat_number", "score", "confidence", "reasoning"])

    for i, company in enumerate(companies, 1):
        texts = get_texts(conn, company["id"])
        print(f"[{i}/{total}] {company['name']}  ({len(texts)} testi) ...", end=" ", flush=True)

        result = score_company(company, texts, args.model)
        save_score(conn, company["id"], result, args.model)

        score_str = str(result["score"]) if result["score"] is not None else "ERR"
        conf_str  = f"{result['confidence']:.2f}" if result["confidence"] is not None else "ERR"
        print(f"score={score_str}  conf={conf_str}")

        # Write to CSV immediately
        csv_writer.writerow([
            company["id"], company["name"], company.get("vat_number", ""),
            result.get("score"), result.get("confidence"), result.get("reasoning", "")
        ])
        csv_file.flush()

        time.sleep(DELAY)

    csv_file.close()
    print(f"\nCompletato. Risultati salvati in company_scores e {csv_path}.")

    conn.close()


if __name__ == "__main__":
    main()