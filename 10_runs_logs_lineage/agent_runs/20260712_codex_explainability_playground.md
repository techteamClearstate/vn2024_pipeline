# Explainability playground upgrade (review-only)

## Scope and authority

- Goal: give business analysts concrete examples at every blocking step and an in-browser gate
  simulator that never changes production.
- Authority: `outputs/20260710_recall_audit_v2/prediction_audit.sqlite`.
- Reused components: `tools/build_funnel_dashboard.py`,
  `tools/_funnel_dashboard_template.py`, and `tools/verify_funnel_dashboard.py`.
- Raw uploads, mapped workbooks, governed references, and pipeline routing were not modified.

## Implementation

- Embedded 994 unique example rows selected deterministically as top-value plus pseudo-random rows
  per file × removal stage × primary reason. Examples payload: 488,673 bytes (budget: 614,400).
- Added expanders to Funnel steps, Hotspots reasons, and Recovery clusters. Fields include source row,
  description, maker, family, mapped product, segment, value, QA status, stage, and primary reason.
- Pre-aggregated 112 exact file × primary-gate × secondary-gate-mask groups from `removal_stage_id`
  and secondary `rule_hit` blockers. Seven gates are toggleable: dental; negative/accessory;
  reference validation; scope; generic-token; extended-HS; ophthalmic guard.
- S13 coverage gaps remain visible and non-toggleable. India FY2025 attribution caveat remains explicit.
- Simulator reports direct releases separately from rows likely held by another enabled gate. It does
  not model downstream recovery dynamics.
- Added per-gate guidance and copy/download adjudication notes linking the simulator insight to
  `Recall_Recovery_Proposals.xlsx` and the governed analyst loop.

## Verification evidence

```text
PYTHONIOENCODING=utf-8 python tools/build_funnel_dashboard.py
PYTHONIOENCODING=utf-8 python tools/verify_funnel_dashboard.py --skip-render
PYTHONIOENCODING=utf-8 python tools/verify_funnel_dashboard_render.py --html outputs/20260710_recall_audit_v2/Recall_Funnel_Dashboard.html
```

- Authority reconciliation: 100/100 checks passed.
- Examples: every reference resolves to a real `row_fact`; identity, attribution, value, cell, and
  simulator-mask membership match the database.
- Simulator: groups exactly match authority-derived primary-gate × secondary-mask groups; per-file
  baseline + all toggleable releases + locked rows equals total.
- Browser: 1,904/1,904 states passed across all tabs, seven scopes, 128 gate masks, desktop and mobile;
  zero JavaScript errors.
- Dashboard remains self-contained with no external network references.

## Publication

The upgraded `Recall_Funnel_Dashboard.html` is published additively to the existing review-only shared-
drive area. The prior dashboard is preserved in `9. Archive`; delivery navigation, tracker, and update
log are updated in the same publish. No mapped-result workbook is replaced.

The governed `Prediction_Funnel_and_Review.xlsx` was also published additively to
`4. Manual Mapped Files/` as the business-team venue for the 150-row Track C precision sample.
Its 20,689,362-byte shared-drive copy matches the local artifact exactly at SHA-256
`A40D3CC1E8AA205542D930EC796C6EF3E32DF1FFD7FAE7CC8093BD11E473A5CB`.

## Completion audit addendum (2026-07-12)

- Rebuilt and verified the current v3 dashboard authority: **107/107 checks passed**; the headless
  harness passed **1,904/1,904 states** across all tabs, scopes, gate masks, desktop, and mobile with
  zero JavaScript errors. The examples payload is 529,110 bytes, below the 600 KB budget.
- Verified the published shared-drive dashboard independently with the same acceptance harness; all
  checks and render states passed. The shared reviewer workbook also passes check-only ingestion with
  150/150 expected sample identities and 0/150 analyst labels.
- Corrected a runbook/CLI mismatch in `tools/verify_prediction_audit.py`: the documented no-argument
  command now resolves the active audit database, workbook, and guide from `config/audit_sources.json`.
  `python tools/verify_prediction_audit.py` now passes for `20260712_recall_audit_v3`.
- Clarified the S12 review boundary: `Recall_Recovery_Candidates.csv` is a ranked prioritization list,
  not a row-complete export. Its all-market S12 section contains the top 15 families (~$45.3M); the
  dashboard reports the complete reference-valid S12 pool (~$60M). Any expansion or approval remains
  governed analyst work and does not change production recall by itself.
