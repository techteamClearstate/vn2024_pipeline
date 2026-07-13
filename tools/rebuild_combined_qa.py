"""Rebuild the six-file combined QA workbook from individual QA reports.

This is intentionally Excel-at-the-edge: pandas reads the final report files,
while all consolidation happens in memory and the existing xlsxwriter helper
writes the final governed workbook without opening Microsoft Excel.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

from batch_surgical_workflow_remap import _add_country_year, build_combined_qa, write_workbook


SHEET_KEYS = {
    "metrics": "Baseline_vs_Improved",
    "validation": "Validation",
    "change_log": "Changes_Applied",
    "alias": "Alias_Update_Request",
    "reference": "Reference_Update_Request",
    "reference_clean": "Reference_Update_Request_Clean",
    "reference_rejected_generic": "Ref_Rejected_GenericToken",
    "reference_needs_review": "Ref_Needs_Human_Review",
    "extended": "Extended_Surgical_Decision",
    "precision": "Precision_Risk_Rows",
    "false_positive": "False_Positive_Screen",
    "trusted_generic_qc": "Trusted_Generic_Token_QC",
    "missed": "Potential_Missed_Surgical_Rows",
    "clusters": "Review_Queue_Cluster_Summary",
    "excluded": "Excluded_Surgicalish_Screen",
    "independent_fn": "Independent_FN_Screen",
}


def market_from_name(path: Path) -> tuple[str, str]:
    match = re.match(r"(?P<country>[A-Za-z]+)_FY(?P<year>20\d{2})_", path.name)
    if not match:
        raise ValueError(f"Cannot infer country/year from {path.name}")
    return match.group("country"), match.group("year")


def read_sheet(path: Path, sheet: str) -> pd.DataFrame:
    try:
        frame = pd.read_excel(path, sheet_name=sheet, keep_default_na=False)
    except ValueError:
        return pd.DataFrame()
    if list(frame.columns) == ["Note"] and len(frame) == 1 and str(frame.iloc[0, 0]) == "No rows":
        return pd.DataFrame()
    return frame


def load_report(path: Path) -> dict[str, pd.DataFrame]:
    country, year = market_from_name(path)
    result: dict[str, pd.DataFrame] = {}
    for key, sheet in SHEET_KEYS.items():
        frame = read_sheet(path, sheet)
        if key == "validation":
            frame = frame.assign(Country=country, Year=year) if not frame.empty else frame
        elif key not in {"metrics", "change_log"}:
            frame = _add_country_year(frame, country, year)
        result[key] = frame
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    reports = sorted(args.reports_dir.glob("*_Surgical_Mapping_QA_Report.xlsx"))
    reports = [path for path in reports if path.name != "All_Countries_Surgical_Mapping_QA_Report.xlsx"]
    if len(reports) != 6:
        raise SystemExit(f"Expected 6 individual QA reports; found {len(reports)} in {args.reports_dir}")

    consolidated = [load_report(path) for path in reports]
    write_workbook(args.output, build_combined_qa(consolidated))
    print(f"Wrote {args.output} from {len(reports)} individual QA reports")


if __name__ == "__main__":
    main()
