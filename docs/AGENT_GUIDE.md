# Agent Operating Guide — Surgical Import-Data Enrichment Pipeline

> **Audience: AI agents** working in this repository. Read this file first, then
> load only what the task needs. The improvement roadmap lives in
> [REFERENCE_COMPLIANCE_PLAN.md](REFERENCE_COMPLIANCE_PLAN.md).
> Last updated: 2026-07-13 (LLM consensus adjudication, governed six-market
> rerun, exact weekend scorecard, and aggregate-only results-navigation publish).

## 1. What this project is

Enriches medical-device **import trade data** (Vietnam, Pakistan, India ×
FY2024 + FY2025) by matching each shipment's free-text `Detailed_Product`
description against a curated surgical brand/model master list. Matched rows are
tagged with `Segment / Sub-segment / Product_V0 / Manufacturer / Family` and
exported as styled Excel workbooks with a trusted revenue Dashboard.

Key vocabulary:

- **"Country" = the import MARKET** the source file represents
  (`cfg.IMPORT_COUNTRY`), never the exporter country.
- **Match tiers**: `family` (Tier-1, brand/model hit — highest confidence) →
  `category` (Tier-2, product-category phrase) → `manufacturer` (Tier-3,
  maker-only) → `hs_prior` (learned HS-code prior, lowest confidence).
- **Match_Scope**: `Surgical` = row's HS4 is in the core surgical code set
  (`cfg.SURGICAL_HS4`); `Extended` = recovered by widened HS matching.
- **Trusted dashboard rule** (post-compliance): a row feeds the trusted
  Dashboard/Rollup/Scope only if `Match_Scope=Surgical` AND `Ref_Valid=Y` AND
  `Scope_Flag` blank AND `QA_Status="Mapped - reference-valid"`.
- **Nothing is ever deleted**: failing rows stay in RawData, tagged via
  `QA_Status`, and are excluded from the trusted aggregates only.

## 2. Complete file map

### 2.1 Repository (`C:\Users\Administrator\Documents\Working Folder\vn2024_pipeline\`)

| Path | What it is | Edit? |
|---|---|---|
| `run_pipeline.py` | End-to-end runner (`--country`, `--source`, `--from`, `--skip-extract`) | rarely |
| `qc_check.py` | Read-only regression invariants; run after every pipeline run | rarely |
| `config/settings.py` | ALL paths, HS4 scope, tuning flags, QA vocabulary. Loads term lists from `reference/` — never hard-code lists here | yes |
| `src/step1_extract.py` | Source → TSV cache; builds Tier-1/2/3 lexicons, product-canonical map, `reference_tuples.pkl` | yes |
| `src/step2_match.py` | 3-tier trie/category/manufacturer matching | yes |
| `src/step3_map.py` | Joins matches → reference fields; `standardize_for_dashboard`; `apply_reference_gate` (the DQ gate) | yes |
| `src/step3b_hs_prior.py` | Learned HS-prior recall re-rank (guarded) | yes |
| `src/step4_export.py` | Styled workbook (RawData/Summary/Dashboard/Scope/Rollup/QA) + `Dashboard.html`; mirrors to Google Drive | yes |
| `src/dashboard_html.py` | Cross-market interactive Dashboard.html | yes |
| `tools/reference_compliance.py` | **Workbook-level reference-compliance DQ pass** (see §4). Market-agnostic CLI | yes |
| `tools/batch_surgical_workflow_remap.py` | **Batch evidence/routing remap** of all six workbooks. Governed aliases are source-description-only, longest-first and exclusion-guarded; oversized final Excel outputs are partitioned without dropping rows. The 2026-07-13 run writes beneath `outputs/20260713_llm_adjudication/raw_outputs/` | yes |
| `tools/vietnam_fy2024_workflow_improvement.py` | Evidence builder + routing library the batch remap imports (product rules, negative rules, fuzzy family channel) | yes |
| `tools/publish_surgical_current_outputs.py` | Publishes `remapped_current` workbooks to the shared delivery folder | yes |
| `tools/build_adjudication_proposals.py` | **Recall loop step 1**: encodes LLM-adjudicated review-cluster decisions into `Adjudication_Proposals_<Market>_FY<yr>.xlsx` (master-validated; `Approved` column blank for humans) | yes |
| `tools/apply_review_adjudications.py` | **Recall loop step 2**: ingests `Approved=Y` rows from either `Adjudication_Proposals` or `Recovery_Proposals`; `--check-pending` validates every unapproved row without writes; application is atomic/fail-closed | yes |
| `tools/verify_recall_recovery_proposals.py` | Verifies recovery-workbook schema, blank approvals, full master-key resolution, all-row ingestion preflight, and exact S12 cluster/value/evidence/regex reconciliation to the audit authority without writes | yes |
| `tools/ingest_precision_labels.py` | Validates and ingests only analyst label fields from the governed 150-row `Review Samples` sheet into the audit SQLite; supports `--check` and idempotent workbook-hash lineage | yes |
| `tools/reconcile_llm_adjudication.py` | Reconciles independent LLM proposal/sample reviews in SQLite; requires dual APPROVE at ≥0.90 before producing final all-row Excel handoffs | yes |
| `tools/build_results_navigation.py` | Builds the aggregate-only six-page HTML business navigation/scorecard and gate simulator from SQLite; never embeds row-level records | yes |
| `tools/*.py` (others) | Benchmarks, diagnostics, precision spot-checks | yes |
| `10_runs_logs_lineage/agent_runs/` | Per-run agent execution logs (lineage) | append |
| `90_archive_deprecated/` | Archived experiments (e.g. vector auto-mapping) + input snapshots | move, never delete |
| `reference/` | **Governed reference data** — brand master + all exclusion/usage lists. See `reference/README.md`. Edit the CSVs, then run `python reference/build_reference_db.py`. NEVER edit lists in settings.py | via CSVs |
| `reference/brand_model/Surg_Brand_model_list_Master_03July26.xlsx` | Canonical brand/model master (= `cfg.V0_REFERENCE_XLSX`). Sheets: `Updated` (full, 11,101 rows incl. 709 generic-flagged), `Updated (excl. generic)` (10,392 rows — used for matching) | no (analyst-owned) |
| `data/uploads/` | Market source workbooks/CSVs (input). Treat as immutable raw data | no |
| `data/intermediate/` | Regenerable caches: `vn_rawdata.tsv`, `vn_v0_mapped.csv`, lexicon pickles, `reference_tuples.pkl`, `dashboard_<market>.csv` slices. **Single-file caches are overwritten per market run** | regenerated |
| `outputs/` | One workbook per market-year + `Dashboard.html` + methodology. See §2.2 | generated |
| `docs/` | This guide, the improvement plan, improvement-methods notes | yes |

### 2.2 Outputs (`outputs/`)

| File | Status |
|---|---|
| `20260713_llm_adjudication/raw_outputs/mapped_results/<Market>_FY<yr>_ML_Map_Mapped.xlsx` | **CURRENT for all six market-years** — 2026-07-13 LLM-adjudicated governed rerun; every source row retained, with India FY2025 partitioned across RawData sheets |
| `20260713_llm_adjudication/raw_outputs/LLM_Review_Raw_Output.xlsx` | All 365 proposal decisions and all 150 sample rows; final Excel review handoff generated from SQLite |
| `20260713_llm_adjudication/dashboard/site/index.html` | **CURRENT business dashboard** — aggregate statistics only; total/family/manufacturer/product/segment comparisons, weekend scorecard, outputs and schemas |
| `remapped_current/reports/<Market>_FY<yr>_Surgical_Mapping_QA_Report.xlsx` | Per-market QA reports (metrics, cluster summaries, alias/reference requests, gold-label template) |
| `remapped_current/reports/All_Countries_Surgical_Mapping_QA_Report.xlsx` | Combined release-validation artifact (Metrics_By_File anchors qc_check §6) |
| `remapped_current/reports/Adjudication_Proposals_<Market>_FY<yr>.xlsx` | Recall-loop proposal workbooks awaiting human `Approved` marks |
| `<Market>_FY<yr>_DQ_Compliance_Report.xlsx` | Reference-compliance DQ reports (Phase-0 tool, all six market-years) |
| `Dashboard.html`, `VN2024_Methodology.html/.pdf` | Cross-market interactive dashboard + methodology |

### 2.3 Stakeholder delivery folder (shared drive — publish here, not just the repo)

`G:\共享云端硬盘\New EIU Gateway\0. Gateway Ops & Databases\Import Data Master\6. Workflow\Surgicals\Claude code\`
(Google Drive may display the first folder as `Shared drives` on an English-localized mount;
bash: `/g/共享云端硬盘/New EIU Gateway/0. Gateway Ops & Databases/Import Data Master/6. Workflow/Surgicals/Claude code/`)

| Subfolder | Contents |
|---|---|
| `1. Mapped Results/` | The 6 deliverable workbooks (`<Market>_FY<yr>_ML_Map_Mapped.xlsx`) + `Pakistan_FY2024_DQ_Compliance_Report.xlsx` |
| `20260713 LLM Adjudicated Results/1. Raw Outputs/` | Current all-row business handoff in Excel; oversized mapped results are partitioned across worksheets without dropping rows |
| `20260713 LLM Adjudicated Results/2. Dashboard/` | Current aggregate-only HTML business dashboard. Row-level evidence is not embedded; prior detailed review dashboards are historical/supporting artifacts, not the current aggregate handoff |
| `3. Reference Brand Lists/` | Master brand list copies |
| `4. Manual Mapped Files/` | Analyst-built comparison workbooks + the governed `Prediction_Funnel_and_Review.xlsx` labeling venue |
| `5. Documentation/` | `DATA_UPDATES_LOG.md` (changelog — UPDATE ON EVERY PUBLISH), `OUTPUT_TRACKER.md` (per-market bounds), `DATA_LINEAGE.md`, `FOLDER_GUIDE.md` |
| `9. Archive/` | Superseded files — move, never delete |
| root | `index.html` (nav portal — update its table/bars on publish) + `README.md` |

**Publish protocol:** copy new workbook(s) into `1. Mapped Results/`, move the
replaced file to `9. Archive/` (suffix e.g. `(pre-DQ-compliance 20260704)`),
update `DATA_UPDATES_LOG.md`, `OUTPUT_TRACKER.md`, `README.md` table, and the
`index.html` table + bounds bars.

There is also an auto-mirror (written by step4 export when mounted):
`G:\我的云端硬盘\Working Folder\Import Data\outputs\<COUNTRY>\vn2024_pipeline\`.

## 3. How to run

```bash
# per market (full run required per market; caches overwrite per market)
PYTHONIOENCODING=utf-8 python run_pipeline.py --country Pakistan --source "data/uploads/<file>"
python qc_check.py

# batch evidence/routing remap over the six pipeline workbooks (CURRENT layer)
PYTHONIOENCODING=utf-8 python tools/batch_surgical_workflow_remap.py

# recall loop (repeatable): propose -> human approves -> ingest -> rerun
PYTHONIOENCODING=utf-8 python tools/build_adjudication_proposals.py --market Pakistan --fy 2024
#   ... human sets Approved=Y in outputs/remapped_current/reports/Adjudication_Proposals_*.xlsx ...
PYTHONIOENCODING=utf-8 python tools/apply_review_adjudications.py          # writes reference/, rebuilds sqlite
#   then rerun affected markets end-to-end + remap + qc_check

# recovery-workbook publication/readiness check (checks blank and pending rows; never writes)
PYTHONIOENCODING=utf-8 python tools/verify_recall_recovery_proposals.py "<path>/Recall_Recovery_Proposals.xlsx" --db "<audit-run>/prediction_audit.sqlite"
# equivalent generic preflight for either supported proposal-sheet schema
PYTHONIOENCODING=utf-8 python tools/apply_review_adjudications.py --proposals "<path>/Recall_Recovery_Proposals.xlsx" --check-pending --no-shared-log

# 2026-07-13 governed outputs: internal processing is SQLite; Excel is final row-level handoff.
PYTHONIOENCODING=utf-8 python tools/reconcile_llm_adjudication.py
PYTHONIOENCODING=utf-8 python tools/batch_surgical_workflow_remap.py
PYTHONIOENCODING=utf-8 python qc_check.py --remap-only
```

- **Market order matters: PK → India → VN LAST** (the VN run rebuilds
  transfer_prior and the combined Dashboard).
- **Adjudicated aliases**: `reference/term_mappings.csv` `family_aliases`
  (alias → pipe-joined master 5-key, merged into the Tier-1 lookup by step1)
  and `category_qualifier_map` additions come ONLY from Approved proposal rows
  via `apply_review_adjudications.py` — never hand-edit them into code.
- **Fuzzy family channel** (`tools/vietnam_fy2024_workflow_improvement.py`):
  rapidfuzz Levenshtein over master family names, Review-only evidence
  (`candidate_source_method=fuzzy_lexical`), guarded by the generic-word
  blacklist, a document-frequency cap, and length-scaled distance. It must
  never feed Trusted directly.
- Windows/Git Bash: always prefix `PYTHONIOENCODING=utf-8`; never pipe
  `run_pipeline` through `head` (SIGPIPE kills it) — use `| tail`.
- Excel hard cap 1,048,576 rows → oversized final workbooks are partitioned
  across `RawData`, `RawData_Part_2`, etc. The sheets together contain every
  source row; SQLite is used for processing, audit, and reconciliation.

## 4. The reference-compliance pass (workbook-level, current for PK FY2024)

```bash
PYTHONIOENCODING=utf-8 python tools/reference_compliance.py \
    --workbook outputs/Pakistan_ML_Map_Mapped.xlsx --country Pakistan \
    --out outputs/Pakistan_FY2024_ML_Map_Mapped.xlsx \
    --report outputs/Pakistan_FY2024_DQ_Compliance_Report.xlsx
```

What it enforces (full spec + rationale in
[REFERENCE_COMPLIANCE_PLAN.md](REFERENCE_COMPLIANCE_PLAN.md) §2):

1. **family tier** — full key `Segment|Sub-segment|Product|Player|Model/Family`
   must exist in the strict master (`Updated` rows with blank
   `Generic Family Name?` ≡ `Updated (excl. generic)`). Loose matches
   (underscore/hyphen/en-dash/slash/™®© folded to spaces) are relabelled to the
   master's exact wording. Failures → `Review - not in latest reference` or
   `Review - reference category conflict`.
2. **category tier** — only the triple `Segment|Sub-segment|Product` must exist;
   `Manufacturer`/`Family` may stay `Unspecified`.
3. **manufacturer tier** → `Audit - manufacturer only`, never dashboard-included.
   **hs_prior tier** → `Audit - hs_prior category (pending validation)`.
4. **generic rule** — full keys existing only among generic-flagged master rows
   → `Review - generic reference family`, excluded from trusted.
5. **Extended rule** — reference-valid rows with `Match_Scope=Extended` →
   `Review - surgical product in Extended HS scope`, parked for a business
   include/exclude decision (they are NOT dashboard-included).
6. **scope keywords** (description-only; party names cause false positives) —
   veterinary/dental/cosmetic/lab-IVD/imaging triggers exclude otherwise-trusted
   rows, EXCEPT: (a) surgical-context whitelist (dilatation catheter incl.
   "dialation" misspelling, x-ray detectable, electrosurgical pencil,
   insufflator, diagnostic catheter); (b) **the trigger token is part of the
   row's master-validated Family name** (e.g. MRI-conditional pacemakers
   "Attesta SR MRI") — validated surgical.
7. **generic-token anomaly** — trusted family rows whose Family is a generic
   token (Target, Light Source, Sprinter, Essential, Unity, Hybrid, Elite,
   Optime, Therapy, Evolution, Physio, Woven, Cone) AND whose description reads
   as capital equipment → `Review - generic-token mapping anomaly`.
8. Rebuilds Summary / Dashboard / Scope / Rollup / QA as **hard values** from
   the updated RawData, and runs a **self-check** (every trusted row must
   exact-match the master; zero unresolved keyword hits) that raises on failure.

Report sheets (all sorted by revenue): `Summary`, `Reference_Label_Fixes`,
`Reference_Hard_Issues`, `Extended_Surgical_Review`, `Irrelevant_Scope_Hits`,
`Unmatched_Surgical_Candidates`, `Final_Action_Log`.

### QA_Status vocabulary (workbook `RawData` column)

| QA_Status | Meaning | In trusted dashboard? |
|---|---|---|
| `Mapped - reference-valid` | Passed all gates | **Yes** (iff Surgical + Ref_Valid=Y + no flag) |
| `Review - surgical product in Extended HS scope` | Valid product, non-core HS | No — pending business decision |
| `Review - not in latest reference` | Player/family or category absent from master | No |
| `Review - reference category conflict` | Player/family exists under a different category | No |
| `Review - generic reference family` | Only matches a generic-flagged master family | No |
| `Review - generic-token mapping anomaly` | Generic token + capital-equipment description | No |
| `Review - excluded scope: <flag>` | veterinary/dental/cosmetic/lab_ivd/imaging/general hit | No |
| `Review - unspecified category` | Category dims blank/`(unspecified)` | No |
| `Audit - manufacturer only` | Tier-3 maker-only match | No |
| `Audit - hs_prior category (pending validation)` | Low-confidence HS-prior match | No |
| `Unmapped` | No match | No |

## 5. Current market-state snapshot (2026-07-06 batch remap, A1 run)

| Market-year | Trusted rows / value | Review rows / value | High-value review (≥$50k) |
|---|---|---|---|
| Pakistan FY2024 | 2,920 / $46.3M | 14,954 / $159.4M | 702 rows / $95.6M |
| Pakistan FY2025 | 3,084 / $58.0M | 18,851 / $192.9M | 889 rows / $119.4M |
| India FY2024 | 163,817 / $684.1M | 454,237 / $1,244.2M | 3,852 rows / $509.8M |
| India FY2025 | 215,687 / $984.5M | 759,350 / $1,905.0M | 5,607 rows / $755.5M |
| Vietnam FY2024 | 52,367 / $260.5M | 160,573 / $562.3M | 1,219 rows / $209.4M |
| Vietnam FY2025 | 55,179 / $250.8M | 149,723 / $450.7M | 1,023 rows / $116.4M |

These trusted numbers are pinned as qc_check §6 anchors. **The dominant gap is
recall**: ~13,300 high-value rows (~$1.8B) sit in Review_Queue — the
adjudication loop above is the mechanism for working them down. Pakistan
FY2024's top clusters (75.8% of its review value) are already adjudicated in
`Adjudication_Proposals_Pakistan_FY2024.xlsx` awaiting approval.

## 6. Hard rules for agents

1. **Raw data is immutable** — never modify `data/uploads/` or analyst files in
   `3. Reference Brand Lists/` / `4. Manual Mapped Files/`.
2. **Reference lists**: edit `reference/*.csv` → run
   `python reference/build_reference_db.py`. Never hard-code lists in code.
3. **Never delete rows** from a mapped workbook — park with `QA_Status`.
4. **Archive, don't overwrite**, in the delivery folder; keep one CURRENT file
   per market-year.
5. After any pipeline change: run the affected markets (PK → India → VN last),
   run `qc_check.py`, and reconcile bounds before publishing.
6. Update the delivery `DATA_UPDATES_LOG.md` + `OUTPUT_TRACKER.md` +
   `index.html`/`README.md` tables on every publish.
7. Keep this guide and the plan document current when the workflow changes —
   they are the durable knowledge base for future agents.

## 7. Recall audit and reporting layer

The prediction audit is a governed, read-only reporting layer over the six
current mapped outputs. Its authority is the row-grain SQLite database; Excel is
used only for final all-row/reviewer handoffs and HTML is an aggregate business
view. The audit itself does not mutate mapping results. Accepted adjudications
change governed reference CSVs only through `apply_review_adjudications.py`,
followed by a full rerun and a fresh audit.

```bash
# 1. Build the complete row/stage authority atomically.
PYTHONIOENCODING=utf-8 python tools/build_prediction_audit.py

# 2. Generate the reviewer workbook and canonical HTML from that authority.
PYTHONIOENCODING=utf-8 python tools/build_prediction_audit_reports.py

# 3. Run all acceptance checks. Add --compare-db after a second full build.
PYTHONIOENCODING=utf-8 python tools/verify_prediction_audit.py
```

Governance inputs for the current run are `config/audit_sources_v4.json` and
`config/prediction_rule_registry.json`. The registry is the sole definition of
ordered stages, rule IDs, primary/additive reasons, secondary/non-additive
reasons, terminal decisions, and presentation-only logic. The audit builder
rejects partial source inputs and any configured row cap. India FY2025 uses the
complete partitioned final Excel output, reconciled exactly to the separately
hashed immutable complete CSV because its population cannot fit in one worksheet.

Run outputs are written beneath `outputs/<run_id>/`:

- `prediction_audit.sqlite` — complete authority at stable key
  `(run_id, output_file_id, source_row_id)`, including raw/parsed value and
  volume, every applicable stage state, rule hits, review sample, recall-risk
  inventory, reconciliation, lineage, and artifact hashes.
- `Prediction_Funnel_and_Review.xlsx` — bounded reviewer view with exactly
  seven governed tabs. Reviewer labels are independent of pipeline decisions;
  proposed outcomes are shadow recommendations only. Built by a pure-Python
  openpyxl builder (`tools/_prediction_audit_workbook.py`) — no external Node/Excel
  runtime (the old `tools/build_prediction_audit_workbook.mjs` is retired/unused).
  Publish the verified workbook to shared-drive `4. Manual Mapped Files/` so the
  business team has one governed venue for the 150-row precision-label sample;
  analyst labels must still be ingested through the governed review tooling.
- The canonical operator narrative is rebuilt at
  `docs/Surgical_Mapping_Workflow_Guide.html` from the same registry and SQLite
  authority.
- `Recall_Funnel_Dashboard.html` — a **self-contained** plain-language funnel &
  recall dashboard (Overview, step-by-step kept-vs-lost funnel, breakdown explorer
  by File/OU=Segment/Sub-OU=Sub-segment/Device=Product/Family/Manufacturer and
  Value/Volume/ASP bands, recall-hotspot "which steps hurt most" analysis, a
  confidence-rated recovery-options view, per-step plain-language cards, glossary,
  and a review-only **What-if playground**). Every removal step, hotspot reason,
  and recovery cluster can expand concrete authority-row examples. The playground
  toggles seven real gates in-browser and uses exact pre-aggregated primary-gate ×
  secondary-gate-mask groups to show direct releases versus rows likely still held
  by another enabled gate. S13 coverage gaps are shown but deliberately cannot be
  toggled; no toggle changes production or models downstream recovery dynamics.
  Built by `tools/build_funnel_dashboard.py` (+ `tools/_funnel_dashboard_template.py`),
  a **read-only** reader of the SQLite authority — it never writes the sqlite or
  changes production. The additive funnel groups `row_fact` by
  `removal_stage_id` + `primary_reason` (each row attributed once). Verify with
  `tools/verify_funnel_dashboard.py` (reconciles every scope, simulator group, and
  example to the authority; asserts no external network references; then invokes
  `tools/verify_funnel_dashboard_render.py` across all tabs, scopes, 128 toggle
  masks, desktop, and mobile). Rebuild + verify:
  `python tools/build_funnel_dashboard.py && python tools/verify_funnel_dashboard.py`.
  Plan/roadmap: `docs/RECALL_FUNNEL_DASHBOARD_PLAN.md`. Recovery guidance is
  review-only — use the playground's copy/download note to document a concern,
  review `Recall_Recovery_Proposals.xlsx`, then feed accepted decisions through
  the adjudication loop and rerun.
  Audit-v3 recovery proposals require each recognised family to resolve to one
  unique canonical master 5-key (not merely one category). The 2026-07-12 v3
  workbook contains 240 review clusters / about $178M, all approvals blank; its
  all-row ingestion preflight resolves 133 unique aliases with zero errors.
  The same governed workbook now also carries 125 evidence-backed S12
  `scope_whitelist` clusters / 7,302 rows / $54.3M. These are a conservative
  subset of the $59.9M reference-valid S12 pool: the validated family must be
  explicit in the source description. Approval can write only to
  `surgical_context_whitelist`; the remap guard consumes that governed list and
  otherwise remains unchanged.
  The Overview also contains a **Measured accuracy** panel. It reports the
  deterministic stratified-random sample as a design-weighted population estimate
  with 95% intervals and keeps purposeful targeted rows separate as unweighted
  diagnostics. Blank/Uncertain judgments are excluded from each denominator.
  Once determinate random judgments exist, each metric also estimates the
  additional determinate labels needed for a conservative 95% interval within
  ±5 percentage points, translating effective sample size through the observed
  design effect. Targeted rows never drive that recommendation.
  The 2026-07-13 production remap carries governed reference-status evidence into
  the partitioned India FY2025 final workbook. Audit v4 consumes that current
  output directly, normalizes the binary S07 gate separately from the detailed
  master status, and reconciles every Excel row to the immutable source CSV.
  Invalid reference tuples therefore attribute to S07, while genuine coverage
  gaps remain at S13; obsolete audit-only enrichment is no longer required.

Precision-label workflow (review-only):

The shared workbook must match the current audit authority before analysts start. Audit v4's
reviewer workbook is generated from the SQLite authority and contains the governed 150-row
sample. LLM double-review is available as decision support, but it is not a substitute for the
business team's labels and does not populate the human-label fields.

```bash
# Validate the shared-drive workbook without changing SQLite.
PYTHONIOENCODING=utf-8 python tools/ingest_precision_labels.py --check --workbook "<shared-drive>/4. Manual Mapped Files/Prediction_Funnel_and_Review.xlsx"

# After validation passes, ingest label fields; then rebuild and verify the panel.
PYTHONIOENCODING=utf-8 python tools/ingest_precision_labels.py --workbook "<shared-drive>/4. Manual Mapped Files/Prediction_Funnel_and_Review.xlsx"
PYTHONIOENCODING=utf-8 python tools/build_funnel_dashboard.py
PYTHONIOENCODING=utf-8 python tools/verify_funnel_dashboard.py
```

The importer never edits production workbooks, routing, references, reviewer
disposition, proposed outcomes, or adjudication fields. An active label row must
have reviewer/date; surgical rows need a mapping judgment, and an Incorrect
mapping needs a correction plus rationale. The current published workbook starts
with 0/150 labels entered, so the panel honestly shows `Awaiting analyst labels`.
The follow-up sample-size decision likewise remains unavailable until valid
labels exist. Its focused acceptance check is
`PYTHONIOENCODING=utf-8 python tools/verify_precision_measurement.py`.

For orientation only, the independent LLM review estimated Trusted mapping
precision at 99.77% by rows, 99.971% by value, and 99.967% by volume. This is
based on only 17 random Trusted sample rows and 82.35% exact reviewer agreement;
label it **LLM estimate, not human-verified ground truth** everywhere it appears.

Never edit a generated report to alter pipeline truth. Preserve source-row IDs,
keep `<Unmapped>` distinct from a genuine `Unspecified` mapping, keep Review
separate from Excluded, and use primary reasons for additive reconciliation.
Secondary reasons may overlap and must never be summed as removals. Any accepted
review decision belongs in the normal adjudication/reference workflow above,
followed by a governed production rerun; the audit itself remains review-only.

Each published audit run must have a record under
`10_runs_logs_lineage/agent_runs/` containing configuration and source hashes,
commands, six-file row/value/volume reconciliation, deterministic rebuild
results, artifact hashes, independent-QC findings and owner responses, fixes,
and final retest evidence. Publication is complete only when all actionable
independent-QC findings are closed.

After any governed production rerun, quantify realized recall against the prior
audit authority with `tools/compare_prediction_audits.py --baseline <old.sqlite>
--candidate <new.sqlite> --out <comparison.json>`. The comparator joins exact
`output_file_id + source_row_id` identities, reports tier transitions, newly and
lost Trusted rows/value/volume, and attributes each newly Trusted row to its
baseline blocking stage/reason. It fails closed if populations differ unless the
change is explicitly acknowledged with `--allow-population-change`. Verify its
recovery/regression arithmetic with `python tools/verify_prediction_audit_comparison.py`.

Results-navigation hub (read-only):

`tools/build_results_navigation.py` builds
`outputs/20260713_llm_adjudication/dashboard/site/`, a six-page static site covering the
current totals, a Vietnam/India/Pakistan macro sense-check, a plain-language weekend
recall/precision scorecard, exact aggregate family/manufacturer/product comparisons, governed
output descriptions, and the six mapped-workbook schemas. The site is aggregate-only: every
row-level record remains in the final Excel raw outputs, and SQLite remains an internal
processing authority rather than a business deliverable. Rebuild and validate it with:

```bash
python tools/build_results_navigation.py --db outputs/20260713_llm_adjudication/raw_outputs/prediction_audit.sqlite --scorecard outputs/20260713_llm_adjudication/dashboard/weekend_scorecard.json --review-aggregate outputs/20260713_llm_adjudication/dashboard/aggregate_data.json --out outputs/20260713_llm_adjudication/dashboard/site
python tools/verify_results_navigation.py --site outputs/20260713_llm_adjudication/dashboard/site --db outputs/20260713_llm_adjudication/raw_outputs/prediction_audit.sqlite --scorecard outputs/20260713_llm_adjudication/dashboard/weekend_scorecard.json
python tools/verify_results_navigation_render.py --site outputs/20260713_llm_adjudication/dashboard/site
```

The scorecard must keep gross recovery separate from safeguard corrections. Audit v3 → v4
recovered 1,623 rows / $8.776M / 218,065 volume into Trusted, while 22,660 previously Trusted
rows / $126.555M / 4.580M volume moved out pending safer validation. Net Trusted therefore
changed by -21,037 rows / -$117.779M / -4.362M volume. Describe this as genuine gross recall
recovery plus a larger defensibility correction—not a net recall increase. A true mAP score is
not defined because this is gated classification, not a ranked retrieval list; report the exact
tier movement and the clearly labeled LLM precision estimate until human labels exist.
