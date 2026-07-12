#!/usr/bin/env python3
"""Design-aware accuracy summaries for the prediction-audit review sample.

The deterministic stratified-random sample supports population inference via
its stored sample weights. Purposeful/targeted rows are useful diagnostics but
must never be combined with that estimate. This module is read-only and is
shared by the funnel dashboard builder and its acceptance checks.
"""
from __future__ import annotations

import math
import sqlite3
from collections.abc import Callable, Iterable
from typing import Any

RANDOM_SAMPLE = "Deterministic stratified random"
TARGETED_SAMPLE = "Targeted"
TIERS = ("Trusted", "Review", "Excluded")
RELEVANCE_DETERMINATE = {"Surgical", "Not surgical"}
MAPPING_DETERMINATE = {"Correct", "Incorrect"}


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(float(value), 8)


def wilson_interval(successes: float, denominator: float, effective_n: float,
                    z: float = 1.959963984540054) -> tuple[float | None, float | None]:
    """Return a 95% Wilson interval using a survey-weight effective sample size."""
    if denominator <= 0 or effective_n <= 0:
        return None, None
    p = min(max(successes / denominator, 0.0), 1.0)
    z2 = z * z
    centre = (p + z2 / (2 * effective_n)) / (1 + z2 / effective_n)
    spread = z * math.sqrt((p * (1 - p) / effective_n) + z2 / (4 * effective_n**2))
    spread /= 1 + z2 / effective_n
    return max(0.0, centre - spread), min(1.0, centre + spread)


def _metric(records: Iterable[dict[str, Any]],
            denominator: Callable[[dict[str, Any]], bool],
            success: Callable[[dict[str, Any]], bool], *, weighted: bool) -> dict[str, Any]:
    eligible = [r for r in records if denominator(r)]
    raw_n = len(eligible)
    raw_success = sum(1 for r in eligible if success(r))
    weights = [float(r["weight"]) if weighted else 1.0 for r in eligible]
    weighted_n = sum(weights)
    weighted_success = sum(w for r, w in zip(eligible, weights) if success(r))
    rate = weighted_success / weighted_n if weighted_n > 0 else None
    sum_w2 = sum(w * w for w in weights)
    effective_n = (weighted_n * weighted_n / sum_w2) if sum_w2 > 0 else 0.0
    low, high = wilson_interval(weighted_success, weighted_n, effective_n) if weighted else (None, None)
    return {
        "denominator": raw_n,
        "numerator": raw_success,
        "weighted_denominator": _rounded(weighted_n),
        "weighted_numerator": _rounded(weighted_success),
        "rate": _rounded(rate),
        "effective_n": _rounded(effective_n) if weighted else None,
        "ci_low": _rounded(low),
        "ci_high": _rounded(high),
    }


def _summary(records: list[dict[str, Any]], *, weighted: bool, tier: str) -> dict[str, Any]:
    relevance = _metric(
        records,
        lambda r: r["surgical_relevance"] in RELEVANCE_DETERMINATE,
        lambda r: r["surgical_relevance"] == "Surgical",
        weighted=weighted,
    )
    mapping = _metric(
        records,
        lambda r: r["surgical_relevance"] == "Surgical"
        and r["mapping_correctness"] in MAPPING_DETERMINATE,
        lambda r: r["mapping_correctness"] == "Correct",
        weighted=weighted,
    )
    end_to_end = _metric(
        records,
        lambda r: r["surgical_relevance"] == "Not surgical"
        or (r["surgical_relevance"] == "Surgical"
            and r["mapping_correctness"] in MAPPING_DETERMINATE),
        lambda r: r["surgical_relevance"] == "Surgical"
        and r["mapping_correctness"] == "Correct",
        weighted=weighted,
    )
    return {
        "tier": tier,
        "sample_rows": len(records),
        "relevance_entered": sum(bool(r["surgical_relevance"]) for r in records),
        "mapping_entered": sum(bool(r["mapping_correctness"]) for r in records),
        "relevance": relevance,
        "mapping": mapping,
        "end_to_end": end_to_end,
    }


def build_measured_accuracy(cur: sqlite3.Cursor, file_ids: list[str]) -> dict[str, Any]:
    rows = []
    for fid, tier, sample_type, weight, relevance, correctness in cur.execute(
        """SELECT rl.output_file_id, rf.output_tier, rl.sample_type,
                  rl.sample_weight, rl.surgical_relevance, rl.mapping_correctness
             FROM review_label rl
             JOIN row_fact rf ON rf.row_fact_id=rl.row_fact_id
            ORDER BY rl.review_label_id"""
    ):
        if sample_type == RANDOM_SAMPLE and (weight is None or float(weight) <= 0):
            raise RuntimeError(f"Random review row in {fid} has no positive sample weight.")
        if sample_type not in {RANDOM_SAMPLE, TARGETED_SAMPLE}:
            raise RuntimeError(f"Unknown review sample type: {sample_type!r}")
        rows.append({
            "file": fid,
            "tier": tier,
            "sample_type": sample_type,
            "weight": float(weight or 1.0),
            "surgical_relevance": relevance,
            "mapping_correctness": correctness,
        })

    entered = sum(bool(r["surgical_relevance"]) for r in rows)
    complete = sum(
        bool(r["surgical_relevance"])
        and (r["surgical_relevance"] != "Surgical" or bool(r["mapping_correctness"]))
        for r in rows
    )
    status = "awaiting_labels" if entered == 0 else ("complete" if complete == len(rows) else "partial")
    by_scope: dict[str, Any] = {}
    for scope in ["ALL", *file_ids]:
        scoped = rows if scope == "ALL" else [r for r in rows if r["file"] == scope]
        by_scope[scope] = {}
        for key, sample_type, weighted in (
            ("random", RANDOM_SAMPLE, True),
            ("targeted", TARGETED_SAMPLE, False),
        ):
            sample = [r for r in scoped if r["sample_type"] == sample_type]
            by_scope[scope][key] = [
                _summary(sample, weighted=weighted, tier="Overall"),
                *[_summary([r for r in sample if r["tier"] == tier], weighted=weighted, tier=tier)
                  for tier in TIERS],
            ]

    return {
        "status": status,
        "sample_rows": len(rows),
        "labels_entered": entered,
        "complete_rows": complete,
        "random_rows": sum(r["sample_type"] == RANDOM_SAMPLE for r in rows),
        "targeted_rows": sum(r["sample_type"] == TARGETED_SAMPLE for r in rows),
        "by_scope": by_scope,
        "method": {
            "random": "Design-weighted estimates from the deterministic stratified-random sample; 95% Wilson intervals use the effective sample size.",
            "targeted": "Purposeful diagnostic rows reported separately and unweighted; they are not population estimates.",
            "uncertain": "Blank and Uncertain judgments are excluded from each metric's denominator.",
        },
    }
