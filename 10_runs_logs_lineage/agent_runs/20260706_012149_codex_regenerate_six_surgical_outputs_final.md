# Six-workbook surgical mapping regeneration

## Run metadata

- Completed: 2026-07-06 01:21:49 +08:00
- Agent: Codex
- Objective: regenerate the six current surgical mapping workbooks using the deterministic old workflow and publish only the latest workbook for each country/year to the shared mapped-results folder.
- Active workflow: deterministic alias/rule/evidence workflow. Vector auto-mapping remained archived and was not used.
- Archived vector experiment: `C:\Users\Administrator\Documents\Working Folder\vn2024_pipeline\90_archive_deprecated\vector_auto_mapping_experiment_20260705_180426`
- Input snapshot: `C:\Users\Administrator\Documents\Working Folder\vn2024_pipeline\90_archive_deprecated\six_workbook_input_snapshot_20260705_233256`
- Master reference: `C:\Users\Administrator\Documents\Working Folder\vn2024_pipeline\reference\brand_model\Surg_Brand_model_list_Master_03July26.xlsx`
- Local output folder: `C:\Users\Administrator\Documents\Working Folder\vn2024_pipeline\outputs\remapped_current`
- Local combined QA report: `C:\Users\Administrator\Documents\Working Folder\vn2024_pipeline\outputs\remapped_current\reports\All_Countries_Surgical_Mapping_QA_Report.xlsx`
- Shared output folder: `G:\共享云端硬盘\New EIU Gateway\0. Gateway Ops & Databases\Import Data Master\6. Workflow\Surgicals\Claude code\1. Mapped Results`

## Published current files

The shared mapped-results folder was left with exactly seven current xlsx files:

| File | Purpose |
|---|---|
| `Pakistan_FY2024_ML_Map_Mapped.xlsx` | Current Pakistan FY2024 mapped workbook |
| `Pakistan_FY2025_ML_Map_Mapped.xlsx` | Current Pakistan FY2025 mapped workbook |
| `India_FY2024_ML_Map_Mapped.xlsx` | Current India FY2024 mapped workbook |
| `India_FY2025_ML_Map_Mapped.xlsx` | Current India FY2025 mapped workbook |
| `Vietnam_FY2024_ML_Map_Mapped.xlsx` | Current Vietnam FY2024 mapped workbook |
| `Vietnam_FY2025_ML_Map_Mapped.xlsx` | Current Vietnam FY2025 mapped workbook |
| `MAPPING_IMPROVEMENT_LOG.xlsx` | Excel-format mapping improvement log and metadata |

## Validation summary

Combined QA report validation status: 132 PASS checks, 0 FAIL checks.

| Country | Year | Trusted rows | Review rows | Excluded rows | Trusted value USD | Review value USD | Excluded value USD | Validation failures |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Pakistan | 2024 | 2,921 | 15,071 | 66,653 | 46,293,274.44 | 167,860,550.99 | 398,322,547.11 | 0 |
| Pakistan | 2025 | 3,085 | 18,989 | 74,219 | 57,979,996.73 | 202,880,845.45 | 511,911,032.02 | 0 |
| India | 2024 | 163,820 | 467,810 | 0 | 684,305,526.52 | 1,399,752,425.84 | 0.00 | 0 |
| India | 2025 | 215,689 | 832,886 | 0 | 984,546,738.72 | 2,256,436,240.88 | 0.00 | 0 |
| Vietnam | 2024 | 52,478 | 146,842 | 321,515 | 260,905,009.41 | 541,784,710.49 | 2,434,133,008.41 | 0 |
| Vietnam | 2025 | 55,217 | 125,155 | 377,671 | 250,897,233.95 | 422,376,166.59 | 1,518,187,381.87 | 0 |

## Workflow changes active in this run

- Kept vector auto-mapping out of the active remap and retained it only in the archive.
- Rebuilt each workbook with the current output structure and added auditable sheets for candidates, extended-HS review, alias/reference requests, precision-risk rows, generic-token QC, potential missed surgical rows, cluster summaries, excluded surgicalish screens, gold-label templates, validation, and routing rules.
- Applied deterministic guardrails for date/month token risks and APT March token handling.
- Split reference update requests into clean requests, generic-token rejections, and human-review-needed requests.
- Preserved master-reference validation gates for trusted family-tier and category-tier rows.
- Published the Excel-format mapping improvement log to the shared folder.

## Notes

- The combined QA report should be used as the release validation artifact for this run.
- The shared mapped-results folder should continue to keep only the six current mapped workbooks plus `MAPPING_IMPROVEMENT_LOG.xlsx`.
- No LLM calls and no token costs were used in this regeneration.
