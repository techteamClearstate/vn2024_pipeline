# Read me first — the surgical mapping workflow, in plain English

*A 2-minute orientation. For concrete row examples and the review-only gate
playground, open
[`Recall_Funnel_Dashboard.html`](../outputs/20260710_recall_audit_v2/Recall_Funnel_Dashboard.html)
in any browser.*

## What this does

We take every shipment row from the customs import data, try to recognise the surgical
product in the free-text description, and sort each row into one of three buckets:

| Bucket | Plain meaning | Use it for |
|---|---|---|
| ✅ **Trusted** | A known surgical product, checked against our master list, no red flags. | The revenue dashboard and roll-ups. |
| 🔶 **Review** | Real evidence, but one check didn't pass (usually: the product isn't in our master yet). | The recall-recovery backlog — worth a human look. |
| ⛔ **Excluded** | No product evidence, or clearly out of scope (vet/dental/cosmetic/imaging). | Mostly ignore; spot-check the biggest ones. |

**Nothing is ever deleted.** Lower-confidence rows are parked, not lost.

## The workflow in six plain steps

1. **Load** every shipment row from the source file.
2. **Match** the description to our master list: brand/model → product category → maker.
3. **Standardise** the labels so they can be checked.
4. **Reference check** — the product must exist in the governed master list to be Trusted. *(biggest filter)*
5. **Safety guards** — remove out-of-scope look-alikes (vet/dental/cosmetic/imaging) and ambiguous tokens. *(second filter)*
6. **Route** each row to Trusted / Review / Excluded, and export the views.

## Where recall (kept data) is lost

Two steps cause most of the drop-off:

- **Reference check (Step 4)** — **$6.23B** held back because the product isn't in the master yet.
- **Ophthalmic/imaging guard (Step 5)** — **$1.43B** held back as imaging-type equipment.

## Can we get some of it back — safely?

Yes, but **much less than it first appears**, and only carefully (we are **not** chasing recall
aggressively). A key check: on rows that failed the reference step, the recognised "family" is often
**wrong** (e.g. a cataract lens mislabelled "Trauma Plates And Screws") — which is exactly why they
were held back. So we only count a family as recoverable when it **actually appears in the product
description**. Ordered by how safe it is:

1. **~$60M** — reference-valid products wrongly caught by the imaging guard → fix the whitelist. *(safest)*
2. **~$180M** — "Safe lever": a specific product recognised, its family present in the text, category just not filled in → backfill + adjudicate per row.
3. **~$272M** — genuine gaps → add these products to the master.
4. **~$1.38B** — maker recognised but product missing (concentrated in ~10 makers, e.g. J&J ATTUNE/SIGMA/TECNIS) → add their product lines to the lexicon, per maker. *(biggest, precision-sensitive)*

**Leave alone:** ~$398M where the family match is spurious (not in the description — the pipeline
correctly held these), ~$407M of ambiguous/generic/date-token matches (recovering them hurts
accuracy), and the ~$2.37B "Unmapped" figure (an India-FY2025 data-source quirk, not a real gap).

All recovery is **review-only**: adjudicate → update `reference/` → rerun → re-audit. Nothing is auto-applied.

For measured precision, business analysts label the 150 rows on the `Review Samples`
sheet in the governed shared-drive workbook
`4. Manual Mapped Files/Prediction_Funnel_and_Review.xlsx`. This is the single
labeling venue; the workbook does not itself change production routing.

## Explore the gates without changing production

Open **What-if playground** in the dashboard and uncheck one or more of the seven
real gates. The page immediately recalculates the potential Trusted population,
separating rows released directly from rows likely to be held by another enabled
gate. Expand the examples to see descriptions, makers, families, mapped products,
segments, values, and QA statuses. S13 coverage gaps and the India FY2025 audit-
source artifact remain visible but cannot be toggled. Copy or download the proposed
adjudication note when a pattern merits analyst review; the simulator never edits
the pipeline, reference files, or published workbooks.

## The deliverables

| File | What it is |
|---|---|
| [`outputs/20260710_recall_audit_v2/Recall_Funnel_Dashboard.html`](../outputs/20260710_recall_audit_v2/Recall_Funnel_Dashboard.html) | Interactive dashboard: funnel, concrete row examples, breakdowns, hotspots, recovery, seven-gate what-if playground, steps, glossary. |
| [`outputs/20260710_recall_audit_v2/Recall_Recovery_Candidates.csv`](../outputs/20260710_recall_audit_v2/Recall_Recovery_Candidates.csv) | 180 ranked recovery candidates (safest first) with a master-check column. |
| [`outputs/20260710_recall_audit_v2/Prediction_Funnel_and_Review.xlsx`](../outputs/20260710_recall_audit_v2/Prediction_Funnel_and_Review.xlsx) | Governed reviewer workbook; its 150-row `Review Samples` sheet is the business-team precision-label venue. |
| [`RECALL_RECOVERY_ANALYSIS.md`](RECALL_RECOVERY_ANALYSIS.md) | The quantified recall-recovery write-up. |
| [`RECALL_FUNNEL_DASHBOARD_PLAN.md`](RECALL_FUNNEL_DASHBOARD_PLAN.md) | How it was built + progress log. |
| `tools/build_funnel_dashboard.py`, `tools/verify_funnel_dashboard.py`, `tools/verify_funnel_dashboard_render.py` | Rebuild (read-only) + verify numbers/examples/masks against SQLite and exercise 1,904 browser states. |

**Vocabulary:** OU = Segment · Sub-OU = Sub-segment · Device = Product · ASP = value ÷ volume.
Every number reconciles to the row-level authority `prediction_audit.sqlite`. This whole layer is
**review-only** — it never changes production routing, the reference lists, or the published workbooks.
