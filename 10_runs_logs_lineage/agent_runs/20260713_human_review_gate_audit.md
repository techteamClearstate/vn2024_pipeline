# Human review gate audit — 2026-07-13

## End goal

Continue the explainable mapping roadmap through governed recall execution and
measured precision, without bypassing analyst decisions or changing production
from review-only evidence.

## Authoritative checks

Shared-drive recall workbook:

```text
apply_review_adjudications.py --check-pending --no-shared-log
approved=0 checked=365
family_alias=133 scope_whitelist=125 skipped_existing=107 errors=0
dry-run: no files written
```

Shared-drive precision workbook:

```text
ingest_precision_labels.py --check
Audit run: 20260712_recall_audit_v3
Sample identities: 150 workbook / 150 authority
Rows with reviewer content: 0
VALIDATION PASSED — check-only; SQLite was not changed
```

Both inputs are structurally ready and exactly aligned with the current audit
authority. The pending state is therefore a human-review dependency, not a
schema, identity, ingestion, or publishing defect.

## Remaining work and owners

1. Business/analyst team: set `Approved=Y` only on accepted rows in
   `2. Interactive Dashboard/Recall_Recovery_Proposals.xlsx`.
2. Business/analyst team: label rows in the `Review Samples` sheet of
   `4. Manual Mapped Files/Prediction_Funnel_and_Review.xlsx`.
3. Pipeline operator after approvals: ingest governed decisions, rebuild the
   reference database, rerun PK → India → VN, run `qc_check.py`, batch remap,
   publish with archive/log/tracker updates, rebuild audit/reports/dashboard,
   and run the exact audit comparator against v3.
4. Audit operator after labels: ingest validated labels, rebuild/verify the
   dashboard, report design-weighted precision by file/tier, and use its
   follow-up recommendation if confidence intervals remain wide.

## Deliberately deferred

- Manufacturer-only and not-in-master recovery batches remain sequenced after
  the first approved batch is rerun and measured, preventing mixed causal
  attribution.
- Runtime optimization remains deferred: the latest complete dashboard build
  plus 110-check/1,904-state browser verification took roughly three minutes
  and does not currently block iteration.

## Current status

No production recall change is authorized or technically meaningful until at
least one governed proposal is approved. No measured precision claim is possible
until determinate business labels exist. Raw sources, references, mapped outputs,
Trusted totals, and SQLite labels were not changed during this audit.
