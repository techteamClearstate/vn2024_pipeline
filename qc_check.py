"""
QC regression check
===================
Read-only invariants over the mapped output (data/intermediate/vn_v0_mapped.csv)
and the dashboard slices. Run after `run_pipeline.py` (or `--from match`) to
confirm a change did not silently regress the cascade. Exits non-zero on failure.

    python qc_check.py

Checks:
  1. Tier-1 family count == EXPECTED_FAMILY (cascade must not regress T1).
  2. Cascade exclusivity — every Matched row has exactly one tier; tiers are a
     subset of {family, category, manufacturer}.
  3. Provenance shape — category rows carry no Family; manufacturer rows carry
     a Manufacturer but no Family/Segment/Product; all manufacturer rows low.
  4. Dashboard bounds — lower <= upper for every row; manufacturer volume is
     NOT in the bounds (bounds restricted to cfg.DASHBOARD_BOUND_TIERS).
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import settings as cfg

# Pin the known-good Tier-1 family count; update deliberately if the reference
# or HS4 scope changes (never to paper over an accidental regression).
EXPECTED_FAMILY = 85_378


def _fail(msg):
    print(f"  [QC] FAIL: {msg}")
    return False


def main() -> int:
    df = pd.read_csv(cfg.MAPPED_CSV, low_memory=False, dtype=str)
    df = df.fillna("")
    tier = cfg.TIER_COL
    ok = True

    # 1. Tier-1 unchanged
    n_fam = (df[tier] == "family").sum()
    if n_fam != EXPECTED_FAMILY:
        ok = _fail(f"Tier-1 family = {n_fam:,}, expected {EXPECTED_FAMILY:,}")
    else:
        print(f"  [QC] PASS: Tier-1 family = {n_fam:,}")

    # 2. Cascade exclusivity
    matched = df[df["Match_Status"] == "Matched"]
    tiers = set(matched[tier].unique())
    allowed = {"family", "category", "manufacturer"}
    if not tiers <= allowed:
        ok = _fail(f"unexpected tiers on Matched rows: {tiers - allowed}")
    if (df[(df["Match_Status"] != "Matched")][tier] != "").any():
        ok = _fail("Unmatched rows carry a non-empty Match_Tier")
    if ok:
        print(f"  [QC] PASS: tiers on Matched rows = {sorted(tiers)}")

    # 3. Provenance shape
    cat = df[df[tier] == "category"]
    if (cat["Family"] != "").any():
        ok = _fail("category rows carry a Family")
    mfr = df[df[tier] == "manufacturer"]
    if (mfr["Family"] != "").any():
        ok = _fail("manufacturer rows carry a Family")
    if (mfr["Segment"] != "").any():
        ok = _fail("manufacturer rows carry a Segment")
    if (mfr["Product_V0"] != "").any():
        ok = _fail("manufacturer rows carry a Product_V0")
    if (mfr["Manufacturer"] == "").any():
        ok = _fail("manufacturer rows missing a Manufacturer")
    if (mfr[cfg.CONFIDENCE_COL] != "low").any():
        ok = _fail("manufacturer rows not all confidence=low")
    if ok:
        print(f"  [QC] PASS: provenance shape "
              f"(category={len(cat):,}, manufacturer={len(mfr):,})")

    # 4. Dashboard bounds
    slices = sorted(cfg.INTERMEDIATE.glob(f"{cfg.DASHBOARD_PARTIAL_PREFIX}*.csv"))
    if slices:
        dash = pd.concat([pd.read_csv(p) for p in slices], ignore_index=True)
        if not (dash["Lower_Bound_USD"] <= dash["Upper_Bound_USD"]).all():
            ok = _fail("some dashboard row has lower > upper")
        else:
            # The mapped CSV holds ONE market's rows, but the dashboard may
            # combine several country slices — compare only the current market's
            # slice against this run's family+category value.
            cur = dash[dash["Country"] == cfg.IMPORT_COUNTRY]
            bound_val = df[df[tier].isin(cfg.DASHBOARD_BOUND_TIERS)]
            v = pd.to_numeric(bound_val[cfg.VALUE_COL], errors="coerce").fillna(0).sum()
            up = cur["Upper_Bound_USD"].sum()
            # upper bound should equal family+category value (within rounding)
            if abs(up - v) > max(1.0, 0.001 * v):
                ok = _fail(f"{cfg.IMPORT_COUNTRY} upper bound {up:,.0f} "
                           f"!= family+category value {v:,.0f}")
            else:
                print(f"  [QC] PASS: bounds lower<=upper; {cfg.IMPORT_COUNTRY} "
                      f"upper=${up:,.0f} (family+category only; "
                      f"{len(slices)} country slice(s) present)")
    else:
        print("  [QC] SKIP: no dashboard slices found")

    print("  [QC] ALL CHECKS PASSED" if ok else "  [QC] SOME CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
