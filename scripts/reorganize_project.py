"""
Reorganize project structure for GitHub Pages deployment.
Run from project root: python scripts/reorganize_project.py
"""
import shutil
import os
import glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

def mv(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.exists(src):
        shutil.move(src, dst)
        print(f"  MOVE {src} → {dst}")

def rm(path):
    if os.path.isdir(path):
        shutil.rmtree(path)
        print(f"  DEL  {path}/")
    elif os.path.isfile(path):
        os.remove(path)
        print(f"  DEL  {path}")

# ── 1. Move frontend → docs (for GitHub Pages) ──
print("\n=== Move frontend to docs ===")
# Remove existing docs content first (specifica_db_import.md)
if os.path.exists("docs"):
    # Save existing docs files
    for f in glob.glob("docs/*"):
        if os.path.isfile(f):
            mv(f, f"scripts/{os.path.basename(f)}")
    shutil.rmtree("docs")

# Move frontend content to docs
os.makedirs("docs", exist_ok=True)
mv("frontend/index.html", "docs/index.html")
if os.path.exists("frontend/src"):
    shutil.copytree("frontend/src", "docs/src")
    print("  COPY frontend/src/ → docs/src/")

# ── 2. Move all Python scripts to scripts/ ──
print("\n=== Move scripts to scripts/ ===")
scripts_to_move = [
    "score_biogas.py", "analyze_companies.py",
    "step_0_get_info_by_ateco.py", "step_1_deduplication.py",
    "step_2_get_details.py", "step_3_concatenate.py",
    "step_4_filter_relevant_company.py", "step_5_intelligence.py",
    "step_6_atoka.py",
    "scrape_atoka_by_url.py", "scrape_atoka.py", "scrape_to_markdown.py",
    "scraper_atoka.py", "scraper_elettricita_futura.py",
    "scraper_registroaziende_by_url.py",
    "convert_atoka_to_markdown.py",
    "export_atoka_companies.py", "export_missing_homepage_data.py",
    "extract_biometano_companies.py",
    "find_company_homepage.py",
    "import_atoka_markdown.py", "import_markdown_to_db.py",
    "import_scores.py",
    "split_atoka_output.py",
    "clean_csv.py", "compare_scores.py", "_prep_csv.py",
    "analyze_company_prompt.md", "atoka_to_markdown_prompt.md",
]
for f in scripts_to_move:
    if os.path.exists(f):
        mv(f, f"scripts/{f}")

# ── 3. Move CSVs + atoka_cache to csv/ ──
print("\n=== Move CSVs to csv/ ===")
os.makedirs("csv", exist_ok=True)
for f in glob.glob("*.csv"):
    mv(f, f"csv/{os.path.basename(f)}")
if os.path.exists("atoka_cache.json"):
    mv("atoka_cache.json", "csv/atoka_cache.json")

# ── 4. Delete obsolete directories ──
print("\n=== Delete obsolete directories ===")
for d in ["app", "backend", "tests", "config", "db", "pipeline", "wrappers",
          "supabase", "frontend", ".hypothesis", ".pytest_cache"]:
    rm(d)

# ── 5. Delete obsolete files ──
print("\n=== Delete obsolete files ===")
for f in ["biogas.db", "aziende.db", "requirements.txt", "score_debug.log",
          "=", "atoka_companies_content_to_markdown.json"]:
    rm(f)

print("\n=== Done ===")
print("Project reorganized. Run 'ls' to verify.")
