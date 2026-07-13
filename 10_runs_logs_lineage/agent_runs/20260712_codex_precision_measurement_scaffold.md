# Agent run — governed precision measurement scaffold

- Date: 2026-07-12
- Agent: Codex
- Scope: Track C2 measurement plumbing over the existing review-only prediction audit
- Authority: `outputs/20260710_recall_audit_v2/prediction_audit.sqlite`
- Label venue: `Prediction_Funnel_and_Review.xlsx`, sheet `Review Samples`

## Changes

- Added `tools/ingest_precision_labels.py` to validate the exact 150 authority identities,
  enforce complete reviewer judgments, ingest only label fields, and record idempotent
  workbook-hash lineage.
- Added `tools/precision_measurement.py` with design-weighted stratified-random estimates and
  effective-sample-size Wilson intervals; targeted rows remain separate and unweighted.
- Added the Measured accuracy panel to the dashboard Overview and authority reconciliation to
  `tools/verify_funnel_dashboard.py`.
- Updated the agent guide and recall roadmap/readme.

## Validation and state

- `python -m py_compile ...`: passed.
- `python tools/ingest_precision_labels.py --check`: passed; 150 workbook identities matched
  150 authority identities; 0 rows contained reviewer content.
- Dashboard rebuild: passed; self-contained HTML is 822 KB and the examples payload is
  488,673 bytes (within the 614,400-byte cap).
- `python tools/verify_funnel_dashboard.py --skip-render`: 106/106 checks passed.
- `python tools/verify_funnel_dashboard.py`: 107/107 checks passed; the headless harness rendered
  1,904 states across all tabs, seven scopes, 128 gate masks, desktop, and mobile with 0 JS errors.
- Production routing/reference lists/mapped workbooks: unchanged.
- Realized recall versus the 2026-07-06 published batch: 0 additional Trusted rows / $0.

## Next owner action

Business analysts label the shared-drive workbook. Re-run the importer first with `--check`,
then ingest, rebuild/verify the dashboard, and interpret random-sample estimates separately from
targeted diagnostics. Recall proposals still require `Approved=Y` and the governed reference/rerun
workflow before any gain is realized.
