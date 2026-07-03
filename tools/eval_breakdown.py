"""
Per-dimension precision/recall breakdown against the human-labeled GT, for:
  1. Family        (Tier-1 brand/model identity vs GT "Family Name")
  2. Manufacturer  (attributed maker vs GT "Manufacturer Name")
  3. Presentation  (Product/OU_Device identity vs GT "OU_Device"), by tier

Precision = correct / (pipeline made a non-blank prediction on that dimension).
Recall    = correct / (GT carries a non-blank label on that dimension).
Reuses the join + token helpers from eval_benchmark.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.eval_benchmark import load, nd, toks, tok_overlap, test_jk

UNSPEC = {"", "unspecified", "nan"}


def agree(a, b):
    """Brand/maker agreement: normalized substring either way, or token overlap."""
    na, nb = nd(a), nd(b)
    if not na or not nb:
        return False
    if na in nb or nb in na:
        return True
    return tok_overlap(a, b)


def pr(label, correct, predicted, labeled):
    p = correct / predicted if predicted else 0.0
    r = correct / labeled if labeled else 0.0
    print(f"  {label:22s} precision {p:6.1%} ({correct:,}/{predicted:,})   "
          f"recall {r:6.1%} ({correct:,}/{labeled:,})")


def main():
    gt, mp = load()
    gt1 = gt.dropna(subset=["jk"]).drop_duplicates("jk", keep="first").set_index("jk")
    m = mp.copy()
    m["gtDev"] = m["jk"].map(gt1["OU_Device"])
    m["gtFam"] = m["jk"].map(gt1["Family Name"])
    m["gtMfr"] = m["jk"].map(gt1["Manufacturer Name"])
    j = m[m["gtDev"].notna() | m["gtFam"].notna() | m["gtMfr"].notna()].copy()
    if "--split" in sys.argv:
        split = sys.argv[sys.argv.index("--split") + 1]
        tj = test_jk() or set()
        inb = j["jk"].isin(tj)
        j = (j[inb] if split == "test" else j[~inb]).copy()
        print(f"[split={split}]")
    n = len(j)
    print(f"GT-joined rows: {n:,}\n")

    tier = j["Match_Tier"].fillna("")
    fam = j["Family"].fillna("").map(lambda s: s if nd(s) not in UNSPEC else "")
    mfr = j["Manufacturer"].fillna("").map(lambda s: s if nd(s) not in UNSPEC else "")
    prod = j["Product_V0"].fillna("")

    def has(s):
        return s.fillna("").map(lambda x: nd(x) not in UNSPEC)

    # 1. FAMILY (Tier-1 only produces a real family)
    print("1. FAMILY (brand/model identity vs GT Family Name)")
    fpred = fam != ""
    flab = has(j["gtFam"])
    fok = [agree(a, b) for a, b in zip(fam, j["gtFam"])]
    fok = pd.Series(fok, index=j.index) & fpred & flab
    pr("family", int(fok.sum()), int((fpred & flab).sum()), int(flab.sum()))
    print(f"     (GT rows carrying a Family Name: {int(flab.sum()):,} of {n:,})\n")

    # 2. MANUFACTURER (attributed on all bound + Tier-3 rows)
    print("2. MANUFACTURER (attributed maker vs GT Manufacturer Name)")
    mpred = mfr != ""
    mlab = has(j["gtMfr"])
    mok = [agree(a, b) for a, b in zip(mfr, j["gtMfr"])]
    mok = pd.Series(mok, index=j.index) & mpred & mlab
    pr("manufacturer (all)", int(mok.sum()), int((mpred & mlab).sum()), int(mlab.sum()))
    for t in ("family", "category", "manufacturer"):
        sel = tier == t
        tp = mpred & mlab & sel
        tok_ = mok & sel
        pr(f"  via tier={t}", int(tok_.sum()), int(tp.sum()), int((mlab & sel).sum()))
    print()

    # 3. PRESENTATION (product identity vs GT OU_Device), by tier
    print("3. PRESENTATION (Product identity vs GT OU_Device)")
    ppred = has(prod) | fpred          # a family also implies a presentation
    plab = has(j["gtDev"])
    pok = [tok_overlap(p, d) or (agree(f, gf))
           for p, d, f, gf in zip(prod, j["gtDev"], fam, j["gtFam"])]
    pok = pd.Series(pok, index=j.index) & ppred & plab
    pr("presentation (all)", int(pok.sum()), int((ppred & plab).sum()), int(plab.sum()))
    for t in ("family", "category"):
        sel = tier == t
        tp = ppred & plab & sel
        tok_ = pok & sel
        pr(f"  via tier={t}", int(tok_.sum()), int(tp.sum()), int((plab & sel).sum()))


if __name__ == "__main__":
    main()
