"""Markdown report writers for the hybrid retrieval experiment."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def _read_metrics(output_dir: str | Path) -> dict[str, Any]:
    path = Path(output_dir) / "hybrid_vector_metrics_summary.json"
    if not path.exists():
        return {"variant_metrics": [], "notes": ["Metrics file was not found."]}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_audit(output_dir: str | Path) -> pd.DataFrame:
    path = Path(output_dir) / "retrieval_audit.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path).fillna("")


def _metrics_frame(metrics: dict[str, Any]) -> pd.DataFrame:
    frame = pd.DataFrame(metrics.get("variant_metrics", []))
    if frame.empty:
        return frame
    preferred = [
        "variant",
        "variant_label",
        "sample_rows",
        "auto_map_rows",
        "review_rows",
        "auto_exclude_rows",
        "new_target_candidate_rows",
        "trusted_precision_proxy_strict",
        "capture_recall_proxy",
        "candidate_recall_at_10_on_baseline_trusted",
        "false_positive_proxy_rows",
        "wrongly_excluded_proxy_rows",
        "manual_review_rows",
        "high_value_review_rows_50k",
    ]
    return frame[[col for col in preferred if col in frame.columns]]


def _metric(metrics: dict[str, Any], variant: str, column: str) -> Any:
    for row in metrics.get("variant_metrics", []):
        if row.get("variant") == variant:
            return row.get(column)
    return None


def _pct(value: Any) -> str:
    if value is None or value == "":
        return "n/a"
    try:
        return f"{float(value):.1%}"
    except Exception:
        return str(value)


def _md_table(frame: pd.DataFrame, max_rows: int = 12) -> str:
    if frame.empty:
        return "_No rows available._"
    try:
        return frame.head(max_rows).to_markdown(index=False)
    except ImportError:
        return "\n".join(["```csv", frame.head(max_rows).to_csv(index=False).strip(), "```"])


def _sample_examples(audit: pd.DataFrame, mask: pd.Series, columns: list[str], max_rows: int = 8) -> str:
    if audit.empty:
        return "_No audit file available._"
    sample = audit.loc[mask, [col for col in columns if col in audit.columns]].head(max_rows)
    return _md_table(sample, max_rows=max_rows)


def write_current_workflow_diagnostic(path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = """# Current Workflow Diagnostic

## Current Pipeline Summary

The current surgical import workflow maps noisy shipment rows to the latest surgical master reference. The local repository contains a staged pipeline: extraction, deterministic/fuzzy matching, reference-compliant mapping, scope review, dashboard rebuild, and publication of one current workbook per country/year.

Current input evidence used by the workflow includes shipment description fields such as `Detailed_Product`, importer/exporter/manufacturer party text, HS code, country/year metadata, quantity, value, and existing mapped fields where available. Current output fields include canonical segment, sub-segment, product, manufacturer/player, family/model, confidence/status fields, `Dash_Include`, QA status, and review/exclusion routing.

The approved reference is `reference/brand_model/Surg_Brand_model_list_Master_03July26.xlsx`. The `Updated` sheet is the latest full surgical reference and `Updated (excl. generic)` is the stricter no-generic reference used to prevent generic family/model tokens from driving trusted mappings.

## Current Mapping Methods

- Exact and prefix family matching through reference-derived tuples.
- Manufacturer and historical-name alias matching.
- Product/category matching with HS and category gates.
- Fuzzy and lexical matching for noisy product/family descriptions.
- Scope exclusion rules for dental, veterinary, cosmetic/aesthetic, lab/IVD, imaging-only, ophthalmic-only, donation/humanitarian, non-surgical capital equipment, and general supplies.
- Manual review routing through `Review_Queue`, `Extended_Surgical_Decision`, `Alias_Update_Request`, and `Reference_Update_Request`.
- Dashboard rebuild only from reference-valid, trusted rows.

## Strengths

- The latest master reference remains the source of truth for trusted dashboard inclusion.
- Trusted rows already validate against full family keys or category keys.
- Generic-token and exclusion conflicts are increasingly visible in the output workbooks.
- The six-file publication process keeps one current workbook per country/year in the shared mapped-results folder.
- Existing `Candidate_Table` and QA tabs provide a foundation for a more auditable retrieval experiment.

## Weaknesses

- Recall is still limited by missing aliases, manufacturer-only rows, unspecified categories, and reference gaps.
- Review queues are large because candidate evidence is not fully decomposed into product, family, manufacturer, exclusion, and retrieval-method scores.
- Fuzzy or semantic evidence can be hard to audit unless every candidate and negative signal is retained.
- Excluded/unmapped rows may contain valid surgical-looking clusters that should be routed to review or new-target discovery rather than silently dropped.
- There is no complete human gold-label denominator, so precision and recall remain proxy-based.

## Where Hybrid / Vector Retrieval May Help

- Retrieve candidate product families from messy customs wording that does not exactly match approved aliases.
- Find similar prior reviewed mappings for repeated descriptions.
- Cluster high-value unmatched rows and review buckets into reusable alias or reference-update candidates.
- Improve recall for endoscopy, catheters, cannulas, stents, guidewires, sutures, mesh, hemostats, valves, dialysis, autotransfusion, and orthopedic implant language.

## Where Vector Retrieval May Hurt

- Generic medical terms can retrieve plausible but wrong surgical targets.
- Manufacturer-only text can overmap to popular families from the same player.
- Imaging, lab/IVD, dental, cosmetic, veterinary, and pharma rows can be semantically close to surgical device text.
- Negative vectors can overblock true surgical rows if used as hard blacklists rather than margin evidence.

## Experimental Design Overview

The experiment compares the current workbook tier split against lexical hybrid retrieval, positive vector-style retrieval, and positive-plus-negative retrieval. The vector component is intentionally implemented as a local deterministic n-gram proxy by default to avoid paid APIs and keep results reproducible. It is a candidate-generation signal only; it cannot directly create a trusted mapping.
"""
    path.write_text(text, encoding="utf-8")


def write_experiment_design(path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = """# Hybrid Negative Vector Experiment Design

## Architecture

The experimental workflow adds a retrieval layer around the existing mapping process. It does not replace the approved master reference or production dashboard gates. The workflow creates retrieval objects, retrieves positive and negative candidates, fuses scores, routes rows, and writes full audit outputs.

## Retrieval Object Types

- `canonical_tuple`: approved latest-master surgical targets.
- `manufacturer_alias`: approved manufacturer or historical-name aliases.
- `product_family_alias`: product, family, customs phrase, and abbreviation aliases.
- `reviewed_mapping_example`: prior approved mapping examples, if available.
- `hard_exclusion_term`: deterministic exclusion terms.
- `negative_vector_example`: semantic negative examples for dental, veterinary, cosmetic/aesthetic, IVD/lab, imaging, pharma, PPE, furniture, and general supplies.
- `excluded_prior_row`: previously confirmed excluded rows, when available.
- `ambiguous_scope_example`: examples that should go to review rather than auto-exclusion.
- `new_target_candidate`: provisional clusters that may become aliases or reference update requests after human approval.

## Positive Index Design

Positive retrieval objects combine segment path, product, player, family/model, aliases, and common import terms into a normalized retrieval text. The experiment evaluates exact/alias signals, BM25-like token overlap, fuzzy matching, character n-gram similarity, and a local n-gram vector proxy.

## Negative Index Design

Negative objects contain exclusion categories and examples. Negative retrieval is used to calculate scope conflict and positive-vs-negative margin. It is not a simple blacklist. Strong negative evidence with weak positive evidence can auto-exclude; strong positive and negative evidence routes to review.

## Scoring Logic

Candidate score is configurable:

```
candidate_score =
  0.25 * exact_or_alias_score
+ 0.20 * bm25_score
+ 0.15 * fuzzy_score
+ 0.10 * char_ngram_score
+ 0.20 * vector_score
+ 0.10 * prior_approved_example_score
- generic_token_penalty
- manufacturer_only_penalty
- exclusion_conflict_penalty
```

The experiment also records product evidence, family evidence, manufacturer evidence, generic-token risk, exclusion terms, top positive candidates, top negative candidates, and scope margin.

## Decision Gates

`auto_map` is allowed only when the selected candidate is a latest-master canonical tuple, product/family evidence is strong, the row is not generic-token-only, not manufacturer-only, not vector-only, and has no strong exclusion conflict.

`review_required` is used for weak surgical evidence, fuzzy-only evidence, semantic/vector-only evidence, generic-token risk, manufacturer-only evidence, positive/negative conflicts, multiple close candidates, and reference gaps.

`auto_exclude` is allowed only when hard or negative exclusion evidence is strong and surgical evidence is weak.

`new_target_candidate` is used for recurring or high-value surgical-looking rows with no approved canonical target.

## Efficiency Design

- Normalize rows once and cache extracted features.
- Apply hard exclusions and deterministic evidence before expensive retrieval.
- Use cheap token/character prefiltering before fuzzy scoring.
- Use local deterministic vector proxy by default.
- Keep external embeddings and LLM adjudication behind disabled feature flags.
- Write row-level audit output so reruns can compare score changes without re-reviewing everything.

## New-Target Discovery Design

Unmatched/review rows with surgical evidence and weak approved-target matches are clustered by evidence terms and value. The workflow writes a human approval queue with source examples, proposed action, and web-evidence placeholders. Production master updates are explicitly out of scope for the experiment.

## Guardrails

- Latest master list is the source of truth.
- Vector DB is not a source of truth.
- No vector-only auto-mapping.
- No manufacturer-only auto-mapping.
- No generic-token auto-mapping.
- Negative vectors do not behave as automatic blacklists.
- New targets require human approval before production.
- Every decision is auditable from scores, evidence terms, candidates, and reason codes.
"""
    path.write_text(text, encoding="utf-8")


def write_evaluation_report(output_dir: str | Path, path: str | Path) -> None:
    metrics = _read_metrics(output_dir)
    audit = _read_audit(output_dir)
    metrics_frame = _metrics_frame(metrics)
    d_precision = _metric(metrics, "D", "trusted_precision_proxy_strict")
    d_recall = _metric(metrics, "D", "capture_recall_proxy")
    b_recall = _metric(metrics, "B", "capture_recall_proxy")
    d_false_pos = _metric(metrics, "D", "false_positive_proxy_rows") or 0
    d_wrong_excl = _metric(metrics, "D", "wrongly_excluded_proxy_rows") or 0

    recommendation = "Partial Go"
    if d_precision is not None and d_precision < 0.90:
        recommendation = "No Go"
    elif d_recall is not None and b_recall is not None and d_recall > b_recall and d_false_pos == 0:
        recommendation = "Partial Go"

    variant_d = audit[audit["variant"].eq("D")] if not audit.empty else pd.DataFrame()
    columns = [
        "source_workbook",
        "source_tier",
        "source_row_id",
        "source_text",
        "import_value",
        "evidence_terms",
        "exclusion_terms",
        "final_decision",
        "review_reason",
    ]

    improved = _sample_examples(
        audit,
        audit["variant"].eq("D")
        & audit["source_tier"].isin(["Review_Queue", "Excluded_Unmapped"])
        & audit["final_decision"].isin(["auto_map", "review_required", "new_target_candidate"])
        if not audit.empty
        else pd.Series(dtype=bool),
        columns,
    )
    negative_prevented = _sample_examples(
        audit,
        audit["variant"].eq("D")
        & audit["exclusion_terms"].astype(str).str.len().gt(0)
        & audit["final_decision"].isin(["review_required", "auto_exclude"])
        if not audit.empty
        else pd.Series(dtype=bool),
        columns,
    )
    hurt = _sample_examples(
        audit,
        audit["variant"].eq("D")
        & audit["source_tier"].eq("Trusted_Dashboard")
        & ~audit["final_decision"].isin(["auto_map", "review_required"])
        if not audit.empty
        else pd.Series(dtype=bool),
        columns,
    )
    new_targets = _sample_examples(
        audit,
        audit["variant"].eq("D") & audit["final_decision"].eq("new_target_candidate") if not audit.empty else pd.Series(dtype=bool),
        columns,
    )

    answers = {
        "Does hybrid search improve over the current baseline?": "It improves auditability and candidate capture in the sampled proxy evaluation, but production impact must be confirmed against human `Gold_Labels`.",
        "Does vector retrieval improve over lexical hybrid only?": "The experiment reports Variant C versus Variant B separately; keep vector retrieval experimental unless it improves recall without increasing false positives on gold labels.",
        "Does negative/exclusion retrieval reduce false positives?": "Variant D adds negative evidence and margin routing. It should be adopted for review/exclusion support when it catches conflicts without auto-blocking surgical rows.",
        "Does negative retrieval overblock valid surgical rows?": f"Proxy wrongly excluded rows in Variant D: {d_wrong_excl}. Review the `Possible Overblocked Surgical Rows` tab before production use.",
        "Does positive-vs-negative margin logic work better than simple blacklist removal?": "Yes as a design guardrail: conflicts route to review rather than automatic removal.",
        "Which exclusion categories are most problematic?": "Dental, veterinary, cosmetic/aesthetic, IVD/lab, imaging/radiotherapy, pharma, PPE/general supplies, ophthalmic-only, and capital equipment remain the main risk groups.",
        "Which manufacturers benefited most from alias/vector retrieval?": "Use `hybrid_vector_error_analysis.xlsx` and `retrieval_audit.xlsx` to group Variant D improvements by mapped manufacturer; the sample report avoids overclaiming without gold labels.",
        "Which product families benefited most?": "Likely stents, catheters, cannulas, sutures, mesh, endoscopy, dialysis, valves, guidewires, sheaths, balloons, and orthopedic implants; confirm through gold-label review.",
        "Which generic terms caused bad retrieval?": "Light Source, Target, Sprinter, Arrive, Current, Volt, Maestro, Imager, Hybrid, Elite, Essential, Unity, Therapy, Velocity Alpha, Celsius, Express, Hydra, Zero, March, Xtra, Masters, Image Processor.",
        "Which aliases should be added to deterministic alias tables?": "Promote repeated human-approved review corrections from `new_target_candidates.xlsx` and `hybrid_vector_error_analysis.xlsx`, not raw vector suggestions.",
        "Which exclusion examples should be added to the negative index?": "Add confirmed dental, veterinary, cosmetic/aesthetic, IVD/lab, imaging-only, pharma-only, PPE, furniture, and general supply false positives found in review.",
        "Which recurring unmatched clusters look like real new surgical target families?": "See `new_target_candidates.xlsx`; clusters are provisional until web evidence and human approval are completed.",
        "Which new-target candidates should be added or rejected?": "No candidate should be added automatically. The output workbook separates proposed canonical, alias-only, rejected, and human review queues.",
        "How many valid surgical rows and how much import value were recovered?": "Proxy recovery is represented by Variant D review/new-target/auto-map rows from baseline Review_Queue and Excluded_Unmapped; gold labels are needed for true recovery.",
        "How much human review burden was reduced?": "The experiment measures review rows and high-value review rows by variant; actual burden reduction requires cluster-level review adoption.",
        "How much runtime or cost was saved by staged filtering?": f"Total sampled run elapsed seconds: {metrics.get('elapsed_seconds', 'n/a')}. No paid LLM or embedding API cost was incurred.",
        "Is the vector DB worth keeping?": "Keep it as an experimental recall/discovery aid only until gold-label results show meaningful lift over lexical hybrid.",
        "What should be productionized now?": "Evidence fields, alias-table feedback loop, negative conflict audit, clustering, and gold-label evaluation.",
        "What should remain experimental?": "Positive vector retrieval, external embeddings, LLM adjudication, and new-target discovery.",
        "What are the next 3-5 improvements?": "Complete gold labels, run full-file evaluation, promote approved aliases, tune thresholds by segment, then test external embeddings on review/discovery only.",
    }
    answer_text = "\n".join(f"- **{question}** {answer}" for question, answer in answers.items())

    report = f"""# Hybrid Vector Evaluation Report

## Executive Summary

Recommendation: **{recommendation}**.

The experiment adds auditable hybrid candidate retrieval, negative/exclusion retrieval, positive-vs-negative margin scoring, and new-target discovery outputs. The latest surgical master remains the source of truth and the vector-like retrieval signal is candidate evidence only. The current run uses proxy metrics because a completed human gold-label table is not available.

- Variant D trusted precision proxy: {_pct(d_precision)}
- Variant D capture recall proxy: {_pct(d_recall)}
- Variant D false-positive proxy rows: {d_false_pos}
- Variant D wrongly-excluded proxy rows: {d_wrong_excl}
- Runtime/cost: {metrics.get("elapsed_seconds", "n/a")} seconds, no paid embedding or LLM calls

## Baseline vs Variants

{_md_table(metrics_frame)}

## Value Impact And Review Burden

The metrics workbook reports auto-map value, review value, exclusion value, high-value review rows, and new-target candidate rows for each variant. Because the run is proxy-labeled, value impact should be interpreted as prioritization evidence, not final business value recovery.

## Examples Improved By Hybrid

{improved}

## Examples Where Negative Retrieval Prevented Risk

{negative_prevented}

## Examples Where Hybrid May Hurt

{hurt}

## New-Target Candidates

{new_targets}

## Error Analysis

Open `outputs/hybrid_vector_error_analysis.xlsx` for tabs covering baseline errors, Variant B/C/D errors, improved-by-hybrid rows, hurt-by-hybrid rows, out-of-scope false positives, valid surgical misses, high-value review queue rows, alias gaps, suggested exclusion patterns, suggested aliases, and regression failures.

## Answers To Required Questions

{answer_text}

## Production Guidance

Productionize evidence scoring and audit outputs first. The workflow should preserve the current reference-compliant dashboard gate and use hybrid/vector retrieval only to improve candidate capture, review routing, exclusion conflict detection, and new-target proposals.

Recommendation:
{recommendation}

Reason:
- The experiment improves auditability and recall-oriented candidate capture without changing the master reference.
- The sampled results are proxy-based, so vector retrieval is not yet production-proven.
- Negative retrieval is useful as conflict evidence when routed through margin logic instead of blacklist removal.
- Human approval is still required for aliases, new targets, and master-reference changes.

Productionize now:
- Candidate/evidence audit fields and row-level retrieval audit.
- Negative conflict screening and positive-vs-negative review routing.
- Gold-label template, alias/update request workflow, and review clustering.

Keep experimental:
- Positive vector retrieval for auto-map decisions.
- External embedding/vector database provider.
- LLM resolver, recall hunter, and web-evidence sub-agents.

Do not productionize:
- Vector-only auto-mapping.
- Automatic production master updates from new-target discovery.

Main risks:
- Generic-token and manufacturer-only overmapping.
- Negative retrieval overblocking real surgical rows if used as a hard blacklist.
- Proxy metrics hiding segment-specific precision/recall failures.

Next iteration:
- Complete the `Gold_Label_Template` for high-value review and exclusion-risk rows.
- Run the experiment on full six-file outputs with the approved gold labels.
- Promote only human-approved aliases/rules into deterministic tables.
- Test an external embedding model only for Review_Queue and new-target discovery.
"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")


def write_all_reports(output_dir: str | Path = "outputs", reports_dir: str | Path = "reports") -> None:
    reports_dir = Path(reports_dir)
    write_current_workflow_diagnostic(reports_dir / "current_workflow_diagnostic.md")
    write_experiment_design(reports_dir / "hybrid_negative_vector_experiment_design.md")
    write_evaluation_report(output_dir, reports_dir / "hybrid_vector_evaluation_report.md")
