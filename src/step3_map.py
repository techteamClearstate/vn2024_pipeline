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
import re

import numpy as np
import pandas as pd

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import settings as cfg
from src.step1_extract import canonicalize_products, norm_party


def _derive_manufacturers(rows: pd.DataFrame) -> pd.Series:
    """Recover a manufacturer by matching the curated alias cores (longest-first)
    against the Importer/Exporter trade-party blob PLUS the product description —
    the description often names the maker after "HSX:" (Hãng Sản Xuất). This alias
    match is ~99.9% precise, so its hit is preferred over the reference Player.
    Rows with no hit resolve to "" (caller keeps the existing value)."""
    with open(cfg.MANUFACTURER_ALIAS_PKL, "rb") as fh:
        alias_cores = pickle.load(fh)                # [(core, canonical), …]
    cols = [c for c in (list(cfg.MANUFACTURER_PARTY_COLS) + [cfg.VN_DESCRIPTION_COL])
            if c in rows.columns]
    blob = rows[cols].fillna("").astype(str).agg(" ".join, axis=1)

    def derive(text: str) -> str:
        b = " " + norm_party(text) + " "
        for core, canonical in alias_cores:
            if " " + core + " " in b:
                return canonical
        return ""

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
    # Mutated in place: the caller (run_mapping) reassigns its variable to our
    # return value and never reuses the frame passed in, so a defensive copy here
    # just doubles peak memory — which OOMs the 2M-row India export at the system
    # commit ceiling. Operate on `out` directly.
    tier   = out[cfg.TIER_COL].fillna("")
    bound  = tier.isin(cfg.DASHBOARD_BOUND_TIERS)
    is_cat = tier == "category"

    # Manufacturer: derive from the trade parties + description for EVERY row and
    # prefer that alias hit (~99.9% precise) over the reference Player. Rows with
    # no alias hit keep whatever maker they already carry.
    if cfg.MANUFACTURER_PARTY_COLS[0] in out.columns:
        derived = _derive_manufacturers(out)
        cur = out["Manufacturer"].fillna("")
        out["Manufacturer"] = derived.where(derived != "", cur)

    out.loc[is_cat, "Family"] = cfg.UNSPECIFIED_LABEL

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


def _norm_series(s: pd.Series) -> pd.Series:
    """Vectorized taxonomy-dimension normalization (matches step1._norm_dim for the
    ASCII taxonomy labels): strip, collapse whitespace, lowercase."""
    return (s.fillna("").astype(str)
             .str.replace(r"\s+", " ", regex=True).str.strip().str.lower())


def _reference_keyset() -> set | None:
    """Load the reference (Seg, Sub, Product) tuples as '\\x1f'-joined keys for fast
    vectorized membership, or None if the gate is off / the pickle is absent."""
    if not getattr(cfg, "REFERENCE_HARDGATE", False):
        return None
    try:
        with open(cfg.REFERENCE_TUPLES_PKL, "rb") as fh:
            data = pickle.load(fh)
    except (FileNotFoundError, OSError):
        print("  [ref-gate] WARNING reference_tuples.pkl missing — gate disabled "
              "for this run (re-run --from extract to build it).")
        return None
    return {"\x1f".join(t) for t in data.get("triples", set())}


def _scope_flag_series(out: pd.DataFrame) -> pd.Series:
    """First negative-scope flag whose cue hits the Detailed_Product+Importer+
    Exporter blob (priority = SCOPE_EXCLUDE_CUES order), else "". One compiled
    regex per flag → vectorized/fast even on the 2M-row India frame."""
    if not getattr(cfg, "APPLY_SCOPE_EXCLUSIONS", False):
        return pd.Series("", index=out.index)
    scope_cols = getattr(cfg, "SCOPE_EXCLUDE_COLS", [cfg.VN_DESCRIPTION_COL])
    cols = [c for c in scope_cols if c in out.columns]
    if not cols:
        return pd.Series("", index=out.index)
    blob = out[cols].fillna("").astype(str).agg(" ".join, axis=1).str.lower()
    flag = pd.Series("", index=out.index)
    for name, cues in cfg.SCOPE_EXCLUDE_CUES.items():
        cues = [c.lower() for c in cues if c]
        if not cues:
            continue
        rx = re.compile("|".join(re.escape(c) for c in cues))
        hit = blob.str.contains(rx, regex=True, na=False) & (flag == "")
        flag = flag.mask(hit, name)
    return flag


def apply_reference_gate(out: pd.DataFrame) -> pd.DataFrame:
    """DQ 2026-07 final-output gate. Adds four columns so the trusted
    Dashboard/Rollup/Scope carry ONLY reference-aligned, in-scope rows — WITHOUT
    dropping anything (failing rows stay in RawData, tagged for review):

      * Ref_Valid    "Y" if a bound (family/category) row's (Segment, Sub-segment,
                     Product) tuple exists in the latest reference taxonomy AND the
                     product is not a "(unspecified)"/blank label;
      * Scope_Flag   the negative-scope cue group that matched (dental/veterinary/
                     cosmetic/imaging/lab_ivd/general), else "";
      * Dash_Include "Y" if the row feeds the trusted Dashboard (bound & Ref_Valid
                     & not scope-excluded). The Dashboard/rollup formulas key on it;
      * QA_Status    human-readable disposition (see cfg.QA_* vocabulary).
    """
    tier  = out[cfg.TIER_COL].fillna("")
    bound = tier.isin(cfg.DASHBOARD_BOUND_TIERS)

    seg  = _norm_series(out[cfg.DASHBOARD_OU_COL])
    sub  = _norm_series(out["Sub-segment"])
    prod = _norm_series(out["Product_V0"])
    unspec = str(cfg.UNSPECIFIED_LABEL).lower()
    mark   = str(cfg.UNSPECIFIED_PRODUCT_MARK).lower()
    prod_unspec = prod.str.contains(re.escape(mark), regex=True, na=False) | (prod == unspec) | (prod == "")
    dims_unspec = prod_unspec | (seg == unspec) | (seg == "") | (sub == unspec) | (sub == "")

    keyset = _reference_keyset()
    if keyset is not None:
        key = seg + "\x1f" + sub + "\x1f" + prod
        ref_valid = bound & key.isin(keyset) & ~prod_unspec
    else:
        ref_valid = bound & ~prod_unspec if getattr(cfg, "DROP_UNSPECIFIED_PRODUCTS", False) else bound

    # Scope-cue regex is the costly part — only bound rows can be included, so only
    # they need a scope flag (keeps the 2M-row India pass fast).
    scope_flag = pd.Series("", index=out.index)
    if bool(bound.any()):
        scope_flag.loc[bound] = _scope_flag_series(out.loc[bound])
    include = ref_valid & (scope_flag == "")

    out[cfg.REF_VALID_COL]    = np.where(ref_valid, "Y", "")
    out[cfg.SCOPE_FLAG_COL]   = scope_flag
    out[cfg.DASH_INCLUDE_COL] = np.where(include, "Y", "")

    # Disposition (priority-ordered): manufacturer-only → unmapped default first,
    # then bound rows resolved include → scope → unspecified → non-reference.
    status = pd.Series(cfg.QA_UNMAPPED, index=out.index)
    status = status.mask(tier == "manufacturer", cfg.QA_AUDIT_MFR)
    ext = (out[cfg.SCOPE_COL] == cfg.SCOPE_EXTENDED_LABEL) if cfg.SCOPE_COL in out.columns \
          else pd.Series(False, index=out.index)
    status = status.mask(include & ext,  cfg.QA_MAPPED_EXT)
    status = status.mask(include & ~ext, cfg.QA_MAPPED)
    status = status.mask(bound & ~include & (scope_flag != ""),
                         cfg.QA_REVIEW_SCOPE + ": " + scope_flag)
    status = status.mask(bound & ~include & (scope_flag == "") & dims_unspec,
                         cfg.QA_REVIEW_UNSPEC)
    status = status.mask(bound & ~include & (scope_flag == "") & ~dims_unspec,
                         cfg.QA_REVIEW_NONREF)
    out[cfg.QA_STATUS_COL] = status

    n_inc = int((include).sum()); n_bound = int(bound.sum())
    n_scope = int((bound & (scope_flag != "")).sum())
    print(f"  [ref-gate] {n_inc:,}/{n_bound:,} bound rows reference-valid & in-scope "
          f"→ Dashboard; {n_bound - n_inc:,} parked as Review "
          f"({n_scope:,} scope-excluded)")
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

    # Read ONLY the carry-through columns (KEEP_COLS) this stage joins onto —
    # the wide 24-col × 2M-row TSV otherwise exhausts commit charge on India.
    # Output is identical: the frame is subset to `keep` immediately below.
    _keepset = set(cfg.KEEP_COLS)
    vn = pd.read_csv(cfg.VN_TSV, sep="\t", dtype=str,
                     usecols=lambda c: c in _keepset)

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

    # DQ 2026-07 final-output gate: tag reference validity / scope exclusions so the
    # export keeps only reference-aligned, in-scope rows in the trusted Dashboard.
    out = apply_reference_gate(out)

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
