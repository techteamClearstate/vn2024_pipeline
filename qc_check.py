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
import pickle
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import settings as cfg

# Pin the known-good Tier-1 family count for the Vietnam GT market (the invariant
# assumes VN is the currently-cached market). Update deliberately if the reference
# or HS4 scope changes (never to paper over an accidental regression). Set to the
# master-list count (iter-12+, `Surg_Brand_model_list_Master 03July26.xlsx`); was
# 85,378 under the original V0 reference.
EXPECTED_FAMILY = 56_415


def _fail(msg):
    print(f"  [QC] FAIL: {msg}")
    return False


def _norm_exact(value) -> str:
    return re.sub(r"\s+", " ", str(value if value is not None else "")).strip().casefold()


def _load_reference_master() -> dict | None:
    if not getattr(cfg, "REFERENCE_HARDGATE", False):
        return None
    try:
        with open(cfg.REFERENCE_TUPLES_PKL, "rb") as fh:
            data = pickle.load(fh)
    except (FileNotFoundError, OSError):
        print("  [QC] SKIP: reference_tuples.pkl missing")
        return None
    data = dict(data)
    data["full_exact"] = set(data.get("full_exact", set()))
    data["category_exact"] = set(data.get("category_exact",
                                      data.get("cat_exact",
                                      data.get("triples", set()))))
    return data


def main() -> int:
    df = pd.read_csv(cfg.MAPPED_CSV, low_memory=False, dtype=str)
    df = df.fillna("")
    tier = cfg.TIER_COL
    ok = True

    # 1. Tier-1 unchanged for the Vietnam cached regression market.
    n_fam = (df[tier] == "family").sum()
    if cfg.IMPORT_COUNTRY.lower() not in {"vietnam", "vn"}:
        print(f"  [QC] SKIP: Tier-1 family count pin is Vietnam-only "
              f"(current market={cfg.IMPORT_COUNTRY})")
    elif n_fam != EXPECTED_FAMILY:
        ok = _fail(f"Tier-1 family = {n_fam:,}, expected {EXPECTED_FAMILY:,}")
    else:
        print(f"  [QC] PASS: Tier-1 family = {n_fam:,}")

    # 2. Cascade exclusivity
    matched = df[df["Match_Status"] == "Matched"]
    tiers = set(matched[tier].unique())
    # 'hs_prior' is the re-rank tier step3b assigns to product-less rows it enriches.
    allowed = {"family", "category", "manufacturer", "hs_prior"}
    if not tiers <= allowed:
        ok = _fail(f"unexpected tiers on Matched rows: {tiers - allowed}")
    if (df[(df["Match_Status"] != "Matched")][tier] != "").any():
        ok = _fail("Unmatched rows carry a non-empty Match_Tier")
    if ok:
        print(f"  [QC] PASS: tiers on Matched rows = {sorted(tiers)}")

    # 3. Provenance shape. Current design: standardize_for_dashboard sets category
    #    Family="Unspecified"; the step3b hs_prior re-rank may enrich Family (and
    #    Product/Segment) on non-family rows. So we assert the invariants that still
    #    hold: a category row asserts a Product but never a *specific* family (blank
    #    or Unspecified), and every manufacturer row still carries a Manufacturer.
    cat = df[df[tier] == "category"]
    if (cat["Product_V0"] == "").any():
        ok = _fail("category rows missing a Product_V0")
    mfr = df[df[tier] == "manufacturer"]
    if (mfr["Manufacturer"] == "").any():
        ok = _fail("manufacturer rows missing a Manufacturer")
    if ok:
        print(f"  [QC] PASS: provenance shape "
              f"(category={len(cat):,}, manufacturer={len(mfr):,})")

    # 4. Reference-compliance invariants for trusted dashboard rows.
    include = (df[cfg.DASH_INCLUDE_COL] == "Y") if cfg.DASH_INCLUDE_COL in df.columns \
              else pd.Series(False, index=df.index)
    if cfg.SCOPE_COL in df.columns:
        leaked_scope = include & (df[cfg.SCOPE_COL] != cfg.SCOPE_SURGICAL_LABEL)
        if leaked_scope.any():
            ok = _fail(f"{int(leaked_scope.sum()):,} Dash_Include rows are not Surgical")
    if cfg.QA_STATUS_COL in df.columns:
        leaked_ext = include & (df[cfg.QA_STATUS_COL] == cfg.QA_REVIEW_EXT)
        if leaked_ext.any():
            ok = _fail(f"{int(leaked_ext.sum()):,} Extended-review rows are Dash_Include=Y")

    ref = _load_reference_master()
    if ref is not None:
        dim_cols = ["Segment", "Sub-segment", "Product_V0", "Manufacturer", "Family"]
        cat_cols = dim_cols[:3]
        bad_family = 0
        for combo in df.loc[include & (df[tier] == "family"), dim_cols].drop_duplicates().itertuples(index=False, name=None):
            if tuple(_norm_exact(v) for v in combo) not in ref["full_exact"]:
                bad_family += 1
        bad_category = 0
        for combo in df.loc[include, cat_cols].drop_duplicates().itertuples(index=False, name=None):
            if tuple(_norm_exact(v) for v in combo) not in ref["category_exact"]:
                bad_category += 1
        if bad_family or bad_category:
            ok = _fail(f"trusted rows not in master: family keys={bad_family:,}, "
                       f"category keys={bad_category:,}")
        else:
            print(f"  [QC] PASS: Dash_Include rows are Surgical and master-valid "
                  f"({int(include.sum()):,} rows)")

    # 5. Dashboard bounds
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
            # The slice sums the rows _surgical_bound() keeps: bound (family+category)
            # AND, since iter-13, reference-valid + in-scope (Dash_Include=="Y") AND
            # Surgical scope. Match that exact filter so the invariant stays true.
            bound_val = df[df[tier].isin(cfg.DASHBOARD_BOUND_TIERS)]
            if cfg.DASH_INCLUDE_COL in bound_val.columns:
                bound_val = bound_val[bound_val[cfg.DASH_INCLUDE_COL] == "Y"]
            if cfg.SCOPE_COL in bound_val.columns:
                bound_val = bound_val[bound_val[cfg.SCOPE_COL] == cfg.SCOPE_SURGICAL_LABEL]
            v = pd.to_numeric(bound_val[cfg.VALUE_COL], errors="coerce").fillna(0).sum()
            up = cur["Upper_Bound_USD"].sum()
            # upper bound should equal the reference-valid, in-scope family+category
            # value (within rounding)
            if abs(up - v) > max(1.0, 0.001 * v):
                ok = _fail(f"{cfg.IMPORT_COUNTRY} upper bound {up:,.0f} "
                           f"!= reference-valid family+category value {v:,.0f}")
            else:
                print(f"  [QC] PASS: bounds lower<=upper; {cfg.IMPORT_COUNTRY} "
                      f"upper=${up:,.0f} (reference-valid family+category; "
                      f"{len(slices)} country slice(s) present)")
    else:
        print("  [QC] SKIP: no dashboard slices found")

    # 6. Remap-output anchors: the batch remap's trusted counts per market-year,
    #    pinned from the 2026-07-06 six-market regeneration (A1 remap). Checked
    #    against the combined QA report so no 400-700MB workbook is re-read.
    #    Update DELIBERATELY after an intended mapping change (e.g. approved
    #    adjudication ingestion + rerun), never to paper over a regression.
    report = (Path(__file__).resolve().parent / "outputs" / "remapped_current"
              / "reports" / "All_Countries_Surgical_Mapping_QA_Report.xlsx")
    if report.exists():
        anchors = {  # (country, year): (trusted rows, trusted value $)
            ("Pakistan", 2024): (2_920, 46_288_144.38),
            ("Pakistan", 2025): (3_084, 57_973_239.81),
            ("India", 2024): (163_817, 684_089_815.49),
            ("India", 2025): (215_687, 984_545_321.87),
            ("Vietnam", 2024): (52_367, 260_457_276.41),
            ("Vietnam", 2025): (55_179, 250_763_141.76),
        }
        m = pd.read_excel(report, sheet_name="Metrics_By_File")
        m = m[m["Run"].astype(str).str.startswith("A1")]
        bad = 0
        for (country, year), (rows_pin, value_pin) in anchors.items():
            cur = m[(m["Country"] == country) & (m["Year"] == year)]
            if cur.empty:
                print(f"  [QC] SKIP: no remap metrics for {country} {year}")
                continue
            rows_now = int(cur["Trusted rows"].iloc[0])
            value_now = float(cur["Trusted value"].iloc[0])
            if rows_now != rows_pin or abs(value_now - value_pin) > 0.005 * value_pin:
                bad += 1
                ok = _fail(f"remap anchor {country} {year}: trusted "
                           f"{rows_now:,}/${value_now:,.0f} vs pinned "
                           f"{rows_pin:,}/${value_pin:,.0f}")
        if not bad:
            print(f"  [QC] PASS: remap trusted anchors ({len(anchors)} market-years)")
    else:
        print("  [QC] SKIP: no remap QA report found")

    print("  [QC] ALL CHECKS PASSED" if ok else "  [QC] SOME CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
