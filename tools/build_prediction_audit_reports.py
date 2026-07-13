#!/usr/bin/env python3
"""Build the bounded audit workbook and canonical HTML guide from SQLite authority.

This module is intentionally downstream of ``build_prediction_audit.py``.  It does
not reinterpret, promote, suppress, or otherwise change a production mapping.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "audit_sources.json"
DEFAULT_REGISTRY = ROOT / "config" / "prediction_rule_registry.json"
WORKBOOK_BUILDER = ROOT / "tools" / "build_prediction_audit_workbook.mjs"
CANONICAL_HTML = ROOT / "docs" / "Surgical_Mapping_Workflow_Guide.html"
MAX_WORKBOOK_BYTES = 100_000_000
MAX_EXCEL_DATA_ROWS = 1_048_571  # title, note and header consume four rows.


def sha256_file(path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def rows_as_dicts(connection: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(sql, tuple(params)).fetchall()]


def title_label(key: str) -> str:
    overrides = {
        "run_id": "Run ID",
        "output_file_id": "Output ID",
        "source_row_id": "Source row ID",
        "stage_id": "Stage ID",
        "rule_id": "Rule ID",
        "rule_version": "Rule version",
        "value_usd": "Value USD",
        "previous_stage_value_usd": "Previous value USD",
        "filtered_value_usd": "Filtered value USD",
        "filtered_value_pct": "Filtered value %",
        "weighted_asp": "Weighted ASP",
        "sha256": "SHA-256",
        "complete_source_sha256": "Complete source SHA-256",
        "source_sha256": "Source SHA-256",
        "qc_id": "QC ID",
        "checked_at": "Checked at",
        "reviewed_at": "Reviewed at",
        "adjudicated_at": "Adjudicated at",
    }
    return overrides.get(key, key.replace("_", " ").title())


def column_specs(keys: list[str]) -> list[dict[str, str]]:
    return [{"key": key, "label": title_label(key)} for key in keys]


def require_authoritative_run(connection: sqlite3.Connection) -> sqlite3.Row:
    connection.row_factory = sqlite3.Row
    runs = connection.execute("SELECT * FROM run").fetchall()
    if len(runs) != 1:
        raise RuntimeError(f"Expected one audit run, found {len(runs)}.")
    run = runs[0]
    if run["status"] != "passed":
        raise RuntimeError(f"Audit run status is {run['status']!r}; reports require 'passed'.")
    failures = connection.execute("SELECT COUNT(*) FROM reconciliation_qc WHERE status='FAIL'").fetchone()[0]
    if failures:
        raise RuntimeError(f"Reconciliation has {failures} FAIL result(s); report publication stopped.")
    source_count = connection.execute("SELECT COUNT(*) FROM source_file WHERE is_complete=1").fetchone()[0]
    if source_count != 6:
        raise RuntimeError(f"Expected six complete outputs, found {source_count}.")
    sample_count = connection.execute("SELECT COUNT(*) FROM review_label").fetchone()[0]
    if sample_count != 150:
        raise RuntimeError(f"Expected 150 review samples, found {sample_count}.")
    bad_sample_outputs = connection.execute(
        """SELECT output_file_id, COUNT(*) n,
                  SUM(sample_type='Targeted') targeted,
                  SUM(sample_type='Deterministic stratified random') random_n
           FROM review_label GROUP BY output_file_id
           HAVING n<>25 OR targeted<>12 OR random_n<>13"""
    ).fetchall()
    if bad_sample_outputs:
        raise RuntimeError(f"Review sample composition is invalid: {list(map(tuple, bad_sample_outputs))}")
    return run


FUNNEL_KEYS = [
    "output_file_id", "output_label", "funnel_type", "stage_id", "stage_order", "stage_label",
    "rule_version", "candidate_status", "outcome", "transaction_count", "value_usd", "volume",
    "missing_value_count", "invalid_value_count", "missing_volume_count", "invalid_volume_count",
    "weighted_asp", "previous_stage_transaction_count", "previous_stage_value_usd",
    "previous_stage_volume", "filtered_transaction_count", "filtered_value_usd", "filtered_volume",
    "filtered_value_pct",
]

REMOVAL_KEYS = [
    "output_file_id", "output_label", "reason_kind", "is_additive", "stage_id", "rule_id",
    "rule_version", "outcome", "reason", "grouping_level", "grouping_id", "manufacturer", "family",
    "product", "transaction_count", "value_usd", "volume", "missing_value_count", "invalid_value_count",
    "missing_volume_count", "invalid_volume_count", "weighted_asp", "previous_stage_transaction_count",
    "previous_stage_value_usd", "previous_stage_volume", "filtered_transaction_count",
    "filtered_value_usd", "filtered_volume", "filtered_value_pct",
]

REVIEW_KEYS = [
    "output_file_id", "output_label", "source_row_id", "sample_type", "sample_stratum", "target_category",
    "inclusion_probability", "sample_weight", "fixed_seed", "sample_rank", "evidence",
    "shadow_recommendation", "country", "fiscal_year", "detailed_product", "manufacturer", "family",
    "product", "segment", "sub_segment", "match_tier", "reference_status", "scope_flag", "qa_status",
    "output_tier", "primary_reason", "raw_value_usd", "raw_volume", "value_usd", "volume",
    "value_numeric_status", "volume_numeric_status", "surgical_relevance", "mapping_correctness",
    "corrected_manufacturer", "corrected_family", "corrected_product", "corrected_segment",
    "corrected_sub_segment", "reviewer_rationale", "reviewer", "reviewed_at", "adjudicator",
    "adjudicated_at", "disposition",
]

QC_KEYS = [
    "run_id", "output_file_id", "check_name", "observed", "expected", "value_delta", "volume_delta",
    "status", "evidence", "checked_at",
]

SOURCE_KEYS = [
    "output_file_id", "output_label", "country", "fiscal_year", "source_path", "complete_source_path",
    "source_format", "ingestion_mode", "completeness_basis", "expected_rows", "observed_rows",
    "source_sha256", "complete_source_sha256", "source_bytes", "complete_source_bytes", "is_complete",
    "transaction_count", "value_usd", "volume", "missing_value_count", "invalid_value_count",
    "missing_volume_count", "invalid_volume_count",
]


def build_payload(connection: sqlite3.Connection, run: sqlite3.Row, database_path: Path) -> dict[str, Any]:
    run_id = run["run_id"]
    removal_count = connection.execute("SELECT COUNT(*) FROM removal_cube WHERE run_id=?", (run_id,)).fetchone()[0]
    if removal_count > MAX_EXCEL_DATA_ROWS:
        raise RuntimeError(
            f"Removal Cube has {removal_count:,} rows, above the bounded Excel limit of "
            f"{MAX_EXCEL_DATA_ROWS:,}. Full detail remains in SQLite; publication stopped for redesign."
        )

    source_lineage = rows_as_dicts(
        connection,
        f"SELECT {','.join(SOURCE_KEYS)} FROM source_file WHERE run_id=? ORDER BY output_file_id",
        (run_id,),
    )
    total_rows = sum(int(row["transaction_count"] or 0) for row in source_lineage)
    sample_notes = rows_as_dicts(
        connection,
        """SELECT output_file_id, COUNT(*) sample_n,
                  SUM(sample_type='Targeted') targeted_n,
                  SUM(sample_type='Deterministic stratified random') random_n
           FROM review_label WHERE run_id=? GROUP BY output_file_id ORDER BY output_file_id""",
        (run_id,),
    )
    baseline_manifest = rows_as_dicts(
        connection,
        "SELECT run_id,artifact_type,path,sha256,bytes,transaction_count,value_usd,volume FROM baseline_manifest WHERE run_id=? ORDER BY path",
        (run_id,),
    )
    recall_summary = rows_as_dicts(
        connection,
        """SELECT output_file_id,output_label,risk_type,current_output_tier,
                  transaction_count,value_usd,volume
           FROM v_recall_risk_summary WHERE run_id=?
           ORDER BY output_file_id,risk_type,current_output_tier""",
        (run_id,),
    )
    recall_evidence = rows_as_dicts(
        connection,
        """WITH ranked AS (
             SELECT i.output_file_id,s.output_label,i.risk_type,i.current_output_tier,i.source_row_id,
                    f.detailed_product,i.evidence,i.recommendation,f.value_usd,
                    ROW_NUMBER() OVER (
                      PARTITION BY i.output_file_id,i.risk_type
                      ORDER BY COALESCE(f.value_usd,0) DESC,i.source_row_id
                    ) AS evidence_rank
             FROM recall_risk_inventory i
             JOIN row_fact f ON f.row_fact_id=i.row_fact_id
             JOIN source_file s ON s.run_id=i.run_id AND s.output_file_id=i.output_file_id
             WHERE i.run_id=?
           )
           SELECT output_file_id,output_label,risk_type,current_output_tier,source_row_id,
                  detailed_product,evidence,recommendation,value_usd
           FROM ranked WHERE evidence_rank<=50
           ORDER BY output_file_id,risk_type,evidence_rank""",
        (run_id,),
    )

    return {
        "meta": {
            "run_id": run_id,
            "registry_version": run["registry_version"],
            "fixed_seed": run["fixed_seed"],
            "policy": run["policy"],
            "sqlite_path": str(database_path.resolve()),
            "total_rows": total_rows,
        },
        "read_me_sections": [
            {
                "title": "Authority and scope",
                "rows": [
                    ["Policy", "Review-only. No production mapping, tier, routing or export is changed by these artifacts."],
                    ["SQLite authority", f"{database_path.resolve()} — complete row facts, stage states, rule hits and risk inventories."],
                    ["Population", f"Six complete outputs; {total_rows:,} physical source rows."],
                    ["Stable key", "(run_id, output_file_id, source_row_id)."],
                    ["Registry", f"Version {run['registry_version']}; fixed sampling seed {run['fixed_seed']}."],
                ],
            },
            {
                "title": "Metric definitions",
                "rows": [
                    ["Transactions", "COUNT(*) over the declared population."],
                    ["Value", "SUM of valid parsed Total_Value_USD values; missing and invalid counts are reported separately."],
                    ["Volume", "SUM of valid parsed Quantity values; missing and invalid counts are reported separately."],
                    ["Weighted ASP", "Average selling price = SUM(valid value) / SUM(valid volume); the average dollars per unit. Blank when volume is zero."],
                    ["Primary reasons", "Each row has exactly one main reason (removal or review) — safe to count and sum."],
                    ["Secondary reasons", "Extra diagnostic notes that can overlap — never sum them into a removal total."],
                    ["Precision compliance", "Deterministic rules-compliance proxy, not statistical precision. In plain terms: did the logic run correctly, not whether measurements are mathematically precise."],
                    ["Recall proxy", "Deterministic complete risk-inventory proxy, not statistical recall; human labels are required. In plain terms: we found all potential risks by rule, but none are human-verified yet."],
                ],
            },
            {
                "title": "Review sample",
                "rows": [
                    ["Composition", "Exactly 25 rows per output: 12 hand-picked targets plus 13 rows chosen by a fixed algorithm that spreads coverage evenly across data groups (same result every run)."],
                    ["Inference", "Only random rows have non-null inclusion probability and sampling weight. Purposeful targets are not population-estimation samples. In simpler terms: the 13 random rows support statistical estimates; the 12 targeted rows were hand-picked for review and cannot be used for math-based estimates."],
                    ["Reviewer fields", "Surgical relevance and mapping correctness are separate, with corrections, rationale, reviewer and adjudication fields."],
                    ["Shadow status", "Recommendations are audit hypotheses only and do not change production data."],
                    ["Per-output check", json.dumps(sample_notes, ensure_ascii=False, separators=(",", ":"))],
                ],
            },
            {
                "title": "Known source constraint",
                "rows": [
                    ["India FY2025", "Ingested from the complete uncapped CSV. The 1,048,575-data-row XLSX is explicitly rejected as Excel-limited."],
                    ["Other five outputs", "Governed legacy XLSX inputs remain below the Excel row limit; this format limitation is recorded in Source Lineage."],
                    ["Bounded workbook", "No RawData or decision-log tab. Full row detail and full recall inventories remain in SQLite."],
                ],
            },
        ],
        "funnel_columns": column_specs(FUNNEL_KEYS),
        "funnel": rows_as_dicts(
            connection,
            f"SELECT {','.join(FUNNEL_KEYS)} FROM funnel_cube WHERE run_id=? ORDER BY output_file_id,stage_order,candidate_status,outcome",
            (run_id,),
        ),
        "removal_columns": column_specs(REMOVAL_KEYS),
        "removal_cube": rows_as_dicts(
            connection,
            f"SELECT {','.join(REMOVAL_KEYS)} FROM removal_cube WHERE run_id=? ORDER BY output_file_id,reason_kind,stage_id,rule_id,grouping_level,grouping_id,outcome,reason",
            (run_id,),
        ),
        "review_columns": column_specs(REVIEW_KEYS),
        "review_samples": rows_as_dicts(
            connection,
            f"SELECT {','.join(REVIEW_KEYS)} FROM v_review_samples WHERE run_id=? ORDER BY output_file_id,sample_type,sample_rank,source_row_id",
            (run_id,),
        ),
        "recall_summary": recall_summary,
        "recall_evidence_columns": column_specs([
            "output_file_id", "output_label", "risk_type", "current_output_tier", "source_row_id",
            "detailed_product", "evidence", "recommendation", "value_usd",
        ]),
        "recall_evidence": recall_evidence,
        "qc_columns": column_specs(QC_KEYS),
        "reconciliation_qc": rows_as_dicts(
            connection,
            f"SELECT {','.join(QC_KEYS)} FROM reconciliation_qc WHERE run_id=? ORDER BY output_file_id,qc_id",
            (run_id,),
        ),
        "source_columns": column_specs(SOURCE_KEYS),
        "source_lineage": source_lineage,
        "baseline_columns": column_specs(["run_id", "artifact_type", "path", "sha256", "bytes", "transaction_count", "value_usd", "volume"]),
        "baseline_manifest": baseline_manifest,
    }


def find_bundled_runtime() -> tuple[Path, Path]:
    configured_node = os.environ.get("CODEX_NODE")
    configured_modules = os.environ.get("CODEX_NODE_MODULES")
    if configured_node and configured_modules:
        return Path(configured_node), Path(configured_modules)
    runtime = Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "node"
    node = runtime / "bin" / ("node.exe" if os.name == "nt" else "node")
    modules = runtime / "node_modules"
    if not node.exists() or not modules.exists():
        raise RuntimeError("Bundled Codex Node runtime or node_modules directory was not found.")
    return node, modules


def build_workbook(payload: dict[str, Any], output_path: Path) -> Path:
    """Build the seven-sheet governed workbook.

    Uses the pure-Python openpyxl builder (`_prediction_audit_workbook`), which has no
    external runtime dependency. The previous bundled node/Excel artifact-tool aborted
    (V8, exit 134) on some machines; the openpyxl path produces the same seven sheets in
    the same order and handles the atomic replace + size ceiling itself.
    """
    from _prediction_audit_workbook import build_workbook_xlsx

    output_path.parent.mkdir(parents=True, exist_ok=True)
    build_workbook_xlsx(payload, output_path)
    return output_path


def e(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def fmt_int(value: Any) -> str:
    return f"{int(value or 0):,}"


def fmt_money(value: Any) -> str:
    return "—" if value is None else f"${float(value):,.2f}"


def fmt_num(value: Any) -> str:
    return "—" if value is None else f"{float(value):,.6f}".rstrip("0").rstrip(".")


def stage_html(stage: dict[str, Any], rules: list[dict[str, Any]], status_counts: list[dict[str, Any]]) -> str:
    rule_blocks = []
    for rule in rules:
        rule_blocks.append(
            f"""<div class="rule">
              <div class="rule-head"><code>{e(rule['rule_id'])}</code><span>v{e(rule['version'])}</span></div>
              <p><strong>Input.</strong> {e(rule['input_population'])}</p>
              <p><strong>Predicate.</strong> <code>{e(rule['predicate_expression'])}</code></p>
              <p><strong>Outcome.</strong> {e(rule['outcome_expression'])}</p>
              <p><strong>Reason precedence.</strong> {e(' → '.join(rule['reason_precedence']))}</p>
            </div>"""
        )
    chips = "".join(
        f"<span class=\"chip\">{e(row['candidate_status'])} · {e(row['outcome'])}: {fmt_int(row['transaction_count'])}</span>"
        for row in status_counts
    ) or '<span class="chip">No applicable row state</span>'
    return f"""<article class="stage" id="{e(stage['stage_id'])}">
      <div class="stage-meta"><span class="stage-type {e(stage['stage_type'])}">{e(stage['stage_type'])}</span><span>Order {stage['execution_order']} · v{e(stage['version'])}</span></div>
      <h3>{e(stage['stage_id'])} · {e(stage['documentation_label'])}</h3>
      <p><strong>Population.</strong> {e(stage['input_population'])}</p>
      <p><strong>Stage logic.</strong> {e(stage['predicate_description'])}</p>
      <p><strong>Outcomes.</strong> {e(', '.join(stage['outcomes']))}</p>
      <div class="chips">{chips}</div>
      {''.join(rule_blocks)}
    </article>"""


def build_html(
    connection: sqlite3.Connection,
    run: sqlite3.Row,
    registry: dict[str, Any],
    database_path: Path,
    workbook_path: Path,
    html_path: Path,
) -> None:
    run_id = run["run_id"]
    sources = rows_as_dicts(connection, "SELECT * FROM source_file WHERE run_id=? ORDER BY output_file_id", (run_id,))
    tiers = rows_as_dicts(
        connection,
        """SELECT output_file_id,output_tier,COUNT(*) transaction_count,SUM(value_usd) value_usd,SUM(volume) volume
           FROM row_fact WHERE run_id=? GROUP BY output_file_id,output_tier ORDER BY output_file_id,output_tier""",
        (run_id,),
    )
    risks = rows_as_dicts(
        connection,
        """SELECT risk_type,current_output_tier,COUNT(*) transaction_count,SUM(f.value_usd) value_usd
           FROM recall_risk_inventory i JOIN row_fact f ON f.row_fact_id=i.row_fact_id
           WHERE i.run_id=? GROUP BY risk_type,current_output_tier ORDER BY risk_type,current_output_tier""",
        (run_id,),
    )
    stage_counts = rows_as_dicts(
        connection,
        """SELECT stage_id,candidate_status,outcome,COUNT(*) transaction_count
           FROM row_stage_state WHERE run_id=? GROUP BY stage_id,candidate_status,outcome
           ORDER BY stage_id,candidate_status,outcome""",
        (run_id,),
    )
    qc = rows_as_dicts(
        connection,
        "SELECT status,COUNT(*) n FROM reconciliation_qc WHERE run_id=? GROUP BY status ORDER BY status",
        (run_id,),
    )
    rules_by_stage: dict[str, list[dict[str, Any]]] = {}
    for rule in registry["rules"]:
        rules_by_stage.setdefault(rule["stage_id"], []).append(rule)
    counts_by_stage: dict[str, list[dict[str, Any]]] = {}
    for row in stage_counts:
        counts_by_stage.setdefault(row["stage_id"], []).append(row)

    total_rows = sum(int(source["transaction_count"] or 0) for source in sources)
    total_value = sum(float(source["value_usd"] or 0) for source in sources)
    total_volume = sum(float(source["volume"] or 0) for source in sources)
    if any(source["ingestion_mode"] == "complete_partitioned_excel_current_remap" for source in sources):
        source_lineage_note = (
            "All six declared populations passed independent physical-row checks. "
            "Oversized final Excel output is split across ordered RawData sheets so every row remains available; "
            "India FY2025 is also reconciled to its immutable complete CSV source."
        )
    else:
        source_lineage_note = (
            "All six declared populations passed independent physical-row checks. India FY2025 uses the complete "
            "uncapped CSV because the legacy single-sheet workbook is Excel-limited; the other governed sources "
            "remain below the single-sheet cap."
        )
    source_rows = "".join(
        f"""<tr><td>{e(s['output_label'])}</td><td>{e(s['country'])}</td><td>{e(s['fiscal_year'])}</td>
        <td class=num>{fmt_int(s['transaction_count'])}</td><td class=num>{fmt_money(s['value_usd'])}</td>
        <td class=num>{fmt_num(s['volume'])}</td><td>{e(s['ingestion_mode'])}</td>
        <td><span class="status pass">complete</span></td></tr>"""
        for s in sources
    )
    tier_rows = "".join(
        f"<tr><td>{e(r['output_file_id'])}</td><td>{e(r['output_tier'])}</td><td class=num>{fmt_int(r['transaction_count'])}</td><td class=num>{fmt_money(r['value_usd'])}</td><td class=num>{fmt_num(r['volume'])}</td></tr>"
        for r in tiers
    )
    risk_rows = "".join(
        f"<tr><td>{e(r['risk_type'])}</td><td>{e(r['current_output_tier'])}</td><td class=num>{fmt_int(r['transaction_count'])}</td><td class=num>{fmt_money(r['value_usd'])}</td></tr>"
        for r in risks
    ) or '<tr><td colspan="4">No risk records.</td></tr>'
    stages = "".join(
        stage_html(stage, rules_by_stage.get(stage["stage_id"], []), counts_by_stage.get(stage["stage_id"], []))
        for stage in sorted(registry["stages"], key=lambda item: item["execution_order"])
    )
    nav_links = "".join(f'<a href="#{e(s["stage_id"])}">{e(s["stage_id"].split("_")[0])}</a>' for s in registry["stages"])
    qc_summary = ", ".join(f"{row['status']}: {row['n']}" for row in qc)
    workbook_rel = os.path.relpath(workbook_path, html_path.parent).replace(os.sep, "/")
    database_rel = os.path.relpath(database_path, html_path.parent).replace(os.sep, "/")

    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Surgical Mapping Workflow Guide · {e(run_id)}</title>
<style>
:root{{--ink:#0e0e0e;--blue:#0047ab;--muted:#777;--paper:#f5f7fa;--line:#d8dee8;--white:#fff;--pale:#eaf1fb;--green:#147a42;--amber:#9a5b00}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 Arial,Helvetica,sans-serif}}
a{{color:var(--blue)}}.hero{{background:var(--ink);color:#fff;padding:54px max(24px,calc((100vw - 1180px)/2)) 44px}}.eyebrow{{text-transform:uppercase;letter-spacing:.14em;color:#94bfff;font-weight:700;font-size:12px}}
h1{{font-size:clamp(32px,5vw,58px);line-height:1.04;max-width:850px;margin:12px 0 18px}}.dek{{font-size:19px;color:#d9dde4;max-width:840px}}
.metrics{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:30px}}.metric{{padding:18px;border:1px solid #333;background:#181818}}.metric b{{font-size:25px;display:block}}.metric span{{color:#aaa}}
nav{{position:sticky;top:0;z-index:3;background:#fff;border-bottom:1px solid var(--line);display:flex;gap:6px;overflow:auto;padding:10px max(16px,calc((100vw - 1180px)/2))}}nav a{{white-space:nowrap;text-decoration:none;padding:7px 9px;border-radius:4px;font-size:12px;font-weight:700}}
main{{max-width:1180px;margin:0 auto;padding:32px 22px 70px}}section{{margin:0 0 46px}}h2{{font-size:29px;margin:0 0 8px}}h3{{font-size:20px;margin:9px 0}}.lead{{color:#555;max-width:850px}}
.notice{{border-left:5px solid var(--blue);background:#fff;padding:18px 20px;margin:18px 0;box-shadow:0 4px 18px #0e0e0e0d}}.notice.warning{{border-color:#d38700}}.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}}
.card,.stage{{background:#fff;border:1px solid var(--line);padding:22px;box-shadow:0 5px 20px #0e0e0e0a}}.stage{{margin:16px 0;scroll-margin-top:70px}}.stage-meta,.rule-head{{display:flex;justify-content:space-between;gap:12px;color:var(--muted);font-size:12px}}.stage-type{{text-transform:uppercase;letter-spacing:.08em;font-weight:700;color:var(--blue)}}
.stage-type.terminal{{color:var(--green)}}.stage-type.presentation{{color:var(--amber)}}.rule{{border-top:1px solid var(--line);margin-top:16px;padding-top:14px}}code{{font:12px/1.5 Consolas,monospace;background:#f1f3f6;padding:2px 5px;word-break:break-word}}
.chips{{display:flex;flex-wrap:wrap;gap:6px;margin-top:13px}}.chip{{font-size:11px;background:var(--pale);color:#153962;padding:5px 8px;border-radius:99px}}
.table-wrap{{overflow:auto;background:#fff;border:1px solid var(--line)}}table{{border-collapse:collapse;width:100%;min-width:760px}}th,td{{padding:10px 12px;border-bottom:1px solid var(--line);text-align:left}}th{{background:var(--blue);color:#fff;position:sticky;top:0}}td.num{{text-align:right;font-variant-numeric:tabular-nums}}.status{{font-size:11px;font-weight:700;text-transform:uppercase}}.pass{{color:var(--green)}}
.flow{{display:grid;grid-template-columns:1fr auto 1fr auto 1fr;align-items:stretch;gap:10px;margin:18px 0}}.flow div{{background:#fff;border:1px solid var(--line);padding:17px}}.arrow{{align-self:center;color:var(--blue);font-size:24px}}
footer{{background:#fff;border-top:1px solid var(--line);padding:24px;text-align:center;color:var(--muted)}}
@media(max-width:760px){{.metrics,.grid{{grid-template-columns:1fr}}.flow{{grid-template-columns:1fr}}.arrow{{transform:rotate(90deg);justify-self:center}}main{{padding-inline:16px}}}}
</style></head><body>
<header class="hero"><div class="eyebrow">Review-only prediction audit · registry {e(run['registry_version'])}</div>
<h1>Surgical mapping workflow, reconstructed and measured</h1>
<p class="dek">A self-readable guide to candidate logic, terminal routing, recall-risk inventories, review sampling, reconciliation, and source lineage. It reports the current production semantics without changing them.</p>
<div class="metrics"><div class="metric"><b>{fmt_int(total_rows)}</b><span>complete source rows</span></div><div class="metric"><b>{fmt_money(total_value)}</b><span>valid parsed value</span></div><div class="metric"><b>{fmt_num(total_volume)}</b><span>valid parsed volume</span></div></div></header>
<nav><a href="#overview">Overview</a><a href="#sources">Sources</a><a href="#routing">Routing</a><a href="#recall">Recall risks</a><a href="#review">Review</a>{nav_links}</nav>
<main>
<section id="overview"><h2>What is authoritative</h2><p class="lead">Run <code>{e(run_id)}</code> is governed by a versioned registry and fixed seed. SQLite holds the complete row-level data; the workbook and this page show summaries and samples generated from it.</p>
<div class="grid"><div class="card"><h3>Row identity</h3><p><code>(run_id, output_file_id, source_row_id)</code> is stable and unique. Raw numeric strings, parsed values and explicit valid/missing/invalid statuses are retained.</p></div><div class="card"><h3>Reconciliation</h3><p>{e(qc_summary)}. Value tolerance is $0.01 and volume tolerance is 0.000001. Publication fails closed on any FAIL.</p></div></div>
<div class="notice"><strong>Metrics.</strong> Transaction count is <code>COUNT(*)</code>. Value and volume sum valid parsed observations; missing and invalid counts remain visible. Weighted ASP (average selling price) is the average dollars per unit — valid value divided by valid volume — and is blank when volume is zero.</div>
<p><a href="{e(database_rel)}">Open SQLite authority</a> · <a href="{e(workbook_rel)}">Open bounded review workbook</a></p></section>
<section id="sources"><h2>Complete-source lineage</h2><p class="lead">{e(source_lineage_note)}</p><div class="table-wrap"><table><thead><tr><th>Output</th><th>Country</th><th>FY</th><th>Rows</th><th>Value</th><th>Volume</th><th>Ingestion</th><th>Status</th></tr></thead><tbody>{source_rows}</tbody></table></div></section>
<section id="routing"><h2>How data flows through the steps</h2><p class="lead">Each record is checked by the candidate steps (S01–S12), then given one final status at the terminal step (S13: Trusted, Review or Excluded), and finally exported (S14). Candidate states are diagnostic and not terminal routes.</p><div class="flow"><div><strong>S01–S12 · candidate</strong><br>Eligible, hit, suppressed, missed, recovered or released states remain observable and can continue.</div><span class="arrow">→</span><div><strong>S13 · terminal</strong><br>Every extracted row receives exactly one current route: Trusted, Review or Excluded.</div><span class="arrow">→</span><div><strong>S14 · presentation</strong><br>Aggregates and the governed sample are exported; complete detail remains in SQLite.</div></div><div class="table-wrap"><table><thead><tr><th>Output</th><th>Terminal tier</th><th>Transactions</th><th>Value</th><th>Volume</th></tr></thead><tbody>{tier_rows}</tbody></table></div></section>
<section id="recall"><h2>Recall-risk inventories</h2><p class="lead">These are complete deterministic inventories, not statistical recall estimates. Human labels are required before estimating statistical recall.</p><div class="notice warning"><strong>MRI separation.</strong> We track three separate things: (1) the label says MRI-safe, (2) the item actually conflicts with imaging systems, and (3) it is a surgical device used around imaging. So “MRI-compatible / conditional / safe” language is inventoried separately from actual imaging equipment and from perioperative surgical-device evidence. The later S12 guard never promotes a row in this release.</div><p>Pakistan nonstandard manufacturer and HS-prior tiers — records with unusual formatting, or matched only via an older HS-code prior — remain reviewable and are never relabeled Trusted by this audit. MRI and nonstandard recommendations are shadow-only.</p><div class="table-wrap"><table><thead><tr><th>Risk type</th><th>Current tier</th><th>Transactions</th><th>Value</th></tr></thead><tbody>{risk_rows}</tbody></table></div></section>
<section id="review"><h2>Reviewer-ready sample</h2><div class="grid"><div class="card"><h3>Exact design</h3><p>25 rows per output: 12 hand-picked target rows plus 13 rows chosen by a fixed algorithm for even coverage across data groups (a deterministic stratified-random sample), for 150 total. The seed is <code>{e(run['fixed_seed'])}</code>.</p></div><div class="card"><h3>Responsible inference</h3><p>Random rows carry inclusion probability and sampling weight. Purposeful targets do not support weighted population estimates. Surgical relevance and mapping correctness are labeled separately.</p></div></div><p><strong>Precision compliance</strong> means the logic ran correctly (deterministic rules compliance), not statistical precision. <strong>Recall proxy</strong> means we listed every potential risk by rule (complete deterministic risk coverage), not statistical recall — human labels are still needed.</p></section>
<section id="logic"><h2>Versioned stage and rule registry</h2><p class="lead">All S00–S14 stages are shown in execution order. Predicates and outcomes below are generated from the same registry loaded into SQLite.</p>{stages}</section>
</main><footer>Generated from registry {e(run['registry_version'])} and SQLite run {e(run_id)}. Review-only; no production mapping changed.</footer>
</body></html>"""
    html_path.parent.mkdir(parents=True, exist_ok=True)
    building = html_path.with_suffix(html_path.suffix + ".building")
    building.write_text(document, encoding="utf-8")
    os.replace(building, html_path)


def record_artifacts(connection: sqlite3.Connection, run_id: str, artifacts: list[tuple[str, Path]]) -> None:
    generated_at = connection.execute("SELECT completed_at FROM run WHERE run_id=?", (run_id,)).fetchone()[0]
    for artifact_type, artifact_path in artifacts:
        relative = artifact_path.resolve().relative_to(ROOT.resolve()).as_posix()
        connection.execute(
            """INSERT INTO artifact_manifest(run_id,artifact_type,path,sha256,bytes,generated_at)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(run_id,path) DO UPDATE SET
                 artifact_type=excluded.artifact_type,sha256=excluded.sha256,
                 bytes=excluded.bytes,generated_at=excluded.generated_at""",
            (run_id, artifact_type, relative, sha256_file(artifact_path), artifact_path.stat().st_size, generated_at),
        )
    connection.commit()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--db", type=Path)
    parser.add_argument("--workbook", type=Path)
    parser.add_argument("--html", type=Path, default=CANONICAL_HTML)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    run_id = config["run_id"]
    database_path = (args.db or ROOT / "outputs" / run_id / "prediction_audit.sqlite").resolve()
    workbook_path = (args.workbook or ROOT / "outputs" / run_id / "Prediction_Funnel_and_Review.xlsx").resolve()
    html_path = args.html.resolve()
    if not database_path.exists():
        raise FileNotFoundError(database_path)

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        run = require_authoritative_run(connection)
        if run["run_id"] != run_id:
            raise RuntimeError(f"Config run {run_id} does not match database run {run['run_id']}.")
        if registry["registry_version"] != run["registry_version"]:
            raise RuntimeError("Registry version does not match the SQLite authority.")
        payload = build_payload(connection, run, database_path)
        preview_dir = build_workbook(payload, workbook_path)
        build_html(connection, run, registry, database_path, workbook_path, html_path)
        record_artifacts(connection, run_id, [("workbook", workbook_path), ("html", html_path)])
    finally:
        connection.close()

    print(json.dumps({
        "run_id": run_id,
        "database": str(database_path),
        "workbook": str(workbook_path),
        "workbook_bytes": workbook_path.stat().st_size,
        "html": str(html_path),
        "preview_dir": str(preview_dir),
    }, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
