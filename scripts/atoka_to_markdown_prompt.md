# TASK: Converti contenuti Atoka scraped in Markdown strutturato

## CONTESTO
Riceverai in input un file CSV (`atoka_companies_content.csv`) con le seguenti colonne:
- `vat_number` - Partita IVA
- `name` - Nome azienda
- `source_url` - URL pagina Atoka
- `content` - Testo grezzo estratto dalla pagina Atoka (escaped: `\n` = newline, `\t` = tab)

Il campo `content` contiene il testo completo della pagina Atoka di ogni azienda, incluso molto rumore (menu, CTA, promo). Il tuo compito e' estrarre solo le informazioni utili e strutturarle in Markdown pulito.

## SEZIONI DA ESTRARRE

Dal content grezzo, identifica e estrai SOLO queste sezioni (se presenti):

### 1. Dati Societari
Cerca blocchi con: RICAVI, TREND RICAVI, P.IVA, C. ATECO, DIPENDENTI, ANZIANITA.
```markdown
## Dati Societari
- Sede legale: [indirizzo]
- P.IVA: [numero]
- Codice ATECO: [codice] - [descrizione]
- Ricavi: [importo]
- Trend ricavi: [valore]
- Dipendenti: [numero]
- Anzianita: [anni]
```

### 2. Descrizione
Cerca il blocco che inizia con "Descrizione di [Nome Azienda]". Contiene l'oggetto sociale.
```markdown
## Descrizione
[Testo della descrizione, pulito e leggibile]
```

### 3. Parole Chiave
Lista di keyword, una per riga nel content originale.
```markdown
## Parole Chiave
- keyword1
- keyword2
- keyword3
```

### 4. Ambito Operativo
Cerca "Ambito Operativo" o "Ambito di Attivita". Descrive macrosettore e classificazione ATECO.
```markdown
## Ambito Operativo
[Testo descrittivo]
```

### 5. Altri Nomi
Cerca "Altri Nomi" o "Denominazioni". Lista di nomi alternativi dell'azienda.
```markdown
## Altri Nomi
- nome1
- nome2
```

### 6. Categoria d'Impresa
Cerca "Categoria d'Impresa" o "Classificazione per Dimensione". Indica micro/piccola/media/grande impresa.
```markdown
## Categoria d'Impresa
[Testo classificazione]
```

### 7. Aziende Simili
Cerca "Aziende simili" o "Aziende Correlate". Lista di aziende con citta e provincia.
```markdown
## Aziende Simili
- Azienda1 (Citta, Provincia)
- Azienda2 (Citta, Provincia)
```

## REGOLE DI PULIZIA

1. RIMUOVI tutto il rumore: menu di navigazione, "Overview", "Persone", "Valutazioni", "News e media", "Vedi piu informazioni", "Vedi altri contatti", "Iscriviti ora gratuitamente", "PROVA ORA GRATIS", "Accedi a tutte le informazioni...", "Affidabilita creditizia...", blocchi promo Cerved
2. RIMUOVI riferimenti a persone: nomi, email, telefoni di amministratori/contatti
3. RIMUOVI sezioni vuote o con solo testo promozionale
4. MANTIENI solo informazioni fattuali sull'azienda
5. Se una sezione non e' presente nel content, omettila dal markdown
6. Pulisci il testo: rimuovi numerazione iniziale tipo "1." o "3.1" dall'oggetto sociale, normalizza spazi

## FORMATO OUTPUT

Produci un JSON con questa struttura:

```json
{
  "total_records": 507,
  "records": [
    {
      "vat_number": "02673550980",
      "name": "3R Energia Srl",
      "source_url": "https://atoka.io/...",
      "markdown_content": "## Dati Societari\n- Sede legale: Via Aldo Moro, 28, 25043, Breno (BS)\n- P.IVA: 02673550980\n..."
    }
  ]
}
```

Il campo `markdown_content` deve contenere il Markdown strutturato con le sezioni trovate, separate da doppio newline.

## ESEMPIO COMPLETO

### Input (content grezzo escaped):
```
3R Energia Srl\nSede legale: Via Aldo Moro, 28, 25043, Breno (BS)\nP.IVA: 02673550980\n71.12: Attivita degli studi d'ingegneria\nOverview\nAziende simili\nPersone\nValutazioni\nNews e media\nDati societari di\n3R Energia Srl\nRICAVI\n1.7 M\nTREND RICAVI\n-55.4%\nP.IVA\n02673550980\nC. ATECO\n71.12\nDIPENDENTI\n11\nANZIANITA\n20 anni\nVedi piu informazioni\n...PROVA ORA GRATIS\nDescrizione di 3R Energia Srl\nLa societa ha per oggetto l'esercizio delle seguenti attivita: ...\nParole chiave\nEnergia\nProgettazione\n...
```

### Output (markdown_content):
```markdown
## Dati Societari
- Sede legale: Via Aldo Moro, 28, 25043, Breno (BS)
- P.IVA: 02673550980
- Codice ATECO: 71.12 - Attivita degli studi d'ingegneria ed altri studi tecnici
- Ricavi: 1.7 M
- Trend ricavi: -55.4%
- Dipendenti: 11
- Anzianita: 20 anni

## Descrizione
La societa ha per oggetto l'esercizio delle seguenti attivita: l'esercizio dell'attivita di fornitura di servizi, progettazioni, ricerche e consulenze...

## Parole Chiave
- Energia
- Progettazione
```

## ISTRUZIONI FINALI

1. Leggi il file CSV allegato (`atoka_companies_content.csv`)
2. Per ogni riga, decodifica il campo `content` (sostituisci `\n` con newline reali, `\t` con tab)
3. Identifica e estrai le sezioni secondo le regole sopra
4. Genera il Markdown strutturato per ogni azienda
5. Restituisci SOLO il JSON finale, nessun testo aggiuntivo

Se il content di una riga e' vuoto o contiene solo rumore (es. solo "PROVA ORA GRATIS"), imposta `markdown_content` a stringa vuota `""`.

---

**FILE IN INPUT**: `atoka_companies_content.csv` (allegato)
**OUTPUT ATTESO**: JSON con tutti i record convertiti in Markdown strutturato
