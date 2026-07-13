# India FY2025 prediction-audit attribution fix

- Date: 2026-07-12
- Run: `20260712_recall_audit_v3`
- Prior authority: `outputs/20260710_recall_audit_v2/prediction_audit.sqlite`
- Scope: review-only audit/reporting layer; no production mapping or reference mutation

## Purpose and decision

India FY2025 uses the complete mapped CSV because the population exceeds one Excel
worksheet. That source lacks the workbook-only master/reference evidence columns, so
v2 attributed reference failures at S13 together with genuine coverage gaps. V3
derives the missing evidence in memory from the governed master, records detailed
`Master_Validation_Status`, and preserves the registry's binary
`Reference_Key_Status` contract.

The enrichment is deliberately non-mutating: source data, mapped dimensions,
`QA_Status`, terminal tier, and production artifacts are unchanged. Therefore the
expected realized recall delta versus v2 is exactly zero; only removal-stage
explanation should change.

## Governed inputs

- `config/audit_sources.json`
- `config/prediction_rule_registry.json`
- `reference/brand_model/Surg_Brand_model_list_Master_03July26.xlsx`
- Six configured mapped-output sources and the complete India FY2025 CSV source

Input and output hashes are stored in the completed SQLite manifest and will be
captured below after the full build.

## Commands

```powershell
$env:PYTHONIOENCODING='utf-8'
python tools/build_prediction_audit.py
python tools/build_prediction_audit_reports.py
python tools/build_funnel_dashboard.py
python tools/verify_prediction_audit.py
python tools/verify_funnel_dashboard.py
```

## Acceptance criteria

- All six files reconcile exactly on row count, value, and volume.
- V2 and v3 terminal tier totals reconcile exactly per file and combined.
- India FY2025 invalid reference evidence is attributed at S07, except for an
  explicitly higher-priority terminal reason such as the ophthalmic conflict;
  blank/non-applicable reference evidence remains at S13.
- Detailed master status and binary reference status agree with the governed
  policy, including strict rejection of generic-family-only matches.
- Dashboard examples and simulator masks reconcile to real authority rows.
- Self-contained headless render suite reports zero JavaScript errors.

## Results

- Authority rebuilt at `outputs/20260712_recall_audit_v3/prediction_audit.sqlite`.
- All 3,573,729 source rows reconciled; source-manifest inventory contains 514 files.
- V2 and v3 terminal outcomes are identical overall and for every market-year:
  - Excluded: 1,386,850 rows / $7,355,243,730.92
  - Review: 1,665,941 rows / $4,735,643,539.53
  - Trusted: 520,938 rows / $2,415,624,774.11
- India FY2025 now attributes 93,714 rows / $280,519,027.39 to S07 reference
  validation. S13 falls from 1,666,962 rows / $5,506,114,180.82 to 1,575,648
  rows / $5,239,682,816.11. This is an explanation correction, not recovery.
- `verify_prediction_audit.py`: PASS, including per-file V2/v3 terminal-tier
  equality and governed India master-status consistency.
- `verify_funnel_dashboard.py`: PASS 107/107. The self-contained headless suite
  rendered 1,904 desktop/mobile states across every tab, scope and gate mask with
  zero JavaScript errors. Examples payload: 529,110 bytes (below 614,400-byte cap).
- Generated review-only reports:
  - `Prediction_Funnel_and_Review.xlsx` (20,429,476 bytes)
  - `Recall_Funnel_Dashboard.html` (self-contained)
  - refreshed `Surgical_Mapping_Workflow_Guide.html`

## Publication

The dashboard and workflow guide were published additively to the shared delivery
folder. Their prior versions are retained in `9. Archive/` with
`pre-india-attribution_20260712` names. Delivery-folder documentation was updated
to state that India attribution improved while terminal outcomes and realized
recall remained unchanged. The existing governed reviewer workbook was not
overwritten because it is the analysts' live labeling venue.
