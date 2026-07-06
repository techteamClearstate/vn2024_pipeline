"""Experiment harness for hybrid retrieval variants."""

from __future__ import annotations

import json
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from .normalize import extract_features, normalize_text
from .retrieval import RetrievalConfig, RetrievalEngine


VARIANTS = {
    "A": "Baseline current workbook tier",
    "B": "Lexical hybrid only",
    "C": "Lexical + positive vector proxy",
    "D": "Positive + negative hybrid with margin",
}

DEFAULT_SAMPLE_TIER_SHEETS = ["Trusted_Dashboard", "Review_Queue", "Excluded_Unmapped"]
VALUE_COLUMNS = ["Total_Value_USD", "Value_USD", "CIF_USD", "Import_Value_USD"]


def load_config(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    path = Path(path)
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(text)
        return loaded or {}
    except Exception:
        return _minimal_yaml(text)


def _minimal_yaml(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current: str | None = None
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if not raw_line.startswith(" ") and ":" in raw_line:
            key, value = raw_line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if value == "":
                data[key] = {}
                current = key
            else:
                data[key] = _parse_scalar(value)
                current = None
        elif current and ":" in raw_line:
            key, value = raw_line.split(":", 1)
            data[current][key.strip()] = _parse_scalar(value.strip())
    return data


def _parse_scalar(value: str) -> Any:
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value.lower() in {"null", "none"}:
        return None
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value.strip("\"'")


def _value_usd(row: dict[str, Any]) -> float:
    for col in VALUE_COLUMNS:
        value = row.get(col)
        if value is None or value == "":
            continue
        try:
            return float(str(value).replace(",", ""))
        except ValueError:
            continue
    return 0.0


def infer_country_year(path: str | Path) -> tuple[str, str]:
    name = Path(path).name
    country = ""
    year = ""
    for candidate in ("Pakistan", "Vietnam", "India"):
        if candidate.lower() in name.lower():
            country = candidate
            break
    match = re.search(r"FY(20\d{2})", name, re.IGNORECASE)
    if match:
        year = match.group(1)
    return country, year


def target_id_from_row(row: dict[str, Any]) -> str:
    segment = row.get("Segment", "")
    subsegment = row.get("Sub-segment", "")
    product = row.get("Product_V0", row.get("Product", ""))
    player = row.get("Manufacturer", row.get("Player", ""))
    family = row.get("Family", row.get("Model/ Family Name", ""))
    return "|".join(normalize_text(part) for part in (segment, subsegment, product, player, family))


def _sheet_names(path: Path) -> list[str]:
    try:
        workbook = pd.ExcelFile(path, engine="openpyxl")
        return workbook.sheet_names
    except Exception:
        return []


def load_sample_rows(input_paths: list[str | Path], sample_size_per_tier: int = 250) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for input_path in input_paths:
        path = Path(input_path)
        country, year = infer_country_year(path)
        sheets = _sheet_names(path)
        tiers = [sheet for sheet in DEFAULT_SAMPLE_TIER_SHEETS if sheet in sheets]
        if not tiers and "RawData" in sheets:
            tiers = ["RawData"]
        for tier in tiers:
            try:
                frame = pd.read_excel(path, sheet_name=tier, nrows=sample_size_per_tier, engine="openpyxl")
            except Exception:
                continue
            if frame.empty:
                continue
            frame["source_file"] = str(path)
            frame["source_workbook"] = path.name
            frame["source_tier"] = tier
            frame["country"] = country
            frame["year"] = year
            frames.append(frame)
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True).fillna("")
    if "UniqueID" not in combined.columns:
        combined["UniqueID"] = [f"sample:{i + 1}" for i in range(len(combined))]
    return combined


def _json_summary(items: list[dict[str, Any]], max_items: int = 5) -> str:
    trimmed = items[:max_items]
    return json.dumps(trimmed, ensure_ascii=True, sort_keys=True)


def _baseline_decision(row: dict[str, Any]) -> str:
    tier = str(row.get("source_tier", ""))
    if tier == "Trusted_Dashboard" or str(row.get("Dash_Include", "")).upper() == "Y":
        return "auto_map"
    if tier == "Review_Queue":
        return "review_required"
    if tier == "Excluded_Unmapped":
        return "auto_exclude"
    return "unmatched"


def _audit_record(row: dict[str, Any], variant: str, result: dict[str, Any]) -> dict[str, Any]:
    features = result["features"]
    selected = result.get("selected_candidate", {})
    return {
        "variant": variant,
        "variant_label": VARIANTS.get(variant, variant),
        "source_row_id": row.get("UniqueID", ""),
        "source_file": row.get("source_file", ""),
        "source_workbook": row.get("source_workbook", ""),
        "source_tier": row.get("source_tier", ""),
        "country": row.get("country", ""),
        "year": row.get("year", ""),
        "source_text": features.source_text,
        "normalized_text": features.normalized_text,
        "import_value": _value_usd(row),
        "hs_code": features.hs_code,
        "top_positive_candidates": _json_summary(result["top_positive_candidates"]),
        "top_negative_candidates": _json_summary(result["top_negative_candidates"]),
        "positive_score": result["best_positive_score"],
        "negative_score": result["best_negative_score"],
        "scope_margin": result["scope_margin"],
        "retrieval_methods_used": selected.get("source_method", ""),
        "evidence_terms": "; ".join(features.detected_surgical_terms),
        "exclusion_terms": "; ".join(features.detected_exclusion_terms),
        "exclusion_categories": "; ".join(features.detected_exclusion_categories),
        "generic_terms": "; ".join(features.detected_generic_terms),
        "final_decision": result["final_decision"],
        "mapped_manufacturer": result["mapped_manufacturer"],
        "mapped_product_family": result["mapped_product_family"],
        "mapped_model": result["mapped_model"],
        "mapped_segment_path": result["mapped_segment_path"],
        "confidence": result["confidence"],
        "review_reason": result["review_reason"],
        "product_evidence": result["product_evidence"],
        "manufacturer_evidence": result["manufacturer_evidence"],
        "generic_token_risk": result["generic_token_risk"],
        "manufacturer_only_risk": result["manufacturer_only_risk"],
        "master_reference_status": result["master_reference_status"],
        "baseline_decision": _baseline_decision(row),
        "baseline_target_id": target_id_from_row(row),
    }


def _baseline_record(row: dict[str, Any]) -> dict[str, Any]:
    features = extract_features(row)
    decision = _baseline_decision(row)
    return {
        "variant": "A",
        "variant_label": VARIANTS["A"],
        "source_row_id": row.get("UniqueID", ""),
        "source_file": row.get("source_file", ""),
        "source_workbook": row.get("source_workbook", ""),
        "source_tier": row.get("source_tier", ""),
        "country": row.get("country", ""),
        "year": row.get("year", ""),
        "source_text": features.source_text,
        "normalized_text": features.normalized_text,
        "import_value": _value_usd(row),
        "hs_code": features.hs_code,
        "top_positive_candidates": "",
        "top_negative_candidates": "",
        "positive_score": "",
        "negative_score": "",
        "scope_margin": "",
        "retrieval_methods_used": "current_workbook_tier",
        "evidence_terms": "; ".join(features.detected_surgical_terms),
        "exclusion_terms": "; ".join(features.detected_exclusion_terms),
        "exclusion_categories": "; ".join(features.detected_exclusion_categories),
        "generic_terms": "; ".join(features.detected_generic_terms),
        "final_decision": decision,
        "mapped_manufacturer": row.get("Manufacturer", ""),
        "mapped_product_family": row.get("Family", ""),
        "mapped_model": row.get("Family", ""),
        "mapped_segment_path": " > ".join(
            str(row.get(col, "")).strip() for col in ("Segment", "Sub-segment", "Product_V0") if str(row.get(col, "")).strip()
        ),
        "confidence": row.get("Match_Confidence", ""),
        "review_reason": row.get("QA_Status", ""),
        "product_evidence": "",
        "manufacturer_evidence": "",
        "generic_token_risk": "",
        "manufacturer_only_risk": "",
        "master_reference_status": row.get("Ref_Valid", ""),
        "baseline_decision": decision,
        "baseline_target_id": target_id_from_row(row),
    }


def run_experiment(
    input_paths: list[str | Path],
    retrieval_objects_path: str | Path,
    config_path: str | Path | None,
    output_dir: str | Path,
    sample_size_per_tier: int = 250,
) -> dict[str, Any]:
    start = time.perf_counter()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    config = load_config(config_path)
    retrieval_config = RetrievalConfig.from_dict(config)
    objects = pd.read_csv(retrieval_objects_path).fillna("")
    engine = RetrievalEngine(objects, retrieval_config)
    sample = load_sample_rows(input_paths, sample_size_per_tier=sample_size_per_tier)

    audit_rows: list[dict[str, Any]] = []
    for _, row in sample.iterrows():
        row_dict = row.to_dict()
        audit_rows.append(_baseline_record(row_dict))
        for variant in ("B", "C", "D"):
            result = engine.retrieve_row(row_dict, variant=variant)
            audit_rows.append(_audit_record(row_dict, variant, result))

    audit = pd.DataFrame(audit_rows)
    audit_path = output_dir / "retrieval_audit.csv"
    audit.to_csv(audit_path, index=False, encoding="utf-8-sig")
    with pd.ExcelWriter(output_dir / "retrieval_audit.xlsx", engine="xlsxwriter") as writer:
        audit.to_excel(writer, sheet_name="Retrieval_Audit", index=False)

    metrics = compute_metrics(audit, elapsed_seconds=time.perf_counter() - start)
    metrics_path = output_dir / "hybrid_vector_metrics_summary.json"
    metrics_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=True), encoding="utf-8")
    pd.DataFrame(metrics["variant_metrics"]).to_excel(output_dir / "metrics_summary.xlsx", index=False)

    write_exclusion_audit(audit, output_dir / "exclusion_audit.xlsx")
    write_error_analysis(audit, output_dir / "hybrid_vector_error_analysis.xlsx")
    write_new_target_candidates(audit, output_dir / "new_target_candidates.xlsx", config)
    write_gold_label_template(audit, output_dir / "gold_label_template.xlsx")
    return metrics


def _is_surgicalish(frame: pd.DataFrame) -> pd.Series:
    return frame["evidence_terms"].astype(str).str.len().gt(0) | frame["source_tier"].isin(["Trusted_Dashboard", "Review_Queue"])


def compute_metrics(audit: pd.DataFrame, elapsed_seconds: float) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    variants = sorted(audit["variant"].unique())
    for variant in variants:
        frame = audit[audit["variant"] == variant].copy()
        surgicalish = _is_surgicalish(frame)
        captured = frame["final_decision"].isin(["auto_map", "review_required", "new_target_candidate"])
        auto_map = frame["final_decision"].eq("auto_map")
        auto_exclude = frame["final_decision"].eq("auto_exclude")
        review = frame["final_decision"].isin(["review_required", "new_target_candidate"])
        false_positive_proxy = auto_map & frame["source_tier"].eq("Excluded_Unmapped") & frame["exclusion_terms"].astype(str).str.len().gt(0)
        wrongly_excluded_proxy = auto_exclude & surgicalish
        strict_precision_denominator = int(auto_map.sum())
        strict_precision_numerator = int((auto_map & frame["source_tier"].eq("Trusted_Dashboard")).sum())
        trusted_precision_proxy = (
            strict_precision_numerator / strict_precision_denominator if strict_precision_denominator else None
        )
        capture_recall_proxy = int((captured & surgicalish).sum()) / int(surgicalish.sum()) if int(surgicalish.sum()) else None
        candidate_recall_at_10 = _candidate_recall_at_10(frame)
        rows.append(
            {
                "variant": variant,
                "variant_label": VARIANTS.get(variant, variant),
                "sample_rows": int(len(frame)),
                "sample_value": round(float(frame["import_value"].sum()), 2),
                "auto_map_rows": int(auto_map.sum()),
                "auto_map_value": round(float(frame.loc[auto_map, "import_value"].sum()), 2),
                "review_rows": int(review.sum()),
                "review_value": round(float(frame.loc[review, "import_value"].sum()), 2),
                "auto_exclude_rows": int(auto_exclude.sum()),
                "auto_exclude_value": round(float(frame.loc[auto_exclude, "import_value"].sum()), 2),
                "new_target_candidate_rows": int(frame["final_decision"].eq("new_target_candidate").sum()),
                "trusted_precision_proxy_strict": trusted_precision_proxy,
                "capture_recall_proxy": capture_recall_proxy,
                "candidate_recall_at_10_on_baseline_trusted": candidate_recall_at_10,
                "false_positive_proxy_rows": int(false_positive_proxy.sum()),
                "false_positive_proxy_value": round(float(frame.loc[false_positive_proxy, "import_value"].sum()), 2),
                "wrongly_excluded_proxy_rows": int(wrongly_excluded_proxy.sum()),
                "wrongly_excluded_proxy_value": round(float(frame.loc[wrongly_excluded_proxy, "import_value"].sum()), 2),
                "manual_review_rows": int(review.sum()),
                "high_value_review_rows_50k": int((review & frame["import_value"].ge(50000)).sum()),
            }
        )
    return {
        "experiment_scope": "sampled_workbook_tiers_proxy_gold",
        "elapsed_seconds": round(elapsed_seconds, 2),
        "variant_metrics": rows,
        "notes": [
            "Metrics are proxy metrics because no completed human Gold_Labels table is present.",
            "Strict precision proxy counts only baseline Trusted_Dashboard rows as known-good auto-map rows.",
            "Capture recall proxy counts rows with surgical terms or baseline trusted/review tier as surgical-looking denominator.",
            "The local vector score is a deterministic hashed n-gram proxy, not an external embedding API.",
        ],
    }


def _candidate_recall_at_10(frame: pd.DataFrame) -> float | None:
    trusted = frame[frame["source_tier"].eq("Trusted_Dashboard") & frame["baseline_target_id"].astype(str).str.len().gt(4)]
    if trusted.empty or trusted["top_positive_candidates"].astype(str).str.len().sum() == 0:
        return None
    hits = 0
    total = 0
    for _, row in trusted.iterrows():
        target = row["baseline_target_id"]
        if not target:
            continue
        total += 1
        try:
            candidates = json.loads(row.get("top_positive_candidates", "[]") or "[]")
        except Exception:
            candidates = []
        if any(candidate.get("canonical_target_id") == target for candidate in candidates):
            hits += 1
    return hits / total if total else None


def write_exclusion_audit(audit: pd.DataFrame, path: str | Path) -> None:
    path = Path(path)
    variant_d = audit[audit["variant"].eq("D")].copy()
    tabs = {
        "Summary": _summary_by(variant_d, ["final_decision", "exclusion_categories"]),
        "Auto Excluded": variant_d[variant_d["final_decision"].eq("auto_exclude")],
        "Review Negative Similarity": variant_d[
            variant_d["final_decision"].eq("review_required") & pd.to_numeric(variant_d["negative_score"], errors="coerce").fillna(0).gt(0.15)
        ],
        "Pos Neg Score Margin": variant_d.sort_values("scope_margin").head(500),
        "Dental Risks": variant_d[variant_d["exclusion_categories"].astype(str).str.contains("dental", case=False, na=False)],
        "Veterinary Risks": variant_d[variant_d["exclusion_categories"].astype(str).str.contains("veterinary", case=False, na=False)],
        "Cosmetic Risks": variant_d[variant_d["exclusion_categories"].astype(str).str.contains("cosmetic", case=False, na=False)],
        "IVD Lab Risks": variant_d[variant_d["exclusion_categories"].astype(str).str.contains("ivd_lab", case=False, na=False)],
        "Imaging Pharma General Risks": variant_d[
            variant_d["exclusion_categories"].astype(str).str.contains("imaging|pharma|ppe|furniture", case=False, na=False)
        ],
        "Possible Overblocked Surgical": variant_d[
            variant_d["final_decision"].eq("auto_exclude") & variant_d["evidence_terms"].astype(str).str.len().gt(0)
        ],
    }
    _write_excel_tabs(path, tabs)


def write_error_analysis(audit: pd.DataFrame, path: str | Path) -> None:
    variant_d = audit[audit["variant"].eq("D")].copy()
    variant_b = audit[audit["variant"].eq("B")].copy()
    variant_c = audit[audit["variant"].eq("C")].copy()
    tabs = {
        "Summary": pd.DataFrame(compute_metrics(audit, 0)["variant_metrics"]),
        "Baseline Errors": audit[audit["variant"].eq("A") & audit["source_tier"].eq("Review_Queue")].head(1000),
        "Variant B Errors": variant_b[variant_b["review_reason"].astype(str).str.contains("weak|generic|manufacturer|vector|no_latest", na=False)].head(1000),
        "Variant C Errors": variant_c[variant_c["review_reason"].astype(str).str.contains("weak|generic|manufacturer|vector|no_latest", na=False)].head(1000),
        "Variant D Errors": variant_d[variant_d["review_reason"].astype(str).str.contains("weak|generic|manufacturer|vector|no_latest|conflict", na=False)].head(1000),
        "Improved By Hybrid": variant_d[variant_d["source_tier"].isin(["Review_Queue", "Excluded_Unmapped"]) & variant_d["final_decision"].isin(["auto_map", "review_required", "new_target_candidate"])].head(1000),
        "Hurt By Hybrid": variant_d[variant_d["source_tier"].eq("Trusted_Dashboard") & ~variant_d["final_decision"].isin(["auto_map", "review_required"])].head(1000),
        "Out Of Scope False Positives": variant_d[variant_d["final_decision"].eq("auto_map") & variant_d["exclusion_terms"].astype(str).str.len().gt(0)],
        "Valid Surgical Misses": variant_d[variant_d["final_decision"].eq("auto_exclude") & variant_d["evidence_terms"].astype(str).str.len().gt(0)],
        "High Value Review Queue": variant_d[variant_d["final_decision"].isin(["review_required", "new_target_candidate"]) & variant_d["import_value"].ge(50000)].head(1000),
        "Alias Gaps": variant_d[variant_d["review_reason"].astype(str).str.contains("no_latest|weak_product|manufacturer_only", na=False)].head(1000),
        "Suggested Exclusion Patterns": _suggest_terms(variant_d, "exclusion_terms"),
        "Suggested New Aliases": _suggest_terms(variant_d[variant_d["final_decision"].isin(["review_required", "new_target_candidate"])], "evidence_terms"),
        "Regression Failures": variant_d[variant_d["source_tier"].eq("Trusted_Dashboard") & variant_d["final_decision"].eq("auto_exclude")],
    }
    _write_excel_tabs(path, tabs)


def write_new_target_candidates(audit: pd.DataFrame, path: str | Path, config: dict[str, Any]) -> None:
    variant_d = audit[audit["variant"].eq("D")].copy()
    candidates = variant_d[
        variant_d["final_decision"].isin(["new_target_candidate", "review_required"])
        & variant_d["evidence_terms"].astype(str).str.len().gt(0)
        & ~variant_d["exclusion_categories"].astype(str).str.contains("dental|veterinary|cosmetic|ivd_lab|imaging", case=False, na=False)
    ].copy()
    if candidates.empty:
        summary = pd.DataFrame(columns=["source_cluster_id", "source_row_count", "source_import_value", "countries_seen"])
    else:
        candidates["cluster_key"] = candidates["evidence_terms"].astype(str).str.split(";").str[0].fillna("surgical_unknown")
        grouped = candidates.groupby("cluster_key", dropna=False).agg(
            source_row_count=("source_row_id", "count"),
            source_import_value=("import_value", "sum"),
            countries_seen=("country", lambda values: ", ".join(sorted(set(str(v) for v in values if str(v))))),
            example_text=("source_text", "first"),
            review_reason=("review_reason", lambda values: "; ".join(sorted(set(str(v) for v in values if str(v)))[:5])),
        )
        grouped = grouped.reset_index().rename(columns={"cluster_key": "source_cluster_id"})
        grouped["status"] = "needs_review"
        grouped["web_evidence_status"] = "not_run_experiment_default"
        grouped["proposed_action"] = "alias_or_reference_review"
        summary = grouped.sort_values(["source_import_value", "source_row_count"], ascending=False)

    web_evidence = pd.DataFrame(
        [
            {
                "source_cluster_id": "",
                "source_url": "",
                "source_type": "",
                "source_title": "",
                "evidence_summary": "Web evidence collection is scaffolded but not run by default; human-approved research is required before master updates.",
                "confidence": "",
            }
        ]
    )
    tabs = {
        "Candidate Summary": summary,
        "Source Row Clusters": candidates.head(5000),
        "Web Evidence": web_evidence,
        "Proposed Canonical Tuples": summary.head(200),
        "Proposed Aliases": summary.head(200),
        "Alias Only Candidates": summary.head(200),
        "Rejected Candidates": pd.DataFrame(columns=summary.columns),
        "Approved Candidates": pd.DataFrame(columns=summary.columns),
        "Regression Impact": pd.DataFrame(
            [{"status": "not_run", "reason": "Production master is not modified by this experiment."}]
        ),
        "Human Review Queue": summary.head(500),
    }
    _write_excel_tabs(path, tabs)


def write_gold_label_template(audit: pd.DataFrame, path: str | Path) -> None:
    variant_d = audit[audit["variant"].eq("D")].copy()
    selected = pd.concat(
        [
            variant_d[variant_d["source_tier"].eq("Trusted_Dashboard") & variant_d["exclusion_terms"].astype(str).str.len().gt(0)],
            variant_d[variant_d["import_value"].ge(50000)],
            variant_d[variant_d["final_decision"].eq("new_target_candidate")],
            variant_d.sample(min(100, len(variant_d)), random_state=7) if not variant_d.empty else variant_d,
        ],
        ignore_index=True,
    ).drop_duplicates(subset=["source_row_id", "source_workbook"])
    labels = selected[
        [
            "source_row_id",
            "source_file",
            "country",
            "year",
            "source_text",
            "normalized_text",
            "import_value",
            "source_tier",
            "final_decision",
            "review_reason",
        ]
    ].copy()
    for col in (
        "correct_decision",
        "true_scope",
        "correct_manufacturer",
        "correct_product_family",
        "correct_model",
        "correct_segment_path",
        "exclusion_category",
        "reviewer",
        "review_date",
        "label_confidence",
        "decision_reason",
        "correction_type",
    ):
        labels[col] = ""
    labels.to_excel(path, index=False)


def _summary_by(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=columns + ["rows", "value"])
    grouped = frame.groupby(columns, dropna=False).agg(rows=("source_row_id", "count"), value=("import_value", "sum"))
    return grouped.reset_index().sort_values("value", ascending=False)


def _suggest_terms(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    counter: Counter[str] = Counter()
    for value in frame[column].fillna("").astype(str):
        for term in [part.strip() for part in value.split(";") if part.strip()]:
            counter[term] += 1
    return pd.DataFrame([{"term": term, "rows": count} for term, count in counter.most_common(200)])


def _write_excel_tabs(path: str | Path, tabs: dict[str, pd.DataFrame]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        for sheet_name, frame in tabs.items():
            safe_name = sheet_name[:31]
            if frame is None:
                frame = pd.DataFrame()
            frame.to_excel(writer, sheet_name=safe_name, index=False)
