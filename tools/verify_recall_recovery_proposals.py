#!/usr/bin/env python3
"""Verify that a recall-recovery workbook is safe to enter human review.

Checks the governed workbook contract, requires all approval cells to remain
blank at publication time, and runs every pending row through the same master
resolution/deduplication preflight used by the ingestion tool. No files are
written.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from apply_review_adjudications import _load_proposal_workbook, apply


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
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

    stats = apply([workbook], dry_run=True, shared_log=False, check_pending=True)
    if stats["errors"]:
        raise SystemExit(f"FAIL: {stats['errors']} proposal rows failed preflight")
    if stats["checked"] != len(frame):
        raise SystemExit("FAIL: preflight row count does not match workbook")
    print(f"PASS: {len(frame)} pending proposals; approvals blank; "
          f"{stats['family_alias']} unique new aliases in batch; "
          f"{stats['skipped_existing']} existing/repeated aliases; 0 errors")


if __name__ == "__main__":
    main()
