# Plain-language improvements for `Surgical_Mapping_Workflow_Guide.html`

> **Status: ready-to-apply recommendations — NOT yet applied.** These edit the
> *governed* guide generator (`tools/build_prediction_audit_reports.py`) and
> require regenerating the guide, which runs the Node/Excel toolchain and writes
> artifact hashes into `prediction_audit.sqlite`. That is a governed mutation of a
> delivery-folder artifact, so it needs an explicit go-ahead. The new
> **Recall_Funnel_Dashboard.html** already delivers plain-language understanding;
> these are optional polish for the denser operator guide.
>
> All rewrites are **additive/minimal** and preserve the exact strings
> `verify_prediction_audit.py` checks for: "not statistical precision",
> "not statistical recall", "MRI separation", "India FY2025", "Pakistan nonstandard",
> and stage IDs S00–S14. After applying, run
> `python tools/build_prediction_audit_reports.py && python tools/verify_prediction_audit.py`.

Source of findings: independent plain-language review (2026-07-12). Each item keeps
the required phrase and adds a one-line clarification for a non-technical reader.

| # | Location (build_prediction_audit_reports.py) | Add / change |
|---|---|---|
| 1 | Metric defs — precision (~L230) | Keep "…not statistical precision." Append: "This means: did the logic run correctly, not whether measurements are mathematically precise." |
| 2 | Metric defs — recall (~L231) | Keep "…not statistical recall; human labels are required." Append: "In plain terms: we found all potential risks by rule, but none are human-verified yet." |
| 3 | Review sample — inference (~L238) | Append: "In simpler terms: the 13 random rows support statistical estimates; the 12 targeted rows were hand-picked for review and can't be used for estimation." |
| 4 | Routing heading (~L476) "Candidate states are not terminal routes" | Add one sentence: "Each record passes through candidate stages (S01–S12) that test conditions, gets a final status at the terminal stage (S13: Trusted / Review / Excluded), then is exported (S14)." |
| 5 | Overview notice — ASP (~L473) | Reword: "Weighted ASP (average selling price) = average dollars per unit across transactions; blank when volume is zero (can't divide)." |
| 6 | Recall-risk — nonstandard/HS-prior (~L477) | Keep "Pakistan nonstandard…". Clarify: nonstandard = unusual formatting; HS-prior = older HS-code-based classification; both stay in Review, never auto-Trusted. |
| 7 | Recall-risk — MRI (~L477) | Keep "MRI separation". Add: "we track three separate things: (1) the label says MRI-safe, (2) it actually conflicts with imaging systems, (3) it's a surgical device used around imaging — listed separately so each is reviewed on its own." |
| 8 | Reviewer sample (~L478) "deterministic stratified-random" | Reword: "12 hand-picked target rows + 13 rows chosen by a fixed algorithm that spreads coverage evenly across data groups (same result every run)." |
| 9 | Overview (~L471) "bounded presentations" | Reword: "SQLite holds the complete row-level data; the workbook and this page show summaries and samples from it." |
| 10 | Metric defs — additive/nonadditive (~L228–229) | Reword: primary reasons = "one main reason per row, safe to count and sum"; secondary reasons = "extra diagnostic notes that overlap — never sum them." |

**Priority if applied:** items 1–3, 6, 7 first (they unblock the core concepts:
metrics, risk categorization, recall). Items 4, 5, 8–10 are lower.

**Decision needed:** apply to the governed generator + regenerate, or leave as-is
(the dashboard covers the plain-language need)?
