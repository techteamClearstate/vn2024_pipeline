# Precision follow-up sample decision — 2026-07-13

## Purpose

Close Track C's remaining approval-independent gap: turn a wide measured-accuracy
interval into an explicit follow-up sample recommendation without overstating the
currently unlabelled evidence.

## Changes

- Added a conservative 95% / ±5 percentage-point follow-up decision to every
  design-weighted random-sample metric.
- Required effective sample size is planned at the maximum-variance rate (0.5).
- Additional effective sample is translated to estimated actual determinate
  judgments using the metric's observed design effect.
- Metrics with no determinate labels remain `awaiting_labels`; targeted rows have
  no follow-up decision and remain diagnostic only.
- Surfaced the recommendation in the dashboard's Measured accuracy table.

## Verification

- `python tools/verify_precision_measurement.py` — PASS.
- `python tools/build_funnel_dashboard.py` — rebuilt audit-v3 dashboard (891 KB).
- `python tools/verify_funnel_dashboard.py` — 110/110 PASS.
- Headless render — 1,904 tab/scope/gate/viewport states, 0 JavaScript errors.
- Examples payload — 529,110 bytes, within the 600 KB cap.

## Current evidence state

The governed workbook still contains 0/150 analyst labels. Therefore the
dashboard correctly shows `Awaiting analyst labels`, no precision estimate, and
no numeric follow-up recommendation. This change does not alter production
mapping or realized recall.
