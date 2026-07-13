"""Export high-confidence LLM proposal approvals for an independent second pass.

The SQLite authority is the processing backend.  JSON packets are temporary
review inputs; Excel is produced only after reconciliation.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN = ROOT / "outputs" / "20260713_llm_adjudication"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--threshold", type=float, default=0.90)
    args = parser.parse_args()

    db = args.run_dir / "raw_outputs" / "llm_review_authority.sqlite"
    out_dir = args.run_dir / "cross_packets"
    out_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """
        SELECT p.proposal_id, p.packet_id, p.payload_json,
               r.reviewer AS first_reviewer, r.confidence AS first_confidence,
               r.rationale AS first_rationale
        FROM proposal_raw p
        JOIN proposal_review r USING (proposal_id)
        WHERE r.decision='APPROVE' AND r.confidence >= ?
          AND lower(r.reviewer) NOT LIKE '%cross%'
        ORDER BY p.packet_id, p.cluster_value_usd DESC, p.proposal_id
        """,
        (args.threshold,),
    ).fetchall()

    # Rotate packets so nobody performs the second pass on their own first pass.
    assignment = {1: 2, 2: 3, 3: 1}
    summary: dict[str, int] = {}
    for source_packet, reviewer_number in assignment.items():
        selected = [row for row in rows if row["packet_id"] == source_packet]
        payload = {
            "purpose": "Independent second review of first-pass high-confidence approvals",
            "source_packet": source_packet,
            "assigned_reviewer_number": reviewer_number,
            "approval_threshold": args.threshold,
            "proposal_rows": [json.loads(row["payload_json"]) for row in selected],
        }
        path = out_dir / f"proposal_packet_{source_packet}_for_reviewer_{reviewer_number}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        summary[str(path)] = len(selected)

    conn.close()
    print(json.dumps({"candidate_count": len(rows), "packets": summary}, indent=2))


if __name__ == "__main__":
    main()
