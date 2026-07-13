# Recall Funnel Dashboard & Understandability — Working Plan

> **Status doc for a long-running improvement loop.** Goal: make the prediction-audit
> output easy to understand, add a funnel dashboard, and surface where recall is lost
> and where it can (carefully) be recovered. **Review-only** — no production routing,
> reference, or workbook changes. Current authority = `outputs/20260712_recall_audit_v3/prediction_audit.sqlite`;
> recovery sizing below remains explicitly the `20260710_recall_audit_v2` historical baseline.
> Last updated: 2026-07-12.

## What the user asked for

1. Don't chase recall aggressively, but find safe recall-recovery opportunities.
2. Make **each step of the output easy to understand** (plain language).
3. An **HTML output** explaining what the output means, what each step means, and how to
   integrate the data.
4. A **funnel dashboard**: after each step, how much data is **left** vs **lost**, and how
   that varies by **file, OU (=Segment), sub-OU (=Sub-segment), device (=Product/Family),
   family, manufacturer, value, volume, ASP**.
5. Identify the **two steps that hurt recall the most** and whether we can improve them.
6. Clear, explainable, traceable results; simple language for the workflow.

Vocabulary mapping for this domain: **OU = Segment, Sub-OU = Sub-segment, Device = Product_V0/Family.**

## Key findings (from the SQLite authority, 2026-07-12)

The additive recall funnel uses `row_fact.removal_stage_id` + `primary_reason` — each row is
attributed to the single stage where it left the Trusted path (sums exactly to the total; no
double counting). Cross-file, the recall drains rank:

| Stage | Primary reason | Rows | Value |
|---|---|---:|---:|
| **S07 Reference Validation** | `reference_tuple_invalid` (mapped Segment×Sub-seg×Product not in master) | 1.27M | **$6.23B** |
| S13 Terminal | `Unmapped` (never matched — IN_2025 only) | 0.57M | $2.37B |
| S13 Terminal | `Audit - manufacturer only` (maker matched, no product) | 0.75M | $1.71B |
| **S12 Remap Guards** | `ophthalmic_imaging_conflict` | 0.35M | **$1.43B** |
| S13 Terminal | `Review - unspecified category` | 0.07M | $0.19B |

**The two production filters that cause the most recall hurt: S07 (reference validation) and
S12 (ophthalmic/imaging guard).** S07 dominates by a wide margin. "Unmapped" and
"manufacturer only" are *never-matched* populations (a coverage problem, not a filter).

**India FY2025 attribution fix:** IN_2025 is still ingested from the complete
`data/intermediate/vn_v0_mapped.csv`, but v3 derives master-validation and binary
reference status from the governed surgical master during audit ingestion. Reference
failures now route to S07 while genuine never-matched coverage gaps stay at S13. This
does not change production mappings, QA status, or Trusted/Review/Excluded totals.

Recovery levers (review-only surfacing, then normal adjudication loop):
- **S07**: rows whose mapped triple is a *loose* match to the master (spacing/punctuation) or a
  real surgical product missing from the master → adjudication → `reference/` → governed rerun.
- **S12 ophthalmic_imaging_conflict**: rows the guard suppressed that are actually surgical →
  scope whitelist refinement.

## Deliverables & progress

- [x] **D0 — Explore & confirm data model** (funnel_cube, removal_cube, row_fact additive funnel).
- [x] **D1 — `tools/build_funnel_dashboard.py`** (+ `tools/_funnel_dashboard_template.py`): read-only
      reader of the sqlite authority; precomputes the additive funnel per file + combined, breakdown
      cubes per removal stage by all 9 dimensions incl. value/volume/ASP bands, and recall-hotspot
      ranking; emits a self-contained HTML. Output: `outputs/20260710_recall_audit_v2/Recall_Funnel_Dashboard.html` (227 KB).
- [x] **D2 — Funnel Dashboard HTML**: 6 tabs — Overview, The funnel (waterfall), Breakdowns explorer,
      Recall hotspots (two-step analysis), Steps explained, Glossary. **Validated**: JSON reconciles to
      sqlite for all 6 files + combined (rows/value/Trusted/additive all exact); 753 render paths, 0 JS
      errors (headless Node harness — browser preview channel was flaky in this env).
- [x] **D3 — Plain-language explainer** — delivered *inside* the dashboard (Overview + Steps explained +
      Glossary tabs) rather than a separate file; one cohesive artifact is easier to understand.
- [x] **D4 — Recall-recovery opportunity view**: added a **Recovery options** tab that partitions all
      held-back value into 5 confidence-rated, non-overlapping buckets (mis-guarded surgical → loose-match
      → manufacturer-only → weak → other), with top recoverable clusters per bucket and an explicit
      false-positive warning (date-token families). Review-only; feeds the adjudication loop.
- [x] **D5 — Verification + governance + docs**: `tools/verify_funnel_dashboard.py` (**53/53 PASS**:
      per-scope reconciliation + recovery-bucket partition + no-external-refs). AGENT_GUIDE §7 updated;
      run log `10_runs_logs_lineage/agent_runs/20260712_claude_recall_funnel_dashboard.md`.
- [x] **D6 — Polish**: added an actionable **`Recall_Recovery_Candidates.csv`** worklist (180 ranked
      candidates: mis-guarded / loose-match / manufacturer-only, per market + combined) emitted by the
      builder; cross-linked the dashboard footer → workflow guide + CSV. Browser screenshot still blocked
      by the env (preview MCP times out on its own seed page) — validated headlessly instead.
- [x] **D7 — Adversarial self-QC + fixes**: independent subagent review confirmed the core logic/claims
      are correct; applied its HIGH/MED clarity+accessibility findings — (1) funnel-bar segment tooltips,
      (2) reworded the misleading S12 "removes" phrasing (now: flags unless strong independent surgical
      evidence), (3) a persistent India-FY2025 caveat banner on **every** tab when the combined view is
      selected, (4) CSV now sorts safest-first, (5) an Unmapped-vs-Unspecified note in the Breakdowns tab.
      Re-validated: verify 53/53, headless 10/10 content checks, 0 errors.
- [ ] **Optional — publish** to the shared delivery folder (outward-facing → needs explicit user go-ahead
      + full publish protocol). Not done without confirmation.
- [ ] **Optional — plain-language review of the existing `Surgical_Mapping_Workflow_Guide.html`** (the
      governed operator narrative) for any confusing wording; higher-risk since its generator is verified,
      so note improvements rather than change lightly.

- [x] **D8 — Master cross-check deep-dive** (2026-07-12 it.8): builder now also reads
      `reference/reference.sqlite` and classifies the S07 recognised-family pool ($1,257M) vs the master:
      **$578M Clean** (safe lever) / $272M missing-from-master / ~$400M ambiguous (correctly held).
      S12 guard ~96% correct (~$60M reference-valid over-suppression). Added a live master cross-check
      panel + `master_check`/`master_category` CSV columns; write-up in `docs/RECALL_RECOVERY_ANALYSIS.md`.
      verify 53/53, headless 12/12 content checks, 0 errors.

- [x] **D9 — Other recall pools characterised** (2026-07-12 it.9): manufacturer-only ($1.71B, top-10
      makers = 81%, identifiable product lines like J&J ATTUNE/SIGMA/TECNIS → per-maker lexicon lever);
      Unmapped ($2.37B) shown to be almost entirely an India-FY2025 audit-source artifact (complete
      pre-mapping CSV) → an upper bound, not a clean gap. Refined recovery bucket text + analysis doc.
      verify 53/53, headless 774/0.

- [x] **D10 — CRITICAL correction: family field is spurious on S07-failed rows** (2026-07-12, doing 1/2/3):
      building the recovery proposals surfaced that the recognised `family` on S07-failed rows is usually
      WRONG (cataract lens tagged "Trauma Plates And Screws" etc.). Verified: for **64% ($805M) of the
      $1,257M** recognised-family value the family token isn't even in the description. Added a
      description-alignment check to the S07 classification: **Safe lever = ~$180M** (evidenced), not the
      earlier overstated $578M; $398M is "Likely spurious" (correctly held). Corrected the dashboard, CSV,
      `RECALL_RECOVERY_ANALYSIS.md`, `RECALL_FUNNEL_README.md`, memory. New tool
      `tools/build_recall_recovery_proposals.py` emits `Recall_Recovery_Proposals.xlsx` (evidence-gated,
      ~$140M, Approved blank) for Option 3. verify 53/53, headless 14/14.
- [x] **Option 2 — guide plain-language edits + regenerate**: applied the plain-language edits to
      `tools/build_prediction_audit_reports.py` (metric definitions, ASP, routing heading, MRI separation,
      nonstandard/HS-prior, stratified sample, precision/recall) preserving all verify-required strings.
      Regenerated `docs/Surgical_Mapping_Workflow_Guide.html` (now the DB-driven guide, 37 KB — the old
      110 KB hard-coded guide is retired per `build_surgical_workflow_guide.py`'s own note). All 6 sections
      + 15 stages present. `verify_prediction_audit.py` = **PASS** (db + html). CAVEAT: the Excel workbook
      `Prediction_Funnel_and_Review.xlsx` cannot be built in this env (bundled node/Excel tool aborts,
      exit 134) — it never existed for this run; the 6 metric-table edits that feed the workbook Read Me
      are in source but await a working Excel toolchain. Guide regenerated via an HTML-only path.
- [x] **Option 1 — publish corrected artifacts to shared delivery folder** (2026-07-12): **additive** publish
      (nothing overwritten/archived), clearly labeled **review-only**. Added to `2. Interactive Dashboard/`:
      `Recall_Funnel_Dashboard.html`, `Recall_Recovery_Candidates.csv`, `Recall_Recovery_Proposals.xlsx`,
      `Surgical_Mapping_Workflow_Guide.html`. Added to `5. Documentation/`: `RECALL_FUNNEL_README.md`,
      `RECALL_RECOVERY_ANALYSIS.md`. Updated `DATA_UPDATES_LOG.md` (2026-07-12 review-only entry),
      `index.html` (new "Recall funnel & understandability · review-only" section), `README.md`
      (review-only section), `OUTPUT_TRACKER.md` (review-only note). All 6 files + 4 nav/log updates verified present.

- [x] **D11 — Excel workbook builder reworked to openpyxl** (2026-07-12): replaced the crashing bundled
      node/Excel artifact-tool with a pure-Python `tools/_prediction_audit_workbook.py` (openpyxl). Same
      seven governed sheets in the same order (Read Me · Funnel · Removal Cube · Review Samples · Recall
      Risks · Reconciliation QC · Source Lineage), with the Review-sample dropdowns and QC conditional
      formatting. `build_prediction_audit_reports.py::build_workbook` now calls it (no node dependency).
      Produced `Prediction_Funnel_and_Review.xlsx` (20.7 MB, 144,478-row Removal Cube). **FULL
      `verify_prediction_audit.py` = PASS** (db + workbook + html). The retired `.mjs` is left in place, unused.

- [x] **D12 — Business Explainability Playground (A1–A4)** (2026-07-12): extended the existing
      builder/template rather than forking it. Added deterministic top-value + pseudo-random concrete
      examples per file × removal stage × primary reason (994 unique rows; 488,673-byte examples payload),
      example expanders in Funnel, Hotspots, and Recovery, and an exact client-side simulator over 112
      file × primary-gate × secondary-mask groups. Seven real gates are toggleable; S13 is visible and
      locked. Added per-gate guidance plus copy/download adjudication notes. Authority verification is
      **100/100 PASS**; the headless harness passes **1,904/1,904 states** (all tabs × scopes × 128 masks,
      desktop + mobile) with zero JavaScript errors. Published additively as review-only per the shared-
      drive protocol; no production mapping, reference, or workbook changed.

- [x] **D13 — Governed reviewer workbook published (Track D2)** (2026-07-12): published the verified
      20.7 MB `Prediction_Funnel_and_Review.xlsx` additively to shared-drive
      `4. Manual Mapped Files/`. The copy matches the local artifact byte-for-byte (SHA-256
      `A40D3CC1E8AA205542D930EC796C6EF3E32DF1FFD7FAE7CC8093BD11E473A5CB`). The `Review Samples`
      sheet is now the single business-team labeling venue for Track C; no label is applied to
      production until it passes through the governed adjudication workflow.

- [x] **D14 — Precision measurement scaffold (Track C2)** (2026-07-12): added a governed,
      idempotent `tools/ingest_precision_labels.py` with check-only validation and workbook-hash
      lineage. The dashboard Overview now reports design-weighted random-sample relevance,
      mapping correctness, and end-to-end accuracy with 95% intervals, while purposeful targeted
      rows remain separate and unweighted. Acceptance checks reconcile the payload to
      `review_label`. Current state is honestly `Awaiting analyst labels` (0/150); this work does
      not change production routing or realized recall.

- [x] **D15 — India FY2025 audit attribution repair (Track D3)** (2026-07-12): the complete
      CSV source is enriched in-memory from the governed surgical master. Detailed master
      validation remains traceable while the rule registry receives its expected binary
      reference status. S07 now captures reference failures and S13 retains genuine coverage
      gaps. Production source files, mapped fields, QA status, and final tiers are unchanged;
      exact v2-v3 reconciliation and artifact verification are recorded in the run log.

- [x] **D16 — Reviewer workbook synchronized to v3** (2026-07-12): check-only ingestion found
      the shared reviewer workbook still carried the v2 deterministic sample (3 missing and 3
      unexpected identities versus v3). Because it contained 0 reviewer labels, the prior file
      was archived and the v3-generated workbook published in its place. Check-only validation
      now passes with 150/150 identities and 0/150 labels; production routing is unchanged.

## Status: EXPLAINABILITY PLAYGROUND COMPLETE; ANALYST ADJUDICATION NEXT
All six original user asks are delivered, reconciled to the row-level authority, self-contained, and
independently QC'd. The business-explainability playground is also delivered. Next progress depends on
business analysts reviewing `Recall_Recovery_Proposals.xlsx`/S12 candidates and the 150-row precision
sample; no simulated result is a production decision.

`Recall_Recovery_Candidates.csv` is intentionally ranked rather than exhaustive: the combined S12
section contains the top 15 families (~$45.3M), while the dashboard quantifies and explains the full
reference-valid S12 opportunity (~$60M). Analysts should treat the CSV as a prioritization queue, not
as proof that every candidate has been reviewed.

The approval-ready recovery workbook now includes a conservative S12 subset:
125 named-family clusters / 7,302 rows / $54.3M where the reference-valid family
is explicit in the source description. The remaining reference-valid S12 rows
stay held. Approved S12 rows feed only the governed surgical-context whitelist
and require the normal end-to-end rerun before any production recall changes.

## Design notes

- Self-contained HTML: all data embedded as JSON, vanilla JS, no external fetches (works from the
  shared drive and as a Claude Artifact). Match the delivery-folder standalone-HTML convention.
- Additive funnel is the backbone (no double counting). The diagnostic `funnel_cube` candidate
  views are kept as an "advanced" drill-down, clearly separated from the clean waterfall.
- Metric toggle: transactions / value (USD) / volume. ASP = value ÷ volume (weighted; NULL when
  volume 0). Keep `<Unmapped>` distinct from `Unspecified`; keep Review distinct from Excluded.
- Top-N (with an "Other" bucket) per breakdown slice to keep the file small.

## Loop log
- 2026-07-12 it.1: explored repo + sqlite; confirmed additive funnel & the two-step finding;
  wrote this plan.
- 2026-07-12 it.2: built + validated the dashboard (D1/D2/D3). All numbers reconcile to the
  authority; 753 render paths pass headlessly. Deliverable: `Recall_Funnel_Dashboard.html`.
  Rebuild with `PYTHONIOENCODING=utf-8 python tools/build_funnel_dashboard.py`.
- 2026-07-12 it.3: added Recovery-options tab (D4) + `verify_funnel_dashboard.py` (D5, 53/53 PASS)
  + AGENT_GUIDE §7 + run log. Browser preview MCP unresponsive (env issue) — validated headlessly
  (774 paths, 0 errors). All six CORE user asks now delivered & reconciled.
- 2026-07-12 it.4 (D6): builder now also emits `Recall_Recovery_Candidates.csv` (180 ranked candidates);
  dashboard footer cross-links the workflow guide + CSV. verify 53/53, headless 774/0. Core work complete.
- 2026-07-12 it.5 (D7): ran an adversarial QC subagent; applied its clarity/accessibility fixes
  (funnel-bar tooltips, S12 rewording, persistent ALL-scope India caveat banner, safest-first CSV,
  Unmapped/Unspecified note). Re-validated 53/53 + 10/10 content checks. **CORE COMPLETE.**
- 2026-07-12 it.6: added a simple "workflow at a glance" flow map to the Overview (marks the two
  recall-loss gates); verify 53/53, headless 774/0. Launched a plain-language review of the existing
  governed `Surgical_Mapping_Workflow_Guide.html`.
- 2026-07-12 it.7: captured the guide review's 10 safe plain-language rewrites in
  `docs/WORKFLOW_GUIDE_PLAIN_LANGUAGE_RECOMMENDATIONS.md` (NOT applied — editing the governed guide +
  regenerating writes to the sqlite authority, so it needs an explicit user go-ahead).
  **Substantive scope exhausted → loop PAUSED.** Awaiting user decisions (publish? apply guide edits?).
- 2026-07-12 it.8 (D12): added concrete examples and the seven-gate what-if playground, analyst
  copy/download notes, exact mask/example verification (100/100), and exhaustive headless rendering
  (1,904 states, 0 JS errors). Republished the dashboard additively with review-only labeling.
- 2026-07-12 it.9 (D13): published the governed reviewer workbook to shared-drive
  `4. Manual Mapped Files/`, linked it from the portal, and verified a byte-identical SHA-256 copy.
- 2026-07-12 it.10 (D14): added governed precision-label validation/ingestion and the dashboard
  measured-accuracy panel; random estimates are design-weighted, targeted rows are descriptive,
  and the blank 150-row venue displays an explicit awaiting-labels state.
