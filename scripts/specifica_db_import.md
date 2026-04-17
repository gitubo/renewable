# Specifica Database e Import — Biogas CRM

## 1. Architettura Generale

```
Script batch esterni → CSV unificato → Import (CLI o Web) → SQLite DB → Web App CRM
```

Gli script batch (step_0..step_6 e futuri) girano indipendentemente, producono CSV.
L'import carica i dati nel DB. La web app li visualizza e permette gestione CRM.

---

## 2. Schema Database

### 2.1 `companies` — Anagrafica aziende

| Campo | Tipo | Note |
|-------|------|------|
| id | INTEGER PK | Auto-increment |
| vat_number | TEXT UNIQUE NOT NULL | Partita IVA — chiave di business |
| name | TEXT NOT NULL | Ragione sociale |
| ateco_code | TEXT | Codice ATECO |
| region | TEXT | Regione |
| county | TEXT | Provincia |
| city | TEXT | Città |
| address | TEXT | Indirizzo (solo via/numero) |
| employees | TEXT | Stringa informativa ("100-199", "più di 1000", "-") |
| website_url | TEXT | Sito web |
| phone | TEXT | Telefono |
| company_type | TEXT | Tipo azienda (libero) |
| relevance_level | TEXT | Livello rilevanza (libero) |
| notes | TEXT | Note libere |
| crm_status | TEXT DEFAULT 'nuovo' | Stato pipeline CRM |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

**Stati CRM:** nuovo → contattato → interessato → in_trattativa → cliente | non_interessato

**Popolata da:** Import CSV `output_scored.csv` (anagrafica iniziale).

### 2.2 `company_data` — Dati estratti (append-only)

Sostituisce le attuali `company_intelligence` e `company_enrichments`.

| Campo | Tipo | Note |
|-------|------|------|
| id | INTEGER PK | Auto-increment |
| company_id | INTEGER FK → companies(id) ON DELETE CASCADE | |
| source | TEXT NOT NULL | Chi ha prodotto il dato ("atoka", "ollama/qwen2.5:3b", "web_scraper", "manual") |
| content | TEXT | Il dato grezzo — testo libero, qualsiasi lunghezza |
| source_url | TEXT | URL di provenienza (nullable) |
| note | TEXT | Annotazione libera (nullable) |
| created_at | TIMESTAMP DEFAULT now | |

**Regole:**
- Append-only: non si cancella mai, si aggiunge sempre
- N righe per azienda, da fonti diverse in momenti diversi
- Nessun vincolo di unicità (stessa azienda + stessa source = ok, sono passaggi diversi)

**Popolata da:** Import CSV unificato (vedi sezione 3).

### 2.3 `company_relevance` — Indice di rilevanza (1 per azienda)

| Campo | Tipo | Note |
|-------|------|------|
| id | INTEGER PK | Auto-increment |
| company_id | INTEGER FK → companies(id) ON DELETE CASCADE UNIQUE | Una sola riga per azienda |
| score | REAL | 0-1, punteggio di rilevanza |
| confidence | REAL | 0-1, affidabilità del punteggio |
| note | TEXT | Annotazione libera (nullable) |
| source | TEXT | Chi/cosa ha calcolato ("batch_scorer_v1", "manual") |
| created_at | TIMESTAMP | Prima creazione |
| updated_at | TIMESTAMP | Ultimo aggiornamento |

**Regole:**
- UNIQUE su company_id — una sola riga per azienda
- Calcolata da batch separato che elabora `company_data`
- UPSERT: se esiste aggiorna score/confidence/updated_at, se no inserisce
- NON viene importata da CSV — è sempre calcolata

### 2.4 `tags` — Ontologia tag

| Campo | Tipo | Note |
|-------|------|------|
| id | INTEGER PK | |
| name | TEXT UNIQUE | "biogas", "biometano", "produttore", "epc" |
| category | TEXT | "settore", "ruolo_filiera", "tecnologia" |
| created_at | TIMESTAMP | |

**Regole:**
- Vocabolario controllato
- Gestibile da frontend (CRUD)
- Popolata inizialmente con seed, poi estendibile

### 2.5 `company_tags` — Tag assegnati alle aziende (N:N)

| Campo | Tipo | Note |
|-------|------|------|
| id | INTEGER PK | |
| company_id | INTEGER FK → companies(id) ON DELETE CASCADE | |
| tag_id | INTEGER FK → tags(id) ON DELETE CASCADE | |
| source | TEXT | "batch_tagger", "manual", "ollama/qwen2.5:3b" |
| confidence | REAL | 0-1 (nullable, per tag AI) |
| created_at | TIMESTAMP | |
| UNIQUE(company_id, tag_id) | | Un tag per azienda, una sola volta |

**Regole:**
- UPSERT su (company_id, tag_id): se il batch rigira, aggiorna confidence e source
- L'utente può aggiungere/rimuovere tag manualmente (source="manual")

### 2.6 `contacts` — Contatti persone (invariata)

| Campo | Tipo | Note |
|-------|------|------|
| id | INTEGER PK | |
| company_id | INTEGER FK → companies(id) ON DELETE CASCADE | |
| name | TEXT NOT NULL | |
| role | TEXT | |
| email | TEXT | |
| phone | TEXT | |
| linkedin_url | TEXT | |
| notes | TEXT | |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

### 2.7 `activities` — Log interazioni CRM (invariata)

| Campo | Tipo | Note |
|-------|------|------|
| id | INTEGER PK | |
| company_id | INTEGER FK → companies(id) ON DELETE CASCADE | |
| activity_type | TEXT NOT NULL | "email_inviata", "telefonata", "meeting", "linkedin", "nota", "altro" |
| subject | TEXT | Oggetto |
| description | TEXT | Dettagli |
| contact_name | TEXT | Persona coinvolta |
| activity_date | TIMESTAMP | Data dell'interazione |
| created_at | TIMESTAMP | |

---

## 3. Formato CSV Unificato per `company_data`

### 3.1 Struttura

```csv
"vat_number","source","content","source_url","note"
```

5 colonne, tutte stringhe, quote-all:

| Colonna | Obbligatoria | Descrizione |
|---------|-------------|-------------|
| vat_number | Sì | Partita IVA — unico identificativo noto agli script |
| source | Sì | Identificativo della fonte/tool |
| content | No | Dato grezzo (testo libero) |
| source_url | No | URL di provenienza (vuoto se non applicabile) |
| note | No | Annotazione libera |

### 3.2 Regole di import

1. Legge il CSV riga per riga
2. Per ogni riga, cerca `company_id` dal `vat_number` nella tabella `companies`
3. Se trovato → INSERT in `company_data` (con company_id risolto)
4. Se non trovato → skip + log warning ("P.IVA XXXXX non presente in companies")
5. Append-only: non cancella mai dati esistenti
6. Righe con `content` vuoto vengono comunque inserite (possono avere solo source_url o note)
7. Il campo `created_at` è sempre NOW() al momento dell'import

### 3.3 Wrapper step_5 (intelligence → company_data)

Input: `output_scored.csv` con colonne `piva, score, sources, confidence, motivazione, come_approcciarla`

Mapping:
```
vat_number   = piva
source       = "ollama/qwen2.5:3b"  (o il modello usato, parametrizzabile)
content      = motivazione
source_url   = sources
note         = come_approcciarla
```

I campi `score` e `confidence` del CSV originale NON vanno in `company_data`.
Verranno usati dal batch di calcolo `company_relevance` separatamente.

### 3.4 Wrapper step_6 (atoka → company_data)

Input: `output_aziende_atoka.csv` con colonne `vat_number, found, description, source`

Pre-filtro: solo righe con `found = "Y"`

Mapping:
```
vat_number   = vat_number
source       = "atoka"
content      = description
source_url   = source  (colonna "source" del CSV atoka)
note         = ""
```

### 3.5 Template per script futuri

Qualsiasi nuovo script batch deve produrre un CSV con esattamente queste 5 colonne:

```csv
"vat_number","source","content","source_url","note"
"12345678901","nome_script_v1","Testo estratto...","https://fonte.example.com","Eventuale nota"
```

L'import funziona senza modifiche.

---

## 4. Import Anagrafica Aziende

L'import da `output_scored.csv` resta separato perché popola `companies` (anagrafica), non `company_data`.

Formato: il CSV attuale con colonne `piva, ragione_sociale, codice_ateco, regione, provincia, citta, indirizzo, dipendenti, ...`

Comportamento:
- Nuove aziende (vat_number non presente) → INSERT
- Aziende esistenti → l'utente sceglie se sovrascrivere (DELETE + re-INSERT) o saltare
- La sovrascrittura cancella anche tutti i dati collegati (CASCADE)

---

## 5. Calcolo Relevance (batch separato)

Il batch di calcolo `company_relevance`:

1. Legge tutti i `company_data` per ogni azienda
2. Applica un algoritmo (da definire) per calcolare score e confidence
3. Fa UPSERT in `company_relevance` (una riga per azienda)
4. Opzionalmente assegna tag in `company_tags`

Questo batch NON è un import CSV — è un processo che legge e scrive nel DB.

---

## 6. Calcolo Tag (batch separato)

Il batch tagger:

1. Legge `company_data` + eventualmente `companies` (anagrafica)
2. Per ogni azienda, determina i tag applicabili dall'ontologia `tags`
3. Fa UPSERT in `company_tags` con confidence e source
4. Tag manuali (source="manual") non vengono sovrascritti dal batch

---

## 7. Riepilogo Flussi

```
                    ┌─────────────────────┐
                    │  Script Batch       │
                    │  (step_0..step_6)   │
                    └────────┬────────────┘
                             │ CSV
                    ┌────────▼────────────┐
                    │  Wrapper            │
                    │  (adatta formato)   │
                    └────────┬────────────┘
                             │ CSV unificato (5 colonne)
                    ┌────────▼────────────┐
                    │  Import company_data│
                    │  (CLI o Web)        │
                    └────────┬────────────┘
                             │
                    ┌────────▼────────────┐
                    │  SQLite DB          │
                    │  ├── companies      │
                    │  ├── company_data   │◄── append-only
                    │  ├── company_relevance│◄── batch scorer
                    │  ├── tags           │
                    │  ├── company_tags   │◄── batch tagger
                    │  ├── contacts       │◄── manuale (CRM)
                    │  └── activities     │◄── manuale (CRM)
                    └────────┬────────────┘
                             │
                    ┌────────▼────────────┐
                    │  Web App CRM        │
                    │  (FastAPI + SPA)    │
                    └─────────────────────┘
```


---

## 8. Wrapper Scripts

### 8.1 `wrappers/wrap_step5.py`

```bash
python wrappers/wrap_step5.py output_scored.csv output_step5_data.csv --source "ollama/qwen2.5:3b"
```

### 8.2 `wrappers/wrap_step6.py`

```bash
python wrappers/wrap_step6.py output_aziende_atoka.csv output_step6_data.csv
```

### 8.3 Flusso completo di import

```bash
# 1. Import anagrafica (step_4 output)
#    Via web: Import CSV → sezione "Import Anagrafica Aziende"
#    Checkbox "Sovrascrivi" per decidere se aggiornare aziende esistenti

# 2. Converti output step_5 e step_6 in formato unificato
python wrappers/wrap_step5.py output_scored.csv output_step5_data.csv
python wrappers/wrap_step6.py output_aziende_atoka.csv output_step6_data.csv

# 3. Import dati estratti
#    Via web: Import CSV → sezione "Import Dati Estratti"
#    Append-only, carica output_step5_data.csv e output_step6_data.csv
```
