"""
Evaluate the pipeline's VN mapping against the human-labeled Client-Ready
ground truth (benchmark_gt_2024.csv), joined on desc+HS+value.

Primary metric = PRODUCT correctness: a matched row is "product-correct" if the
pipeline Product_V0 shares a meaningful product token with the GT OU_Device, OR
the pipeline Family brand-agrees (substring) with the GT Family Name. This
catches within-OU product errors (suture->mesh, plate->middle-ear implant) that
segment-level agreement misses.
"""
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import settings as cfg

# Generic tokens that carry no product identity (grouping / form / material-agnostic).
STOP = {
    "wound", "closure", "cv", "trauma", "spine", "si", "neuro", "core", "access",
    "other", "others", "device", "devices", "disposable", "reusable", "manual",
    "system", "systems", "and", "the", "of", "for", "with", "surgical", "open",
    "endo", "total", "fixation", "management", "solutions", "unspecified",
    "powered", "instrument", "instruments", "product", "products", "reloads",
    "implant", "implants", "kit", "set", "sr", "l", "ii", "iii", "new", "type",
    "conventional", "standard", "adj", "ex", "acc",
}


def nd(s):
    s = re.sub(r"[^a-z0-9]+", " ", str(s).lower())
    return re.sub(r"\s+", " ", s).strip()


def toks(s):
    return {t for t in nd(s).split() if t not in STOP and len(t) > 2}


def tok_overlap(a, b):
    """True if any token of a prefix-matches any token of b (>=4 char common
    prefix), so stems like plate/plating and nail/nailing count as agreeing."""
    ta, tb = toks(a), toks(b)
    if ta & tb:
        return True
    pa = {x[:4] for x in ta if len(x) >= 4}
    pb = {y[:4] for y in tb if len(y) >= 4}
    return bool(pa & pb)


def load():
    gt = pd.read_csv(cfg.INTERMEDIATE / "benchmark_gt_2024.csv", dtype=str)
    mp = pd.read_csv(cfg.MAPPED_CSV, dtype=str)
    gt["value"] = pd.to_numeric(gt["value"], errors="coerce").astype("Int64")
    gt["hs_code"] = pd.to_numeric(gt["hs_code"], errors="coerce").astype("Int64")
    gt["jk"] = gt["desc_key"] + "|" + gt["hs_code"].astype(str) + "|" + gt["value"].astype(str)
    mp["desc_key"] = mp["Detailed_Product"].map(nd)
    mp["value"] = pd.to_numeric(mp["Total_Value_USD"], errors="coerce").round(0).astype("Int64")
    mp["hs_code"] = pd.to_numeric(mp["HS_Code"], errors="coerce").astype("Int64")
    mp["jk"] = mp["desc_key"] + "|" + mp["hs_code"].astype(str) + "|" + mp["value"].astype(str)
    return gt, mp


def test_jk():
    """Held-out join keys written by tools/harvest_from_benchmark.py (None if the
    split hasn't been generated)."""
    p = cfg.BENCHMARK_TEST_JK
    if p.exists():
        return set(pd.read_csv(p, dtype=str)["jk"])
    return None


def evaluate(mp, gt, verbose=True, split=None):
    gt1 = gt.dropna(subset=["jk"]).drop_duplicates("jk", keep="first").set_index("jk")
    m = mp.copy()
    m["gtOU"] = m["jk"].map(gt1["OU"])
    m["gtDev"] = m["jk"].map(gt1["OU_Device"])
    m["gtFam"] = m["jk"].map(gt1["Family Name"])
    j = m[m["gtOU"].notna()].copy()
    # Optionally restrict to the held-out TEST (or complementary TRAIN) split so a
    # benchmark-harvested lexicon is scored only on rows it never learned from.
    if split in ("test", "train"):
        tj = test_jk() or set()
        inb = j["jk"].isin(tj)
        j = j[inb] if split == "test" else j[~inb]
        if verbose:
            print(f"[split={split}]  {len(j):,} rows")

    def prod_ok(r):
        if r["Match_Status"] != "Matched":
            return False
        # brand agreement
        fk, gk = nd(r.get("Family", "")), nd(r.get("gtFam", ""))
        if fk and gk and (fk in gk or gk in fk):
            return True
        # product token overlap (prefix-stemmed)
        return tok_overlap(r.get("Product_V0", ""), r["gtDev"])

    j["matched"] = j["Match_Status"] == "Matched"
    j["ok"] = j.apply(prod_ok, axis=1)
    j["v"] = pd.to_numeric(j["Total_Value_USD"], errors="coerce").fillna(0)

    n = len(j)
    nm = j["matched"].sum()
    nok = j["ok"].sum()
    nwrong = (j["matched"] & ~j["ok"]).sum()
    if verbose:
        print(f"GT-joined rows: {n:,}")
        print(f"  matched (any tier)   : {nm:,} ({nm/n:.1%})")
        print(f"  product-CORRECT      : {nok:,}  (recall {nok/n:.1%})")
        print(f"  matched but WRONG prod: {nwrong:,}  (precision {nok/nm:.1%})")
        print(f"  unmatched (missed)   : {n-nm:,}")
    return j


def main():
    split = None
    if "--split" in sys.argv:
        split = sys.argv[sys.argv.index("--split") + 1]
    gt, mp = load()
    j = evaluate(mp, gt, split=split)

    print("\n=== Worst FALSE-POSITIVE product buckets (matched, wrong product) ===")
    w = j[j["matched"] & ~j["ok"]]
    wb = (w.groupby(["Family", "Product_V0", "gtDev"])
          .agg(n=("v", "size"), val=("v", "sum")).reset_index()
          .sort_values("n", ascending=False))
    print(wb.head(25).to_string(index=False))

    print("\n=== Per Tier-1 family keyword: precision (n>=15), worst first ===")
    t1 = j[j["Match_Tier"] == "family"]
    kp = (t1.groupby("Family").agg(n=("ok", "size"), prec=("ok", "mean"),
                                   val=("v", "sum")).reset_index())
    kp = kp[kp["n"] >= 15].sort_values(["prec", "n"], ascending=[True, False])
    print(kp.head(30).to_string(index=False))


if __name__ == "__main__":
    main()
