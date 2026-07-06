"""Retrieval and routing logic for the hybrid experiment."""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

import pandas as pd

from .normalize import RowFeatures, char_ngrams, extract_features, normalize_text, tokenize


POSITIVE_OBJECT_TYPES = {
    "canonical_tuple",
    "manufacturer_alias",
    "product_family_alias",
    "reviewed_mapping_example",
}
NEGATIVE_OBJECT_TYPES = {
    "hard_exclusion_term",
    "negative_vector_example",
    "excluded_prior_row",
    "ambiguous_scope_example",
}
INDEX_STOPWORDS = {
    "object",
    "type",
    "canonical",
    "manufacturer",
    "product",
    "family",
    "model",
    "segment",
    "path",
    "alias",
    "aliases",
    "terms",
    "common",
    "import",
    "review",
    "status",
    "approved",
    "source",
    "reference",
    "version",
    "latest",
    "surgical",
    "medical",
    "device",
    "devices",
    "system",
    "systems",
    "equipment",
    "instruments",
    "consumables",
}


@dataclass
class RetrievalConfig:
    top_k_bm25: int = 8
    top_k_fuzzy: int = 8
    top_k_vector: int = 8
    top_k_negative: int = 8
    top_k_final: int = 10
    auto_map_threshold: float = 0.74
    review_threshold: float = 0.42
    auto_exclude_threshold: float = 0.78
    positive_negative_margin_threshold: float = 0.18
    generic_token_penalty: float = 0.18
    manufacturer_only_penalty: float = 0.22
    exclusion_conflict_penalty: float = 0.35
    weights: dict[str, float] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "RetrievalConfig":
        if not data:
            return cls()
        allowed = {field.name for field in cls.__dataclass_fields__.values()}
        values = {key: value for key, value in data.items() if key in allowed}
        if "scoring_weights" in data and "weights" not in values:
            values["weights"] = data["scoring_weights"]
        return cls(**values)

    @property
    def scoring_weights(self) -> dict[str, float]:
        return self.weights or {
            "exact_or_alias_score": 0.25,
            "bm25_score": 0.20,
            "fuzzy_score": 0.15,
            "char_ngram_score": 0.10,
            "vector_score": 0.20,
            "prior_approved_example_score": 0.10,
        }


class RetrievalEngine:
    """Small local retrieval engine used for experiment variants.

    This class intentionally avoids external vector services. Its vector score is
    a local hashed n-gram cosine proxy so the experiment can run offline and the
    retrieval provider can be swapped later behind the same audit schema.
    """

    def __init__(self, retrieval_objects: pd.DataFrame, config: RetrievalConfig | None = None) -> None:
        self.config = config or RetrievalConfig()
        objects = retrieval_objects.fillna("").copy()
        if "normalized_retrieval_text" not in objects.columns:
            objects["normalized_retrieval_text"] = objects["retrieval_text"].map(normalize_text)
        objects["_tokens"] = objects["normalized_retrieval_text"].map(lambda text: set(tokenize(text)))
        objects["_chars"] = objects["normalized_retrieval_text"].map(lambda text: char_ngrams(text, 4))
        objects["_dense_terms"] = objects.apply(self._dense_terms_for_object, axis=1)
        self.objects = objects
        self.positive = objects[objects["object_type"].isin(POSITIVE_OBJECT_TYPES)].reset_index(drop=True)
        self.negative = objects[objects["object_type"].isin(NEGATIVE_OBJECT_TYPES)].reset_index(drop=True)
        self._positive_token_index = self._build_token_index(self.positive)
        self._negative_token_index = self._build_token_index(self.negative)

    @staticmethod
    def _build_token_index(objects: pd.DataFrame) -> dict[str, list[int]]:
        token_index: dict[str, list[int]] = defaultdict(list)
        for idx, tokens in objects["_tokens"].items():
            for token in tokens:
                if len(token) < 3 or token in INDEX_STOPWORDS:
                    continue
                token_index[token].append(idx)
        return dict(token_index)

    @staticmethod
    def _dense_terms_for_object(row: pd.Series) -> set[str]:
        text = " ".join(
            str(row.get(col, ""))
            for col in (
                "retrieval_text",
                "canonical_manufacturer",
                "manufacturer_aliases",
                "product_family",
                "model",
                "segment_path",
                "common_import_terms",
                "alias_text",
            )
        )
        norm = normalize_text(text)
        return set(tokenize(norm)) | char_ngrams(norm, 5)

    @staticmethod
    def _cosine_like(left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        intersection = len(left & right)
        if intersection == 0:
            return 0.0
        return intersection / math.sqrt(len(left) * len(right))

    @staticmethod
    def _jaccard(left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        union = left | right
        return len(left & right) / len(union) if union else 0.0

    @staticmethod
    def _phrase_score(row_text: str, values: list[str], row_tokens: set[str] | None = None) -> float:
        score = 0.0
        padded = f" {row_text} "
        for value in values:
            norm = normalize_text(value)
            if not norm:
                continue
            if " " in norm and norm in row_text:
                score = max(score, 1.0)
            elif f" {norm} " in padded:
                score = max(score, 1.0)
            elif len(norm) >= 5:
                value_tokens = set(tokenize(norm))
                if row_tokens is not None and value_tokens and not (row_tokens & value_tokens):
                    continue
                ratio = SequenceMatcher(None, row_text[:400], norm).ratio()
                score = max(score, min(ratio, 0.82))
        return score

    @staticmethod
    def _metadata(row: pd.Series) -> dict[str, Any]:
        raw = row.get("metadata_json", "")
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def _score_candidate(
        self,
        features: RowFeatures,
        row: pd.Series,
        variant: str,
        row_chars: set[str] | None = None,
        dense_terms: set[str] | None = None,
    ) -> dict[str, Any]:
        row_text = features.normalized_text
        row_tokens = set(features.tokens)
        row_chars = row_chars if row_chars is not None else char_ngrams(row_text, 4)
        dense_terms = dense_terms if dense_terms is not None else (set(row_tokens) | char_ngrams(row_text, 5))
        object_tokens = row.get("_tokens", set())
        object_chars = row.get("_chars", set())
        object_dense = row.get("_dense_terms", set())

        manufacturer_values = [row.get("canonical_manufacturer", ""), *str(row.get("manufacturer_aliases", "")).split(";")]
        product_values = [row.get("product_family", ""), row.get("segment_path", ""), row.get("common_import_terms", "")]
        alias_values = [row.get("alias_text", ""), row.get("term", "")]

        manufacturer_score = self._phrase_score(row_text, manufacturer_values, row_tokens)
        family_score = self._phrase_score(
            row_text,
            [row.get("product_family", ""), row.get("model", ""), row.get("alias_text", "")],
            row_tokens,
        )
        product_score = max(
            self._phrase_score(row_text, product_values, row_tokens),
            0.72 if features.detected_surgical_terms and row.get("object_type") == "canonical_tuple" else 0.0,
        )
        exact_or_alias_score = max(manufacturer_score, family_score, self._phrase_score(row_text, alias_values, row_tokens))
        bm25_score = self._cosine_like(row_tokens, object_tokens)
        fuzzy_score = max(
            SequenceMatcher(None, row_text[:500], str(row.get("normalized_retrieval_text", ""))[:500]).ratio() * 0.75,
            SequenceMatcher(None, row_text[:240], normalize_text(row.get("alias_text", ""))).ratio()
            if row.get("alias_text", "")
            else 0.0,
        )
        char_ngram_score = self._jaccard(row_chars, object_chars)
        vector_score = self._cosine_like(dense_terms, object_dense)
        prior_score = 1.0 if row.get("object_type") == "reviewed_mapping_example" and exact_or_alias_score >= 0.9 else 0.0

        if variant == "B":
            vector_score = 0.0
        weights = self.config.scoring_weights
        final = (
            weights["exact_or_alias_score"] * exact_or_alias_score
            + weights["bm25_score"] * bm25_score
            + weights["fuzzy_score"] * fuzzy_score
            + weights["char_ngram_score"] * char_ngram_score
            + weights["vector_score"] * vector_score
            + weights["prior_approved_example_score"] * prior_score
        )
        if family_score >= 0.95 and manufacturer_score >= 0.95 and product_score >= 0.80:
            final = max(final, 0.92)
        elif exact_or_alias_score >= 0.95 and product_score >= 0.90 and not features.detected_generic_terms:
            final = max(final, 0.62)
        methods: list[str] = []
        if exact_or_alias_score >= 0.95:
            methods.append("exact_alias")
        if bm25_score > 0:
            methods.append("bm25")
        if fuzzy_score >= 0.45:
            methods.append("fuzzy")
        if char_ngram_score >= 0.02:
            methods.append("char_ngram")
        if vector_score >= 0.18:
            methods.append("vector")

        metadata = self._metadata(row)
        return {
            "object_id": row.get("object_id", ""),
            "object_type": row.get("object_type", ""),
            "canonical_target_id": row.get("canonical_target_id", ""),
            "candidate_segment": metadata.get("Segment", ""),
            "candidate_subsegment": metadata.get("Sub-segment", ""),
            "candidate_product": metadata.get("Product", ""),
            "candidate_player": row.get("canonical_manufacturer", metadata.get("Player", "")),
            "candidate_family": row.get("product_family", metadata.get("Model/ Family Name", "")),
            "segment_path": row.get("segment_path", ""),
            "source_method": "+".join(methods) if methods else "weak_similarity",
            "exact_or_alias_score": round(exact_or_alias_score, 4),
            "product_score": round(product_score, 4),
            "family_score": round(family_score, 4),
            "manufacturer_score": round(manufacturer_score, 4),
            "bm25_score": round(bm25_score, 4),
            "fuzzy_score": round(fuzzy_score, 4),
            "char_ngram_score": round(char_ngram_score, 4),
            "vector_score": round(vector_score, 4),
            "prior_approved_example_score": round(prior_score, 4),
            "final_candidate_score": round(min(final, 1.0), 4),
            "exclusion_category": row.get("exclusion_category", ""),
            "review_status": row.get("review_status", ""),
            "retrieval_text": str(row.get("retrieval_text", ""))[:600],
        }

    def _prefilter(
        self,
        features: RowFeatures,
        objects: pd.DataFrame,
        limit: int,
        token_index: dict[str, list[int]] | None = None,
    ) -> pd.DataFrame:
        """Cheaply shortlist objects before expensive fuzzy scoring.

        The master list can contain thousands of canonical tuples. Running full
        SequenceMatcher comparisons for every object and every row is wasteful,
        so this pass keeps objects with token/character overlap and leaves the
        detailed scoring to the smaller candidate pool.
        """

        if objects.empty:
            return objects
        row_tokens = set(features.tokens)
        if token_index:
            counts: Counter[int] = Counter()
            for token in row_tokens:
                if len(token) < 3 or token in INDEX_STOPWORDS:
                    continue
                counts.update(token_index.get(token, []))
            if counts:
                shortlist_size = max(limit * 20, 60)
                candidate_ids = [idx for idx, _ in counts.most_common(shortlist_size)]
                return objects.loc[candidate_ids]

        row_chars = char_ngrams(features.normalized_text, 4)
        hints: list[tuple[int, float]] = []
        for idx, obj in objects.iterrows():
            object_tokens = obj.get("_tokens", set())
            token_overlap = len(row_tokens & object_tokens)
            if token_overlap == 0:
                dense_overlap = len((set(features.tokens) | char_ngrams(features.normalized_text, 5)) & obj.get("_dense_terms", set()))
                if dense_overlap < 2:
                    continue
            else:
                dense_overlap = token_overlap
            char_hint = self._jaccard(row_chars, obj.get("_chars", set())) if token_overlap else 0.0
            hints.append((idx, token_overlap * 2.0 + dense_overlap + char_hint))
        if not hints:
            return objects.head(max(limit, 25))
        hints.sort(key=lambda item: item[1], reverse=True)
        shortlist_size = max(limit * 20, 80)
        return objects.loc[[idx for idx, _ in hints[:shortlist_size]]]

    def _rank(
        self,
        features: RowFeatures,
        objects: pd.DataFrame,
        variant: str,
        limit: int,
        token_index: dict[str, list[int]] | None = None,
    ) -> list[dict[str, Any]]:
        if objects.empty:
            return []
        shortlisted = self._prefilter(features, objects, limit, token_index)
        row_chars = char_ngrams(features.normalized_text, 4)
        dense_terms = set(features.tokens) | char_ngrams(features.normalized_text, 5)
        scored = [
            self._score_candidate(features, row, variant, row_chars=row_chars, dense_terms=dense_terms)
            for _, row in shortlisted.iterrows()
        ]
        scored.sort(key=lambda item: item["final_candidate_score"], reverse=True)
        return scored[:limit]

    def retrieve_row(self, row: dict[str, Any], variant: str = "D") -> dict[str, Any]:
        features = extract_features(row)
        positive_candidates = self._rank(
            features,
            self.positive,
            variant,
            self.config.top_k_final,
            self._positive_token_index,
        )
        negative_candidates: list[dict[str, Any]] = []
        if variant == "D":
            negative_candidates = self._rank(
                features,
                self.negative,
                variant,
                self.config.top_k_negative,
                self._negative_token_index,
            )

        best_positive = positive_candidates[0] if positive_candidates else {}
        best_negative = negative_candidates[0] if negative_candidates else {}
        positive_score = float(best_positive.get("final_candidate_score", 0.0))
        negative_score = float(best_negative.get("final_candidate_score", 0.0))
        scope_margin = positive_score - negative_score

        hard_exclusion = bool(features.detected_exclusion_terms)
        surgical_evidence = bool(features.detected_surgical_terms)
        best_canonical = next((candidate for candidate in positive_candidates if candidate["object_type"] == "canonical_tuple"), {})
        if (
            best_canonical
            and (
                best_positive.get("object_type") == "canonical_tuple"
                or float(best_canonical.get("final_candidate_score", 0.0) or 0.0) >= self.config.auto_map_threshold
            )
        ):
            selected = best_canonical
        else:
            selected = best_positive

        product_evidence = max(
            float(selected.get("product_score", 0.0) or 0.0),
            float(selected.get("family_score", 0.0) or 0.0),
            0.65 if surgical_evidence else 0.0,
        )
        manufacturer_evidence = float(selected.get("manufacturer_score", 0.0) or 0.0)
        family_evidence = float(selected.get("family_score", 0.0) or 0.0)
        generic_only = bool(features.detected_generic_terms) and not surgical_evidence and product_evidence < 0.55
        manufacturer_only = manufacturer_evidence >= 0.8 and product_evidence < 0.50 and family_evidence < 0.50
        master_valid = selected.get("object_type") == "canonical_tuple" and bool(selected.get("canonical_target_id", ""))
        vector_only = "vector" in str(selected.get("source_method", "")) and not any(
            method in str(selected.get("source_method", "")) for method in ("exact_alias", "bm25", "fuzzy", "char_ngram")
        )

        final_score = float(selected.get("final_candidate_score", 0.0) or 0.0)
        if generic_only:
            final_score -= self.config.generic_token_penalty
        if manufacturer_only:
            final_score -= self.config.manufacturer_only_penalty
        if hard_exclusion:
            final_score -= self.config.exclusion_conflict_penalty
        final_score = round(max(0.0, final_score), 4)

        final_decision = "unmatched"
        review_reason = ""
        confidence = final_score

        if hard_exclusion and not surgical_evidence and negative_score >= 0.18:
            final_decision = "auto_exclude"
            review_reason = "strong_exclusion_no_surgical_evidence"
            confidence = max(negative_score, 0.80)
        elif hard_exclusion and surgical_evidence:
            final_decision = "review_required"
            review_reason = "positive_and_negative_scope_conflict"
        elif variant == "D" and negative_score >= self.config.auto_exclude_threshold and scope_margin < -0.18:
            final_decision = "auto_exclude"
            review_reason = "negative_retrieval_high_positive_weak"
            confidence = negative_score
        elif not master_valid and surgical_evidence and positive_score >= self.config.review_threshold:
            final_decision = "new_target_candidate"
            review_reason = "surgical_evidence_without_approved_canonical_target"
        elif master_valid and final_score >= self.config.auto_map_threshold and product_evidence >= 0.55 and not (
            generic_only or manufacturer_only or vector_only
        ):
            final_decision = "auto_map"
            review_reason = "latest_master_valid_with_supported_product_evidence"
        elif positive_score >= self.config.review_threshold or surgical_evidence:
            final_decision = "review_required"
            reasons = []
            if not master_valid:
                reasons.append("no_latest_master_canonical_candidate")
            if generic_only:
                reasons.append("generic_token_only")
            if manufacturer_only:
                reasons.append("manufacturer_only")
            if vector_only:
                reasons.append("vector_only")
            if product_evidence < 0.55:
                reasons.append("weak_product_evidence")
            if not reasons:
                reasons.append("candidate_below_auto_map_threshold")
            review_reason = "; ".join(reasons)
        else:
            review_reason = "weak_positive_and_negative_evidence"

        mapped = selected if final_decision == "auto_map" else {}
        return {
            "features": features,
            "top_positive_candidates": positive_candidates,
            "top_negative_candidates": negative_candidates,
            "best_positive_score": round(positive_score, 4),
            "best_negative_score": round(negative_score, 4),
            "scope_margin": round(scope_margin, 4),
            "selected_candidate": selected,
            "final_decision": final_decision,
            "review_reason": review_reason,
            "confidence": round(confidence, 4),
            "mapped_manufacturer": mapped.get("candidate_player", ""),
            "mapped_product_family": mapped.get("candidate_family", ""),
            "mapped_model": mapped.get("candidate_family", ""),
            "mapped_segment_path": mapped.get("segment_path", ""),
            "product_evidence": round(product_evidence, 4),
            "manufacturer_evidence": round(manufacturer_evidence, 4),
            "generic_token_risk": "Y" if generic_only else "",
            "manufacturer_only_risk": "Y" if manufacturer_only else "",
            "master_reference_status": "pass" if master_valid else "no_canonical_tuple",
        }
