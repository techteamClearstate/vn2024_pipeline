# Reviewer workbook v3 synchronization — 2026-07-12

## Scope

Review-only governance repair. No production workbooks, reference lists, mapped fields, QA status,
or terminal tiers were changed.

## Finding

`tools/ingest_precision_labels.py --check` compared the shared reviewer workbook with audit run
`20260712_recall_audit_v3`. Both contained 150 sample rows, but the identities differed by 3 missing
and 3 unexpected rows. Reviewer content was 0/150, so no analyst work required migration.

## Action

- Archived the prior shared workbook as
  `9. Archive/Prediction_Funnel_and_Review_pre-v3_20260712.xlsx`.
- Published the v3-generated workbook to
  `4. Manual Mapped Files/Prediction_Funnel_and_Review.xlsx`.
- Updated the shared `DATA_UPDATES_LOG.md` and `OUTPUT_TRACKER.md`.

## Verification

The shared workbook now passes check-only ingestion:

- 150 workbook identities / 150 authority identities;
- 0 rows with reviewer content;
- validation passed;
- SQLite was not changed.

## Remaining governed inputs

The recovery-proposal workbook still has no human approvals and the precision sample still has no
human labels. Therefore a production rerun, realized-recall claim, or measured-accuracy claim is not
authorized yet.
