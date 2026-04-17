"""
Analizza le aziende estratte dai file markdown e genera un report JSON.

Usa un LLM per analizzare ogni azienda dal punto di vista di un business analyst
esperto nel settore biometano/biogas.
"""

import json
import sys
from pathlib import Path
from datetime import datetime

# Prompt per l'analisi
ANALYSIS_PROMPT = """# RUOLO
Sei un business analyst con grande esperienza come sviluppatore di progetti nel settore biometano con particolare riferimento all'ottimizzazione della matrice del feedstock.

# OBIETTIVO
Analizzare la descrizione della homepage di una azienda per:
1. Indicare quanto la sua attività sia attinente alla gestione di biomasse con l'obiettivo di produrre biometano (o in alternativa biogas)
2. Scrivere un sunto semplice e professionale dell'azienda stessa, 400-500 parole

# OUTPUT RICHIESTO
Rispondi SOLO con un JSON valido nel seguente formato (senza markdown, senza ```json):
{
  "relevance_score": <numero da 0 a 10, dove 10 = massima attinenza al settore biometano/biogas>,
  "relevance_confidence": <numero da 0.00 a 1.00, dove 1.00 = massima confidenza nello score prodotto sulla base della qualità e quantità di informazioni analizzate>,
  "relevance_explanation": "<breve spiegazione del punteggio in 2-3 frasi>",
  "company_summary": "<sunto professionale dell'azienda in 400-500 parole>"
}

# CONTENUTO AZIENDA DA ANALIZZARE
"""


def read_markdown_files(directory: str = "markdown_output") -> dict:
    """Legge tutti i file markdown dalla directory."""
    md_dir = Path(directory)
    
    if not md_dir.exists():
        print(f"Errore: directory {directory} non trovata")
        sys.exit(1)
    
    files = list(md_dir.glob("*.md"))
    
    if not files:
        print(f"Errore: nessun file .md trovato in {directory}")
        sys.exit(1)
    
    print(f"Trovati {len(files)} file markdown\n")
    
    content_map = {}
    for file_path in files:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            content_map[file_path.stem] = {
                "filename": file_path.name,
                "content": content
            }
    
    return content_map


def extract_vat_from_markdown(content: str) -> str:
    """Estrae il VAT number dal markdown."""
    import re
    match = re.search(r"\*\*VAT Number\*\*:\s*(.+)", content)
    if match:
        vat_text = match.group(1).strip()
        # Estrai solo i numeri
        vat_match = re.search(r"(\d{11})", vat_text)
        if vat_match:
            return vat_match.group(1)
    return ""


def extract_url_from_markdown(content: str) -> str:
    """Estrae l'URL dal markdown."""
    import re
    match = re.search(r"\*\*URL\*\*:\s*(.+)", content)
    if match:
        return match.group(1).strip()
    return ""


def analyze_with_llm(company_content: str) -> dict:
    """
    Analizza il contenuto dell'azienda usando Ollama locale con streaming.
    
    Usa il modello qwen2.5:3b su porta 11434.
    """
    import requests
    
    # Prepara il prompt completo
    full_prompt = ANALYSIS_PROMPT + "\n\n" + company_content
    
    # Chiamata a Ollama con streaming (usa /api/generate per Ollama 0.20.4)
    ollama_url = "http://localhost:11434/api/generate"
    
    payload = {
        "model": "qwen2.5:3b",
        "prompt": full_prompt,
        "stream": True,
        "options": {
            "temperature": 0.3,
            "top_p": 0.9
        }
    }
    
    try:
        print("  Chiamata a Ollama (qwen2.5:3b) - streaming attivo...")
        print("  " + "-" * 70)
        
        response = requests.post(ollama_url, json=payload, stream=True, timeout=180)
        response.raise_for_status()
        
        # Accumula la risposta mentre fa streaming
        full_response = ""
        
        for line in response.iter_lines():
            if line:
                chunk = json.loads(line)
                token = chunk.get("response", "")
                full_response += token
                
                # Stampa il token in tempo reale
                print(token, end="", flush=True)
                
                # Se done, esci
                if chunk.get("done", False):
                    break
        
        print("\n  " + "-" * 70)
        
        # Parse JSON dalla risposta completa
        llm_output = full_response.strip()
        
        # Rimuovi eventuali markdown code blocks
        if llm_output.startswith("```json"):
            llm_output = llm_output[7:]
        if llm_output.startswith("```"):
            llm_output = llm_output[3:]
        if llm_output.endswith("```"):
            llm_output = llm_output[:-3]
        llm_output = llm_output.strip()
        
        # Parse JSON
        analysis = json.loads(llm_output)
        
        print(f"  Score rilevanza: {analysis.get('relevance_score', 'N/A')}/10")
        
        return analysis
        
    except requests.exceptions.ConnectionError:
        print("  Errore: Ollama non raggiungibile su localhost:11434")
        print("  Assicurati che Ollama sia in esecuzione: ollama serve")
        return {
            "relevance_score": 0,
            "relevance_explanation": "Errore: Ollama non disponibile",
            "company_summary": "Analisi non completata - Ollama non raggiungibile"
        }
    except requests.exceptions.HTTPError as e:
        print(f"  Errore HTTP: {e}")
        print("  Il modello qwen2.5:3b potrebbe non essere installato.")
        print("  Scaricalo con: ollama pull qwen2.5:3b")
        return {
            "relevance_score": 0,
            "relevance_explanation": "Errore: modello non disponibile",
            "company_summary": "Analisi non completata - modello non trovato"
        }
    except json.JSONDecodeError as e:
        print(f"\n  Errore parsing JSON: {e}")
        print(f"  Output LLM: {llm_output[:200]}...")
        return {
            "relevance_score": 0,
            "relevance_explanation": "Errore parsing risposta LLM",
            "company_summary": "Analisi non completata - errore formato risposta"
        }
    except Exception as e:
        print(f"\n  Errore: {e}")
        return {
            "relevance_score": 0,
            "relevance_explanation": f"Errore durante analisi: {str(e)}",
            "company_summary": "Analisi non completata"
        }


def create_analysis_report(content_map: dict) -> dict:
    """Crea il report di analisi per tutte le aziende."""
    
    report = {
        "analysis_date": datetime.now().isoformat(),
        "total_companies": len(content_map),
        "companies": []
    }
    
    for idx, (company_id, data) in enumerate(content_map.items(), 1):
        print(f"[{idx}/{len(content_map)}] Analisi: {data['filename']}")
        
        # Estrai metadati
        vat_number = extract_vat_from_markdown(data["content"])
        url = extract_url_from_markdown(data["content"])
        
        print(f"  URL: {url}")
        print(f"  VAT: {vat_number}")
        
        # Analizza con LLM
        analysis = analyze_with_llm(data["content"])
        
        # Aggiungi al report
        company_report = {
            "company_id": company_id,
            "filename": data["filename"],
            "url": url,
            "vat_number": vat_number,
            "analysis": analysis
        }
        
        report["companies"].append(company_report)
        print()
    
    return report


def main():
    print("Analisi aziende da file markdown")
    print("Usando Ollama locale (qwen2.5:3b) su localhost:11434\n")
    print("=" * 60)
    print()
    
    # Leggi file markdown
    content_map = read_markdown_files()
    
    # Crea report
    report = create_analysis_report(content_map)
    
    # Salva JSON
    output_file = f"company_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print("=" * 60)
    print(f"\nReport salvato: {output_file}")
    print(f"Aziende analizzate: {report['total_companies']}")
    
    # Statistiche
    scores = [c["analysis"]["relevance_score"] for c in report["companies"] if isinstance(c["analysis"]["relevance_score"], (int, float))]
    if scores:
        avg_score = sum(scores) / len(scores)
        print(f"Score medio rilevanza: {avg_score:.1f}/10")
        print(f"Score minimo: {min(scores)}/10")
        print(f"Score massimo: {max(scores)}/10")


if __name__ == "__main__":
    main()
