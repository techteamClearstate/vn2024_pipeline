"""
READ-ONLY validation: quantify how many product-less rows in a GT-less market's
existing workbook the VN-learned (hs6, token) transfer prior would recover, and the
$ value involved. Proves the cross-market transfer magnitude without re-running the
pipeline (which would overwrite the single-file VN caches).

Usage: python tools/validate_hs6_transfer.py outputs/Pakistan_ML_Map_Mapped.xlsx
Nothing is written.
"""
import pickle
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import settings as cfg
from src.step3b_hs_prior import _hs6_of, _hs8, _tokens


def main(xlsx: str):
    with open(cfg.TRANSFER_PRIOR_PKL, "rb") as fh:
        prior = pickle.load(fh)
    hs6_token = prior.get("hs6_token", {})
    hs6_token_mfr = prior.get("hs6_token_mfr", {})
    print(f"transfer prior: {len(hs6_token):,} (hs6,token) product + "
          f"{len(hs6_token_mfr):,} (hs6,token) maker rules")

    mp = pd.read_excel(xlsx, sheet_name="RawData", dtype=str)
    print(f"{Path(xlsx).name}: {len(mp):,} rows")
    hs8 = _hs8(mp["HS_Code"])
    tier = mp[cfg.TIER_COL].fillna("")
    prod = mp["Product_V0"].fillna("")
    val = pd.to_numeric(mp["Total_Value_USD"], errors="coerce").fillna(0)
    dk = mp["Detailed_Product"].map(
        lambda s: re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(s).lower())).strip())

    # scope = rows the lexical family/category tiers left product-less (same gate as
    # apply_prior would use, minus the hs8 rules which don't transfer)
    scope = ~tier.isin(["family", "category"])
    empty = prod.str.strip() == ""
    cand = mp.index[scope & empty]

    n_fire = 0
    fired_val = 0.0
    hits = {}
    for i in cand:
        h6 = _hs6_of(hs8[i])
        best = None
        for t in _tokens(dk[i]):
            rec = hs6_token.get((h6, t))
            if rec and (best is None or rec["share"] > best["share"]):
                best = rec
        if best:
            n_fire += 1
            fired_val += val[i]
            hits[best["Product"]] = hits.get(best["Product"], 0) + val[i]

    print(f"\nproduct-less in-scope rows: {len(cand):,}")
    print(f"(hs6,token) transfer would recover: {n_fire:,} rows  "
          f"(${fired_val/1e6:.1f}M value)")
    print("\ntop recovered products by $:")
    for p, v in sorted(hits.items(), key=lambda kv: -kv[1])[:15]:
        print(f"  ${v/1e6:6.2f}M  {p}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1
         else "outputs/Pakistan_ML_Map_Mapped.xlsx")
