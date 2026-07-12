#!/usr/bin/env python3
"""Draft recall-recovery adjudication proposals for the top "Clean" S07 clusters.

REVIEW-ONLY. This reads the prediction-audit authority + the governed brand master
and emits a proposals workbook of the safest recall-recovery candidates — rows the
pipeline held back at Reference validation (S07) whose recognised family maps to
exactly ONE specific master category. Each proposal names the master category that
would let the row become reference-valid, with the ``Approved`` column left blank
for a human reviewer. Nothing is applied: accepted rows still flow through the normal
``apply_review_adjudications.py`` -> reference/ -> governed rerun loop.

This tool NEVER writes to the sqlite authority, the reference lists, or any workbook.

Usage:
    PYTHONIOENCODING=utf-8 python tools/build_recall_recovery_proposals.py \
        [--db outputs/<run_id>/prediction_audit.sqlite] [--top 40]
"""
from __future__ import annotations

import argparse
import re
import sqlite3
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
DEFAULT_RUN = "20260712_recall_audit_v3"
REF_DB = REPO / "reference" / "reference.sqlite"

# Same objective "clean vs ambiguous" signal used by the dashboard.
GENERIC_TOKENS = {
    "target", "light source", "sprinter", "essential", "unity", "hybrid", "elite",
    "optime", "therapy", "evolution", "physio", "woven", "cone", "vector", "crescent",
    "traveler", "forceps", "scissor", "scissors", "monopolar", "bipolar", "retractor",
    "cannula", "trocar", "catheter", "guidewire", "balloon", "clip", "mesh", "suture",
    "needle", "drain", "stapler", "probe", "blade",
}
MONTHS = {"january", "february", "march", "april", "may", "june", "july", "august",
          "september", "october", "november", "december"}

PROPOSAL_COLUMNS = [
    "Market", "FY", "Cluster_QA_Status", "Cluster_HS4", "Cluster_Manufacturer",
    "Cluster_Family", "Cluster_Rows", "Cluster_Value_USD",
    "Family_In_Evidence", "Evidence_Coverage_Pct",
    "Decision", "Proposal_Type", "Alias_Term", "Target_Table",
    "Proposed_Segment", "Proposed_Subsegment", "Proposed_Product",
    "Proposed_Player", "Proposed_Family", "Master_Validated",
    "Rationale", "Evidence_Quote", "Reviewer_Guidance",
    "Approved", "Reviewer_Notes",
]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _desc_norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())


def _family_in_desc(family: str, desc_normed: str) -> bool:
    nf = _norm(family)
    if not nf:
        return False
    if nf in desc_normed:
        return True
    return any(w in desc_normed for w in nf.split() if len(w) >= 4)


def load_clean_family_map(ref_db: Path):
    """family(norm) -> (segment, sub, product, player) when the family maps to exactly
    one specific master category and is not a generic/date token."""
    con = sqlite3.connect(f"file:{ref_db}?mode=ro", uri=True)
    cats: dict[str, set] = {}
    players: dict[str, set] = {}
    try:
        for seg, sub, prod, player, fam in con.execute(
            "SELECT segment, sub_segment, product, player, family_name FROM brand_model_master"
        ):
            nf = _norm(fam)
            if nf:
                cats.setdefault(nf, set()).add((seg, sub, prod))
                players.setdefault(nf, set()).add(player)
    finally:
        con.close()
    clean = {}
    for nf, cs in cats.items():
        if nf in GENERIC_TOKENS or nf in MONTHS or len(nf) <= 3:
            continue
        if len(cs) == 1:
            seg, sub, prod = next(iter(cs))
            player = next(iter(players[nf])) if len(players[nf]) == 1 else ""
            clean[nf] = (seg, sub, prod, player)
    return clean


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=str(REPO / "outputs" / DEFAULT_RUN / "prediction_audit.sqlite"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--top", type=int, default=40, help="top clusters per market by value")
    args = ap.parse_args()

    db = Path(args.db)
    if not db.exists():
        raise SystemExit(f"SQLite authority not found: {db}")
    if not REF_DB.exists():
        raise SystemExit(f"Reference master not found: {REF_DB}")
    out = Path(args.out) if args.out else db.parent / "Recall_Recovery_Proposals.xlsx"

    clean = load_clean_family_map(REF_DB)
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    cur = con.cursor()

    # Single pass over S07 recognised-family rows. Per (market, maker, family) cluster we
    # accumulate the TOTAL and the DESCRIPTION-EVIDENCED value (family actually appears in
    # the text). Only evidenced clusters become proposals — on failed rows the family match
    # is often spurious, so bulk-backfilling from it would misclassify products.
    from collections import defaultdict
    agg = defaultdict(lambda: {"tot": [0, 0.0], "ev": [0, 0.0], "quote": "", "quote_v": -1.0})
    for country, fy, mfr, fam, desc, val in cur.execute(
        """
        SELECT country, fiscal_year,
               COALESCE(NULLIF(TRIM(manufacturer),''),'(unknown maker)') mfr,
               TRIM(family) fam, detailed_product, value_usd
        FROM row_fact
        WHERE removal_stage_id='S07_REFERENCE_VALIDATION'
          AND COALESCE(NULLIF(TRIM(family),''),'')<>''
          AND LOWER(TRIM(family)) NOT IN ('unspecified','(unspecified)')
        """
    ):
        nf = _norm(fam)
        if nf not in clean:
            continue  # only families mapping to one specific master category
        v = float(val or 0.0)
        d = agg[(country, fy, mfr, fam)]
        d["tot"][0] += 1
        d["tot"][1] += v
        if _family_in_desc(fam, _desc_norm(desc)):
            d["ev"][0] += 1
            d["ev"][1] += v
            if v > d["quote_v"]:
                d["quote_v"] = v
                d["quote"] = (desc or "")[:180]

    # keep only evidenced clusters, rank per market by evidenced value, take top N
    per_market = defaultdict(list)
    for (country, fy, mfr, fam), d in agg.items():
        if d["ev"][1] <= 0:
            continue
        per_market[(country, fy)].append((mfr, fam, d))
    rows = []
    for key, items in per_market.items():
        items.sort(key=lambda t: -t[2]["ev"][1])
        for mfr, fam, d in items[:args.top]:
            nf = _norm(fam)
            seg, sub, prod, player = clean[nf]
            cov = round(100 * d["ev"][1] / d["tot"][1], 0) if d["tot"][1] else 0
            rows.append({
                "Market": key[0], "FY": key[1],
                "Cluster_QA_Status": "Review - not in latest reference",
                "Cluster_HS4": "",
                "Cluster_Manufacturer": mfr, "Cluster_Family": fam,
                "Cluster_Rows": int(d["ev"][0]), "Cluster_Value_USD": round(d["ev"][1], 2),
                "Family_In_Evidence": "Y", "Evidence_Coverage_Pct": cov,
                "Decision": "PROPOSE map to master category (backfill)",
                "Proposal_Type": "family_alias",
                "Alias_Term": fam,
                "Target_Table": "family_aliases",
                "Proposed_Segment": seg, "Proposed_Subsegment": sub,
                "Proposed_Product": prod, "Proposed_Player": player or mfr,
                "Proposed_Family": fam,
                "Master_Validated": "Y",
                "Rationale": ("Held back at Reference validation (S07). The recognised family maps to "
                              "exactly one specific master category AND appears in the product "
                              "description for these %d rows (%.0f%% of the raw cluster), so it is a "
                              "genuine candidate. Verify per row before approving." % (int(d["ev"][0]), cov)),
                "Evidence_Quote": d["quote"],
                "Reviewer_Guidance": ("Approve only if the description is genuinely this product. "
                                      "The remaining rows in this family are likely spurious and are "
                                      "excluded here. Set Approved=Y to accept."),
                "Approved": "", "Reviewer_Notes": "",
            })

    props = pd.DataFrame(rows, columns=PROPOSAL_COLUMNS)
    # Summary per market
    if len(props):
        summ = (props.groupby(["Market", "FY"])
                .agg(Clusters=("Cluster_Family", "count"),
                     Rows=("Cluster_Rows", "sum"),
                     Value_USD=("Cluster_Value_USD", "sum"))
                .reset_index().sort_values("Value_USD", ascending=False))
    else:
        summ = pd.DataFrame(columns=["Market", "FY", "Clusters", "Rows", "Value_USD"])

    readme = pd.DataFrame({
        "Recall-Recovery Proposals — REVIEW ONLY": [
            "Source: prediction_audit.sqlite (run %s) cross-checked against reference/reference.sqlite." % db.parent.name,
            "Scope: the safest S07 recall-recovery candidates — recognised family maps to ONE specific master category",
            "  AND the family actually appears in the product description (Family_In_Evidence=Y).",
            "Rows whose family is NOT in the description are EXCLUDED: on failed rows the family match is often spurious",
            "  (e.g. a cataract lens tagged 'Trauma Plates And Screws'), which is why S07 correctly held them back.",
            "Cluster_Rows / Cluster_Value_USD count only the evidenced rows; Evidence_Coverage_Pct is their share of the raw cluster.",
            "NOTHING is applied. The Approved column is blank; a human reviewer sets Approved=Y only after checking each in context.",
            "Accepted rows flow through the normal apply_review_adjudications.py -> reference/ -> governed rerun loop.",
        ]
    })

    with pd.ExcelWriter(out, engine="xlsxwriter") as xw:
        readme.to_excel(xw, sheet_name="Read Me", index=False)
        props.to_excel(xw, sheet_name="Recovery_Proposals", index=False)
        summ.to_excel(xw, sheet_name="Summary", index=False)
        for name, df in (("Recovery_Proposals", props), ("Summary", summ), ("Read Me", readme)):
            ws = xw.sheets[name]
            ws.set_column(0, max(0, len(df.columns) - 1), 22)
    con.close()
    print(f"Wrote {out}  ({len(props)} proposal clusters across {len(summ)} market-years)")
    if len(props):
        tv = props["Cluster_Value_USD"].sum()
        print(f"Total proposed clean-recovery value: ${tv/1e6:,.0f}M (review-only)")


if __name__ == "__main__":
    main()
