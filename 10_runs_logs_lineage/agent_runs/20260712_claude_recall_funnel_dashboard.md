# Recall Funnel & Understandability dashboard (review-only)

## Run metadata

- Date: 2026-07-12
- Agent: Claude (self-paced improvement loop)
- Objective: make the prediction-audit output easy to understand; add a funnel
  dashboard (kept-vs-lost per step, sliced by many dimensions); identify the
  steps that hurt recall most and safe recovery options. **Review-only** — no
  change to production routing, reference lists, or published workbooks.
- Authority (unchanged): `outputs/20260710_recall_audit_v2/prediction_audit.sqlite`
  (run `20260710_recall_audit_v2`, registry 2026.07.10.2, 3,573,729 rows).

## What was added (all read-only over the sqlite authority)

| Path | Purpose |
|---|---|
| `tools/build_funnel_dashboard.py` | Read-only builder; computes the additive funnel, breakdown cubes (9 dimensions incl. value/volume/ASP bands), recall hotspots, and confidence-rated recovery buckets; emits self-contained HTML. Never writes the sqlite. |
| `tools/_funnel_dashboard_template.py` | HTML/CSS/JS template (no external deps). |
| `tools/verify_funnel_dashboard.py` | Acceptance checks: per-scope reconciliation to the authority + self-contained assertion. |
| `outputs/20260710_recall_audit_v2/Recall_Funnel_Dashboard.html` | Deliverable dashboard (244 KB): Overview, The funnel, Breakdowns, Recall hotspots, Recovery options, Steps explained, Glossary. |
| `docs/RECALL_FUNNEL_DASHBOARD_PLAN.md` | Working plan / roadmap. |

## Method

The additive recall funnel attributes each row to the single stage where it left
the Trusted path (`row_fact.removal_stage_id` + `primary_reason`), so counts sum
to the total with no double counting. Breakdown cubes and recovery buckets are
aggregated per file + combined.

## Key finding — the two steps that hurt recall most (all six files)

| Step | Reason held back | Rows | Value |
|---|---|---:|---:|
| S07 Reference-master validation | product tuple not in master (`reference_tuple_invalid`) | 1,274,170 | $6.23B |
| S12 Final guards | `ophthalmic_imaging_conflict` | 348,178 | $1.43B |

(Also: S13 terminal `Unmapped` $2.37B and `Audit - manufacturer only` $1.71B are
never-matched coverage gaps, not filters.)

## Recovery options surfaced (review-only, non-overlapping partition of held-back value)

- **Mis-guarded surgical** (S12 Review, reference-valid) — highest confidence; whitelist review.
- **Loose-match / missing-from-master** (S07, recognised family) ~$1.6B — adjudicate top clusters
  (WARNING: value ranking also surfaces known false positives such as date-token families).
- **Manufacturer recognised, product missing** — lexicon expansion, precision-sensitive.
- **Little/no evidence** (Unmapped / no family) — largest but hardest.

## Validation

- `tools/verify_funnel_dashboard.py`: **53/53 PASS** — every scope's funnel total,
  Trusted total, additive sum, tier sum, recovery-bucket partition, and population
  cubes reconcile to the sqlite authority; **0 external network references**.
- Headless render harness: **774 render paths across all tabs/scopes/metrics/dimensions,
  0 JS runtime errors**; content checks pass. (Browser preview MCP was unresponsive in
  this environment — validated headlessly instead.)

## Notes / caveats

- India FY2025 (complete-CSV source) attributes held-back rows at terminal routing
  (`Unmapped` / `manufacturer only`) rather than S07, lacking reference-status columns.
  The combined view mixes attribution granularities; per-file views are cleanest. Surfaced
  in the dashboard (Funnel + Glossary warnings), not hidden.
- Not published to the shared delivery folder — that is a separate, explicit decision.

## Addendum — master cross-check deep-dive (same day)

The builder now also reads `reference/reference.sqlite` (`brand_model_master`, read-only) to
classify the S07 recognised-family loss pool ($1,257M) by how safe recovery is:
**$578M Clean** (family → one specific master category; backfill+adjudicate), $272M missing-from-master,
~$400M ambiguous/generic/date-token (correctly held — recovering hurts precision). S12 ophthalmic guard
is ~96% aligned with reference status (only ~$60M reference-valid over-suppression). Surfaced as a live
"Master check" panel in the Recovery tab and `master_check`/`master_category` columns in the CSV.
Analysis write-up: `docs/RECALL_RECOVERY_ANALYSIS.md`. Re-validated: verify 53/53; headless 774 render
paths, 12/12 content checks, 0 errors. Still fully review-only; no production or authority mutation.

## Addendum 2 — CRITICAL correction: spurious family matches on S07-failed rows

While drafting recovery proposals we inspected the evidence and found the recognised `family` on
S07-FAILED rows is frequently spurious (e.g. a "Cataract HOYA Vivinex" lens carries family
"Trauma Plates And Screws"; a dialysis filter carries "CH-S200"). Quantified: for **64% ($805M) of the
$1,257M** recognised-family value the family token does not appear in the product description — the
pipeline correctly rejected these at reference validation. The earlier "$578M Clean safe recovery" was
therefore overstated. Added a description-alignment check: the genuine **"Safe lever" is ~$180M**
(family maps to one master category AND is evidenced in the text); ~$398M is "Likely spurious"
(correctly held). Corrected the dashboard master-cross-check panel, the CSV, RECALL_RECOVERY_ANALYSIS.md,
RECALL_FUNNEL_README.md, and memory. New review-only tool `tools/build_recall_recovery_proposals.py`
emits `Recall_Recovery_Proposals.xlsx` (evidence-gated, ~$140M top clusters, Approved blank). Lesson:
looking at row-level evidence caught a materially misleading aggregate. verify 53/53; headless 14/14.

## Addendum 3 — governed guide plain-language edits (Option 2)

Applied the 10 reviewer plain-language edits to `tools/build_prediction_audit_reports.py` (preserving the
verify-required strings: "not statistical precision/recall", "MRI separation", "India FY2025",
"Pakistan nonstandard", S00–S14) and regenerated `docs/Surgical_Mapping_Workflow_Guide.html`. The guide is
now the database-driven output (37 KB; the retired 110 KB hard-coded guide is replaced per
`build_surgical_workflow_guide.py`). All 6 sections + 15 stages render; `verify_prediction_audit.py` = PASS
(db + html). LIMITATION: the Excel workbook `Prediction_Funnel_and_Review.xlsx` cannot be regenerated here —
the bundled node/Excel builder aborts (exit 134, V8) even at 8 GB heap; it never existed for this run. The
guide was regenerated via an HTML-only path (build_html + record_artifacts('html')). artifact_manifest now
holds the html entry (was empty before).

## Addendum 4 — published to shared delivery folder (Option 1, additive, review-only)

Published the corrected review-only artifacts to
`G:\...\6. Workflow\Surgicals\Claude code\` (additive — nothing overwritten or archived):
`2. Interactive Dashboard/` gained `Recall_Funnel_Dashboard.html`, `Recall_Recovery_Candidates.csv`,
`Recall_Recovery_Proposals.xlsx`, `Surgical_Mapping_Workflow_Guide.html`; `5. Documentation/` gained
`RECALL_FUNNEL_README.md`, `RECALL_RECOVERY_ANALYSIS.md`. Updated `DATA_UPDATES_LOG.md` (2026-07-12
review-only entry), `index.html` (new review-only section + links), `README.md`, and `OUTPUT_TRACKER.md`.
All labeled clearly as a read-only analysis layer that changes no mapped workbook, trusted dashboard, or
value bound. Verified all 6 files + 4 nav/log updates present on the shared drive.

## Addendum 5 — Excel workbook builder reworked to openpyxl (no Node dependency)

The bundled Node/Excel artifact-tool aborts (V8, exit 134) in this environment, so
`Prediction_Funnel_and_Review.xlsx` could not be built. Reworked the builder to pure Python
(`tools/_prediction_audit_workbook.py`, openpyxl); `build_prediction_audit_reports.py::build_workbook`
now calls it. Produces the same seven governed sheets in the same order (Read Me · Funnel · Removal Cube ·
Review Samples · Recall Risks · Reconciliation QC · Source Lineage), with the Review-sample dropdowns and
QC PASS/WARN/FAIL conditional formatting, atomic replace, and the 100 MB ceiling. Output: 20.7 MB,
144,478-row Removal Cube. **FULL `verify_prediction_audit.py` = PASS** (db + workbook + html); workbook
sheet names/order match `EXPECTED_SHEETS` exactly. The old `.mjs` is retired/unused. Not auto-published to
the shared drive (separate decision — it is the governed reviewer workbook, ~20 MB).
