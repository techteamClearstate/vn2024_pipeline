#!/usr/bin/env python3
"""Verify that a recall-recovery workbook is safe to enter human review.

Checks the governed workbook contract, requires all approval cells to remain
blank at publication time, and runs every pending row through the same master
resolution/deduplication preflight used by the ingestion tool. No files are
written.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
import re
import sqlite3

from apply_review_adjudications import _load_proposal_workbook, apply
from build_recall_recovery_proposals import DEFAULT_RUN, REPO, _desc_norm, _family_in_desc, _norm


def _text(value) -> str:
    """Normalize workbook/SQLite key values without changing meaningful text."""
    if value is None:
        return ""
    text = str(value).strip()
    return text[:-2] if text.endswith(".0") and text[:-2].isdigit() else text


def _expected_s12(db: Path) -> dict[tuple[str, str, str, str], dict]:
    expected = defaultdict(lambda: {"rows": 0, "value": 0.0, "quote": "", "quote_v": -1.0})
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        records = con.execute(
            """
            SELECT country, fiscal_year, manufacturer, family, detailed_product, value_usd
            FROM row_fact
            WHERE removal_stage_id='S12_REMAP_GUARDS'
              AND output_tier='Review' AND LOWER(reference_status)='valid'
            """
        )
        for country, fy, maker, family, description, value in records:
            nf = _norm(family)
            if (not nf or nf in {"unspecified", "(unspecified)"}
                    or not _family_in_desc(family, _desc_norm(description))):
                continue
            key = tuple(_text(v) for v in (country, fy, maker, family))
            item = expected[key]
            amount = float(value or 0.0)
            item["rows"] += 1
            item["value"] += amount
            if amount > item["quote_v"]:
                item["quote_v"] = amount
                item["quote"] = (description or "")[:180]
    finally:
        con.close()
    return dict(expected)


def _verify_s12(frame, db: Path) -> tuple[int, int, float]:
    s12 = frame[frame["Proposal_Type"].astype(str).str.strip().eq("scope_whitelist")]
    if s12.empty:
        return 0, 0, 0.0
    if not db.exists():
        raise SystemExit(f"FAIL: SQLite authority not found for S12 verification: {db}")

    expected = _expected_s12(db)
    actual: dict[tuple[str, str, str, str], int] = {}
    errors: list[str] = []
    for index, row in s12.iterrows():
        excel_row = index + 2
        key = tuple(_text(row[col]) for col in
                    ("Market", "FY", "Cluster_Manufacturer", "Cluster_Family"))
        if key in actual:
            errors.append(f"row {excel_row}: duplicate S12 authority cluster {key}")
            continue
        actual[key] = excel_row
        authority = expected.get(key)
        if authority is None:
            errors.append(f"row {excel_row}: S12 cluster absent from authority/evidence subset")
            continue
        family = _text(row["Cluster_Family"])
        expected_regex = r"\\b" + r"\\s+".join(re.escape(w) for w in _norm(family).split()) + r"\\b"
        checks = {
            "Target_Table": _text(row["Target_Table"]) == "surgical_context_whitelist",
            "Family_In_Evidence": _text(row["Family_In_Evidence"]).upper() == "Y",
            "Alias_Term": _text(row["Alias_Term"]) == expected_regex,
            "Proposed_Player": _text(row["Proposed_Player"]) == key[2],
            "Proposed_Family": _text(row["Proposed_Family"]) == key[3],
            "Cluster_Rows": int(float(row["Cluster_Rows"] or 0)) == authority["rows"],
            "Cluster_Value_USD": abs(float(row["Cluster_Value_USD"] or 0) - round(authority["value"], 2)) < .005,
            "Evidence_Quote": _text(row["Evidence_Quote"]) == authority["quote"],
        }
        failed = [name for name, ok in checks.items() if not ok]
        if failed:
            errors.append(f"row {excel_row}: mismatched {', '.join(failed)}")

    missing = set(expected) - set(actual)
    extra = set(actual) - set(expected)
    if missing:
        errors.append(f"{len(missing)} authority S12 clusters missing from workbook")
    if extra:
        errors.append(f"{len(extra)} workbook S12 clusters absent from authority")
    if errors:
        raise SystemExit("FAIL: S12 authority verification: " + "; ".join(errors[:10]))
    return len(s12), sum(item["rows"] for item in expected.values()), sum(
        item["value"] for item in expected.values())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument(
        "--db", type=Path,
        default=REPO / "outputs" / DEFAULT_RUN / "prediction_audit.sqlite",
        help="prediction-audit SQLite authority used to prove every S12 proposal",
    )
    args = parser.parse_args()
    workbook = args.workbook.resolve()
    if not workbook.exists():
        raise SystemExit(f"workbook not found: {workbook}")

    frame = _load_proposal_workbook(workbook).fillna("")
    approvals = frame["Approved"].astype(str).str.strip()
    if approvals.ne("").any():
        rows = ", ".join(str(i + 2) for i in frame.index[approvals.ne("")][:10])
        raise SystemExit(f"FAIL: publication workbook has nonblank Approved cells: {rows}")
    invalid_flags = frame["Master_Validated"].astype(str).str.strip().str.upper().ne("Y") \
        if "Master_Validated" in frame else []
    if len(invalid_flags) and invalid_flags.any():
        raise SystemExit("FAIL: proposal rows not marked Master_Validated=Y")

    s12_clusters, s12_rows, s12_value = _verify_s12(frame, args.db.resolve())

    stats = apply([workbook], dry_run=True, shared_log=False, check_pending=True)
    if stats["errors"]:
        raise SystemExit(f"FAIL: {stats['errors']} proposal rows failed preflight")
    if stats["checked"] != len(frame):
        raise SystemExit("FAIL: preflight row count does not match workbook")
    print(f"PASS: {len(frame)} pending proposals; approvals blank; "
          f"{stats['family_alias']} unique new aliases in batch; "
          f"{stats['skipped_existing']} existing/repeated aliases; 0 errors")
    if s12_clusters:
        print(f"PASS: {s12_clusters} S12 clusters reconcile exactly to {s12_rows:,} "
              f"authority rows / ${s12_value:,.2f}; evidence quotes and regexes verified")


if __name__ == "__main__":
    main()
