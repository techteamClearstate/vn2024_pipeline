"""
Supervised recall expansion from the human-labeled Client-Ready ground truth.

We hold out a deterministic TEST split of the GT and mine brand/maker knowledge
from the TRAIN split ONLY, so the recall gain the eval reports on the held-out
split is honest generalization (we learn brand STRINGS a lexicon lacked, not
per-row answers).

Outputs (consumed by step1_extract when cfg.USE_BENCHMARK_HARVEST):
  * harvest_keywords.pkl       kw → {Segment, Sub-segment, Product, Player, Family_Name}
  * harvest_manufacturers.pkl  [(core, canonical), …]  (extra Tier-3 aliases)
  * benchmark_test_jk.csv       the held-out join keys (eval restricts to these)

A brand is only harvested when it is frequent (≥ MIN_ROWS train rows), literally
present in its rows' descriptions (≥ MIN_OCCUR), and resolves to one dominant
OU_Device (purity ≥ MIN_PURITY) — guards that protect trie precision.
"""
import hashlib
import pickle
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import settings as cfg
from tools.eval_benchmark import STOP

GT_CSV = cfg.INTERMEDIATE / "benchmark_gt_2024.csv"

# Generic label values that are never a usable brand keyword.
BAD = {"", "nan", "none", "unspecified", "other", "others", "standard", "manual",
       "generic", "n a", "na", "various", "assorted"}


def norm(s) -> str:
    s = re.sub(r"[^a-z0-9]+", " ", str(s).lower())
    return re.sub(r"\s+", " ", s).strip()


def is_test(jk: str) -> bool:
    """Deterministic, salt-free hash split so train/test is stable across runs."""
    h = int(hashlib.md5(jk.encode("utf-8")).hexdigest(), 16)
    return (h % 1000) < int(cfg.HARVEST_TEST_FRAC * 1000)


def load_gt() -> pd.DataFrame:
    gt = pd.read_csv(GT_CSV, dtype=str)
    gt["value"] = pd.to_numeric(gt["value"], errors="coerce").astype("Int64")
    gt["hs_code"] = pd.to_numeric(gt["hs_code"], errors="coerce").astype("Int64")
    gt["jk"] = (gt["desc_key"] + "|" + gt["hs_code"].astype(str)
                + "|" + gt["value"].astype(str))
    gt = gt.dropna(subset=["jk"])
    gt["test"] = gt["jk"].map(is_test)
    return gt


def _viable_kw(kw: str) -> bool:
    if len(kw) < cfg.MIN_KEYWORD_LEN or kw in BAD or kw in STOP:
        return False
    if kw in cfg.BLACKLIST:
        return False
    if re.fullmatch(r"[\d ]+", kw):          # pure numbers/spaces
        return False
    return bool(re.search(r"[a-z]", kw))     # must carry a letter


def harvest_keywords(train: pd.DataFrame) -> dict:
    """Mine Family Name → dominant (OU, OU_Device, Manufacturer) brand entries."""
    out = {}
    kept = dropped = 0
    for fam, g in train.groupby(train["Family Name"].map(norm)):
        if not _viable_kw(fam) or len(g) < cfg.HARVEST_MIN_ROWS:
            continue
        # literal presence in the description column the trie actually scans
        desc = g[cfg.VN_DESCRIPTION_COL].fillna("").str.lower()
        occur = desc.str.contains(re.escape(fam), regex=True).mean()
        if occur < cfg.HARVEST_MIN_OCCUR:
            dropped += 1
            continue
        dev = g["OU_Device"].dropna()
        if dev.empty:
            continue
        dom_dev, n_dev = Counter(dev).most_common(1)[0]
        if n_dev / len(g) < cfg.HARVEST_MIN_PURITY:
            dropped += 1
            continue
        ou = Counter(g["OU"].dropna()).most_common(1)
        mfr = Counter(g["Manufacturer Name"].dropna()).most_common(1)
        # original-case family label for display (first non-null raw value)
        raw_fam = next((x for x in g["Family Name"] if pd.notna(x)), fam)
        out[fam] = {
            "Segment":     ou[0][0] if ou else "",
            "Sub-segment": "",
            "Product":     str(dom_dev),
            "Player":      mfr[0][0] if mfr else "",
            "Family_Name": str(raw_fam).strip(),
        }
        kept += 1
    print(f"  [harvest] keywords: kept {kept:,}  (dropped {dropped:,} on "
          f"occurrence/purity guards)")
    return out


def harvest_manufacturers(train: pd.DataFrame) -> list:
    """Mine Manufacturer Name → alias core (the maker name itself), as extra
    Tier-3 aliases. Conservative: ≥5 rows, ≥5-char core carrying a letter."""
    seen = {}
    for mfr, g in train.groupby(train["Manufacturer Name"].map(norm)):
        if mfr in BAD or len(mfr) < 5 or len(g) < max(cfg.HARVEST_MIN_ROWS, 5):
            continue
        if not re.search(r"[a-z]", mfr) or mfr in STOP:
            continue
        raw = next((x for x in g["Manufacturer Name"] if pd.notna(x)), mfr)
        seen.setdefault(mfr, str(raw).strip())
    ordered = sorted(seen.items(), key=lambda kv: len(kv[0]), reverse=True)
    print(f"  [harvest] manufacturers: {len(ordered):,} alias cores")
    return ordered


def main():
    # --full mines from ALL labels for the production lexicons (use after the
    # held-out split has already validated the method); the default 70/30 split
    # is for honest measurement only.
    full = "--full" in sys.argv
    gt = load_gt()
    train = gt if full else gt[~gt["test"]]
    test = gt[gt["test"]]
    mode = "FULL (all GT, production)" if full else f"{cfg.HARVEST_TEST_FRAC:.0%} held out"
    print(f"  [harvest] GT rows {len(gt):,}  train {len(train):,}  "
          f"test {len(test):,}  [{mode}]")

    kw = harvest_keywords(train)
    mfr = harvest_manufacturers(train)

    with open(cfg.HARVEST_KEYWORDS_PKL, "wb") as fh:
        pickle.dump(kw, fh)
    with open(cfg.HARVEST_MANUFACTURERS_PKL, "wb") as fh:
        pickle.dump(mfr, fh)
    test[["jk"]].drop_duplicates().to_csv(cfg.BENCHMARK_TEST_JK, index=False)
    print(f"  [harvest] wrote {cfg.HARVEST_KEYWORDS_PKL.name}, "
          f"{cfg.HARVEST_MANUFACTURERS_PKL.name}, {cfg.BENCHMARK_TEST_JK.name}")


if __name__ == "__main__":
    main()
