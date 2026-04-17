# Biomassa CRM

CRM per la gestione di aziende nel settore biogas/biometano/biomasse in Italia.

## Architettura

- **Frontend**: Vanilla JS + Tailwind CSS (servito da GitHub Pages)
- **Database**: Supabase (Postgres, free tier)
- **Script offline**: Python (scoring LLM, scraping, pipeline dati)

## Setup

### Frontend
Il frontend è nella cartella `docs/` e viene servito automaticamente da GitHub Pages.

Per sviluppo locale:
```bash
npx serve docs
```

### Configurazione Supabase
Modifica `docs/src/config.js` con URL e anon key del tuo progetto Supabase.

### Script Python
Gli script offline sono in `scripts/`. Richiedono Python 3.10+ e le dipendenze:
```bash
pip install supabase requests
```

## Struttura

```
docs/           Frontend (GitHub Pages)
scripts/        Script Python offline (pipeline, scraping, scoring)
csv/            Dati di lavoro (non in git)
markdown_output/ Output scraping (non in git)
```
