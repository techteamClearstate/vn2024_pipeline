"""READ-ONLY diagnostic: classify matched rows in the current mapped CSV by tier
and surface the residual error mechanisms (Trauma_Plating leaks, family-keyword
collisions, generic hs_prior fabrications). Nothing is written."""
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import settings as cfg

mp = pd.read_csv(cfg.MAPPED_CSV, dtype=str).fillna("")
m = mp[mp["Match_Status"] == "Matched"]
print(f"matched rows: {len(m):,} / {len(mp):,}")
print("\n=== by tier ===")
print(m["Match_Tier"].value_counts().to_string())

# hs_prior tier: which predicted Product_V0 values, and sample descriptions
hp = m[m["Match_Tier"] == "hs_prior"]
print(f"\n=== hs_prior fills: {len(hp):,} ===")
print(hp["Product_V0"].value_counts().head(30).to_string())

# family tier: short/generic family keywords that likely collide
fam = m[m["Match_Tier"] == "family"]
print(f"\n=== family fills: {len(fam):,}; top families ===")
print(fam["Family"].value_counts().head(30).to_string())

# targeted probes
probes = ["ACET", "LPS", "SHELL", "SURGICAL INSTRUMENT", "BLOOD BAG", "BLOOD GLUCOSE",
          "PLASTIC CLIP", "ECG ELECTRODE", "PESSARY", "HEALTH CARE KIT", "OXYGEN TERMINAL",
          "TEST STRIP", "GRIP", "BIOPROS"]
print("\n=== targeted probes (desc -> Product_V0 [tier]) ===")
for p in probes:
    hit = m[m["Detailed_Product"].str.upper().str.contains(re.escape(p), na=False)]
    for _, r in hit.head(2).iterrows():
        print(f"  [{r['Match_Tier']:9s}] {r['Detailed_Product'][:55]:55s} -> "
              f"{r['Product_V0']} | fam={r['Family']}")
