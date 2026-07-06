# Codex Run Log - Regenerate Six Surgical Mapping Outputs

## Run Metadata

| Field | Value |
|---|---|
| Timestamp | 2026-07-05 22:04:58 +08:00 |
| Operator | Codex |
| Request | Regenerate all six current surgical mapping workbooks in the shared Mapped Results folder |
| Workflow mode | Old deterministic/reference-compliant workflow |
| Vector auto mapping | Archived and not used |
| Repository | `C:\Users\Administrator\Documents\Working Folder\vn2024_pipeline` |
| Shared output folder | `G:\共享云端硬盘\New EIU Gateway\0. Gateway Ops & Databases\Import Data Master\6. Workflow\Surgicals\Claude code\1. Mapped Results` |
| Master reference | `Surg_Brand_model_list_Master 03July26.xlsx` |
| Combined QA report | `C:\Users\Administrator\Documents\Working Folder\vn2024_pipeline\outputs\remapped_current\reports\All_Countries_Surgical_Mapping_QA_Report.xlsx` |
| Mapping improvement log | `G:\共享云端硬盘\New EIU Gateway\0. Gateway Ops & Databases\Import Data Master\6. Workflow\Surgicals\Claude code\1. Mapped Results\MAPPING_IMPROVEMENT_LOG.xlsx` |
| Archived vector experiment | `C:\Users\Administrator\Documents\Working Folder\vn2024_pipeline\90_archive_deprecated\vector_auto_mapping_experiment_20260705_180426` |

## Command Run

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' `
  'C:\Users\Administrator\Documents\Working Folder\vn2024_pipeline\tools\batch_surgical_workflow_remap.py' `
  --input-dir 'G:\共享云端硬盘\New EIU Gateway\0. Gateway Ops & Databases\Import Data Master\6. Workflow\Surgicals\Claude code\1. Mapped Results'
```

## Rule And Audit Changes Used

| Area | Change |
|---|---|
| Exclusion controls | Added expanded controls for pharmaceutical/vaccine, donation/humanitarian, ophthalmic/intraocular, cochlear/hearing, blood pressure monitor, suction generator, food/nutrition, and general medical supplies. |
| Generic token controls | Added month names and additional high-risk family tokens including Signia, Stride, Enterprise, Concerto, Legion, Lens, and Exacta. |
| Reference QA | Added clean and rejected reference-update request views. |
| Precision QA | Added false-positive screen for trusted rows. |
| Output discipline | Published only the six current mapped workbooks to the shared folder; no extra mapped workbook variants remain there. |

## File-Level Output Metrics

| File | Raw Rows | Trusted Rows | Review Rows | Excluded Rows | Trusted Value USD | Validation Failures |
|---|---:|---:|---:|---:|---:|---:|
| Pakistan_FY2024_ML_Map_Mapped.xlsx | 84,645 | 2,921 | 15,071 | 66,653 | 46,293,274.44 | 0 |
| Pakistan_FY2025_ML_Map_Mapped.xlsx | 96,293 | 3,085 | 18,989 | 74,219 | 57,979,996.73 | 0 |
| India_FY2024_ML_Map_Mapped.xlsx | 631,630 | 163,820 | 467,810 | 0 | 684,305,526.52 | 0 |
| India_FY2025_ML_Map_Mapped.xlsx | 1,048,575 | 215,689 | 832,886 | 0 | 984,546,738.72 | 0 |
| Vietnam_FY2024_ML_Map_Mapped.xlsx | 520,835 | 52,478 | 146,842 | 321,515 | 260,905,009.41 | 0 |
| Vietnam_FY2025_ML_Map_Mapped.xlsx | 558,043 | 55,217 | 125,155 | 377,671 | 250,897,233.95 | 0 |

## Validation Summary

| Check | Result |
|---|---|
| Combined validation failures | 0 |
| Tier row reconciliation to RawData | PASS for all six files |
| Tier value reconciliation to RawData | PASS for all six files; India FY2025 had only a -0.000001 rounding delta within tolerance |
| Tier UniqueID reconciliation to RawData | PASS for all six files |
| RawData duplicate UniqueID count | 0 for all six files |
| Trusted family latest-master full-key failures | 0 for all six files |
| Trusted family strict no-generic failures | 0 for all six files |
| Trusted category latest-master key failures | 0 for all six files |
| Trusted rows with Scope_Flag | 0 for all six files |
| Trusted rows with Ref_Valid not equal to Y | 0 for all six files |
| Trusted rows with QA_Status not mapped | 0 for all six files |
| Dashboard aggregation value delta | 0 for all six files |
| Dashboard aggregation quantity delta | 0 for all six files |
| Trusted high-confidence exclusion conflicts | 0 for all six files |
| Trusted pharmaceutical/vaccine conflicts | 0 for all six files |
| Trusted date-month token false positives | 0 for all six files |
| Trusted category-tier rows with weak product evidence | 0 for all six files |
| Capture recall proxy | >= 0.95 for all six files |
| Trusted precision proxy | >= 0.90 for all six files |

## Shared Folder Inventory

The shared Mapped Results folder contains exactly these six mapped workbooks:

| Current Workbook |
|---|
| India_FY2024_ML_Map_Mapped.xlsx |
| India_FY2025_ML_Map_Mapped.xlsx |
| Pakistan_FY2024_ML_Map_Mapped.xlsx |
| Pakistan_FY2025_ML_Map_Mapped.xlsx |
| Vietnam_FY2024_ML_Map_Mapped.xlsx |
| Vietnam_FY2025_ML_Map_Mapped.xlsx |

Additional allowed support files in the same folder:

| Support File |
|---|
| `_ABOUT.txt` |
| `MAPPING_IMPROVEMENT_LOG.xlsx` |
| `Surgical_Mapping_Workflow_Guide.html` |

