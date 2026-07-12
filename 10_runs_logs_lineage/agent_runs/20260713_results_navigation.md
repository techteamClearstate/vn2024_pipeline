# Results navigation and weekend scorecard — 2026-07-13

## Outcome

- Built a five-page, read-only HTML navigation site from audit-v3 SQLite and the six current
  mapped-workbook schemas.
- Added exact Trusted/Review/Excluded comparisons by family, manufacturer, product, segment,
  and sub-segment across Vietnam, India, and Pakistan.
- Added a Vietnam benchmark using 2024 World Bank population and nominal GDP, explicitly
  labeled as a reasonableness signal rather than a market forecast.
- Added a nontechnical weekend scorecard that separates realized production change from
  unapproved recall opportunity.

## Score evidence

- Exact audit v2 → v3 population: 3,573,729 common rows; no source-population changes.
- Realized Trusted movement: 0 rows / $0 value / 0 volume.
- Pending proposal workbook: 365 clusters, 30,813 cluster-row occurrences, $232,319,022.89
  ($178,018,186.11 family-alias candidates plus $54,300,836.78 scope-whitelist candidates).
- Human approvals: 0/365. Precision labels: 0/150. No precision or mAP claim is made.

## Verification

- `python tools/verify_results_navigation.py`: 18 totals and 90 dimension totals reconciled;
  16,303 comparison groups and six workbook schemas validated.
- `python tools/verify_results_navigation_render.py`: five pages at desktop/mobile widths,
  filters exercised, zero JavaScript errors.
- Raw sources, reference CSVs, mapped production workbooks, and reviewer inputs were unchanged.
