# Agent Run Log: Archive Vector Auto Mapping

Timestamp: 2026-07-05 18:04:26 Asia/Shanghai

Request:
Use the old workflow and archive vector auto mapping.

Completed:
- Moved the experimental vector/hybrid retrieval package, config, reports, outputs, and tests into `90_archive_deprecated/vector_auto_mapping_experiment_20260705_180426/`.
- Moved generated vector-experiment Python cache folders into the same archive.
- Removed empty active containers left behind by the vector experiment: `pipeline/`, `configs/`, `reports/`, and `tests/`.
- Left the old deterministic/reference-compliant workflow in place.
- Did not modify the surgical master reference file.
- Did not modify the shared mapped-result workbooks.
- Added an archive manifest documenting status, rationale, contents, and guardrails.

Active workflow:
- `run_pipeline.py`
- `src/`
- `tools/batch_surgical_workflow_remap.py`
- `tools/publish_surgical_current_outputs.py`
- current mapped-result workbooks in the shared mapped-results folder

Archive path:
`90_archive_deprecated/vector_auto_mapping_experiment_20260705_180426/`

Tests and QC:
- Path-safety checks were applied before moving files.
- No workflow tests were required because active production logic was not changed.

Remaining risk:
- Empty `pipeline/`, `configs/`, `reports/`, or `tests/` folders may remain as harmless containers after archiving.
- Any future vector experiment should be explicitly restored from archive or rebuilt in a new research branch.
