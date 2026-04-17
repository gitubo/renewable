"""
Clean Unicode escape sequences from company_data.csv that Postgres rejects.
Replaces \\uXXXX sequences with the actual Unicode characters.

Usage: python scripts/clean_csv_unicode.py
"""
import re
import os

CSV_PATH = os.path.join("supabase", "data", "company_data.csv")

with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
    content = f.read()

# Replace literal \uXXXX sequences with actual Unicode chars
def replace_escape(match):
    try:
        return chr(int(match.group(1), 16))
    except (ValueError, OverflowError):
        return match.group(0)  # keep original if invalid

cleaned = re.sub(r'\\u([0-9a-fA-F]{4})', replace_escape, content)

# Also remove null bytes which Postgres hates
cleaned = cleaned.replace('\x00', '')

with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
    f.write(cleaned)

original_len = len(content)
cleaned_len = len(cleaned)
print(f"Cleaned {CSV_PATH}")
print(f"  Before: {original_len} chars")
print(f"  After:  {cleaned_len} chars")
print(f"  Diff:   {original_len - cleaned_len} chars removed/replaced")
