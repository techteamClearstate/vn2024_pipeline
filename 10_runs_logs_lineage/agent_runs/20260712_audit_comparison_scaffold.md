# Prediction-audit comparison scaffold — 2026-07-12

## Purpose

Prepare the exact Track B4 measurement needed after analyst-approved recall
adjudications and a governed production rerun. This work is read-only and does
not change mappings, references, approvals, or shared-drive artifacts.

## Implementation

- Added `tools/compare_prediction_audits.py`.
- Stable identity: `output_file_id + source_row_id` (unique in both audit v2/v3).
- Measures tier totals, full transition matrix, newly Trusted, lost Trusted, net
  Trusted, and newly Trusted attribution to the baseline gate/reason.
- Fails closed on population changes by default and reports changed source hashes.
- Added a synthetic verifier covering recovery, regression, attribution, and
  transition reconciliation.

## Commands

```text
python tools/verify_prediction_audit_comparison.py
python tools/compare_prediction_audits.py --baseline outputs/20260710_recall_audit_v2/prediction_audit.sqlite --candidate outputs/20260712_recall_audit_v3/prediction_audit.sqlite --out outputs/audit_v2_to_v3_comparison.json
```

The generated JSON is diagnostic output and is not a production publication.

## Verification result

- Synthetic verifier: PASS.
- Full audit-v2 → audit-v3 comparison: 3,573,729/3,573,729 exact identities,
  zero baseline-only/candidate-only rows, zero changed source hashes.
- Newly Trusted: 0 rows / $0; lost Trusted: 0 rows / $0; net Trusted: $0.

This confirms audit v3's India attribution repair did not change production
recall. Realized recovery remains pending analyst approvals and the governed
reference rebuild + PK → India → VN rerun.
