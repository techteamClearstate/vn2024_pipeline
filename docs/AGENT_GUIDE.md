# Agent Operating Guide — Surgical Import-Data Enrichment Pipeline

> **Audience: AI agents** working in this repository. Read this file first, then
> load only what the task needs. The improvement roadmap lives in
> [REFERENCE_COMPLIANCE_PLAN.md](REFERENCE_COMPLIANCE_PLAN.md).
> Last updated: 2026-07-04 (after the Pakistan FY2024 reference-compliance pass).

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
| `tools/*.py` (others) | Benchmarks, diagnostics, precision spot-checks | yes |
| `reference/` | **Governed reference data** — brand master + all exclusion/usage lists. See `reference/README.md`. Edit the CSVs, then run `python reference/build_reference_db.py`. NEVER edit lists in settings.py | via CSVs |
| `reference/brand_model/Surg_Brand_model_list_Master_03July26.xlsx` | Canonical brand/model master (= `cfg.V0_REFERENCE_XLSX`). Sheets: `Updated` (full, 11,101 rows incl. 709 generic-flagged), `Updated (excl. generic)` (10,392 rows — used for matching) | no (analyst-owned) |
| `data/uploads/` | Market source workbooks/CSVs (input). Treat as immutable raw data | no |
| `data/intermediate/` | Regenerable caches: `vn_rawdata.tsv`, `vn_v0_mapped.csv`, lexicon pickles, `reference_tuples.pkl`, `dashboard_<market>.csv` slices. **Single-file caches are overwritten per market run** | regenerated |
| `outputs/` | One workbook per market-year + `Dashboard.html` + methodology. See §2.2 | generated |
| `docs/` | This guide, the improvement plan, improvement-methods notes | yes |

### 2.2 Outputs (`outputs/`)

| File | Status |
|---|---|
| `Pakistan_FY2024_ML_Map_Mapped.xlsx` | **CURRENT for PK FY2024** — produced by `tools/reference_compliance.py` on 2026-07-04 (trusted 3,758 rows / $67.75M; hard-value sheets) |
| `Pakistan_FY2024_DQ_Compliance_Report.xlsx` | Companion 7-sheet DQ report for the above |
| `Pakistan_ML_Map_Mapped.xlsx` | Pipeline-generated PK FY2024 output — **pre-compliance, superseded**; will be regenerated (still non-compliant) until the plan's Phase 1 lands |
| `Vietnam_ML_Map_Mapped.xlsx`, `India_ML_Map_Mapped.xlsx` | FY2024 pipeline outputs (iter-13 gate, not yet compliance-passed) |
| `Vietnam_FY2025_…`, `Pakistan_FY2025_…`, `India_FY2025_…` | FY2025 pipeline outputs (iter-13 gate) |
| `Dashboard.html`, `VN2024_Methodology.html/.pdf` | Cross-market interactive dashboard + methodology |

### 2.3 Stakeholder delivery folder (shared drive — publish here, not just the repo)

`G:\Shared drives\New EIU Gateway\0. Gateway Ops & Databases\Import Data Master\6. Workflow\Surgicals\Claude code\`
(bash: `/g/共享云端硬盘/New EIU Gateway/0. Gateway Ops & Databases/Import Data Master/6. Workflow/Surgicals/Claude code/`)

| Subfolder | Contents |
|---|---|
| `1. Mapped Results/` | The 6 deliverable workbooks (`<Market>_FY<yr>_ML_Map_Mapped.xlsx`) + `Pakistan_FY2024_DQ_Compliance_Report.xlsx` |
| `2. Interactive Dashboard/` | `Dashboard.html` + methodology (keep together) |
| `3. Reference Brand Lists/` | Master brand list copies |
| `4. Manual Mapped Files/` | Analyst-built comparison workbooks |
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
```

- **Market order matters: PK → India → VN LAST** (the VN run rebuilds
  transfer_prior and the combined Dashboard).
- Windows/Git Bash: always prefix `PYTHONIOENCODING=utf-8`; never pipe
  `run_pipeline` through `head` (SIGPIPE kills it) — use `| tail`.
- Excel hard cap 1,048,576 rows → India export uses matched-only + truncation
  fallback; QA numbers are computed from the full frame, not the sheet.

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

## 5. Current market-state snapshot (2026-07-04)

| Market-year | Lower / Upper bound | Basis |
|---|---|---|
| Pakistan FY2024 | **$56.6M / $67.8M** | reference-compliance pass (521 line items) |
| Pakistan FY2025 | $65.2M / $82.7M | iter-13 gate |
| Vietnam FY2024 | $253.8M / $370.9M | iter-13 gate |
| Vietnam FY2025 | $254.2M / $331.9M | iter-13 gate |
| India FY2024 | $746.1M / $846.6M | iter-13 gate |
| India FY2025 | $1,080.7M / $1,199.5M | iter-13 gate |

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
