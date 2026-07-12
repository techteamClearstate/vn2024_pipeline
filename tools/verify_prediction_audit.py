#!/usr/bin/env python3
"""Acceptance verification for the prediction audit authority and reports."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]
VALUE_TOLERANCE = 0.01
VOLUME_TOLERANCE = 0.000001
EXPECTED_ROWS = {
    "VN_2024": 520_835,
    "VN_2025": 558_043,
    "PK_2024": 84_645,
    "PK_2025": 96_293,
    "IN_2024": 631_630,
    "IN_2025": 1_682_283,
}
EXPECTED_SHEETS = [
    "Read Me", "Funnel", "Removal Cube", "Review Samples", "Recall Risks",
    "Reconciliation QC", "Source Lineage",
]
MASTER_VALIDATION_STATUSES = {
    "not_applicable",
    "pass_full_strict",
    "pass_full_latest_generic_risk",
    "reference_update_needed",
    "pass_category",
    "category_reference_update_needed",
}


class VerificationError(AssertionError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def stable_query_hash(connection: sqlite3.Connection, query: str) -> str:
    digest = hashlib.sha256()
    for row in connection.execute(query):
        digest.update(json.dumps(list(row), ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def workbook_sheet_names(path: Path) -> list[str]:
    import xml.etree.ElementTree as ET

    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("xl/workbook.xml"))
    namespace = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    return [node.attrib["name"] for node in root.findall("m:sheets/m:sheet", namespace)]


def verify(database: Path, workbook: Path | None, html_path: Path | None) -> dict[str, object]:
    require(database.exists(), f"Database not found: {database}")
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        run = connection.execute("SELECT * FROM run").fetchall()
        require(len(run) == 1 and run[0]["status"] == "passed", "Exactly one passed run is required.")
        run_id = run[0]["run_id"]
        require(connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "SQLite integrity_check failed.")
        require(not connection.execute("PRAGMA foreign_key_check").fetchall(), "SQLite foreign_key_check failed.")
        require(connection.execute("SELECT COUNT(*) FROM rule_registry_stage").fetchone()[0] == 15, "Registry must contain S00-S14.")
        require(connection.execute("SELECT COUNT(*) FROM rule_registry_rule").fetchone()[0] == 16, "Registry must contain 16 rules.")
        require(connection.execute("SELECT COUNT(*) FROM reconciliation_qc WHERE status='FAIL'").fetchone()[0] == 0, "Reconciliation contains FAIL.")

        sources = connection.execute("SELECT * FROM source_file ORDER BY output_file_id").fetchall()
        require(len(sources) == 6, "Exactly six source outputs are required.")
        require(
            sum(int(source["transaction_count"]) for source in sources) == sum(EXPECTED_ROWS.values()) == 3_573_729,
            "The six governed outputs must contain exactly 3,573,729 transactions.",
        )
        for source in sources:
            output_id = source["output_file_id"]
            expected = EXPECTED_ROWS[output_id]
            require(source["expected_rows"] == source["observed_rows"] == source["transaction_count"] == expected,
                    f"{output_id} row total is incomplete.")
            source_path = Path(source["source_path"])
            require(source_path.exists(), f"Source file missing: {source_path}")
            require(sha256_file(source_path) == source["source_sha256"], f"Source hash mismatch: {output_id}")
            complete_source_path = Path(source["complete_source_path"])
            require(complete_source_path.exists(), f"Complete source file missing: {complete_source_path}")
            require(
                sha256_file(complete_source_path) == source["complete_source_sha256"],
                f"Complete source hash mismatch: {output_id}",
            )
            require(source_path.stat().st_size == source["source_bytes"], f"Source byte size mismatch: {output_id}")
            require(
                complete_source_path.stat().st_size == source["complete_source_bytes"],
                f"Complete source byte size mismatch: {output_id}",
            )
            fact = connection.execute(
                """SELECT COUNT(*) n,SUM(value_usd) value_usd,SUM(volume) volume,
                          SUM(value_numeric_status='missing') missing_value,
                          SUM(value_numeric_status='invalid') invalid_value,
                          SUM(volume_numeric_status='missing') missing_volume,
                          SUM(volume_numeric_status='invalid') invalid_volume
                   FROM row_fact WHERE run_id=? AND output_file_id=?""",
                (run_id, output_id),
            ).fetchone()
            require(fact["n"] == expected, f"{output_id} fact count does not reconcile.")
            require(abs(float(fact["value_usd"] or 0) - float(source["value_usd"] or 0)) <= VALUE_TOLERANCE,
                    f"{output_id} value does not reconcile.")
            require(abs(float(fact["volume"] or 0) - float(source["volume"] or 0)) <= VOLUME_TOLERANCE,
                    f"{output_id} volume does not reconcile.")
            require((fact["missing_value"], fact["invalid_value"], fact["missing_volume"], fact["invalid_volume"]) ==
                    (source["missing_value_count"], source["invalid_value_count"], source["missing_volume_count"], source["invalid_volume_count"]),
                    f"{output_id} numeric statuses do not reconcile.")
            require(connection.execute(
                """SELECT COUNT(*) FROM row_fact
                   WHERE run_id=? AND output_file_id=?
                     AND (raw_value_usd IS NULL OR raw_volume IS NULL
                          OR value_numeric_status NOT IN ('valid','missing','invalid')
                          OR volume_numeric_status NOT IN ('valid','missing','invalid'))""",
                (run_id, output_id),
            ).fetchone()[0] == 0, f"{output_id} raw/parsed numeric audit fields are incomplete.")
            sample = connection.execute(
                """SELECT COUNT(*) n,SUM(sample_type='Targeted') targeted,
                          SUM(sample_type='Deterministic stratified random') random_n,
                          SUM(sample_type='Targeted' AND (inclusion_probability IS NOT NULL OR sample_weight IS NOT NULL)) bad_target,
                          SUM(sample_type='Deterministic stratified random' AND (inclusion_probability IS NULL OR sample_weight IS NULL)) bad_random
                   FROM review_label WHERE run_id=? AND output_file_id=?""",
                (run_id, output_id),
            ).fetchone()
            require(tuple(sample) == (25, 12, 13, 0, 0), f"{output_id} sample design is invalid: {tuple(sample)}")

        india = connection.execute("SELECT * FROM source_file WHERE output_file_id='IN_2025'").fetchone()
        require(india["source_format"].lower() == "csv" and india["observed_rows"] > 1_048_575,
                "India FY2025 must use its complete uncapped CSV.")
        require(india["ingestion_mode"] == "complete_csv_current_remap", "India FY2025 ingestion mode is incorrect.")
        require(
            Path(india["source_path"]).resolve() != Path(india["complete_source_path"]).resolve(),
            "India FY2025 must retain distinct mapped-current and immutable-complete lineage.",
        )
        require(
            "governed master validation v1" in india["completeness_basis"].lower(),
            "India FY2025 must disclose its audit-only governed master enrichment.",
        )
        india_master_statuses = {
            row[0] for row in connection.execute(
                "SELECT DISTINCT master_validation_status FROM row_fact WHERE output_file_id='IN_2025'"
            )
        }
        require(india_master_statuses <= MASTER_VALIDATION_STATUSES and india_master_statuses,
                f"India FY2025 contains unsupported master statuses: {india_master_statuses}")
        india_reference_statuses = {
            row[0] for row in connection.execute(
                "SELECT DISTINCT reference_status FROM row_fact WHERE output_file_id='IN_2025'"
            )
        }
        require(india_reference_statuses <= {"", "Valid", "Invalid"},
                f"India FY2025 contains unsupported binary reference statuses: {india_reference_statuses}")
        require(connection.execute(
            """SELECT COUNT(*) FROM row_fact WHERE output_file_id='IN_2025' AND (
                 master_validation_status=''
                 OR (master_validation_status IN ('pass_full_strict','pass_category')
                     AND reference_status<>'Valid')
                 OR (master_validation_status='not_applicable' AND reference_status<>'')
                 OR (master_validation_status IN
                       ('pass_full_latest_generic_risk','reference_update_needed',
                        'category_reference_update_needed')
                     AND reference_status<>'Invalid')
               )"""
        ).fetchone()[0] == 0, "India FY2025 detailed and binary reference evidence is inconsistent.")
        require(connection.execute(
            """SELECT COUNT(*) FROM row_fact WHERE output_file_id='IN_2025' AND (
                 (LOWER(match_tier)='family' AND master_validation_status NOT IN
                    ('pass_full_strict','pass_full_latest_generic_risk','reference_update_needed'))
                 OR (LOWER(match_tier)='category' AND master_validation_status NOT IN
                    ('pass_category','category_reference_update_needed'))
                 OR (LOWER(match_tier) NOT IN ('family','category') AND master_validation_status<>'not_applicable')
               )"""
        ).fetchone()[0] == 0, "India FY2025 master statuses do not reconcile to Match_Tier.")
        require(connection.execute(
            """SELECT COUNT(*) FROM row_fact WHERE output_file_id='IN_2025'
               AND output_tier<>'Trusted' AND primary_reason<>'ophthalmic_imaging_conflict'
               AND reference_status='Invalid'
               AND removal_stage_id<>'S07_REFERENCE_VALIDATION'"""
        ).fetchone()[0] == 0, "India FY2025 invalid-reference losses are not attributed at S07.")
        require(connection.execute(
            """SELECT COUNT(*) FROM row_fact WHERE output_file_id='IN_2025'
               AND output_tier<>'Trusted' AND primary_reason<>'ophthalmic_imaging_conflict'
               AND reference_status=''
               AND removal_stage_id<>'S13_TERMINAL_ROUTING'"""
        ).fetchone()[0] == 0, "India FY2025 genuine coverage gaps are not retained at S13.")
        require(connection.execute(
            "SELECT COUNT(*) FROM row_fact WHERE output_file_id LIKE 'PK_%' AND nonstandard_tier=1 AND output_tier='Trusted'"
        ).fetchone()[0] == 0, "Pakistan nonstandard tiers must not be Trusted.")

        mri_facts = connection.execute("SELECT COUNT(*) FROM row_fact WHERE mri_risk=1").fetchone()[0]
        mri_inventory = connection.execute(
            "SELECT COUNT(*) FROM recall_risk_inventory WHERE risk_type='MRI compatible recall risk'"
        ).fetchone()[0]
        require(mri_facts == mri_inventory, "MRI-compatible inventory is incomplete.")
        require(connection.execute(
            """SELECT COUNT(*) FROM recall_risk_inventory i JOIN row_fact f ON f.row_fact_id=i.row_fact_id
               WHERE i.current_output_tier<>f.output_tier"""
        ).fetchone()[0] == 0, "A recall inventory changed terminal routing.")
        for risk_type, fact_column in (
            ("MRI actual imaging-system conflict", "mri_actual_imaging"),
            ("MRI perioperative surgical signal", "mri_perioperative_signal"),
        ):
            fact_count = connection.execute(f"SELECT COUNT(*) FROM row_fact WHERE {fact_column}=1").fetchone()[0]
            inventory_count = connection.execute(
                "SELECT COUNT(*) FROM recall_risk_inventory WHERE risk_type=?", (risk_type,)
            ).fetchone()[0]
            require(fact_count == inventory_count, f"{risk_type} inventory is incomplete.")
        require(
            connection.execute(
                "SELECT COUNT(*) FROM row_fact WHERE mri_actual_imaging=1 AND mri_perioperative_signal=0"
            ).fetchone()[0] > 0,
            "MRI imaging-system conflicts are not independently represented.",
        )
        require(
            connection.execute(
                "SELECT COUNT(*) FROM row_fact WHERE mri_actual_imaging=0 AND mri_perioperative_signal=1"
            ).fetchone()[0] > 0,
            "MRI perioperative surgical signals are not independently represented.",
        )

        funnel_types = {row[0] for row in connection.execute("SELECT DISTINCT funnel_type FROM funnel_cube")}
        require(
            funnel_types == {"Extraction", "Candidate", "Terminal", "Presentation"},
            f"Funnel stage types are incomplete or misclassified: {funnel_types}",
        )
        presentation_rows = connection.execute(
            "SELECT COUNT(*) FROM funnel_cube WHERE stage_id='S14_PRESENTATION_EXPORT' AND funnel_type='Presentation'"
        ).fetchone()[0]
        require(presentation_rows == 7, f"S14 presentation must have six output rows plus Overall, found {presentation_rows}.")

        outputs = {row[0] for row in connection.execute("SELECT DISTINCT output_file_id FROM removal_cube")}
        require(outputs == set(EXPECTED_ROWS) | {"OVERALL"}, f"Removal cube outputs are incomplete: {outputs}")
        groupings = {row[0] for row in connection.execute("SELECT DISTINCT grouping_level FROM removal_cube")}
        require(groupings == {"All", "Manufacturer", "Family", "Product", "Manufacturer × Family", "Manufacturer × Family × Product"},
                f"Removal cube grouping levels are invalid: {groupings}")
        require(connection.execute(
            "SELECT COUNT(*) FROM removal_cube WHERE grouping_id IS NULL OR manufacturer='' OR family='' OR product=''"
        ).fetchone()[0] == 0, "Removal cube contains an unstable blank grouping.")
        require(connection.execute(
            "SELECT COUNT(*) FROM removal_cube WHERE reason_kind='Primary' AND is_additive<>1"
        ).fetchone()[0] == 0, "Primary reasons must be additive.")
        require(connection.execute(
            "SELECT COUNT(*) FROM removal_cube WHERE reason_kind='Secondary' AND is_additive<>0"
        ).fetchone()[0] == 0, "Secondary reasons must be nonadditive.")
        require(connection.execute(
            "SELECT COUNT(*) FROM review_label WHERE production_changed<>0"
        ).fetchone()[0] == 0, "Review recommendations changed production state.")

        baseline_rows = connection.execute("SELECT * FROM baseline_manifest ORDER BY manifest_id").fetchall()
        require(len(baseline_rows) == 11, f"Baseline manifest must contain 11 governed inputs, found {len(baseline_rows)}.")
        baseline_types = {row["artifact_type"] for row in baseline_rows}
        require(
            {"code", "configuration", "rule_registry", "reference_source", "mapped_complete_source", "immutable_complete_input"}
            <= baseline_types,
            f"Baseline manifest types are incomplete: {baseline_types}",
        )
        require(sum(row["artifact_type"] == "reference_source" for row in baseline_rows) == 1,
                "Baseline manifest must fingerprint exactly one governed master source.")
        for row in baseline_rows:
            path = Path(row["path"])
            require(path.exists(), f"Baseline artifact missing: {path}")
            require(path.stat().st_size == row["bytes"], f"Baseline artifact byte size mismatch: {path}")
            require(sha256_file(path) == row["sha256"], f"Baseline artifact hash mismatch: {path}")

        if workbook is not None:
            require(workbook.exists(), f"Workbook not found: {workbook}")
            require(workbook.stat().st_size < 100_000_000, "Workbook exceeds 100 MB.")
            require(workbook_sheet_names(workbook) == EXPECTED_SHEETS, "Workbook tabs are not exact or are out of order.")
        if html_path is not None:
            require(html_path.exists(), f"HTML guide not found: {html_path}")
            html_text = html_path.read_text(encoding="utf-8")
            for stage_number in range(15):
                require(f"S{stage_number:02d}_" in html_text, f"HTML is missing stage S{stage_number:02d}.")
            for phrase in ("not statistical precision", "not statistical recall", "MRI separation", "India FY2025", "Pakistan nonstandard"):
                require(phrase in html_text, f"HTML is missing required disclosure: {phrase}")

        for artifact_type, path in (("workbook", workbook), ("html", html_path)):
            if path is None:
                continue
            manifest = connection.execute(
                "SELECT * FROM artifact_manifest WHERE run_id=? AND artifact_type=?",
                (run_id, artifact_type),
            ).fetchone()
            require(manifest is not None, f"Artifact manifest is missing {artifact_type}: {path}")
            manifest_path = Path(manifest["path"])
            if not manifest_path.is_absolute():
                manifest_path = ROOT / manifest_path
            require(manifest_path.resolve() == path.resolve(), f"Artifact manifest path mismatch: {path}")
            require(path.stat().st_size == manifest["bytes"], f"Artifact manifest byte size mismatch: {path}")
            require(sha256_file(path) == manifest["sha256"], f"Artifact manifest hash mismatch: {path}")

        logical_hashes = {
            "source_manifest": stable_query_hash(connection, "SELECT output_file_id,expected_rows,observed_rows,source_sha256,complete_source_sha256,transaction_count,value_usd,volume FROM source_file ORDER BY output_file_id"),
            "review_sample": stable_query_hash(connection, "SELECT output_file_id,source_row_id,sample_type,sample_stratum,target_category,inclusion_probability,sample_weight,fixed_seed,sample_rank,evidence,shadow_recommendation FROM review_label ORDER BY output_file_id,sample_type,sample_rank,source_row_id"),
            "funnel_cube": stable_query_hash(connection, "SELECT * FROM funnel_cube ORDER BY output_file_id,stage_order,candidate_status,outcome"),
            "removal_cube": stable_query_hash(connection, "SELECT * FROM removal_cube ORDER BY output_file_id,reason_kind,stage_id,rule_id,grouping_level,grouping_id,outcome,reason"),
            "india_reference_attribution": stable_query_hash(connection, "SELECT reference_status,output_tier,removal_stage_id,primary_reason,COUNT(*),SUM(value_usd),SUM(volume) FROM row_fact WHERE output_file_id='IN_2025' GROUP BY reference_status,output_tier,removal_stage_id,primary_reason ORDER BY reference_status,output_tier,removal_stage_id,primary_reason"),
        }
        return {
            "run_id": run_id,
            "status": "PASS",
            "source_rows": sum(EXPECTED_ROWS.values()),
            "mri_inventory_rows": mri_inventory,
            "logical_hashes": logical_hashes,
        }
    finally:
        connection.close()


def default_artifact_paths() -> tuple[Path, Path, Path]:
    """Resolve the current governed run exactly as the report builder does."""
    config_path = ROOT / "config" / "audit_sources.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    run_id = str(config["run_id"])
    run_dir = ROOT / "outputs" / run_id
    return (
        run_dir / "prediction_audit.sqlite",
        run_dir / "Prediction_Funnel_and_Review.xlsx",
        ROOT / "docs" / "Surgical_Mapping_Workflow_Guide.html",
    )


def parse_args() -> argparse.Namespace:
    default_db, default_workbook, default_html = default_artifact_paths()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db)
    parser.add_argument("--workbook", type=Path, default=default_workbook)
    parser.add_argument("--html", type=Path, default=default_html)
    parser.add_argument("--compare-db", type=Path, help="Second full rebuild; logical hashes must match.")
    parser.add_argument("--json", type=Path, help="Optional path for the verification result.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = verify(args.db.resolve(), args.workbook.resolve() if args.workbook else None, args.html.resolve() if args.html else None)
    if args.compare_db:
        comparison = verify(args.compare_db.resolve(), None, None)
        require(result["logical_hashes"] == comparison["logical_hashes"], "Logical hashes differ between full rebuilds.")
        result["deterministic_compare"] = "PASS"
    output = json.dumps(result, indent=2, ensure_ascii=False)
    print(output)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(output + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
