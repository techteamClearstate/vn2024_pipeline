#!/usr/bin/env python3
"""Build the Recall Funnel & Understandability dashboard (REVIEW-ONLY).

Reads the governed prediction-audit SQLite authority
(`outputs/<run_id>/prediction_audit.sqlite`) and emits a single, self-contained
HTML dashboard that answers, in plain language:

  * What the pipeline does and what each output tier (Trusted / Review / Excluded)
    means for integration.
  * An **additive recall funnel** per file: after each step, how much data is
    KEPT vs LOST (transactions, value, volume) with no double-counting.
  * A **breakdown explorer**: how the kept/lost split varies by File, OU (Segment),
    Sub-OU (Sub-segment), Device (Product), Family, Manufacturer, and by
    Value / Volume / ASP band.
  * **Recall hotspots**: which one or two steps cause most of the loss, and where
    the safe recovery opportunities are.
  * Plain-language explanation of every step, and a glossary for traceability.

GOVERNANCE: This tool NEVER writes to the SQLite authority and NEVER changes
production routing, reference lists, or published workbooks. It only reads the
authority and writes an HTML *view*. The additive funnel uses
`row_fact.removal_stage_id` + `primary_reason` (the single stage where each row
left the Trusted path), so every number reconciles to the row grain.

Usage:
    PYTHONIOENCODING=utf-8 python tools/build_funnel_dashboard.py \
        [--db outputs/<run_id>/prediction_audit.sqlite] \
        [--out outputs/<run_id>/Recall_Funnel_Dashboard.html]
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import html
import json
import sqlite3
from pathlib import Path

from precision_measurement import build_measured_accuracy

REPO = Path(__file__).resolve().parents[1]
DEFAULT_RUN = "20260710_recall_audit_v2"

# ---------------------------------------------------------------------------
# Dimension definitions (SQL expression + display label). Domain vocabulary:
#   OU = Segment, Sub-OU = Sub-segment, Device = Product_V0, Family = Family.
# Band labels are prefixed "N · " so they sort naturally; the prefix is stripped
# for display in the front-end.
# ---------------------------------------------------------------------------
UNMAPPED = "<Unmapped>"

def _cat(col: str) -> str:
    return f"CASE WHEN COALESCE(NULLIF(TRIM({col}),''),'')='' THEN '{UNMAPPED}' ELSE {col} END"

VALUE_BAND = (
    "CASE WHEN value_numeric_status<>'valid' THEN '7 · (no value)' "
    "WHEN value_usd < 1000 THEN '1 · <$1k' "
    "WHEN value_usd < 10000 THEN '2 · $1k–10k' "
    "WHEN value_usd < 50000 THEN '3 · $10k–50k' "
    "WHEN value_usd < 250000 THEN '4 · $50k–250k' "
    "WHEN value_usd < 1000000 THEN '5 · $250k–1M' "
    "ELSE '6 · ≥$1M' END"
)
VOLUME_BAND = (
    "CASE WHEN volume_numeric_status<>'valid' THEN '7 · (no volume)' "
    "WHEN volume < 1 THEN '1 · <1' "
    "WHEN volume < 10 THEN '2 · 1–9' "
    "WHEN volume < 100 THEN '3 · 10–99' "
    "WHEN volume < 1000 THEN '4 · 100–999' "
    "WHEN volume < 10000 THEN '5 · 1k–9,999' "
    "ELSE '6 · ≥10k' END"
)
ASP_BAND = (
    "CASE WHEN value_numeric_status<>'valid' OR volume_numeric_status<>'valid' OR volume<=0 THEN '6 · (n/a)' "
    "WHEN value_usd/volume < 10 THEN '1 · <$10' "
    "WHEN value_usd/volume < 100 THEN '2 · $10–100' "
    "WHEN value_usd/volume < 1000 THEN '3 · $100–1k' "
    "WHEN value_usd/volume < 10000 THEN '4 · $1k–10k' "
    "ELSE '5 · ≥$10k' END"
)

# key -> (label, sql_expr, is_band)
DIMENSIONS = {
    "file":         ("File (market-year)", "(country || ' FY' || fiscal_year)", False),
    "segment":      ("OU · Segment", _cat("segment"), False),
    "sub_segment":  ("Sub-OU · Sub-segment", _cat("sub_segment"), False),
    "product":      ("Device · Product", _cat("product"), False),
    "family":       ("Family", _cat("family"), False),
    "manufacturer": ("Manufacturer", _cat("manufacturer"), False),
    "value_band":   ("Value band (USD/row)", VALUE_BAND, True),
    "volume_band":  ("Volume band (units/row)", VOLUME_BAND, True),
    "asp_band":     ("ASP band (USD/unit)", ASP_BAND, True),
}
TOP_N = 15  # top categories per slice; remainder bucketed as "Other"

TIERS = ["Trusted", "Review", "Excluded"]

# Explainability playground controls.  A checked gate in the browser means the
# production gate is still active; unchecking it is a review-only counterfactual.
# Bit values are stable within the dashboard payload and deliberately explicit
# so verification can re-derive every mask from rule_hit.
GATES = [
    {"key": "dental", "bit": 1, "stage": "S02_DENTAL_SUPPRESSION",
     "label": "Dental-only screen",
     "guidance": "Check whether dental wording is incidental to a genuinely surgical device; propose a narrowly evidenced whitelist, never a blanket dental bypass."},
    {"key": "negative", "bit": 2, "stage": "S04_CATEGORY_FALLBACK",
     "label": "Negative / accessory conflict",
     "guidance": "Confirm that the accessory or negative cue is misleading in context, then submit the exact phrase and examples for adjudication."},
    {"key": "reference", "bit": 4, "stage": "S07_REFERENCE_VALIDATION",
     "label": "Reference-master validation",
     "guidance": "Use the evidenced proposals workbook to approve exact product tuples or master additions; do not backfill from a family label alone."},
    {"key": "scope", "bit": 8, "stage": "S08_SCOPE_WHITELIST",
     "label": "Scope exclusions",
     "guidance": "Identify the independent surgical evidence that outweighs the veterinary, cosmetic, lab, dental, or imaging cue and request a precise whitelist."},
    {"key": "generic", "bit": 16, "stage": "S09_GENERIC_ANOMALY",
     "label": "Generic-token guard",
     "guidance": "Show why the ambiguous token is a real brand or product in this slice; propose a contextual rule rather than removing the generic-token protection."},
    {"key": "extended", "bit": 32, "stage": "S10_EXTENDED_HS",
     "label": "Extended-HS guard",
     "guidance": "Document the surgical evidence for rows outside the core HS scope and adjudicate a bounded HS/product exception."},
    {"key": "ophthalmic", "bit": 64, "stage": "S12_REMAP_GUARDS",
     "label": "Ophthalmic / imaging guard",
     "guidance": "Verify the item is a surgical product caught by stray imaging language, then request a family- or phrase-specific whitelist."},
]
GATE_BY_STAGE = {g["stage"]: g for g in GATES}
EXAMPLE_CELL_TOP = 6
EXAMPLE_CELL_RANDOM = 2
EXAMPLE_SIM_TOP = 2
EXAMPLE_SIM_RANDOM = 1
EXAMPLE_RECOVERY_CAP = 5
EXAMPLE_PAYLOAD_BUDGET = 600 * 1024

# Recovery analysis SQL fragments -------------------------------------------
REF_VALID = ("lower(coalesce(reference_status,'')) in "
             "('valid','y','yes','true','1','reference-valid')")
# "recognised family" = a real brand/model family, not a blank or the
# 'Unspecified' placeholder (which means matched-but-dimension-unspecified).
RECOG_FAMILY = ("coalesce(nullif(trim(family),''),'')<>'' "
                "and lower(trim(family)) not in ('unspecified','(unspecified)')")
# Partition of every NON-Trusted row into one recovery bucket (mutually
# exclusive; ordered by confidence that recovery is safe).
BUCKET_CASE = f"""CASE
  WHEN removal_stage_id='S12_REMAP_GUARDS' AND output_tier='Review' AND {REF_VALID} THEN 'misguarded'
  WHEN removal_stage_id='S07_REFERENCE_VALIDATION' AND ({RECOG_FAMILY}) THEN 'loose'
  WHEN primary_reason='Audit - manufacturer only' THEN 'mfr_only'
  WHEN primary_reason='Unmapped' OR (removal_stage_id='S07_REFERENCE_VALIDATION' AND NOT ({RECOG_FAMILY})) THEN 'weak'
  WHEN output_tier<>'Trusted' THEN 'other'
  ELSE 'trusted' END"""

RECOVERY_BUCKETS = {
    "misguarded": {
        "label": "Mis-guarded surgical (caught by a scope guard)",
        "safety": "High confidence",
        "signal": "Reference-valid product held back only by the ophthalmic/imaging guard (S12).",
        "action": "Review the scope whitelist — these are known catalogued products flagged by a stray keyword. Smallest but safest lever.",
    },
    "loose": {
        "label": "Recognised-family, reference-invalid (S07)",
        "safety": "Mostly correctly held",
        "signal": "A family name was recognised but the tuple failed reference validation. IMPORTANT: on failed rows the family match is usually SPURIOUS — ~64% of this value has a family that does not even appear in the product description (e.g. a cataract lens tagged 'Trauma Plates And Screws'). Reference validation correctly rejects these.",
        "action": "Only the small description-evidenced slice (see the master cross-check panel) is a real lever — adjudicate those per row. Do NOT bulk-backfill categories from the family field; it would misclassify products and hurt precision.",
    },
    "mfr_only": {
        "label": "Manufacturer recognised, product missing",
        "safety": "Lower — coverage work",
        "signal": "Only the maker was identified; no product/model matched. Highly concentrated — the top ~10 makers hold ~80% of this value, and the descriptions often name a known product line (e.g. J&J ATTUNE/SIGMA knees, TECNIS IOLs).",
        "action": "Add the top makers' product families to the lexicon, per maker, highest value first. Precision-sensitive but the descriptions are clean; recover in controlled batches, then re-audit.",
    },
    "weak": {
        "label": "Little/no product evidence (Unmapped or no family)",
        "safety": "Lowest — new evidence needed",
        "signal": "Never matched a product, or reference-invalid with no recognised family.",
        "action": "Requires new reference/lexicon terms or richer source text. NOTE: the Unmapped part is almost entirely India FY2025, whose audit uses the complete pre-final-mapping CSV source — treat its size as an upper bound, not a direct production gap.",
    },
    "other": {
        "label": "Other held-back (scope / anomaly / imaging Excluded)",
        "safety": "Mostly correct exclusions",
        "signal": "Out-of-scope keyword, generic/date-token anomaly, or imaging equipment with no surgical signal.",
        "action": "Generally correct to hold back; spot-check only the very highest-value rows.",
    },
}
RECOVERY_ORDER = ["misguarded", "loose", "mfr_only", "weak", "other"]

REF_DB = REPO / "reference" / "reference.sqlite"
# Ambiguous family tokens that exist in the master but should stay held back
# (from the registry generic-token list + common instrument words + month names).
GENERIC_TOKENS = {
    "target", "light source", "sprinter", "essential", "unity", "hybrid", "elite",
    "optime", "therapy", "evolution", "physio", "woven", "cone", "vector", "crescent",
    "traveler", "forceps", "scissor", "scissors", "monopolar", "bipolar", "retractor",
    "cannula", "trocar", "catheter", "guidewire", "balloon", "clip", "mesh", "suture",
    "needle", "drain", "stapler", "probe", "blade",
}
MONTHS = {"january", "february", "march", "april", "may", "june", "july", "august",
          "september", "october", "november", "december"}
# S07 recognised-family recovery classes, ordered by how safe recovery is.
# CRITICAL: on failed rows the family match is frequently SPURIOUS (e.g. a cataract
# lens tagged "Trauma Plates And Screws"), which is why they failed validation. So a
# family that maps cleanly to the master is only a real lever when the family token
# actually appears in the product description — otherwise it is correctly held.
S07_CLASSES = {
    "clean_evidenced": "Safe lever — family maps to one master category AND appears in the description",
    "not_in_master": "Not in master — genuine catalogue gap (needs a master addition)",
    "ambiguous_multi": "Ambiguous — family maps to several master categories (needs disambiguation)",
    "ambiguous_generic": "Ambiguous — generic / date-token family (correctly held; low recovery)",
    "clean_unevidenced": "Likely spurious — family maps to master but is NOT in the description (correctly held)",
}
S07_CLASS_ORDER = ["clean_evidenced", "not_in_master", "ambiguous_multi",
                   "ambiguous_generic", "clean_unevidenced"]


def _norm(s):
    import re
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _desc_norm(s):
    import re
    return re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())


def _family_in_desc(family, desc_normed):
    """True when the family name (or a significant word of it, len>=4) appears in the
    already-normalised description — a cheap check that the family match is real."""
    nf = _norm(family)
    if not nf:
        return False
    if nf in desc_normed:
        return True
    return any(w in desc_normed for w in nf.split() if len(w) >= 4)


def build_master_classifier(ref_db: Path):
    """Return (classify_fn, cat_fn) using the governed brand master, or (None, None)
    if the reference DB is unavailable. classify_fn(family)->class; cat_fn(family)->
    'Segment | Sub | Product' when the family maps to exactly one master category."""
    if not ref_db.exists():
        return None, None
    con = sqlite3.connect(f"file:{ref_db}?mode=ro", uri=True)
    fam_cats: dict[str, set] = {}
    try:
        for seg, sub, prod, _player, fam in con.execute(
            "SELECT segment, sub_segment, product, player, family_name FROM brand_model_master"
        ):
            nf = _norm(fam)
            if nf:
                fam_cats.setdefault(nf, set()).add((seg, sub, prod))
    finally:
        con.close()

    def classify(family: str) -> str:
        nf = _norm(family)
        if nf not in fam_cats:
            return "not_in_master"
        if nf in GENERIC_TOKENS or nf in MONTHS:
            return "ambiguous_generic"
        if len(fam_cats[nf]) > 1 or len(nf) <= 3:
            return "ambiguous_multi"
        return "clean"

    def category(family: str):
        nf = _norm(family)
        cats = fam_cats.get(nf)
        if cats and len(cats) == 1:
            seg, sub, prod = next(iter(cats))
            return " | ".join(x for x in (seg, sub, prod) if x)
        return ""

    return classify, category

# ---------------------------------------------------------------------------
# Plain-language descriptions of every registry stage. Keyed by stage_id.
# "what" = one-sentence plain meaning; "why" = why the step exists;
# "kept"/"lost" describe what continuing vs. leaving means for that step.
# ---------------------------------------------------------------------------
STAGE_PLAIN = {
    "S00_EXTRACTION": {
        "short": "Load every source row",
        "what": "Read every shipment row from the complete source file, exactly as delivered.",
        "why": "Nothing can be analysed that was never loaded. We verify the row count matches the source so no data is silently dropped.",
    },
    "S01_HS_ELIGIBILITY": {
        "short": "HS-code eligibility",
        "what": "Check each row's customs HS code against the configured scope.",
        "why": "Today every HS code is allowed to continue (MATCH_ALL_HS4), so this step removes nothing — it is kept for auditability.",
    },
    "S02_DENTAL_SUPPRESSION": {
        "short": "Dental-only screen",
        "what": "Set aside rows that read as purely dental unless they also carry an independent surgical signal.",
        "why": "Dental consumables are out of surgical scope, but a genuine surgical device that merely mentions 'dental' is recovered.",
    },
    "S03_FAMILY_MATCH": {
        "short": "Brand / model match (Tier-1)",
        "what": "Try to match the product description to a specific brand/model family in the master list — the strongest evidence.",
        "why": "A family hit is the highest-confidence mapping. Rows that never match here fall through to weaker matchers.",
    },
    "S04_CATEGORY_FALLBACK": {
        "short": "Category match (Tier-2)",
        "what": "When no brand/model matches, try a broader product-category phrase; negative / accessory cues can block it.",
        "why": "Recovers rows with generic but recognisable category wording, while blocking obvious accessories and conflicts.",
    },
    "S05_MANUFACTURER_FALLBACK": {
        "short": "Manufacturer-only match (Tier-3)",
        "what": "When only the maker is recognisable, tag the manufacturer but not a specific product.",
        "why": "Keeps the maker for context, but a maker with no product is not trusted for the revenue dashboard.",
    },
    "S06_STANDARDIZATION": {
        "short": "Standardise the labels",
        "what": "Canonicalise the matched Segment / Sub-segment / Product / Manufacturer / Family wording.",
        "why": "Consistent labels are required before they can be checked against the reference master.",
    },
    "S07_REFERENCE_VALIDATION": {
        "short": "Reference-master validation",
        "what": "Require the standardised Segment × Sub-segment × Product tuple to exist in the governed surgical master before a row can be Trusted.",
        "why": "This is the main quality gate: it guarantees every Trusted row is a known, catalogued surgical product. It is also the single biggest place recall is lost — many real products simply are not in the master yet.",
    },
    "S08_SCOPE_WHITELIST": {
        "short": "Scope exclusions",
        "what": "Apply veterinary / dental / cosmetic / lab-IVD / imaging exclusion cues; a whitelist or independent surgical signal can recover a row.",
        "why": "Removes look-alikes that are out of surgical scope, while protecting genuine surgical products caught by a stray keyword.",
    },
    "S09_GENERIC_ANOMALY": {
        "short": "Generic / token anomaly guard",
        "what": "Hold back rows relying on generic words, date/month tokens, or other risky tokens.",
        "why": "Stops accidental matches on ambiguous words (e.g. a month name colliding with a brand) from being trusted.",
    },
    "S10_EXTENDED_HS": {
        "short": "Extended-HS support",
        "what": "Handle rows matched only via widened HS scope; block them where false-positive risk is flagged.",
        "why": "Extended-HS can add evidence but must not override stronger negative or reference controls.",
    },
    "S11_HS_PRIOR": {
        "short": "HS-prior recovery",
        "what": "Recover a likely product from a learned HS × manufacturer prior when nothing stronger matched.",
        "why": "Lowest-confidence recovery; kept visible but not trusted unless it clears every later guard.",
    },
    "S12_REMAP_GUARDS": {
        "short": "Final precision guards",
        "what": "Apply the final evidence / reference / generic / ophthalmic-imaging / vector guards before routing.",
        "why": "Last-line precision protection. The ophthalmic/imaging guard here is the second-largest source of recall loss.",
    },
    "S13_TERMINAL_ROUTING": {
        "short": "Final routing",
        "what": "Send each row to exactly one destination: Trusted, Review, or Excluded.",
        "why": "Rows that never matched a product (Unmapped) or matched only a manufacturer end here — a coverage gap rather than a filter.",
    },
    "S14_PRESENTATION_EXPORT": {
        "short": "Export the views",
        "what": "Publish bounded roll-ups and a review sample; the full row-level detail stays in the SQLite authority.",
        "why": "Keeps deliverables small and readable while every fact remains traceable in the database.",
    },
}

TIER_PLAIN = {
    "Trusted": ("Ready to use", "Passed every gate: a known surgical product, reference-valid, in surgical HS scope, no conflict flag. Use these for the trusted revenue dashboard and roll-ups."),
    "Review": ("Needs a human look", "Has real evidence but did not clear a gate (e.g. the product is not in the master yet, or a guard flagged it). This is the recall-recovery backlog — adjudicate the high-value ones."),
    "Excluded": ("Out of scope / no evidence", "No accepted product evidence or an out-of-scope signal. Mostly genuinely non-surgical, but the highest-value Excluded rows are still worth spot-checking."),
}


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")


def m3(rows, val, vol):
    """Normalise a metric triple to [int, float, float]."""
    return [int(rows or 0), round(float(val or 0.0), 2), round(float(vol or 0.0), 2)]


def add3(a, b):
    return [a[0] + b[0], round(a[1] + b[1], 2), round(a[2] + b[2], 2)]


def strip_prefix(label: str) -> str:
    # "3 · $10k–50k" -> "$10k–50k"; leave non-prefixed labels untouched
    if len(label) > 3 and label[1:4] == " · ":
        return label[4:]
    return label


def _gate_case(alias: str = "rf") -> str:
    """SQL CASE mapping an authoritative primary removal stage to a gate key."""
    parts = " ".join(
        f"WHEN {alias}.removal_stage_id='{g['stage']}' THEN '{g['key']}'" for g in GATES
    )
    return f"CASE {parts} ELSE NULL END"


def _gate_bit_case(alias: str = "rf") -> str:
    parts = " ".join(
        f"WHEN {alias}.removal_stage_id='{g['stage']}' THEN {g['bit']}" for g in GATES
    )
    return f"CASE {parts} ELSE 0 END"


def _secondary_bit_case(alias: str = "rh") -> str:
    """Map only secondary hits that can genuinely act as another gate.

    S05/S11 matching signals and S12's MRI-compatible recovery-risk signal are
    intentionally excluded: they are evidence/risk annotations, not blockers.
    """
    return f"""CASE
      WHEN {alias}.stage_id='S02_DENTAL_SUPPRESSION' AND {alias}.reason='dental_cue' THEN 1
      WHEN {alias}.stage_id='S04_CATEGORY_FALLBACK' AND {alias}.reason LIKE 'negative_conflict:%' THEN 2
      WHEN {alias}.stage_id='S08_SCOPE_WHITELIST' AND {alias}.reason LIKE 'scope_flag:%' THEN 8
      WHEN {alias}.stage_id='S09_GENERIC_ANOMALY' AND {alias}.reason='generic_or_token_anomaly' THEN 16
      WHEN {alias}.stage_id='S10_EXTENDED_HS' AND {alias}.reason='extended_hs_false_positive_risk' THEN 32
      WHEN {alias}.stage_id='S12_REMAP_GUARDS' AND {alias}.reason='ophthalmic_imaging_conflict' THEN 64
      ELSE 0 END"""


def _display_example_value(value, *, qa: bool = False) -> str:
    """Preserve literal Unspecified and reserve <Unmapped> for missing mapping text."""
    value = "" if value is None else str(value).strip()
    if value:
        return value
    return "Unspecified" if qa else UNMAPPED


def _metric_from_row(row) -> list:
    return m3(row[0], row[1], row[2])


# ---------------------------------------------------------------------------
# Data assembly
# ---------------------------------------------------------------------------
def _build_simulator(cur: sqlite3.Cursor, file_ids: list[str]) -> dict:
    """Build the exact client-side what-if grain from primary + secondary hits.

    The temporary table lives only in SQLite's temp database; the authority is
    opened read-only and is never mutated.  Each non-Trusted row has one primary
    removal stage and a bit mask of *other* gates that could still hold it.
    """
    primary_case = _gate_case("rf")
    primary_bit = _gate_bit_case("rf")
    secondary_bit = _secondary_bit_case("rh")
    cur.execute("DROP TABLE IF EXISTS temp.dashboard_sim_row")
    cur.execute(f"""
        CREATE TEMP TABLE dashboard_sim_row AS
        WITH hit_bits AS (
          SELECT DISTINCT rh.row_fact_id, {secondary_bit} AS bit
          FROM rule_hit rh
          WHERE rh.hit_kind='secondary'
        ), masks AS (
          SELECT row_fact_id, SUM(bit) AS secondary_mask
          FROM hit_bits WHERE bit<>0 GROUP BY row_fact_id
        )
        SELECT rf.row_fact_id, rf.output_file_id,
               {primary_case} AS primary_gate,
               (COALESCE(masks.secondary_mask,0) & ~({primary_bit})) AS secondary_mask
        FROM row_fact rf
        LEFT JOIN masks ON masks.row_fact_id=rf.row_fact_id
        WHERE rf.output_tier<>'Trusted'
    """)
    cur.execute(
        "CREATE INDEX temp.idx_dashboard_sim_group "
        "ON dashboard_sim_row(output_file_id, primary_gate, secondary_mask, row_fact_id)"
    )

    groups = []
    for fid, gate, mask, n, value, volume in cur.execute(
        "SELECT s.output_file_id, s.primary_gate, s.secondary_mask, COUNT(*), "
        "SUM(r.value_usd), SUM(r.volume) FROM dashboard_sim_row s "
        "JOIN row_fact r ON r.row_fact_id=s.row_fact_id "
        "WHERE s.primary_gate IS NOT NULL "
        "GROUP BY s.output_file_id, s.primary_gate, s.secondary_mask "
        "ORDER BY s.output_file_id, s.primary_gate, s.secondary_mask"
    ):
        groups.append({"file": fid, "gate": gate, "mask": int(mask or 0),
                       "m": m3(n, value, volume), "examples": []})

    locked = {fid: {"m": [0, 0.0, 0.0], "reasons": []} for fid in file_ids + ["ALL"]}
    reason_raw = {fid: [] for fid in file_ids}
    for fid, stage, reason, n, value, volume in cur.execute(
        "SELECT s.output_file_id, r.removal_stage_id, r.primary_reason, COUNT(*), "
        "SUM(r.value_usd), SUM(r.volume) FROM dashboard_sim_row s "
        "JOIN row_fact r ON r.row_fact_id=s.row_fact_id "
        "WHERE s.primary_gate IS NULL "
        "GROUP BY s.output_file_id, r.removal_stage_id, r.primary_reason"
    ):
        met = m3(n, value, volume)
        reason_raw[fid].append({"stage": stage, "reason": reason, "m": met})
        locked[fid]["m"] = add3(locked[fid]["m"], met)
        locked["ALL"]["m"] = add3(locked["ALL"]["m"], met)
    for fid in file_ids:
        locked[fid]["reasons"] = sorted(reason_raw[fid], key=lambda x: -x["m"][1])
    all_reasons = {}
    for rows in reason_raw.values():
        for row in rows:
            key = (row["stage"], row["reason"])
            all_reasons[key] = add3(all_reasons.get(key, [0, 0.0, 0.0]), row["m"])
    locked["ALL"]["reasons"] = [
        {"stage": k[0], "reason": k[1], "m": met}
        for k, met in sorted(all_reasons.items(), key=lambda kv: -kv[1][1])
    ]

    # Small, deterministic example set per aggregate group: highest value plus
    # one hash-ordered row to prevent examples from being only outliers.
    for group in groups:
        params = (group["file"], group["gate"], group["mask"])
        top = [r[0] for r in cur.execute(
            "SELECT s.row_fact_id FROM dashboard_sim_row s JOIN row_fact r USING(row_fact_id) "
            "WHERE s.output_file_id=? AND s.primary_gate=? AND s.secondary_mask=? "
            "ORDER BY COALESCE(r.value_usd,0) DESC, s.row_fact_id LIMIT ?",
            (*params, EXAMPLE_SIM_TOP),
        )]
        rnd = [r[0] for r in cur.execute(
            "SELECT s.row_fact_id FROM dashboard_sim_row s JOIN row_fact r USING(row_fact_id) "
            "WHERE s.output_file_id=? AND s.primary_gate=? AND s.secondary_mask=? "
            "ORDER BY COALESCE(r.source_text_hash,''), s.row_fact_id LIMIT ?",
            (*params, EXAMPLE_SIM_RANDOM),
        )]
        group["examples"] = list(dict.fromkeys(top + rnd))

    return {
        "gates": GATES,
        "groups": groups,
        "locked": locked,
        "mask_max": sum(g["bit"] for g in GATES),
        "semantics": "A row can move only when its primary gate is unchecked. Enabled secondary gates then decide whether it reaches simulated Trusted or is likely held elsewhere.",
    }


def _collect_cell_examples(cur: sqlite3.Cursor) -> dict:
    """Top-value + deterministic-random examples per file × stage × reason."""
    cells: dict[str, dict] = {}
    keys = list(cur.execute(
        "SELECT output_file_id, removal_stage_id, primary_reason FROM row_fact "
        "WHERE output_tier<>'Trusted' "
        "GROUP BY output_file_id, removal_stage_id, primary_reason"
    ))
    for fid, stage, reason in keys:
        args = (fid, stage, reason)
        top = [r[0] for r in cur.execute(
            "SELECT row_fact_id FROM row_fact WHERE output_tier<>'Trusted' "
            "AND output_file_id=? AND removal_stage_id=? AND primary_reason=? "
            "ORDER BY COALESCE(value_usd,0) DESC, row_fact_id LIMIT ?",
            (*args, EXAMPLE_CELL_TOP),
        )]
        rnd = [r[0] for r in cur.execute(
            "SELECT row_fact_id FROM row_fact WHERE output_tier<>'Trusted' "
            "AND output_file_id=? AND removal_stage_id=? AND primary_reason=? "
            "ORDER BY COALESCE(source_text_hash,''), row_fact_id LIMIT ?",
            (*args, EXAMPLE_CELL_RANDOM),
        )]
        cells.setdefault(fid, {}).setdefault(stage, {})[reason] = list(dict.fromkeys(top + rnd))
    return cells


def _attach_recovery_examples(cur: sqlite3.Cursor, recovery: dict, file_ids: list[str]) -> None:
    """Attach example row ids to every displayed recovery cluster."""
    specs = [
        ("clusters_mfr", "manufacturer",
         "primary_reason='Audit - manufacturer only'"),
        ("clusters_misguarded", "family",
         f"removal_stage_id='S12_REMAP_GUARDS' AND output_tier='Review' AND {REF_VALID}"),
        ("clusters_loose", "loose", f"removal_stage_id='S07_REFERENCE_VALIDATION' AND ({RECOG_FAMILY})"),
    ]
    for dest, key_type, where in specs:
        wanted_all = {tuple(c["k"]) for c in recovery["ALL"].get(dest, [])}
        wanted = {
            fid: {tuple(c["k"]) for c in recovery[fid].get(dest, [])} | wanted_all
            for fid in file_ids
        }
        heaps: dict[tuple, list[tuple[float, int]]] = {}
        for row in cur.execute(
            "SELECT row_fact_id, output_file_id, "
            "coalesce(nullif(trim(manufacturer),''),'?'), "
            "coalesce(nullif(trim(family),''),'?'), detailed_product, value_usd "
            f"FROM row_fact WHERE {where}"
        ):
            rowid, fid, mfr, fam, desc, value = row
            cluster_key = (mfr,) if key_type == "manufacturer" else ((fam,) if key_type == "family" else (mfr, fam))
            if cluster_key not in wanted.get(fid, set()):
                continue
            if key_type == "loose" and not _family_in_desc(fam, _desc_norm(desc)):
                continue
            hk = (fid, cluster_key)
            bucket = heaps.setdefault(hk, [])
            item = (float(value or 0.0), int(rowid))
            if len(bucket) < EXAMPLE_RECOVERY_CAP:
                import heapq
                heapq.heappush(bucket, item)
            elif item > bucket[0]:
                import heapq
                heapq.heapreplace(bucket, item)

        def ids_for(scope, ckey):
            if scope == "ALL":
                vals = [item for fid in file_ids for item in heaps.get((fid, ckey), [])]
            else:
                vals = list(heaps.get((scope, ckey), []))
            vals.sort(reverse=True)
            return [rowid for _value, rowid in vals[:EXAMPLE_RECOVERY_CAP]]

        for scope in file_ids + ["ALL"]:
            for cluster in recovery[scope].get(dest, []):
                cluster["examples"] = ids_for(scope, tuple(cluster["k"]))


def _build_example_store(cur: sqlite3.Cursor, cells: dict, simulator: dict,
                         recovery: dict) -> dict:
    ids = set()
    for by_stage in cells.values():
        for by_reason in by_stage.values():
            for row_ids in by_reason.values():
                ids.update(row_ids)
    for group in simulator["groups"]:
        ids.update(group["examples"])
    for scope in recovery.values():
        if not isinstance(scope, dict):
            continue
        for key in ("clusters_mfr", "clusters_misguarded", "clusters_loose"):
            for cluster in scope.get(key, []):
                ids.update(cluster.get("examples", []))

    rows = {}
    id_list = sorted(ids)
    for start in range(0, len(id_list), 800):
        chunk = id_list[start:start + 800]
        marks = ",".join("?" for _ in chunk)
        for r in cur.execute(
            "SELECT row_fact_id, output_file_id, source_row_id, detailed_product, "
            "manufacturer, family, product, segment, value_usd, qa_status, output_tier, "
            "removal_stage_id, primary_reason FROM row_fact "
            f"WHERE row_fact_id IN ({marks})", chunk
        ):
            rowid, fid, source_id, desc, maker, family, product, segment, value, qa, tier, stage, reason = r
            rows[str(rowid)] = {
                "id": rowid, "file": fid, "source_row": source_id,
                "description": _display_example_value(desc),
                "maker": _display_example_value(maker),
                "family": _display_example_value(family),
                "product": _display_example_value(product),
                "segment": _display_example_value(segment),
                "value": round(float(value or 0.0), 2),
                "qa": _display_example_value(qa, qa=True),
                "tier": tier, "stage": stage, "reason": reason,
            }
    payload = {"rows": rows, "cells": cells}
    size = len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    if size > EXAMPLE_PAYLOAD_BUDGET:
        raise RuntimeError(
            f"Example payload is {size / 1024:.0f} KB, above the {EXAMPLE_PAYLOAD_BUDGET / 1024:.0f} KB budget"
        )
    payload["payload_bytes"] = size
    payload["selection"] = {
        "cell_top": EXAMPLE_CELL_TOP, "cell_random": EXAMPLE_CELL_RANDOM,
        "sim_top": EXAMPLE_SIM_TOP, "sim_random": EXAMPLE_SIM_RANDOM,
        "recovery_cap": EXAMPLE_RECOVERY_CAP,
    }
    return payload


def build_data(con: sqlite3.Connection) -> dict:
    cur = con.cursor()

    run = cur.execute(
        "SELECT run_id, registry_version, code_commit, completed_at FROM run LIMIT 1"
    ).fetchone()
    run_id, registry_version, code_commit, completed_at = run

    files = []
    for r in cur.execute(
        "SELECT output_file_id, output_label, country, fiscal_year, observed_rows, ingestion_mode "
        "FROM source_file ORDER BY country, fiscal_year"
    ):
        files.append({
            "id": r[0], "label": r[1], "country": r[2], "fy": r[3],
            "rows": r[4], "ingestion": r[5],
        })
    file_ids = [f["id"] for f in files]

    # Stage order + labels from the registry (authoritative funnel definition).
    stage_order = {}
    stage_label = {}
    for sid, order, label in cur.execute(
        "SELECT stage_id, execution_order, documentation_label FROM rule_registry_stage ORDER BY execution_order"
    ):
        stage_order[sid] = order
        stage_label[sid] = label

    # ---- Totals + funnel drops (one scan) --------------------------------
    # Per file: totals by tier, and non-Trusted drops attributed by stage+reason.
    totals = {fid: {t: [0, 0.0, 0.0] for t in TIERS} for fid in file_ids}
    totals["ALL"] = {t: [0, 0.0, 0.0] for t in TIERS}
    # drops[fid][stage_id] = {tier: metric, reasons: {(reason,tier): metric}}
    drops = {fid: {} for fid in file_ids}
    drops["ALL"] = {}

    def ensure_stage(d, sid):
        if sid not in d:
            d[sid] = {"Review": [0, 0.0, 0.0], "Excluded": [0, 0.0, 0.0],
                      "Trusted": [0, 0.0, 0.0], "reasons": {}}
        return d[sid]

    for fid, sid, tier, reason, n, v, vol in cur.execute(
        "SELECT output_file_id, removal_stage_id, output_tier, primary_reason, "
        "COUNT(*), SUM(value_usd), SUM(volume) FROM row_fact "
        "GROUP BY output_file_id, removal_stage_id, output_tier, primary_reason"
    ):
        met = m3(n, v, vol)
        for scope in (fid, "ALL"):
            totals[scope][tier] = add3(totals[scope][tier], met)
            st = ensure_stage(drops[scope], sid)
            st[tier] = add3(st[tier], met)
            key = (reason, tier)
            st["reasons"][key] = add3(st["reasons"].get(key, [0, 0.0, 0.0]), met)

    # Assemble the ordered additive funnel per scope.
    funnel = {}
    for scope in file_ids + ["ALL"]:
        tot = [0, 0.0, 0.0]
        for t in TIERS:
            tot = add3(tot, totals[scope][t])
        steps = []
        remaining = list(tot)
        for sid in sorted(drops[scope], key=lambda s: stage_order.get(s, 999)):
            st = drops[scope][sid]
            lost_review = st["Review"]
            lost_excl = st["Excluded"]
            lost = add3(lost_review, lost_excl)
            entering = list(remaining)
            remaining = [entering[i] - lost[i] for i in range(3)]
            remaining = [round(x, 2) for x in remaining]
            # top reasons at this step (non-Trusted), by value
            reasons = sorted(
                ([r, t, *met] for (r, t), met in st["reasons"].items() if t != "Trusted"),
                key=lambda x: -x[3],
            )[:6]
            steps.append({
                "stage": sid,
                "label": stage_label.get(sid, sid),
                "short": STAGE_PLAIN.get(sid, {}).get("short", stage_label.get(sid, sid)),
                "entering": [round(x, 2) for x in entering],
                "lost_review": lost_review,
                "lost_excluded": lost_excl,
                "lost": lost,
                "retained": remaining,
                "reasons": [{"reason": r, "tier": t, "m": [a, b, c]} for r, t, a, b, c in reasons],
            })
        funnel[scope] = {
            "total": [round(x, 2) for x in tot],
            "trusted": totals[scope]["Trusted"],
            "review": totals[scope]["Review"],
            "excluded": totals[scope]["Excluded"],
            "steps": steps,
        }

    # ---- Breakdown cubes -------------------------------------------------
    # population[scope][dim] = [{k,label,T,R,E}]  (recall by slice)
    # loss_by_stage[scope][stage][dim] = [{k,label,m}]  (where each step hurts)
    population = {fid: {} for fid in file_ids}
    population["ALL"] = {}
    loss_by_stage = {fid: {} for fid in file_ids}
    loss_by_stage["ALL"] = {}

    for dim, (dlabel, expr, is_band) in DIMENSIONS.items():
        # ---- population cube (by tier) ----
        raw = {}  # (scope, dv) -> {tier: metric}
        for fid, dv, tier, n, v, vol in cur.execute(
            f"SELECT output_file_id, {expr} AS dv, output_tier, "
            f"COUNT(*), SUM(value_usd), SUM(volume) FROM row_fact "
            f"GROUP BY output_file_id, dv, output_tier"
        ):
            met = m3(n, v, vol)
            for scope in (fid, "ALL"):
                d = raw.setdefault((scope, dv), {t: [0, 0.0, 0.0] for t in TIERS})
                d[tier] = add3(d[tier], met)
        _fold_population(raw, dim, is_band, file_ids, population)

        # ---- loss-by-stage cube (non-Trusted only) ----
        rawl = {}  # (scope, stage, dv) -> metric
        for fid, sid, dv, n, v, vol in cur.execute(
            f"SELECT output_file_id, removal_stage_id, {expr} AS dv, "
            f"COUNT(*), SUM(value_usd), SUM(volume) FROM row_fact "
            f"WHERE output_tier<>'Trusted' GROUP BY output_file_id, removal_stage_id, dv"
        ):
            met = m3(n, v, vol)
            for scope in (fid, "ALL"):
                key = (scope, sid, dv)
                rawl[key] = add3(rawl.get(key, [0, 0.0, 0.0]), met)
        _fold_loss(rawl, dim, is_band, file_ids, loss_by_stage)

    classify_fn, category_fn = build_master_classifier(REF_DB)
    recovery = _build_recovery(cur, file_ids, classify_fn, category_fn)
    simulator = _build_simulator(cur, file_ids)
    cells = _collect_cell_examples(cur)
    _attach_recovery_examples(cur, recovery, file_ids)
    examples = _build_example_store(cur, cells, simulator, recovery)
    measured_accuracy = build_measured_accuracy(cur, file_ids)

    return {
        "generated_at": utc_now(),
        "run_id": run_id,
        "registry_version": registry_version,
        "code_commit": code_commit,
        "completed_at": completed_at,
        "files": files,
        "tiers": TIERS,
        "tier_plain": {t: {"short": TIER_PLAIN[t][0], "text": TIER_PLAIN[t][1]} for t in TIERS},
        "dimensions": [{"key": k, "label": v[0], "band": v[2]} for k, v in DIMENSIONS.items()],
        "stage_order": stage_order,
        "stage_label": stage_label,
        "stage_plain": STAGE_PLAIN,
        "funnel": funnel,
        "totals": totals,
        "population": population,
        "loss_by_stage": loss_by_stage,
        "recovery": recovery,
        "simulator": simulator,
        "examples": examples,
        "measured_accuracy": measured_accuracy,
        "recovery_meta": {"buckets": RECOVERY_BUCKETS, "order": RECOVERY_ORDER,
                           "s07_classes": S07_CLASSES, "s07_class_order": S07_CLASS_ORDER,
                           "master_available": classify_fn is not None},
    }


def _build_recovery(cur, file_ids, classify_fn=None, category_fn=None):
    """Partition every non-Trusted row into confidence-rated recovery buckets and
    surface the top recoverable clusters. Review-only guidance — no production change."""
    rec = {fid: {"buckets": {b: [0, 0.0, 0.0] for b in RECOVERY_ORDER},
                 "clusters_loose": [], "clusters_mfr": [], "clusters_misguarded": []}
           for fid in file_ids + ["ALL"]}

    # bucket sizing (one scan)
    for fid, bucket, n, v, vol in cur.execute(
        f"SELECT output_file_id, {BUCKET_CASE} AS bkt, COUNT(*), SUM(value_usd), SUM(volume) "
        f"FROM row_fact WHERE output_tier<>'Trusted' GROUP BY output_file_id, bkt"
    ):
        if bucket == "trusted":
            continue
        met = m3(n, v, vol)
        for scope in (fid, "ALL"):
            rec[scope]["buckets"][bucket] = add3(rec[scope]["buckets"][bucket], met)

    def _fold_clusters(sql, keyfn, dest, topn=20):
        raw = {}
        for row in cur.execute(sql):
            fid = row[0]
            key = keyfn(row)
            met = m3(row[-3], row[-2], row[-1])
            for scope in (fid, "ALL"):
                raw.setdefault(scope, {}).setdefault(key, [0, 0.0, 0.0])
                raw[scope][key] = add3(raw[scope][key], met)
        for scope, d in raw.items():
            items = sorted(d.items(), key=lambda kv: -kv[1][1])[:topn]
            rec[scope][dest] = [{"k": list(k), "m": met} for k, met in items]

    _fold_clusters(
        f"SELECT output_file_id, coalesce(nullif(trim(manufacturer),''),'?'), "
        f"COUNT(*), SUM(value_usd), SUM(volume) "
        f"FROM row_fact WHERE primary_reason='Audit - manufacturer only' "
        f"GROUP BY output_file_id, 2",
        lambda r: (r[1],), "clusters_mfr", 15)
    _fold_clusters(
        f"SELECT output_file_id, coalesce(nullif(trim(family),''),'?'), "
        f"COUNT(*), SUM(value_usd), SUM(volume) "
        f"FROM row_fact WHERE removal_stage_id='S12_REMAP_GUARDS' AND output_tier='Review' AND {REF_VALID} "
        f"GROUP BY output_file_id, 2",
        lambda r: (r[1],), "clusters_misguarded", 15)

    # Master cross-check (single Python pass over the S07 recognised-family rows):
    # classify each row against the master AND check the family actually appears in the
    # product description. A clean master mapping is only a real recovery lever when the
    # family is evidenced in the text — on failed rows the family match is often spurious.
    for fid in file_ids + ["ALL"]:
        rec[fid]["s07_classes"] = {c: [0, 0.0, 0.0] for c in S07_CLASS_ORDER}
    if classify_fn is not None:
        # per-cluster accumulator: (scope, mfr, fam) -> {tot:met, ev:met, cls, mcat}
        clus = {}
        for fid, mfr, fam, desc, v, vol in cur.execute(
            f"SELECT output_file_id, coalesce(nullif(trim(manufacturer),''),'?'), "
            f"trim(family), detailed_product, value_usd, volume FROM row_fact "
            f"WHERE removal_stage_id='S07_REFERENCE_VALIDATION' AND ({RECOG_FAMILY})"
        ):
            base = classify_fn(fam)
            evidenced = _family_in_desc(fam, _desc_norm(desc))
            cls = base
            if base == "clean":
                cls = "clean_evidenced" if evidenced else "clean_unevidenced"
            met = m3(1, v, vol)
            for scope in (fid, "ALL"):
                rec[scope]["s07_classes"][cls] = add3(rec[scope]["s07_classes"][cls], met)
                key = (scope, mfr, fam)
                d = clus.setdefault(key, {"tot": [0, 0.0, 0.0], "ev": [0, 0.0, 0.0], "cls": cls})
                d["tot"] = add3(d["tot"], met)
                if evidenced:
                    d["ev"] = add3(d["ev"], met)
        # Build loose clusters from the evidenced pool only (the real, safe candidates),
        # ranked by evidenced value; annotate class + master category + evidenced share.
        by_scope = {}
        for (scope, mfr, fam), d in clus.items():
            if d["ev"][1] <= 0:
                continue  # no description-evidenced value → not a safe candidate
            by_scope.setdefault(scope, []).append((mfr, fam, d))
        for scope, items in by_scope.items():
            items.sort(key=lambda t: -t[2]["ev"][1])
            rec[scope]["clusters_loose"] = [{
                "k": [mfr, fam], "m": d["ev"], "cls": "clean_evidenced",
                "mcat": category_fn(fam),
                "ev_pct": round(100 * d["ev"][1] / d["tot"][1], 0) if d["tot"][1] else 0,
            } for mfr, fam, d in items[:20]]
    return rec


def _topn(items, is_band):
    """items: list of (dv, sortval, payload_builder). Returns ordered list with
    Other bucket. For bands we keep all (sorted by label); otherwise top-N by value."""
    if is_band:
        return sorted(items, key=lambda x: x[0]), []
    ordered = sorted(items, key=lambda x: -x[1])
    keep = ordered[:TOP_N]
    rest = ordered[TOP_N:]
    return keep, rest


def _fold_population(raw, dim, is_band, file_ids, population):
    # group by scope
    by_scope = {}
    for (scope, dv), tiers in raw.items():
        by_scope.setdefault(scope, []).append((dv, tiers))
    for scope, rows in by_scope.items():
        items = [(dv, tiers["Trusted"][1] + tiers["Review"][1] + tiers["Excluded"][1], tiers)
                 for dv, tiers in rows]
        keep, rest = _topn(items, is_band)
        out = []
        for dv, _sv, tiers in keep:
            out.append({"label": strip_prefix(dv), "T": tiers["Trusted"],
                        "R": tiers["Review"], "E": tiers["Excluded"]})
        if rest:
            agg = {t: [0, 0.0, 0.0] for t in TIERS}
            for _dv, _sv, tiers in rest:
                for t in TIERS:
                    agg[t] = add3(agg[t], tiers[t])
            out.append({"label": f"Other ({len(rest)})", "T": agg["Trusted"],
                        "R": agg["Review"], "E": agg["Excluded"]})
        population[scope][dim] = out


def _fold_loss(rawl, dim, is_band, file_ids, loss_by_stage):
    by = {}  # (scope, stage) -> [(dv, metric)]
    for (scope, stage, dv), met in rawl.items():
        by.setdefault((scope, stage), []).append((dv, met))
    for (scope, stage), rows in by.items():
        items = [(dv, met[1], met) for dv, met in rows]
        keep, rest = _topn(items, is_band)
        out = []
        for dv, _sv, met in keep:
            out.append({"label": strip_prefix(dv), "m": met})
        if rest:
            agg = [0, 0.0, 0.0]
            for _dv, _sv, met in rest:
                agg = add3(agg, met)
            out.append({"label": f"Other ({len(rest)})", "m": agg})
        loss_by_stage[scope].setdefault(stage, {})[dim] = out


# ---------------------------------------------------------------------------
# HTML rendering (self-contained; data embedded as JSON, vanilla JS)
# ---------------------------------------------------------------------------
def render_html(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    # Neutralise any "</script>" / "<!--" sequences so the embedded JSON cannot
    # break out of the <script> block.
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    gen = html.escape(data["generated_at"])
    run_id = html.escape(data["run_id"])
    reg = html.escape(str(data["registry_version"]))
    return _TEMPLATE.replace("__PAYLOAD__", payload).replace("__GEN__", gen).replace(
        "__RUN__", run_id).replace("__REG__", reg)


def write_recovery_csv(data: dict, path: Path) -> int:
    """Emit an actionable, ranked recall-recovery worklist for the adjudication
    team. Review-only: a prioritised candidate list, not an instruction to change
    production. One row per (market, opportunity, cluster)."""
    label_by_id = {f["id"]: f["label"] for f in data["files"]}
    meta = data["recovery_meta"]["buckets"]
    # (bucket key, cluster field, action)
    SRC = [
        ("misguarded", "clusters_misguarded"),
        ("loose", "clusters_loose"),
        ("mfr_only", "clusters_mfr"),
    ]
    rows = []
    for scope in ["ALL"] + [f["id"] for f in data["files"]]:
        market = "All markets" if scope == "ALL" else label_by_id.get(scope, scope)
        rec = data["recovery"][scope]
        for bkey, cfield in SRC:
            b = meta[bkey]
            for c in rec.get(cfield, []):
                k = c["k"]
                mfr = k[0] if cfield in ("clusters_loose", "clusters_mfr") else ""
                fam = (k[1] if cfield == "clusters_loose" else
                       (k[0] if cfield == "clusters_misguarded" else ""))
                cls = c.get("cls", "")
                rows.append({
                    "market": market,
                    "opportunity": b["label"],
                    "safety": b["safety"],
                    "manufacturer": mfr,
                    "family": fam,
                    "master_check": S07_CLASSES.get(cls, "").split(" — ")[0] if cls else "",
                    "master_category": c.get("mcat", ""),
                    "transactions": c["m"][0],
                    "value_usd": round(c["m"][1], 2),
                    "recommended_action": b["action"],
                    "_rank": RECOVERY_ORDER.index(bkey),
                    "_cls": {"clean_evidenced": 0, "not_in_master": 1, "ambiguous_multi": 2,
                             "ambiguous_generic": 3, "clean_unevidenced": 4, "": 5}.get(cls, 5),
                })
    # Useful order: All-markets first, then by SAFETY (safest recoveries lead),
    # then master-check class within the loose bucket, then value.
    rows.sort(key=lambda r: (r["market"] != "All markets", r["market"], r["_rank"],
                             r["_cls"], -r["value_usd"]))
    for r in rows:
        r.pop("_rank", None)
        r.pop("_cls", None)
    cols = ["market", "opportunity", "safety", "manufacturer", "family",
            "master_check", "master_category", "transactions", "value_usd",
            "recommended_action"]
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=str(REPO / "outputs" / DEFAULT_RUN / "prediction_audit.sqlite"))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    db = Path(args.db)
    if not db.exists():
        raise SystemExit(f"SQLite authority not found: {db}")
    out = Path(args.out) if args.out else db.parent / "Recall_Funnel_Dashboard.html"

    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        data = build_data(con)
    finally:
        con.close()

    html_text = render_html(data)
    out.write_text(html_text, encoding="utf-8")
    size = out.stat().st_size
    print(f"Wrote {out}  ({size/1024:.0f} KB)")

    csv_path = out.parent / "Recall_Recovery_Candidates.csv"
    n = write_recovery_csv(data, csv_path)
    print(f"Wrote {csv_path}  ({n} candidate rows)")

    # Quick self-check: JSON round-trips and key scopes present.
    assert "ALL" in data["funnel"], "missing combined funnel"
    print(f"Files: {len(data['files'])}  Dimensions: {len(data['dimensions'])}  "
          f"Funnel scopes: {len(data['funnel'])}")


# The big HTML/CSS/JS template lives in a sibling module to keep this file
# focused on data; imported lazily so the data logic can be unit-tested alone.
from _funnel_dashboard_template import TEMPLATE as _TEMPLATE  # noqa: E402

if __name__ == "__main__":
    main()
