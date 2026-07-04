# Workflow Improvement Plan — Reference Compliance & Beyond

> **Audience: AI agents and reviewers.** This is the authoritative plan for
> bringing the whole enrichment workflow up to the latest surgical master
> reference, following the Pakistan FY2024 DQ pass of 2026-07-04. Read
> [AGENT_GUIDE.md](AGENT_GUIDE.md) first for the file map and vocabulary.
>
> Status legend: ✅ done · 🔲 open · 🅑 blocked on business decision

---

## 0. Context — why this plan exists

A stakeholder DQ review of the Pakistan FY2024 output demanded compliance with
the latest master (`reference/brand_model/Surg_Brand_model_list_Master_03July26.xlsx`):
family-tier rows must match the **full** master key (not just the category
triple the iter-13 gate checked), labels must use the master's exact wording,
Extended-HS and generic-family rows must be parked for review, and no
veterinary/dental/cosmetic/lab-IVD/imaging rows may remain in the trusted
dashboard.

**Phase 0 (done)** implemented this as a workbook-level post-process,
`tools/reference_compliance.py`, and applied it to Pakistan FY2024:

- Trusted dashboard: 3,897 rows / $74.5M → **3,758 rows / $67.75M**
  (lower bound $56.6M, 521 line items), every trusted row exact-master-valid.
- 1,388 rows relabelled to master wording
  (e.g. `Conventional Suture_Absorbable` → `Conventional Suture - Absorbable`).
- Parked: $5.9M generic-token capital-equipment anomalies (incl. a $5.35M
  robotic-surgery console under family "Light Source" and a $1.69M Elekta Unity
  MR-linac counted as knee replacement "Unity"), $2.3M player/family pairs not
  in the master, $0.3M category conflicts, $0.4M new scope-keyword catches.
- Restored: $2.1M of MRI-conditional pacemakers/ICDs ("Attesta/Sphera/Primo
  MRI") that the old imaging cue had wrongly excluded.
- Deliverables: `outputs/Pakistan_FY2024_ML_Map_Mapped.xlsx` +
  `outputs/Pakistan_FY2024_DQ_Compliance_Report.xlsx`, published to the
  delivery folder `1. Mapped Results/` (old file archived in `9. Archive/`).

**The gap this plan closes:** the compliance rules live only in the post-process
tool. The pipeline (`src/step3_map.py`) still applies the weaker iter-13 gate,
so re-running any market regenerates non-compliant output, and the other five
market-years have never had the stricter pass.

---

## 1. Phase 1 — Fold the compliance rules into the pipeline 🔲

**Goal:** every pipeline run produces compliant output by construction; the
post-process tool becomes a verification/audit step, not a correction step.

**End state / definition of done**

- `python run_pipeline.py --country Pakistan --source <PK FY2024 file>`
  reproduces `outputs/Pakistan_FY2024_ML_Map_Mapped.xlsx` semantics:
  **trusted = 3,758 rows / $67,750,722** (the regression anchor).
- Running `tools/reference_compliance.py` on any fresh pipeline output makes
  **zero changes** (0 relabels, 0 status changes).
- `qc_check.py` passes for all six market-years.

**Implementation steps** (reuse the logic in `tools/reference_compliance.py` —
`norm_loose`, `load_master`, the family/category decision trees — rather than
re-deriving it):

1. **`src/step1_extract.py` → `build_reference_tuples()`** (~line 279):
   besides the category triples, pickle into `reference_tuples.pkl`:
   - the strict full-key set (exact-normalized 5-tuples from master rows with
     blank `Generic Family Name?`),
   - the loose-key → canonical-labels map (for relabelling),
   - the generic-only full-key map (loose + exact),
   - the (player, family)-loose → canonical-categories index (for
     `Review - reference category conflict`).
2. **`src/step3_map.py` → `apply_reference_gate()`** (~line 138): replace the
   triple-only check with the tier decision trees from the tool (§4 of the
   AGENT_GUIDE): full-key family validation with canonical relabelling; the new
   QA statuses; Extended parking (delete the `QA_MAPPED_EXT` /
   `Mapped - reference-valid (Extended HS scope)` path — Extended rows get
   `Review - surgical product in Extended HS scope` and blank `Dash_Include`);
   the family-name-token whitelist; the generic-token anomaly rule.
3. **`config/settings.py`**: add the new QA vocabulary constants; keep flags
   `REFERENCE_HARDGATE` / `APPLY_SCOPE_EXCLUSIONS`.
4. **Governance**: move the keyword lists that currently live in the tool
   (`SCOPE_KEYWORDS`, `SURGICAL_CONTEXT_WHITELIST`, `GENERIC_TOKENS`,
   `CAPITAL_EQUIPMENT_CUES`, `SURGICAL_CANDIDATE_TERMS`) into
   `reference/term_lists.csv` (+ `list_catalog.csv` rows), rebuild
   `reference.sqlite`, and load them in settings like the existing cue lists.
5. **`src/step4_export.py`**: Scope sheet gains the
   `Extended (ref-valid, pending review)` row semantics; Dashboard formulas
   still key on `Dash_Include` so they need no change, but verify the QA tab
   reflects the new vocabulary.
6. **`qc_check.py`**: add invariants — every `Dash_Include=Y` family row's
   5-key is in the strict master set; no `Dash_Include=Y` row has
   `Match_Scope=Extended`.
7. **Re-run all six market-years, order PK → India → VN LAST** (VN rebuilds
   transfer_prior + the combined Dashboard); `qc_check.py` after each.
8. Verify the PK FY2024 regression anchor, then **commit** (note: iter-12/13
   working-tree changes are still uncommitted — land as one reviewed PR to
   `github.com/techteamClearstate/vn2024_pipeline`).
9. Publish refreshed workbooks per the delivery protocol (AGENT_GUIDE §2.3) and
   update `docs/AGENT_GUIDE.md` §2.2/§5.

> A pre-scoped task chip "Fold reference-compliance rules into pipeline gate"
> exists for this phase.

---

## 2. Phase 2 — Business decisions the data is staged for 🅑

These need stakeholder input; the data is already prepared in
`outputs/Pakistan_FY2024_DQ_Compliance_Report.xlsx` (delivery copy in
`1. Mapped Results/`).

1. **Extended-HS inclusion** — sheet `Extended_Surgical_Review`: $10.8M / 1,017
   reference-valid surgical rows under non-core HS, aggregated by
   HS4 × category × family, sorted by revenue. Decision per block: include
   (→ widen `cfg.SURGICAL_HS4` or add an explicit allow-list) or exclude
   (→ leave parked). Record the ruling in the delivery `DATA_UPDATES_LOG.md`.
2. **Master-list gaps** — sheet `Reference_Hard_Issues`: $2.6M of player/family
   pairs absent from the master (top: Getinge Group "Hybrid" $0.96M, Medtronic
   "SafeSheath II" $0.48M). Per combo: add to the master workbook (then rows
   re-validate on the next run) or confirm the match is wrong (leave parked).
   Master edits are analyst-owned — propose, don't edit their workbook.
3. **Anomaly confirmations** — the 42 parked generic-token rows ($5.9M) are
   near-certain mis-mappings, but decide whether surgical-robot capital
   equipment ("MIS platforms") belongs in scope, and under which family, before
   the $5.35M console row is finalized either way.

---

## 3. Phase 3 — Recall recovery & roll-out to other markets 🔲

1. **Unmatched surgical backlog (PK FY2024)** — sheet
   `Unmatched_Surgical_Candidates`: 1,544 rows / $22.5M of unmatched shipments
   whose descriptions contain surgical terms, sorted by revenue. Harvest new
   brand/model aliases into the master + `reference/term_mappings.csv`
   (manufacturer aliases), following the held-out eval protocol used in
   iters 1–12 (see `tools/eval_benchmark.py`, `tools/harvest_from_benchmark.py`).
2. **Apply compliance to the other five market-years** — after Phase 1 this is
   just a re-run; if Phase 1 is delayed, run
   `tools/reference_compliance.py` per workbook (it is market-agnostic) and
   publish workbook + report pairs the same way as Pakistan FY2024.
   Expect the same label-drift and generic-token classes.
3. **Further matching improvements** — ranked backlog in
   [IMPROVEMENT_METHODS.md](IMPROVEMENT_METHODS.md) (multi-candidate re-ranker,
   LLM re-rank of ambiguous high-$ collisions, embedding similarity, …).

---

## 4. Verification checklist (any phase)

```bash
# pipeline invariants (after each market run)
PYTHONIOENCODING=utf-8 python qc_check.py

# compliance no-op check (Phase 1 done-criterion)
PYTHONIOENCODING=utf-8 python tools/reference_compliance.py \
  --workbook outputs/<Market>_ML_Map_Mapped.xlsx --country <Market> \
  --out /tmp_check.xlsx --report /tmp_report.xlsx
# → log must show "relabelled 0 rows" and unchanged trusted counts
```

Manual checks: trusted bounds vs §5 of AGENT_GUIDE; delivery-folder docs
(`DATA_UPDATES_LOG.md`, `OUTPUT_TRACKER.md`, `index.html`) consistent with the
workbooks actually in `1. Mapped Results/`.

## 5. Risks / gotchas

- **Cache overwrite**: intermediates are single-file per market — never
  interleave two markets' stages; always run a market end-to-end.
- **Relabelled dimensions differ across markets** until Phase 1 + re-runs
  complete: PK FY2024 uses master wording, the other five still use pipeline
  canonical labels — the combined `Dashboard.html` will show both spellings
  until then.
- **Keyword screens are review triggers, not deletes**: bare tokens (`control`,
  `ct`) are deliberately word-bounded; extend the whitelist rather than
  weakening the trigger when false positives appear, and log every adjudication
  in the report's `Final_Action_Log`.
- **India scale**: ~2M rows; keep gate logic vectorized (the iter-13
  implementation notes in `src/step3_map.py` explain the memory ceiling).
