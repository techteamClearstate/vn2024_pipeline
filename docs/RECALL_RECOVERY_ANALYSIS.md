# Recall-recovery analysis — how much can we safely recover, and how?

> Review-only analysis over `outputs/20260710_recall_audit_v2/prediction_audit.sqlite`,
> cross-checked against the governed master `reference/reference.sqlite`
> (`brand_model_master`, 10,392 rows). 2026-07-12. Combined across all six market-years.
> Guiding principle (per the request): **do not chase recall aggressively** — quantify the
> *safe* levers and clearly separate them from losses the guards hold back for good reason.

> **Historical sizing note:** this document remains the governed v2 proposal-sizing
> snapshot. Audit v3 fixes India FY2025 stage attribution by deriving reference status
> from the governed master, but does not apply any proposal or change realized recall.

## Where recall is lost (the two dominant gates)

| Gate | Reason | Rows | Value |
|---|---|---:|---:|
| S07 Reference-master validation | product tuple not in master | 1.27M | $6.23B |
| S12 Final guards | ophthalmic/imaging conflict | 0.35M | $1.43B |

(Plus never-matched coverage gaps at terminal routing: Unmapped $2.37B, manufacturer-only $1.71B.)

## S07 — the recognised-family sub-pool, cross-checked against the master

Of the S07 loss, the part with a **recognised brand/model family** (not blank/Unspecified) is
**359,740 rows / $1,257M**. Cross-checking each family against the master splits it by how safe
recovery is:

> **Important correction (verified against descriptions).** On rows that *failed* S07 the family
> match is frequently **spurious**: e.g. a "Cataract HOYA Vivinex" lens is tagged family
> "Trauma Plates And Screws", a dialysis filter is tagged "CH-S200", a dental fixture is tagged
> "Puros". Across the whole recognised-family pool, the family token **does not even appear in the
> product description for 64% of the value** ($805M of $1,257M). So a clean master mapping is only a
> real lever when the family is **evidenced in the text**. Reference validation (S07) is correctly
> rejecting the spurious majority — the pipeline is doing its job.

| Class (evidence-aware) | Meaning | Value | Share |
|---|---|---:|---:|
| **Safe lever** | family maps to one specific master category **AND appears in the description** | **$180M** | 14% |
| Not in master | genuine catalogue gap → add the product to the master | $272M | 22% |
| Ambiguous (multi-category) | family maps to several master categories → needs disambiguation | $286M | 23% |
| Ambiguous (generic/date-token) | e.g. "March", "Forceps", "Vector" → **correctly held** | $121M | 10% |
| **Likely spurious** | maps to a master category but family is **NOT** in the description → **correctly held** | $398M | 32% |

**Read:** the genuinely *safe* S07 lever is only the **~$180M "Safe lever"** slice (family maps
cleanly *and* is evidenced in the text) — and even that needs per-row verification. The ~$398M
"Likely spurious" and ~$407M ambiguous slices are held back correctly; recovering them would hurt
precision. ~$272M needs deliberate master additions. The dashboard's master cross-check panel shows
this split live; `Recall_Recovery_Proposals.xlsx` contains only the evidenced candidates (~$140M in
the top clusters), each with an `Evidence_Coverage_Pct` and the `Approved` column blank for review.

Genuine evidenced examples (family appears in the text): Biofreedom (BioFreedom drug-eluting stent),
Palacos (PALACOS R+G bone cement), Concerto (CONCERTO cochlear implant), Telescope (rigid endoscope).

## S12 — is the ophthalmic/imaging guard over-suppressing?

Mostly **no**. Of the $1,425M S12 holds back, only **$59.9M / 8,269 rows are reference-valid**
(a catalogued surgical product caught by the guard) — i.e. the guard is ~96% aligned with
reference status. The safe lever here is small: **review those ~$60M reference-valid rows** for a
scope-whitelist refinement (e.g. MRI-conditional cardiac implants like Assurity/Endurity/Entrant).

## The other two large pools (coverage gaps, not filters)

**Manufacturer-only ($1.71B, 753k rows) — a genuine, targeted lever.** Highly concentrated: the
top ~10 makers hold ~81% ($1,380M). Descriptions usually name a known product line, e.g. J&J:
"ATTUNE PS FEM" / "SIGMA STAB" (knee implants), "TECNIS EYHANCE IOL" (intraocular lens). These
matched the maker but no product/family. Safe recovery = add those makers' product families to the
lexicon, per maker, highest value first, in controlled batches (precision-sensitive but the text is
clean). This is the largest genuinely-actionable coverage lever after S07-Clean.

**Unmapped ($2.37B, 571k rows) — largely an India-FY2025 audit-source artifact, NOT a clean gap.**
The Unmapped pool is essentially all India FY2025, whose audit deliberately uses the complete
`data/intermediate/vn_v0_mapped.csv` (pre-final-mapping) source to capture the full 1.68M-row
population. That source attributes everything to Unmapped / manufacturer-only at terminal routing, so
the $2.37B is an **upper bound**, not a directly-actionable production recall gap. It does contain
real surgical products (e.g. Meril "SUPRALIMUS"/"TETRIFLEX" coronary stents, "VOLAR DISTAL RADIUS
PLATE") mixed with out-of-scope items (e.g. "DENTAL FILLING PRODUCTS") and generic text ("Proximal
Shaft Assembly"). Interpret with the India-FY2025 caveat; don't headline it as recoverable recall.

## Net: the safe recall opportunity

| Lever | Approx. value | Effort / risk |
|---|---:|---|
| S12 whitelist — reference-valid caught by guard | ~$60M | Low value, highest confidence |
| S07 "Safe lever" — evidenced family → backfill category + adjudicate | ~$180M (top clusters ~$140M) | Per-row verify; the only genuinely safe S07 slice |
| S07 missing-from-master — add products | ~$272M | Medium; deliberate master growth |
| Manufacturer-only — add top makers' product lines to lexicon | ~$1.38B (top-10 makers) | Larger; precision-sensitive; do per-maker in batches |
| **Held back correctly (do NOT chase)** | ~$398M spurious-family + ~$407M ambiguous (S07) + most of S12 | recovering hurts precision |
| **Not a clean gap (interpret with caveat)** | ~$2.37B Unmapped = India FY2025 audit-source artifact | upper bound, not directly actionable |

Rough prioritisation: start with S12 whitelist (~$60M, safest) and the **evidenced** S07 clusters
(~$140–180M — verify per row), then grow the master for S07 missing-from-master (~$272M), then tackle
the manufacturer-only lexicon per top maker (~$1.38B, biggest but precision-sensitive). Do **not**
bulk-backfill from the S07 family field (~$398M is spurious), do **not** chase the S07 ambiguous
slice, and do **not** headline the India-FY2025 Unmapped number.

All of this is **review-only**. The mechanism to realise it is unchanged: adjudicate → update
`reference/` → governed rerun → re-audit. The dashboard's **Recovery options** tab now shows this
master cross-check live, and `Recall_Recovery_Candidates.csv` carries a `master_check` +
`master_category` column per cluster so the team can start with the "Clean" ones.

## Method / traceability

- Family→category map built from `brand_model_master`; a family is "Clean" when it maps to exactly
  one (segment, sub-segment, product) and is not a registry generic token or a month name.
- Reference-valid = `reference_status ∈ {valid,y,yes,true,1,reference-valid}`.
- Numbers reconcile to the row grain; regenerate with
  `python tools/build_funnel_dashboard.py` (reads the audit + reference DBs read-only).
