#!/usr/bin/env python3
"""Focused acceptance checks for precision follow-up sample planning."""
from __future__ import annotations

from precision_measurement import FOLLOW_UP_TARGET_HALF_WIDTH, follow_up_sample_decision, wilson_interval


def main() -> None:
    awaiting = follow_up_sample_decision(None, 0, 0)
    assert awaiting["status"] == "awaiting_labels"
    assert awaiting["estimated_additional_labels"] is None

    wide = follow_up_sample_decision(0.90, 78, 78)
    assert wide["status"] == "more_labels_needed"
    assert wide["estimated_additional_labels"] > 0
    required = wide["required_effective_n"]
    low, high = wilson_interval(0.5 * required, required, required)
    assert (high - low) / 2 <= FOLLOW_UP_TARGET_HALF_WIDTH
    if required > 1:
        low, high = wilson_interval(0.5 * (required - 1), required - 1, required - 1)
        assert (high - low) / 2 > FOLLOW_UP_TARGET_HALF_WIDTH

    # A design effect of two doubles the estimated actual labels needed.
    weighted = follow_up_sample_decision(0.90, 39, 78)
    assert weighted["estimated_additional_labels"] == 2 * (required - 39)

    sufficient = follow_up_sample_decision(0.90, required + 10, required + 10)
    assert sufficient["status"] == "sufficient"
    assert sufficient["estimated_additional_labels"] == 0
    print("PASS: precision follow-up sampling decisions are conservative and design-aware")


if __name__ == "__main__":
    main()
