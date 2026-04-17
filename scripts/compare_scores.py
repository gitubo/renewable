import csv
from collections import Counter

def load_scores(filepath):
    scores = {}
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            cid = row['company_id'].strip()
            score_raw = row['score'].strip()
            if score_raw == '' or not score_raw.replace('.','').replace('-','').isdigit():
                continue
            scores[cid] = int(float(score_raw))
    return scores

file1 = 'scores_incremental.csv'
file2 = 'company_score_biomass.csv'

scores1 = load_scores(file1)
scores2 = load_scores(file2)

common_ids = set(scores1.keys()) & set(scores2.keys())
print(f"Companies in {file1}: {len(scores1)}")
print(f"Companies in {file2}: {len(scores2)}")
print(f"Companies in common (used for comparison): {len(common_ids)}")
print()

exact_match = 0
approx_match = 0  # within +/-1
diffs = []

for cid in common_ids:
    s1 = scores1[cid]
    s2 = scores2[cid]
    diff = s1 - s2
    diffs.append(diff)
    if s1 == s2:
        exact_match += 1
    if abs(s1 - s2) <= 1:
        approx_match += 1

print(f"--- Score Comparison (on {len(common_ids)} common companies) ---")
print(f"Exact match (same score):        {exact_match} ({exact_match/len(common_ids)*100:.1f}%)")
print(f"Approx match (within +/-1):      {approx_match} ({approx_match/len(common_ids)*100:.1f}%)")
print()

# Distribution of score differences
diff_counter = Counter(diffs)
print("--- Distribution of score differences (file1 - file2) ---")
for d in sorted(diff_counter.keys()):
    print(f"  diff={d:+d}: {diff_counter[d]} companies")
print()

# Score distributions per file
print(f"--- Score distribution in {file1} (common companies only) ---")
dist1 = Counter(scores1[cid] for cid in common_ids)
for s in sorted(dist1.keys()):
    print(f"  score={s}: {dist1[s]}")
print()

print(f"--- Score distribution in {file2} (common companies only) ---")
dist2 = Counter(scores2[cid] for cid in common_ids)
for s in sorted(dist2.keys()):
    print(f"  score={s}: {dist2[s]}")
