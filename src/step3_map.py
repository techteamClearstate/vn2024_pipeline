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
from src.step1_extract import canonicalize_products, norm_exact, norm_loose, norm_party


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


DIM_COLS = ["Segment", "Sub-segment", "Product_V0", "Manufacturer", "Family"]
CATEGORY_COLS = DIM_COLS[:3]
GATE_TIERS = {"family", "category", "hs_prior"}


def _reference_master() -> dict | None:
    """Load the full reference compliance cache built from the latest master."""
    if not getattr(cfg, "REFERENCE_HARDGATE", False):
        return None
    try:
        with open(cfg.REFERENCE_TUPLES_PKL, "rb") as fh:
            data = pickle.load(fh)
    except (FileNotFoundError, OSError):
        print("  [ref-gate] WARNING reference_tuples.pkl missing; all bound rows "
              "will be parked for review (re-run --from extract to build it).")
        return None

    def canonical_full(value):
        if isinstance(value, (tuple, list)) and len(value) == 2 and isinstance(value[0], (tuple, list)):
            return tuple(value[0])
        return tuple(value)

    data = dict(data)
    data["category_exact"] = set(data.get("category_exact",
                                      data.get("cat_exact",
                                      data.get("triples", set()))))
    data["category_loose"] = dict(data.get("category_loose",
                                       data.get("cat_loose", {})))
    data["full_exact"] = set(data.get("full_exact", set()))
    data["full_loose"] = dict(data.get("full_loose", {}))
    data["generic_exact"] = {
        k: canonical_full(v)
        for k, v in dict(data.get("generic_exact", data.get("gen_exact", {}))).items()
    }
    data["generic_loose"] = {
        k: canonical_full(v)
        for k, v in dict(data.get("generic_loose", data.get("gen_loose", {}))).items()
    }
    data["pf_cats"] = {
        tuple(k): {tuple(vv) for vv in vals}
        for k, vals in dict(data.get("pf_cats", {})).items()
    }
    return data


def _compile_union(patterns):
    parts = []
    for pat in patterns or []:
        pat = str(pat).strip()
        if not pat:
            continue
        try:
            re.compile(pat)
            parts.append(pat)
        except re.error:
            parts.append(re.escape(pat))
    if not parts:
        return None
    return re.compile("|".join(f"(?:{p})" for p in parts), re.IGNORECASE)


def _scope_regexes():
    scope_rx = [
        (name, _compile_union(cues))
        for name, cues in getattr(cfg, "SCOPE_EXCLUDE_CUES", {}).items()
    ]
    scope_rx = [(name, rx) for name, rx in scope_rx if rx is not None]
    whitelist_rx = _compile_union(getattr(cfg, "SURGICAL_CONTEXT_WHITELIST", ()))
    capital_rx = _compile_union(getattr(cfg, "CAPITAL_EQUIPMENT_CUES", ()))
    return scope_rx, whitelist_rx, capital_rx


def _scope_text(out: pd.DataFrame) -> pd.Series:
    scope_cols = getattr(cfg, "SCOPE_EXCLUDE_COLS", [cfg.VN_DESCRIPTION_COL])
    cols = [c for c in scope_cols if c in out.columns]
    if not cols:
        return pd.Series("", index=out.index)
    return out[cols].fillna("").astype(str).agg(" ".join, axis=1).str.lower()


def _scope_hit(text: str, scope_rx, whitelist_rx):
    if whitelist_rx is not None and whitelist_rx.search(text or ""):
        return None, "whitelist"
    for name, rx in scope_rx:
        match = rx.search(text or "")
        if match:
            return name, match.group(0)
    return None, None


def _unspecified_mask(out: pd.DataFrame) -> pd.Series:
    seg = out["Segment"].map(norm_exact)
    sub = out["Sub-segment"].map(norm_exact)
    prod = out["Product_V0"].map(norm_exact)
    unspec = norm_exact(cfg.UNSPECIFIED_LABEL)
    mark = norm_exact(getattr(cfg, "UNSPECIFIED_PRODUCT_MARK", ""))
    prod_unspec = (prod == "") | (prod == unspec)
    if mark:
        prod_unspec = prod_unspec | prod.map(lambda value: mark in value)
    return prod_unspec | (seg == "") | (seg == unspec) | (sub == "") | (sub == unspec)


def _align_category(out: pd.DataFrame, idx, cat_key):
    for col, value in zip(CATEGORY_COLS, cat_key):
        out.loc[idx, col] = value


def apply_reference_gate(out: pd.DataFrame) -> pd.DataFrame:
    """Apply the latest master-list compliance decision tree.

    Trusted Dashboard rows must be Surgical scope, exact strict-master rows, and
    free of unresolved negative-scope cues. All other rows remain in RawData with
    a review/audit disposition for recall review.
    """
    for col in DIM_COLS:
        if col not in out.columns:
            out[col] = ""
    if cfg.TIER_COL not in out.columns:
        out[cfg.TIER_COL] = ""
    if cfg.SCOPE_COL not in out.columns:
        out[cfg.SCOPE_COL] = ""
    if cfg.SCOPE_FLAG_COL not in out.columns:
        out[cfg.SCOPE_FLAG_COL] = ""

    tier = out[cfg.TIER_COL].fillna("")
    matched = out.get(cfg.MATCH_STATUS_COL, pd.Series("", index=out.index)).fillna("").eq("Matched")
    scope_surg = out[cfg.SCOPE_COL].fillna("").eq(cfg.SCOPE_SURGICAL_LABEL)
    bound = tier.isin(GATE_TIERS)
    qa = pd.Series(cfg.QA_UNMAPPED, index=out.index, dtype=object)
    ref_valid = pd.Series("", index=out.index, dtype=object)
    scope_flag = out[cfg.SCOPE_FLAG_COL].fillna("").astype(str).copy()

    master = _reference_master()
    relabels = 0

    if master is None:
        qa.loc[tier.eq("manufacturer")] = cfg.QA_AUDIT_MFR
        qa.loc[matched & bound] = cfg.QA_REVIEW_NOREF
        qa.loc[matched & bound & _unspecified_mask(out)] = cfg.QA_REVIEW_UNSPEC
    else:
        family_mask = matched & tier.eq("family")
        for combo, idx in out.loc[family_mask, DIM_COLS].fillna("").astype(str).groupby(
                DIM_COLS, dropna=False, sort=False).groups.items():
            exact = tuple(norm_exact(v) for v in combo)
            loose = tuple(norm_loose(v) for v in combo)
            if exact in master["full_exact"]:
                ref_valid.loc[idx] = "Y"
                qa.loc[idx] = cfg.QA_MAPPED
                continue
            canon = master["full_loose"].get(loose)
            if canon is not None:
                for col, value in zip(DIM_COLS, canon):
                    out.loc[idx, col] = value
                ref_valid.loc[idx] = "Y"
                qa.loc[idx] = cfg.QA_MAPPED
                relabels += len(idx)
                continue
            canon = master["generic_exact"].get(exact) or master["generic_loose"].get(loose)
            if canon is not None:
                for col, value in zip(DIM_COLS, canon):
                    out.loc[idx, col] = value
                ref_valid.loc[idx] = "Y"
                qa.loc[idx] = cfg.QA_REVIEW_GEN
                relabels += len(idx)
                continue
            conflict_cats = master["pf_cats"].get(loose[3:5])
            if conflict_cats:
                qa.loc[idx] = cfg.QA_REVIEW_CAT
            else:
                qa.loc[idx] = cfg.QA_REVIEW_NOREF

            cat_canon = master["category_loose"].get(loose[:3])
            if cat_canon is not None:
                _align_category(out, idx, cat_canon)

        unspec = _unspecified_mask(out)
        for tier_name, ok_status in (
            ("category", cfg.QA_MAPPED),
            ("hs_prior", cfg.QA_AUDIT_HSPRIOR),
        ):
            cat_mask = matched & tier.eq(tier_name)
            if not bool(cat_mask.any()):
                continue
            bad_unspec = cat_mask & unspec
            qa.loc[bad_unspec] = cfg.QA_REVIEW_UNSPEC

            valid_cat_mask = cat_mask & ~unspec
            for combo, idx in out.loc[valid_cat_mask, CATEGORY_COLS].fillna("").astype(str).groupby(
                    CATEGORY_COLS, dropna=False, sort=False).groups.items():
                exact = tuple(norm_exact(v) for v in combo)
                loose = tuple(norm_loose(v) for v in combo)
                if exact in master["category_exact"]:
                    if tier_name == "category":
                        ref_valid.loc[idx] = "Y"
                    qa.loc[idx] = ok_status
                    continue
                canon = master["category_loose"].get(loose)
                if canon is not None:
                    _align_category(out, idx, canon)
                    if tier_name == "category":
                        ref_valid.loc[idx] = "Y"
                    qa.loc[idx] = ok_status
                    relabels += len(idx)
                else:
                    qa.loc[idx] = cfg.QA_REVIEW_NOREF

        qa.loc[tier.eq("manufacturer")] = cfg.QA_AUDIT_MFR
        qa.loc[~matched] = cfg.QA_UNMAPPED

    if getattr(cfg, "APPLY_SCOPE_EXCLUSIONS", False):
        scope_rx, whitelist_rx, capital_rx = _scope_regexes()
        desc_lc = _scope_text(out)
        check_scope = bound
        for i in out.index[check_scope]:
            group, keyword = _scope_hit(desc_lc.at[i], scope_rx, whitelist_rx)
            prior_flag = scope_flag.at[i].strip()
            if group is None and keyword == "whitelist":
                if prior_flag:
                    scope_flag.at[i] = ""
                continue
            if group is None and not prior_flag:
                continue
            flag = group or prior_flag

            if tier.at[i] == "family" and ref_valid.at[i] == "Y":
                family_norm = norm_loose(out.at[i, "Family"])
                keyword_norm = norm_loose(keyword or "")
                if keyword_norm and keyword_norm in family_norm:
                    scope_flag.at[i] = ""
                    continue

            scope_flag.at[i] = flag
            if qa.at[i] in (cfg.QA_MAPPED, cfg.QA_AUDIT_HSPRIOR, ""):
                qa.at[i] = cfg.QA_REVIEW_SCOPE + ": " + flag
    else:
        capital_rx = None
        desc_lc = _scope_text(out)

    review_blank = bound & qa.eq("")
    qa.loc[review_blank & ref_valid.eq("Y")] = cfg.QA_MAPPED
    qa.loc[review_blank & ~ref_valid.eq("Y")] = cfg.QA_REVIEW_NOREF

    generic_tokens = {norm_loose(value) for value in getattr(cfg, "GENERIC_TOKENS", set())}
    if generic_tokens and capital_rx is not None:
        cap_hit = desc_lc.str.contains(capital_rx, regex=True, na=False)
        fam_loose = out["Family"].map(norm_loose)
        anomaly = tier.eq("family") & qa.eq(cfg.QA_MAPPED) & fam_loose.isin(generic_tokens) & cap_hit
        qa.loc[anomaly] = cfg.QA_REVIEW_ANOM

    extended = qa.eq(cfg.QA_MAPPED) & ~scope_surg
    qa.loc[extended] = cfg.QA_REVIEW_EXT

    include = qa.eq(cfg.QA_MAPPED) & scope_surg & ref_valid.eq("Y") & scope_flag.eq("")
    out[cfg.REF_VALID_COL] = np.where(ref_valid.eq("Y"), "Y", "")
    out[cfg.SCOPE_FLAG_COL] = scope_flag
    out[cfg.DASH_INCLUDE_COL] = np.where(include, "Y", "")
    out[cfg.QA_STATUS_COL] = qa

    if master is not None:
        bad_full = 0
        for combo in out.loc[include & tier.eq("family"), DIM_COLS].fillna("").astype(str).drop_duplicates().itertuples(index=False, name=None):
            if tuple(norm_exact(v) for v in combo) not in master["full_exact"]:
                bad_full += 1
        bad_cat = 0
        for combo in out.loc[include, CATEGORY_COLS].fillna("").astype(str).drop_duplicates().itertuples(index=False, name=None):
            if tuple(norm_exact(v) for v in combo) not in master["category_exact"]:
                bad_cat += 1
        scope_leaks = 0
        scope_rx, whitelist_rx, _ = _scope_regexes()
        desc_lc = _scope_text(out)
        for i in out.index[include]:
            group, keyword = _scope_hit(desc_lc.at[i], scope_rx, whitelist_rx)
            if group is None:
                continue
            family_norm = norm_loose(out.at[i, "Family"])
            keyword_norm = norm_loose(keyword or "")
            if not (tier.at[i] == "family" and keyword_norm and keyword_norm in family_norm):
                scope_leaks += 1
        if bad_full or bad_cat or scope_leaks:
            raise AssertionError(
                "reference gate invariant failed: "
                f"family={bad_full}, category={bad_cat}, scope_leaks={scope_leaks}"
            )

    n_inc = int(include.sum())
    n_bound = int(bound.sum())
    n_scope = int((bound & scope_flag.ne("")).sum())
    n_ext = int(qa.eq(cfg.QA_REVIEW_EXT).sum())
    n_ref = int(ref_valid.eq("Y").sum())
    print(f"  [ref-gate] {n_inc:,}/{n_bound:,} bound rows trusted "
          f"({n_ref:,} reference-valid; {n_ext:,} Extended-review; "
          f"{n_scope:,} scope-excluded; {relabels:,} relabelled)")
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
