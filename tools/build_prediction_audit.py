#!/usr/bin/env python3
"""Build the governed prediction-audit SQLite database.

SQLite is the analytical authority.  Excel files are accepted only by the
explicit one-time, uncapped legacy migration entries in audit_sources.json.
Any input at Excel's data-row ceiling is rejected.  Complete CSV remaps are
performed in chunks with the current production routing semantics.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

import openpyxl
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings as cfg  # noqa: E402
from tools import batch_surgical_workflow_remap as br  # noqa: E402
from tools import vietnam_fy2024_workflow_improvement as wf  # noqa: E402

EXCEL_MAX_DATA_ROWS = 1_048_575
CHUNK_ROWS = 50_000
MRI_RE = re.compile(r"\bmri[\s-]*(?:compatible|compatibility|conditional|safe)\b", re.I)
DENTAL_RE = re.compile(r"\b(?:dental|dentist|orthodont|endodont|root\s+canal)\b", re.I)
ACCESSORY_RE = re.compile(r"\b(?:accessor(?:y|ies)|spare\s+part|replacement\s+part)\b", re.I)

FACT_COLUMNS = [
    "run_id", "output_file_id", "source_row_id", "original_unique_id", "source_row_number",
    "country", "fiscal_year", "detailed_product", "manufacturer", "family", "product",
    "segment", "sub_segment", "match_tier", "reference_status", "scope_flag", "qa_status",
    "output_tier", "primary_reason", "removal_stage_id", "value_usd", "volume",
    "value_numeric_status", "volume_numeric_status", "mri_risk", "nonstandard_tier",
    "independent_surgical_signal", "negative_conflict_group", "generic_token_risk",
    "ophthalmic_imaging_conflict_risk", "extended_false_positive_risk", "source_text_hash"
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path, block: int = 4 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(block):
            h.update(chunk)
    return h.hexdigest()


def count_delimited_rows(path: Path) -> int:
    with path.open("rb") as fh:
        return max(sum(chunk.count(b"\n") for chunk in iter(lambda: fh.read(8 * 1024 * 1024), b"")) - 1, 0)


def text(value: object) -> str:
    if value is None:
        return ""
    value = str(value)
    return "" if value.lower() == "nan" else value.strip()


def parse_number(value: object) -> tuple[float | None, str]:
    raw = text(value)
    if not raw:
        return None, "missing"
    try:
        number = float(raw.replace(",", ""))
        if not math.isfinite(number):
            return None, "invalid"
        return number, "valid"
    except (TypeError, ValueError):
        return None, "invalid"


def truthy(value: object) -> int:
    return int(text(value).lower() in {"1", "true", "yes", "y"})


def source_text(row: dict[str, object]) -> str:
    return " | ".join(text(row.get(c)) for c in ("Detailed_Product", "Importer", "Exporter", "Manufacturer", "Family", "Product_V0"))


def terminal_tier(row: dict[str, object]) -> str:
    explicit = text(row.get("Output_Tier"))
    if explicit in {"Trusted", "Review", "Excluded"}:
        return explicit
    if explicit == "Trusted_Dashboard":
        return "Trusted"
    if explicit == "Review_Queue":
        return "Review"
    if explicit == "Excluded_Unmapped":
        return "Excluded"
    if text(row.get("Dash_Include")).upper() == "Y":
        return "Trusted"
    qa = text(row.get("QA_Status")).lower()
    return "Review" if qa.startswith(("review", "audit")) else "Excluded"


def derive_reason(row: dict[str, object], tier: str) -> tuple[str, str]:
    qa = text(row.get("QA_Status"))
    neg = text(row.get("Negative_Conflict_Group"))
    scope = text(row.get("Scope_Flag"))
    ref = text(row.get("Reference_Key_Status") or row.get("Ref_Valid"))
    if tier == "Trusted":
        return "trusted_reference_valid_surgical", "S13_TERMINAL_ROUTING"
    if truthy(row.get("Ophthalmic_Imaging_Conflict_Risk")) or "ophthalmic" in qa.lower() or "imaging" in qa.lower():
        return "ophthalmic_imaging_conflict", "S12_REMAP_GUARDS"
    if ref and ref.lower() not in {"valid", "y", "yes", "true", "1", "reference-valid"}:
        return "reference_tuple_invalid", "S07_REFERENCE_VALIDATION"
    if scope:
        return "scope_exclusion", "S08_SCOPE_WHITELIST"
    if neg:
        return f"negative_conflict:{neg}", "S04_CATEGORY_FALLBACK"
    if truthy(row.get("Generic_Token_Risk")) or truthy(row.get("Date_Month_Token_Risk")) or truthy(row.get("APT_March_Rule_Risk")):
        return "generic_or_token_anomaly", "S09_GENERIC_ANOMALY"
    if truthy(row.get("Extended_False_Positive_Risk")):
        return "extended_hs_false_positive_risk", "S10_EXTENDED_HS"
    if qa:
        return qa, "S13_TERMINAL_ROUTING"
    return ("review_required" if tier == "Review" else "excluded_no_accepted_candidate"), "S13_TERMINAL_ROUTING"


def stage_path(row: dict[str, object], tier: str, reason: str) -> list[dict[str, object]]:
    description = source_text(row)
    match_tier = text(row.get("Match_Tier")).lower()
    mapped = any(text(row.get(c)) for c in ("Manufacturer", "Family", "Segment", "Sub-segment", "Product_V0"))
    negative = text(row.get("Negative_Conflict_Group"))
    scope = text(row.get("Scope_Flag"))
    ref = text(row.get("Reference_Key_Status") or row.get("Ref_Valid"))
    path = [
        {"stage_id": "S00_EXTRACTION", "outcome": "Passed", "reason": "complete_source_loaded", "continues": 1},
        {"stage_id": "S01_HS_ELIGIBILITY", "outcome": "Passed", "reason": "hs_eligible", "continues": 1},
    ]
    if DENTAL_RE.search(description):
        recovered = truthy(row.get("Independent_Surgical_Signal"))
        path.append({"stage_id": "S02_DENTAL_SUPPRESSION", "outcome": "Recovered" if recovered else "Suppressed", "reason": "dental_with_independent_surgical_signal" if recovered else "dental_only", "continues": 1})
    if "family" in match_tier:
        path.append({"stage_id": "S03_FAMILY_MATCH", "outcome": "Passed", "reason": "family_match", "continues": 1})
    if "category" in match_tier or negative or ACCESSORY_RE.search(description):
        path.append({"stage_id": "S04_CATEGORY_FALLBACK", "outcome": "Suppressed" if negative else "Passed", "reason": f"negative_conflict:{negative}" if negative else "category_match", "continues": 1})
    if "manufacturer" in match_tier:
        path.append({"stage_id": "S05_MANUFACTURER_FALLBACK", "outcome": "Review" if tier != "Trusted" else "Passed", "reason": "manufacturer_fallback", "continues": 1})
    if mapped:
        path.append({"stage_id": "S06_STANDARDIZATION", "outcome": "Passed", "reason": "standardized", "continues": 1})
        ref_ok = ref.lower() in {"valid", "y", "yes", "true", "1", "reference-valid"}
        path.append({"stage_id": "S07_REFERENCE_VALIDATION", "outcome": "Passed" if ref_ok else "Review", "reason": "reference_tuple_valid" if ref_ok else "reference_tuple_invalid", "continues": 1})
    if scope:
        path.append({"stage_id": "S08_SCOPE_WHITELIST", "outcome": "Suppressed", "reason": "scope_exclusion", "continues": 1})
    if any(truthy(row.get(c)) for c in ("Generic_Token_Risk", "Date_Month_Token_Risk", "APT_March_Rule_Risk")):
        path.append({"stage_id": "S09_GENERIC_ANOMALY", "outcome": "Review", "reason": "generic_or_token_anomaly", "continues": 1})
    if "extended" in match_tier or truthy(row.get("Extended_False_Positive_Risk")):
        bad = truthy(row.get("Extended_False_Positive_Risk"))
        path.append({"stage_id": "S10_EXTENDED_HS", "outcome": "Suppressed" if bad else "Passed", "reason": "extended_hs_false_positive_risk" if bad else "extended_hs_supported", "continues": 1})
    if "hs_prior" in match_tier:
        path.append({"stage_id": "S11_HS_PRIOR", "outcome": "Recovered" if tier == "Trusted" else "Review", "reason": "hs_prior_recovery", "continues": 1})
    guard_outcome = "Passed" if tier == "Trusted" else ("Review" if tier == "Review" else "Suppressed")
    path.append({"stage_id": "S12_REMAP_GUARDS", "outcome": guard_outcome, "reason": reason, "continues": 1})
    path.append({"stage_id": "S13_TERMINAL_ROUTING", "outcome": tier, "reason": reason, "continues": 0})
    return path


def rule_hits(row: dict[str, object], mri: int, nonstandard: int) -> list[tuple[str, str, str]]:
    hits: list[tuple[str, str, str]] = []
    description = source_text(row)
    if mri:
        hits.append(("S12_REMAP_GUARDS", "MRI_COMPATIBLE_RECALL_RISK", "MRI-compatible text can be surgical and is review-only in this release"))
    if nonstandard:
        hits.append(("S05_MANUFACTURER_FALLBACK" if "manufacturer" in text(row.get("Match_Tier")).lower() else "S11_HS_PRIOR", "NONSTANDARD_TIER_RETAINED", text(row.get("Match_Tier"))))
    flags = {
        "Negative_Conflict_Group": ("S04_CATEGORY_FALLBACK", "NEGATIVE_CONFLICT"),
        "Scope_Flag": ("S08_SCOPE_WHITELIST", "SCOPE_FLAG"),
        "Generic_Token_Risk": ("S09_GENERIC_ANOMALY", "GENERIC_TOKEN_RISK"),
        "Date_Month_Token_Risk": ("S09_GENERIC_ANOMALY", "DATE_MONTH_TOKEN_RISK"),
        "APT_March_Rule_Risk": ("S09_GENERIC_ANOMALY", "APT_MARCH_TOKEN_RISK"),
        "Ophthalmic_Imaging_Conflict_Risk": ("S12_REMAP_GUARDS", "OPHTHALMIC_IMAGING_CONFLICT"),
        "Extended_False_Positive_Risk": ("S10_EXTENDED_HS", "EXTENDED_HS_FALSE_POSITIVE_RISK"),
    }
    for column, (stage, rule) in flags.items():
        value = row.get(column)
        if (column in {"Negative_Conflict_Group", "Scope_Flag"} and text(value)) or (column not in {"Negative_Conflict_Group", "Scope_Flag"} and truthy(value)):
            hits.append((stage, rule, text(value) or "1"))
    if DENTAL_RE.search(description):
        hits.append(("S02_DENTAL_SUPPRESSION", "DENTAL_CUE", "dental phrase"))
    return hits


def initialize_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    con = sqlite3.connect(path)
    # The governed database is rebuilt atomically from immutable inputs.  DELETE
    # journaling bounds temporary disk use during multi-million-row ingestion;
    # WAL can transiently duplicate most of the database on constrained drives.
    con.execute("PRAGMA journal_mode=DELETE")
    con.execute("PRAGMA synchronous=OFF")
    con.execute("PRAGMA temp_store=FILE")
    con.execute("PRAGMA cache_size=-200000")
    con.executescript("""
    CREATE TABLE run (
      run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, completed_at TEXT,
      registry_version TEXT NOT NULL, policy TEXT NOT NULL, status TEXT NOT NULL,
      code_commit TEXT, notes TEXT
    );
    CREATE TABLE source_file (
      run_id TEXT NOT NULL, output_file_id TEXT NOT NULL, output_label TEXT NOT NULL,
      country TEXT NOT NULL, fiscal_year TEXT NOT NULL, source_path TEXT NOT NULL,
      complete_source_path TEXT, ingestion_mode TEXT NOT NULL, expected_rows INTEGER NOT NULL,
      observed_rows INTEGER NOT NULL, sha256 TEXT NOT NULL, source_sha256 TEXT,
      is_complete INTEGER NOT NULL, PRIMARY KEY (run_id, output_file_id)
    );
    CREATE TABLE row_fact (
      row_fact_id INTEGER PRIMARY KEY,
      run_id TEXT NOT NULL, output_file_id TEXT NOT NULL, source_row_id TEXT NOT NULL,
      original_unique_id TEXT, source_row_number INTEGER NOT NULL, country TEXT NOT NULL,
      fiscal_year TEXT NOT NULL, detailed_product TEXT, manufacturer TEXT, family TEXT,
      product TEXT, segment TEXT, sub_segment TEXT, match_tier TEXT, reference_status TEXT,
      scope_flag TEXT, qa_status TEXT, output_tier TEXT NOT NULL, primary_reason TEXT NOT NULL,
      removal_stage_id TEXT NOT NULL, value_usd REAL, volume REAL,
      value_numeric_status TEXT NOT NULL, volume_numeric_status TEXT NOT NULL,
      mri_risk INTEGER NOT NULL, nonstandard_tier INTEGER NOT NULL,
      independent_surgical_signal INTEGER NOT NULL, negative_conflict_group TEXT,
      generic_token_risk INTEGER NOT NULL, ophthalmic_imaging_conflict_risk INTEGER NOT NULL,
      extended_false_positive_risk INTEGER NOT NULL, source_text_hash TEXT NOT NULL,
      UNIQUE (run_id, output_file_id, source_row_id)
    );
    CREATE TABLE row_stage_state (
      row_fact_id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, output_file_id TEXT NOT NULL,
      source_row_id TEXT NOT NULL, stage_path_json TEXT NOT NULL,
      FOREIGN KEY (row_fact_id) REFERENCES row_fact(row_fact_id)
    );
    CREATE TABLE rule_hit (
      rule_hit_id INTEGER PRIMARY KEY, row_fact_id INTEGER NOT NULL, run_id TEXT NOT NULL,
      output_file_id TEXT NOT NULL, source_row_id TEXT NOT NULL, stage_id TEXT NOT NULL,
      rule_id TEXT NOT NULL, reason TEXT, hit_kind TEXT NOT NULL DEFAULT 'secondary',
      is_additive INTEGER NOT NULL DEFAULT 0,
      FOREIGN KEY (row_fact_id) REFERENCES row_fact(row_fact_id)
    );
    CREATE TABLE review_label (
      review_label_id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, output_file_id TEXT NOT NULL,
      source_row_id TEXT NOT NULL, sample_type TEXT NOT NULL, sample_stratum TEXT NOT NULL,
      surgical_relevance TEXT, mapping_correctness TEXT, corrected_manufacturer TEXT,
      corrected_family TEXT, corrected_product TEXT, corrected_segment TEXT,
      corrected_sub_segment TEXT, rationale TEXT, reviewer TEXT, reviewed_at TEXT,
      adjudicator TEXT, adjudicated_at TEXT, disposition TEXT NOT NULL,
      shadow_recommendation TEXT NOT NULL, production_changed INTEGER NOT NULL DEFAULT 0,
      UNIQUE (run_id, output_file_id, source_row_id)
    );
    CREATE TABLE recall_risk_inventory (
      inventory_id INTEGER PRIMARY KEY, row_fact_id INTEGER NOT NULL, run_id TEXT NOT NULL,
      output_file_id TEXT NOT NULL, source_row_id TEXT NOT NULL, risk_type TEXT NOT NULL,
      current_output_tier TEXT NOT NULL, recommendation TEXT NOT NULL,
      UNIQUE (run_id, output_file_id, source_row_id, risk_type)
    );
    CREATE TABLE rule_registry_stage (
      stage_id TEXT PRIMARY KEY, registry_version TEXT NOT NULL, execution_order INTEGER NOT NULL,
      documentation_label TEXT NOT NULL, stage_type TEXT NOT NULL, input_population TEXT NOT NULL,
      predicate_description TEXT NOT NULL, outcomes_json TEXT NOT NULL,
      reason_precedence_json TEXT NOT NULL, row_continues_json TEXT NOT NULL
    );
    CREATE TABLE funnel_cube (
      run_id TEXT NOT NULL, output_file_id TEXT NOT NULL, output_label TEXT NOT NULL,
      funnel_type TEXT NOT NULL, stage_id TEXT NOT NULL, stage_order INTEGER NOT NULL,
      stage_label TEXT NOT NULL, outcome TEXT NOT NULL, transaction_count INTEGER NOT NULL,
      value_usd REAL, volume REAL, missing_value_count INTEGER NOT NULL,
      invalid_value_count INTEGER NOT NULL, missing_volume_count INTEGER NOT NULL,
      invalid_volume_count INTEGER NOT NULL, weighted_asp REAL,
      PRIMARY KEY (run_id, output_file_id, funnel_type, stage_id, outcome)
    );
    CREATE TABLE removal_cube (
      run_id TEXT NOT NULL, output_file_id TEXT NOT NULL, output_label TEXT NOT NULL,
      reason_kind TEXT NOT NULL, is_additive INTEGER NOT NULL, stage_id TEXT NOT NULL,
      outcome TEXT NOT NULL, reason TEXT NOT NULL, grouping_level TEXT NOT NULL,
      manufacturer TEXT NOT NULL, family TEXT NOT NULL, product TEXT NOT NULL,
      transaction_count INTEGER NOT NULL, value_usd REAL, volume REAL,
      missing_value_count INTEGER NOT NULL, invalid_value_count INTEGER NOT NULL,
      missing_volume_count INTEGER NOT NULL, invalid_volume_count INTEGER NOT NULL,
      weighted_asp REAL
    );
    CREATE TABLE reconciliation_qc (
      qc_id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, output_file_id TEXT NOT NULL,
      check_name TEXT NOT NULL, observed TEXT NOT NULL, expected TEXT NOT NULL,
      status TEXT NOT NULL, evidence TEXT NOT NULL, checked_at TEXT NOT NULL
    );
    CREATE TABLE baseline_manifest (
      manifest_id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, artifact_type TEXT NOT NULL,
      path TEXT NOT NULL, sha256 TEXT NOT NULL, bytes INTEGER NOT NULL
    );
    """)
    return con


def load_registry(con: sqlite3.Connection, registry: dict[str, object]) -> None:
    rows = []
    for stage in registry["stages"]:
        rows.append((stage["stage_id"], registry["registry_version"], stage["execution_order"], stage["documentation_label"], stage["stage_type"], stage["input_population"], stage["predicate_description"], json.dumps(stage["outcomes"]), json.dumps(stage["reason_precedence"]), json.dumps(stage["row_continues"])))
    con.executemany("INSERT INTO rule_registry_stage VALUES (?,?,?,?,?,?,?,?,?,?)", rows)


def iter_legacy_xlsx(path: Path) -> tuple[int, Iterator[list[dict[str, object]]]]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    if "RawData" not in wb.sheetnames:
        wb.close()
        raise RuntimeError(f"FAIL CLOSED: RawData sheet missing: {path}")
    ws = wb["RawData"]
    rows = ws.max_row - 1
    if rows >= EXCEL_MAX_DATA_ROWS:
        wb.close()
        raise RuntimeError(f"FAIL CLOSED: legacy Excel source is capped/truncated ({rows:,} rows): {path}")
    headers = [text(cell.value) for cell in next(ws.iter_rows(min_row=1, max_row=1))]

    def chunks() -> Iterator[list[dict[str, object]]]:
        batch: list[dict[str, object]] = []
        try:
            for values in ws.iter_rows(min_row=2, values_only=True):
                batch.append(dict(zip(headers, values)))
                if len(batch) >= CHUNK_ROWS:
                    yield batch
                    batch = []
            if batch:
                yield batch
        finally:
            wb.close()
    return rows, chunks()


def iter_current_csv(path: Path, master_keys: wf.MasterKeys) -> tuple[int, Iterator[list[dict[str, object]]]]:
    observed = count_delimited_rows(path)

    def chunks() -> Iterator[list[dict[str, object]]]:
        for frame in pd.read_csv(path, dtype=str, keep_default_na=False, chunksize=CHUNK_ROWS, low_memory=False):
            routed, _, _ = br.route_file(frame, master_keys)
            tier = wf.output_tier(routed).map({"Trusted_Dashboard": "Trusted", "Review_Queue": "Review", "Excluded_Unmapped": "Excluded"})
            routed["Output_Tier"] = tier
            yield routed.fillna("").to_dict("records")
    return observed, chunks()


def ingest_output(con: sqlite3.Connection, run_id: str, spec: dict[str, object], master_keys: wf.MasterKeys) -> None:
    path = ROOT / str(spec["path"])
    if not path.exists():
        raise RuntimeError(f"FAIL CLOSED: source missing: {path}")
    mode = str(spec["ingestion_mode"])
    if mode == "governed_uncapped_legacy_excel_migration":
        observed, chunks = iter_legacy_xlsx(path)
    elif mode == "complete_csv_current_remap":
        complete = ROOT / str(spec["complete_source_path"])
        if not complete.exists():
            raise RuntimeError(f"FAIL CLOSED: complete source missing: {complete}")
        complete_rows = count_delimited_rows(complete)
        if complete_rows != int(spec["expected_rows"]):
            raise RuntimeError(f"FAIL CLOSED: complete source count {complete_rows:,} != expected {int(spec['expected_rows']):,}")
        observed, chunks = iter_current_csv(path, master_keys)
        if observed != complete_rows:
            raise RuntimeError(f"FAIL CLOSED: mapped CSV count {observed:,} != complete source {complete_rows:,}")
    else:
        raise RuntimeError(f"Unsupported ingestion mode: {mode}")
    if observed != int(spec["expected_rows"]):
        raise RuntimeError(f"FAIL CLOSED: {spec['output_label']} observed {observed:,} != expected {int(spec['expected_rows']):,}")

    output_id = str(spec["output_file_id"])
    fact_sql = f"INSERT INTO row_fact ({','.join(FACT_COLUMNS)}) VALUES ({','.join('?' for _ in FACT_COLUMNS)})"
    fact_id = con.execute("SELECT COALESCE(MAX(row_fact_id),0) FROM row_fact").fetchone()[0]
    processed = 0
    for batch in chunks:
        fact_rows = []
        stage_rows = []
        hit_rows = []
        inventory_rows = []
        for row in batch:
            processed += 1
            fact_id += 1
            uid = text(row.get("UniqueID")) or f"ROW{processed}"
            stable_id = f"{uid}#{processed}"
            desc = source_text(row)
            tier = terminal_tier(row)
            reason, removal_stage = derive_reason(row, tier)
            value, value_status = parse_number(row.get("Total_Value_USD"))
            volume, volume_status = parse_number(row.get("Quantity"))
            mri = int(bool(MRI_RE.search(desc)))
            match_tier = text(row.get("Match_Tier"))
            nonstandard = int(match_tier.lower() in {"manufacturer", "hs_prior"})
            src_hash = hashlib.sha256(desc.encode("utf-8", errors="replace")).hexdigest()
            fact_values = (
                run_id, output_id, stable_id, uid, processed, str(spec["country"]), str(spec["fiscal_year"]),
                text(row.get("Detailed_Product")), text(row.get("Manufacturer")), text(row.get("Family")),
                text(row.get("Product_V0")), text(row.get("Segment")), text(row.get("Sub-segment")),
                match_tier, text(row.get("Reference_Key_Status") or row.get("Ref_Valid")), text(row.get("Scope_Flag")),
                text(row.get("QA_Status")), tier, reason, removal_stage, value, volume, value_status, volume_status,
                mri, nonstandard, truthy(row.get("Independent_Surgical_Signal")), text(row.get("Negative_Conflict_Group")),
                truthy(row.get("Generic_Token_Risk")), truthy(row.get("Ophthalmic_Imaging_Conflict_Risk")),
                truthy(row.get("Extended_False_Positive_Risk")), src_hash,
            )
            fact_rows.append(fact_values)
            stage_rows.append((fact_id, run_id, output_id, stable_id, json.dumps(stage_path(row, tier, reason), separators=(",", ":"))))
            for stage_id, rule_id, hit_reason in rule_hits(row, mri, nonstandard):
                hit_rows.append((fact_id, run_id, output_id, stable_id, stage_id, rule_id, hit_reason))
            if mri:
                inventory_rows.append((fact_id, run_id, output_id, stable_id, "MRI compatible", tier, "Human review; consider governed alias/reference update only after adjudication and a full rerun"))
            if nonstandard:
                inventory_rows.append((fact_id, run_id, output_id, stable_id, f"Non-standard tier: {match_tier}", tier, "Retain mapping in SQLite; review evidence before any future Trusted promotion"))
        con.executemany(fact_sql, fact_rows)
        con.executemany("INSERT INTO row_stage_state VALUES (?,?,?,?,?)", stage_rows)
        con.executemany("INSERT INTO rule_hit (row_fact_id,run_id,output_file_id,source_row_id,stage_id,rule_id,reason) VALUES (?,?,?,?,?,?,?)", hit_rows)
        con.executemany("INSERT OR IGNORE INTO recall_risk_inventory (row_fact_id,run_id,output_file_id,source_row_id,risk_type,current_output_tier,recommendation) VALUES (?,?,?,?,?,?,?)", inventory_rows)
        con.commit()
        print(f"  [{spec['output_label']}] {processed:,}/{observed:,}", flush=True)
    if processed != observed:
        raise RuntimeError(f"FAIL CLOSED: processed {processed:,} != observed {observed:,} for {spec['output_label']}")

    complete_path = ROOT / str(spec["complete_source_path"]) if spec.get("complete_source_path") else None
    con.execute("""INSERT INTO source_file VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
        run_id, output_id, str(spec["output_label"]), str(spec["country"]), str(spec["fiscal_year"]),
        str(path.relative_to(ROOT)), str(complete_path.relative_to(ROOT)) if complete_path else None,
        mode, int(spec["expected_rows"]), observed, sha256_file(path), sha256_file(complete_path) if complete_path else None, 1,
    ))
    con.commit()


def create_views(con: sqlite3.Connection) -> None:
    con.executescript("""
    CREATE INDEX idx_row_output ON row_fact(output_file_id);
    CREATE INDEX idx_row_tier ON row_fact(output_file_id, output_tier);
    CREATE INDEX idx_row_removal ON row_fact(removal_stage_id, output_tier, primary_reason);
    CREATE INDEX idx_row_dims ON row_fact(manufacturer, family, product);
    CREATE INDEX idx_hit_rule ON rule_hit(output_file_id, stage_id, rule_id);
    CREATE INDEX idx_inventory ON recall_risk_inventory(output_file_id, risk_type);
    CREATE VIEW v_row_stage_state_long AS
      SELECT s.row_fact_id, s.run_id, s.output_file_id, s.source_row_id,
             json_extract(j.value,'$.stage_id') AS stage_id,
             json_extract(j.value,'$.outcome') AS outcome,
             json_extract(j.value,'$.reason') AS reason,
             CAST(json_extract(j.value,'$.continues') AS INTEGER) AS row_continues
      FROM row_stage_state s, json_each(s.stage_path_json) j;
    CREATE VIEW v_recall_risk_summary AS
      SELECT output_file_id, risk_type, current_output_tier,
             COUNT(*) AS transaction_count,
             SUM(r.value_usd) AS value_usd, SUM(r.volume) AS volume,
             CASE WHEN SUM(r.volume) != 0 THEN SUM(r.value_usd)/SUM(r.volume) END AS weighted_asp
      FROM recall_risk_inventory i JOIN row_fact r USING(row_fact_id)
      GROUP BY output_file_id, risk_type, current_output_tier;
    CREATE VIEW v_review_samples AS
      SELECT l.*, r.detailed_product, r.manufacturer, r.family, r.product, r.match_tier,
             r.output_tier, r.primary_reason, r.value_usd, r.volume, r.mri_risk, r.nonstandard_tier
      FROM review_label l JOIN row_fact r
        ON r.run_id=l.run_id AND r.output_file_id=l.output_file_id AND r.source_row_id=l.source_row_id;
    """)


def insert_review_samples(con: sqlite3.Connection, run_id: str, specs: list[dict[str, object]]) -> None:
    for spec in specs:
        output_id = str(spec["output_file_id"])
        targeted = con.execute("""
          SELECT source_row_id,
                 CASE WHEN mri_risk=1 THEN 'MRI compatible'
                      WHEN nonstandard_tier=1 THEN 'Non-standard tier'
                      WHEN independent_surgical_signal=1 AND output_tier!='Trusted' THEN 'Surgical signal not Trusted'
                      ELSE 'High-value Review/Excluded' END AS stratum
          FROM row_fact
          WHERE run_id=? AND output_file_id=?
            AND (mri_risk=1 OR nonstandard_tier=1 OR (independent_surgical_signal=1 AND output_tier!='Trusted') OR output_tier!='Trusted')
          ORDER BY mri_risk DESC, nonstandard_tier DESC, independent_surgical_signal DESC,
                   COALESCE(value_usd,0) DESC, source_row_id
          LIMIT 12
        """, (run_id, output_id)).fetchall()
        chosen = {row[0] for row in targeted}
        random_rows: list[tuple[str, str]] = []
        for tier, count in (("Trusted", 5), ("Review", 4), ("Excluded", 4)):
            placeholders = ",".join("?" for _ in chosen) or "''"
            params: list[object] = [run_id, output_id, tier, *sorted(chosen), count]
            query = f"""
              SELECT source_row_id FROM row_fact
              WHERE run_id=? AND output_file_id=? AND output_tier=?
                AND source_row_id NOT IN ({placeholders})
              ORDER BY ((row_fact_id * 1103515245 + 12345) & 2147483647), source_row_id
              LIMIT ?
            """
            selected = [r[0] for r in con.execute(query, params)]
            random_rows.extend((sid, f"Deterministic random — {tier}") for sid in selected)
            chosen.update(selected)
        if len(targeted) + len(random_rows) != 25:
            raise RuntimeError(f"Review sample for {output_id} is not 25 rows")
        records = []
        for sid, stratum in targeted:
            records.append((run_id, output_id, sid, "Targeted risk", stratum, "Pending", "Review only; no production promotion without governed reference/alias update and full rerun"))
        for sid, stratum in random_rows:
            records.append((run_id, output_id, sid, "Deterministic stratified-random", stratum, "Pending", "Adjudicate relevance and mapping correctness; production routing remains unchanged"))
        con.executemany("""
          INSERT INTO review_label
          (run_id,output_file_id,source_row_id,sample_type,sample_stratum,disposition,shadow_recommendation)
          VALUES (?,?,?,?,?,?,?)
        """, records)
    con.commit()


def metrics_sql(prefix: str = "") -> str:
    p = f"{prefix}." if prefix else ""
    return f"""COUNT(*) AS transaction_count,
      SUM({p}value_usd) AS value_usd, SUM({p}volume) AS volume,
      SUM(CASE WHEN {p}value_numeric_status='missing' THEN 1 ELSE 0 END) AS missing_value_count,
      SUM(CASE WHEN {p}value_numeric_status='invalid' THEN 1 ELSE 0 END) AS invalid_value_count,
      SUM(CASE WHEN {p}volume_numeric_status='missing' THEN 1 ELSE 0 END) AS missing_volume_count,
      SUM(CASE WHEN {p}volume_numeric_status='invalid' THEN 1 ELSE 0 END) AS invalid_volume_count,
      CASE WHEN SUM({p}volume) != 0 THEN SUM({p}value_usd)/SUM({p}volume) END AS weighted_asp"""


def build_funnel(con: sqlite3.Connection, run_id: str) -> None:
    registry = {r[0]: (r[1], r[2], r[3]) for r in con.execute("SELECT stage_id,execution_order,documentation_label,stage_type FROM rule_registry_stage")}
    output_labels = {r[0]: r[1] for r in con.execute("SELECT output_file_id,output_label FROM source_file WHERE run_id=?", (run_id,))}
    output_labels["OVERALL"] = "Overall"
    for output_id, label in output_labels.items():
        where = "" if output_id == "OVERALL" else "WHERE l.output_file_id=?"
        params = () if output_id == "OVERALL" else (output_id,)
        rows = con.execute(f"""
          SELECT l.stage_id,l.outcome,{metrics_sql('r')}
          FROM v_row_stage_state_long l JOIN row_fact r USING(row_fact_id)
          {where}
          GROUP BY l.stage_id,l.outcome
        """, params).fetchall()
        inserts = []
        for stage_id, outcome, *metrics in rows:
            order, stage_label, stage_type = registry[stage_id]
            funnel_type = "Terminal routing" if stage_type == "terminal" else "Candidate processing"
            inserts.append((run_id, output_id, label, funnel_type, stage_id, order, stage_label, outcome, *metrics))
        con.executemany("INSERT INTO funnel_cube VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", inserts)
    con.commit()


GROUPINGS = [
    ("All", "''", "''", "''"),
    ("Manufacturer", "manufacturer", "''", "''"),
    ("Family", "''", "family", "''"),
    ("Product", "''", "''", "product"),
    ("Manufacturer × Family", "manufacturer", "family", "''"),
    ("Manufacturer × Family × Product", "manufacturer", "family", "product"),
]


def build_removal_cube(con: sqlite3.Connection, run_id: str) -> None:
    output_labels = {r[0]: r[1] for r in con.execute("SELECT output_file_id,output_label FROM source_file WHERE run_id=?", (run_id,))}
    output_labels["OVERALL"] = "Overall"
    for output_id, label in output_labels.items():
        output_where = "" if output_id == "OVERALL" else "AND output_file_id=?"
        output_params: tuple[object, ...] = () if output_id == "OVERALL" else (output_id,)
        for level, mfr, fam, prod in GROUPINGS:
            expressions = [mfr or "''", fam or "''", prod or "''"]
            group_expr = ",".join(expressions)
            primary = con.execute(f"""
              SELECT removal_stage_id,output_tier,primary_reason,{group_expr},{metrics_sql()}
              FROM row_fact WHERE run_id=? AND output_tier!='Trusted' {output_where}
              GROUP BY removal_stage_id,output_tier,primary_reason,{group_expr}
            """, (run_id, *output_params)).fetchall()
            con.executemany("INSERT INTO removal_cube VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [
                (run_id, output_id, label, "Primary", 1, stage, outcome, reason, level, manufacturer, family, product, *metrics)
                for stage, outcome, reason, manufacturer, family, product, *metrics in primary
            ])
            secondary = con.execute(f"""
              SELECT h.stage_id,r.output_tier,h.rule_id,{','.join('r.'+x if x != "''" else x for x in expressions)},{metrics_sql('r')}
              FROM rule_hit h JOIN row_fact r USING(row_fact_id)
              WHERE r.run_id=? {('AND r.output_file_id=?' if output_id != 'OVERALL' else '')}
              GROUP BY h.stage_id,r.output_tier,h.rule_id,{','.join('r.'+x if x != "''" else x for x in expressions)}
            """, (run_id, *output_params)).fetchall()
            con.executemany("INSERT INTO removal_cube VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [
                (run_id, output_id, label, "Secondary", 0, stage, outcome, reason, level, manufacturer, family, product, *metrics)
                for stage, outcome, reason, manufacturer, family, product, *metrics in secondary
            ])
            con.commit()


def add_qc(con: sqlite3.Connection, run_id: str, output_id: str, name: str, observed: object, expected: object, ok: bool, evidence: str) -> None:
    con.execute("INSERT INTO reconciliation_qc (run_id,output_file_id,check_name,observed,expected,status,evidence,checked_at) VALUES (?,?,?,?,?,?,?,?)", (run_id, output_id, name, str(observed), str(expected), "PASS" if ok else "FAIL", evidence, utc_now()))


def run_qc(con: sqlite3.Connection, run_id: str, specs: list[dict[str, object]]) -> None:
    for spec in specs:
        oid = str(spec["output_file_id"])
        expected = int(spec["expected_rows"])
        rows = con.execute("SELECT COUNT(*) FROM row_fact WHERE run_id=? AND output_file_id=?", (run_id, oid)).fetchone()[0]
        add_qc(con, run_id, oid, "Complete source row count", rows, expected, rows == expected, "row_fact versus frozen source manifest")
        terminals = con.execute("SELECT COUNT(*) FROM row_fact WHERE run_id=? AND output_file_id=? AND output_tier IN ('Trusted','Review','Excluded')", (run_id, oid)).fetchone()[0]
        add_qc(con, run_id, oid, "Terminal route uniqueness", terminals, expected, terminals == expected, "one row_fact record with exactly one terminal tier")
        sample = con.execute("SELECT COUNT(*),SUM(sample_type='Targeted risk'),SUM(sample_type='Deterministic stratified-random') FROM review_label WHERE run_id=? AND output_file_id=?", (run_id, oid)).fetchone()
        add_qc(con, run_id, oid, "Review sample design", f"{sample[0]} total; {sample[1]} targeted; {sample[2]} random", "25 total; 12 targeted; 13 random", sample == (25, 12, 13), "governed review_label table")
        source_metrics = con.execute(f"SELECT {metrics_sql()} FROM row_fact WHERE run_id=? AND output_file_id=?", (run_id, oid)).fetchone()
        terminal_metrics = con.execute(f"SELECT {metrics_sql()} FROM row_fact WHERE run_id=? AND output_file_id=? AND output_tier IN ('Trusted','Review','Excluded')", (run_id, oid)).fetchone()
        ok = source_metrics[:3] == terminal_metrics[:3]
        add_qc(con, run_id, oid, "Terminal metric reconciliation", source_metrics[:3], terminal_metrics[:3], ok, "count, value and volume must reconcile")
        if oid.startswith("PK_"):
            nonstandard = con.execute("SELECT COUNT(*) FROM row_fact WHERE run_id=? AND output_file_id=? AND nonstandard_tier=1", (run_id, oid)).fetchone()[0]
            inventory = con.execute("SELECT COUNT(*) FROM recall_risk_inventory WHERE run_id=? AND output_file_id=? AND risk_type LIKE 'Non-standard tier:%'", (run_id, oid)).fetchone()[0]
            add_qc(con, run_id, oid, "Pakistan non-standard tier retention", inventory, nonstandard, inventory == nonstandard and nonstandard > 0, "all manufacturer/hs_prior rows retained in SQLite inventory")
    mri = con.execute("SELECT COUNT(*) FROM recall_risk_inventory WHERE run_id=? AND risk_type='MRI compatible'", (run_id,)).fetchone()[0]
    add_qc(con, run_id, "OVERALL", "MRI-compatible risk detection", mri, ">0", mri > 0, "complete MRI-compatible inventory")
    overall = con.execute("SELECT transaction_count,value_usd,volume FROM funnel_cube WHERE run_id=? AND output_file_id='OVERALL' AND stage_id='S13_TERMINAL_ROUTING'", (run_id,)).fetchall()
    six = con.execute("SELECT SUM(transaction_count),SUM(value_usd),SUM(volume) FROM funnel_cube WHERE run_id=? AND output_file_id!='OVERALL' AND stage_id='S13_TERMINAL_ROUTING'", (run_id,)).fetchone()
    ov = (sum(r[0] for r in overall), sum((r[1] or 0) for r in overall), sum((r[2] or 0) for r in overall))
    ok = ov[0] == six[0] and abs(ov[1] - (six[1] or 0)) < 0.01 and abs(ov[2] - (six[2] or 0)) < 0.0001
    add_qc(con, run_id, "OVERALL", "Overall equals six outputs", ov, six, ok, "terminal funnel summation")
    quick = con.execute("PRAGMA quick_check").fetchone()[0]
    add_qc(con, run_id, "OVERALL", "SQLite quick check", quick, "ok", quick == "ok", "PRAGMA quick_check")
    con.commit()
    failures = con.execute("SELECT COUNT(*) FROM reconciliation_qc WHERE run_id=? AND status='FAIL'", (run_id,)).fetchone()[0]
    if failures:
        raise RuntimeError(f"QC failed with {failures} reconciliation failure(s)")


def freeze_manifest(con: sqlite3.Connection, run_id: str, specs: list[dict[str, object]]) -> None:
    paths = {
        ROOT / "config" / "prediction_rule_registry.json",
        ROOT / "config" / "audit_sources.json",
        ROOT / "config" / "settings.py",
        ROOT / "run_pipeline.py",
        ROOT / "tools" / "build_prediction_audit.py",
        ROOT / "tools" / "batch_surgical_workflow_remap.py",
        ROOT / "tools" / "vietnam_fy2024_workflow_improvement.py",
        cfg.V0_REFERENCE_XLSX,
    }
    for spec in specs:
        paths.add(ROOT / str(spec["path"]))
        if spec.get("complete_source_path"):
            paths.add(ROOT / str(spec["complete_source_path"]))
    rows = []
    for path in sorted(paths, key=lambda p: str(p).lower()):
        kind = "source" if "data" in path.parts or "outputs" in path.parts or "reference" in path.parts else "code_or_config"
        rows.append((run_id, kind, str(path.relative_to(ROOT)), sha256_file(path), path.stat().st_size))
    con.executemany("INSERT INTO baseline_manifest (run_id,artifact_type,path,sha256,bytes) VALUES (?,?,?,?,?)", rows)
    con.commit()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", type=Path, default=ROOT / "config" / "audit_sources.json")
    ap.add_argument("--registry", type=Path, default=ROOT / "config" / "prediction_rule_registry.json")
    args = ap.parse_args()
    manifest = json.loads(args.sources.read_text(encoding="utf-8"))
    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    run_id = manifest["run_id"]
    out_dir = ROOT / "outputs" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = out_dir / "prediction_audit.sqlite"
    con = initialize_db(db_path)
    try:
        con.execute("INSERT INTO run VALUES (?,?,?,?,?,?,?,?)", (run_id, utc_now(), None, registry["registry_version"], registry["policy"], "building", os.environ.get("GIT_COMMIT", "working-tree"), "Review-only release; production routing semantics unchanged"))
        load_registry(con, registry)
        con.commit()
        master_keys = wf.build_master_keys(cfg.V0_REFERENCE_XLSX)
        for spec in manifest["outputs"]:
            print(f"[audit] ingesting {spec['output_label']}", flush=True)
            ingest_output(con, run_id, spec, master_keys)
        create_views(con)
        insert_review_samples(con, run_id, manifest["outputs"])
        build_funnel(con, run_id)
        build_removal_cube(con, run_id)
        freeze_manifest(con, run_id, manifest["outputs"])
        run_qc(con, run_id, manifest["outputs"])
        con.execute("UPDATE run SET completed_at=?, status='passed' WHERE run_id=?", (utc_now(), run_id))
        con.commit()
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        print(f"[audit] PASS: {db_path}", flush=True)
    except Exception:
        con.execute("UPDATE run SET completed_at=?, status='failed' WHERE run_id=?", (utc_now(), run_id))
        con.commit()
        raise
    finally:
        con.close()


if __name__ == "__main__":
    main()
