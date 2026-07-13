#!/usr/bin/env python3
"""Record an independent prediction-audit QC review in the SQLite authority."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3


REQUIRED_FIELDS = (
    "severity",
    "finding",
    "evidence",
    "required_action",
    "owner_response",
    "retest_result",
    "status",
)
OPTIONAL_FIELDS = ("stage_id", "rule_id", "file_path")
ALLOWED_SEVERITIES = {"Critical", "High", "Medium", "Low", "Info"}
ALLOWED_STATUSES = {"Open", "Closed", "Accepted"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--findings", type=Path, required=True, help="JSON array of independent QC findings.")
    parser.add_argument("--replace", action="store_true", help="Replace existing findings for this run.")
    return parser.parse_args()


def validate_finding(finding: dict[str, object], index: int) -> None:
    missing = [field for field in REQUIRED_FIELDS if not str(finding.get(field, "")).strip()]
    if missing:
        raise ValueError(f"Finding {index} is missing required fields: {', '.join(missing)}")
    if finding["severity"] not in ALLOWED_SEVERITIES:
        raise ValueError(f"Finding {index} has invalid severity: {finding['severity']}")
    if finding["status"] not in ALLOWED_STATUSES:
        raise ValueError(f"Finding {index} has invalid status: {finding['status']}")


def main() -> int:
    args = parse_args()
    database = args.db.resolve()
    payload = json.loads(args.findings.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise ValueError("Findings JSON must be a non-empty array; use one Info/Closed record for a clean audit.")
    for index, finding in enumerate(payload, start=1):
        if not isinstance(finding, dict):
            raise ValueError(f"Finding {index} is not an object.")
        validate_finding(finding, index)

    connection = sqlite3.connect(database)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        run = connection.execute("SELECT status FROM run WHERE run_id=?", (args.run_id,)).fetchone()
        if run is None:
            raise ValueError(f"Unknown run_id: {args.run_id}")
        if args.replace:
            connection.execute("DELETE FROM independent_qc_finding WHERE run_id=?", (args.run_id,))
        elif connection.execute(
            "SELECT COUNT(*) FROM independent_qc_finding WHERE run_id=?", (args.run_id,)
        ).fetchone()[0]:
            raise ValueError("Findings already exist; pass --replace to replace them intentionally.")
        connection.executemany(
            """INSERT INTO independent_qc_finding
               (run_id,severity,finding,evidence,stage_id,rule_id,file_path,required_action,
                owner_response,retest_result,status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            [
                (
                    args.run_id,
                    finding["severity"],
                    finding["finding"],
                    finding["evidence"],
                    finding.get("stage_id"),
                    finding.get("rule_id"),
                    finding.get("file_path"),
                    finding["required_action"],
                    finding["owner_response"],
                    finding["retest_result"],
                    finding["status"],
                )
                for finding in payload
            ],
        )
        open_actionable = connection.execute(
            """SELECT COUNT(*) FROM independent_qc_finding
               WHERE run_id=? AND severity<>'Info' AND status='Open'""",
            (args.run_id,),
        ).fetchone()[0]
        connection.commit()
        print(json.dumps({"run_id": args.run_id, "recorded": len(payload), "open_actionable": open_actionable}))
        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
