"""
Held-out error anatomy for the >90% push. Rebuilds the TRAIN-prior state (so the
test split is genuinely unseen), then on the TEST split reports:
  * WRONG rows by Match_Tier + top confusion buckets (Product_V0 → GT OU_Device)
  * UNMATCHED rows and how recoverable they look (have a maker? hs8 in prior?)
and dumps the ambiguous/wrong rows to intermediate/wrong_test.csv for the
sub-agent re-ranker.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import settings as cfg
from src import step3_map, step3b_hs_prior
from tools.eval_benchmark import load, nd, tok_overlap, test_jk


def prod_ok(r):
    if r["Match_Status"] != "Matched":
        return False
    fk, gk = nd(r.get("Family", "")), nd(r.get("gtFam", ""))
    if fk and gk and (fk in gk or gk in fk):
        return True
    return tok_overlap(r.get("Product_V0", ""), r["gtDev"])


def main():
    print(">> rebuilding TRAIN-prior state (base + train prior)")
    step3_map.run_mapping()
    step3b_hs_prior.run(full=False)

    gt, mp = load()
    gt1 = gt.dropna(subset=["jk"]).drop_duplicates("jk", keep="first").set_index("jk")
    tj = test_jk() or set()
    m = mp.copy()
    m["gtDev"] = m["jk"].map(gt1["OU_Device"])
    m["gtFam"] = m["jk"].map(gt1["Family Name"])
    m["gtMfr"] = m["jk"].map(gt1["Manufacturer Name"])
    j = m[m["gtDev"].notna() & m["jk"].isin(tj)].copy()
    j["ok"] = j.apply(prod_ok, axis=1)
    j["tier"] = j[cfg.TIER_COL].fillna("")
    n = len(j)
    matched = (j["Match_Status"] == "Matched").sum()
    ok = j["ok"].sum()
    print(f"\nTEST rows {n:,}  recall {ok/n:.1%}  precision {ok/matched:.1%}")
    print(f"  correct {ok:,}  wrong {matched-ok:,}  unmatched {n-matched:,}\n")

    wrong = j[(j["Match_Status"] == "Matched") & ~j["ok"]]
    print("WRONG by Match_Tier:")
    print(wrong["tier"].value_counts().to_string(), "\n")

    print("Top confusion buckets (tier | Product_V0 → gtDev):")
    wb = (wrong.groupby(["tier", "Product_V0", "gtDev"]).size()
          .reset_index(name="n").sort_values("n", ascending=False))
    print(wb.head(25).to_string(index=False), "\n")

    un = j[j["Match_Status"] != "Matched"]
    has_mk = un["Manufacturer"].fillna("").map(lambda s: nd(s) not in ("", "unspecified")).sum()
    print(f"UNMATCHED {len(un):,}: with a maker {has_mk:,}, without {len(un)-has_mk:,}")

    # dump wrong + ambiguous for the sub-agent reranker
    cols = ["Detailed_Product", "HS_Code", cfg.MANUFACTURER_PARTY_COLS[0],
            cfg.MANUFACTURER_PARTY_COLS[1], "Manufacturer", "tier", "Family",
            "Product_V0", "Segment", "gtDev", "gtFam"]
    cols = [c for c in cols if c in wrong.columns]
    out = cfg.INTERMEDIATE / "wrong_test.csv"
    wrong[cols].to_csv(out, index=False)
    print(f"\ndumped {len(wrong):,} wrong rows → {out.name}")


if __name__ == "__main__":
    main()
