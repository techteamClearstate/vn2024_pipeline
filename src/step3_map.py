"""
Step 3 — Mapping
================
Join matched keywords back to their V0 reference fields and assemble the
enriched output DataFrame:

  V0 Segment       → Segment
  V0 Sub-segment   → Sub-segment
  V0 Product       → Product_V0
  V0 Player        → Manufacturer
  V0 Model/Family  → Family   (the matched keyword itself)
  derived          → Match_Status  ("Matched" / "Unmatched")
"""
import json
import pickle

import pandas as pd

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import settings as cfg
from src.step1_extract import canonicalize_products, norm_party


def _derive_manufacturers(rows: pd.DataFrame) -> pd.Series:
    """Recover a manufacturer for rows that have none by matching the curated
    alias cores against the Importer/Exporter trade-party blob (same cores as
    Tier-3, longest-first). Rows with no hit resolve to "Unspecified"."""
    with open(cfg.MANUFACTURER_ALIAS_PKL, "rb") as fh:
        alias_cores = pickle.load(fh)                # [(core, canonical), …]
    blob = (rows[cfg.MANUFACTURER_PARTY_COLS].fillna("").astype(str)
            .agg(" ".join, axis=1))

    def derive(text: str) -> str:
        b = " " + norm_party(text) + " "
        for core, canonical in alias_cores:
            if " " + core + " " in b:
                return canonical
        return cfg.UNSPECIFIED_LABEL

    return blob.map(derive)


def standardize_for_dashboard(out: pd.DataFrame) -> pd.DataFrame:
    """Fold the Dashboard's dimension standardization into the mapped output so
    RawData carries the final values directly (no separate Dash_* helper columns):

      * category (Tier-2) rows get Family = "Unspecified" (family unknown) and a
        Manufacturer recovered from the trade parties — so every bound row carries
        a non-blank Family, which is the gate the Dashboard's SUMIFS use to
        include only family+category rows (Tier-3/unmatched keep a blank Family);
      * blank OU / Sub-OU / Product / Manufacturer on bound rows → "Unspecified"
        so each Dashboard line is labelled and its criteria match the cells;
      * ASP_USD = Total_Value_USD / Quantity per shipment (qty>0) for the
        Min/Max/Avg ASP formulas.
    """
    out = out.copy()
    tier   = out[cfg.TIER_COL].fillna("")
    bound  = tier.isin(cfg.DASHBOARD_BOUND_TIERS)
    is_cat = tier == "category"

    out.loc[is_cat, "Family"] = cfg.UNSPECIFIED_LABEL
    if cfg.MANUFACTURER_PARTY_COLS[0] in out.columns and is_cat.any():
        out.loc[is_cat, "Manufacturer"] = _derive_manufacturers(out.loc[is_cat])

    for col in [cfg.DASHBOARD_OU_COL, "Sub-segment", "Product_V0",
                "Manufacturer", "Family"]:
        if col in out.columns:
            out.loc[bound, col] = (out.loc[bound, col].fillna("")
                                   .replace("", cfg.UNSPECIFIED_LABEL))

    if cfg.VALUE_COL in out.columns and "Quantity" in out.columns:
        val = pd.to_numeric(out[cfg.VALUE_COL], errors="coerce")
        qty = pd.to_numeric(out["Quantity"], errors="coerce")
        out[cfg.ASP_COL] = (val / qty).where(qty.notna() & (qty > 0))
    return out


def run_mapping() -> pd.DataFrame:
    with open(cfg.V0_LOOKUP_PKL, "rb") as fh:
        lookup = pickle.load(fh)
    with open(cfg.MATCHED_KW_JSON) as fh:
        matched_kw = json.load(fh)
    with open(cfg.MATCHED_CATEGORY_JSON) as fh:
        matched_cat = json.load(fh)
    with open(cfg.MATCHED_MANUFACTURER_JSON) as fh:
        matched_mfr = json.load(fh)

    vn = pd.read_csv(cfg.VN_TSV, sep="\t", low_memory=False, dtype=str)

    seg, subseg, prod_v0, player, family = [], [], [], [], []
    status, tier, conf = [], [], []
    for kw, cat, mfr in zip(matched_kw, matched_cat, matched_mfr):
        if kw and kw in lookup:                       # Tier-1 family (wins)
            m = lookup[kw]
            seg.append(m["Segment"]); subseg.append(m["Sub-segment"])
            prod_v0.append(m["Product"]); player.append(m["Player"])
            family.append(m["Family_Name"])
            status.append("Matched"); tier.append("family"); conf.append("high")
        elif cat:                                     # Tier-2 category (no family)
            seg.append(cat["Segment"]); subseg.append(cat["Sub-segment"])
            prod_v0.append(cat["Product"]); player.append(""); family.append("")
            status.append("Matched"); tier.append("category")
            conf.append(cat["Confidence"])
        elif mfr:                                     # Tier-3 manufacturer only
            seg.append(""); subseg.append(""); prod_v0.append("")
            player.append(mfr); family.append("")
            status.append("Matched"); tier.append("manufacturer")
            conf.append("low")
        else:
            seg.append(""); subseg.append(""); prod_v0.append("")
            player.append(""); family.append("")
            status.append("Unmatched"); tier.append(""); conf.append("")

    # Keep only configured carry-through columns that exist
    keep = [c for c in cfg.KEEP_COLS if c in vn.columns]
    out = vn[keep].copy()

    # Overwrite Manufacturer/Family with V0 values where matched; else blank
    if "Manufacturer" in out.columns:
        out["Manufacturer"] = [p if p else "" for p in player]
    else:
        out["Manufacturer"] = player
    out["Family"]            = family
    out["Segment"]           = seg
    out["Sub-segment"]       = subseg
    # Collapse the reference's spelling/separator/order variants of a product to a
    # single canonical label (e.g. "Reusable trocars" → "Trocars_Reusable") so the
    # Dashboard lists each product once.
    out["Product_V0"]        = canonicalize_products(pd.Series(prod_v0)).tolist()
    out["Match_Status"]      = status
    out[cfg.TIER_COL]        = tier
    out[cfg.CONFIDENCE_COL]  = conf

    # Scope tag (widened matching): Surgical if the row's HS4 is one of the core
    # surgical codes, else Extended. Lets the export report how much matched value
    # comes from the original surgical scope vs the widened one.
    if cfg.VN_HS4_COL in out.columns:
        hs4 = pd.to_numeric(out[cfg.VN_HS4_COL], errors="coerce")
        out[cfg.SCOPE_COL] = hs4.isin(cfg.SURGICAL_HS4).map(
            {True: cfg.SCOPE_SURGICAL_LABEL, False: cfg.SCOPE_EXTENDED_LABEL})

    # Standardize the Dashboard dimensions in place (family/manufacturer
    # attribution, Unspecified labelling, per-shipment ASP) so the export needs no
    # Dash_* helper columns — its formulas key on these columns directly.
    out = standardize_for_dashboard(out)

    out.to_csv(cfg.MAPPED_CSV, index=False)
    n_fam = tier.count("family")
    n_cat = tier.count("category")
    n_mfr = tier.count("manufacturer")
    print(f"  [map] {n_fam:,} family + {n_cat:,} category + {n_mfr:,} manufacturer "
          f"= {n_fam + n_cat + n_mfr:,} matched / {status.count('Unmatched'):,} "
          f"unmatched → {cfg.MAPPED_CSV.name}")
    return out


if __name__ == "__main__":
    print("Step 3 — Mapping")
    run_mapping()
