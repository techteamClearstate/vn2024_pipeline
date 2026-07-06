# Vector Auto-Mapping Experiment Archive

Status: archived

Archived timestamp: 2026-07-05 18:04:26 Asia/Shanghai

Reason: user instructed to use the old workflow and archive vector auto mapping.

Active workflow to use:
- Existing deterministic/reference-compliant workflow in `run_pipeline.py`, `src/`, and `tools/`.
- Current remap/publish utilities, especially `tools/batch_surgical_workflow_remap.py` and `tools/publish_surgical_current_outputs.py`.
- Current mapped-result workbooks in the shared mapped-results folder remain the active deliverables.

Archived scope:
- Experimental hybrid/vector retrieval package.
- Hybrid retrieval experiment configuration.
- Vector/hybrid experiment reports.
- Retrieval, exclusion, new-target, metrics, and error-analysis outputs.
- Unit tests created only for the vector experiment.
- Python cache folders generated during the vector experiment.

Important guardrails:
- The vector database/retrieval path is not active production logic.
- Do not use vector similarity as a source of truth for dashboard mapping.
- Do not auto-map from vector-only, manufacturer-only, or generic-token-only evidence.
- Do not update the surgical master reference from new-target discovery without human approval.
- Any future vector work should start from this archive as a research branch, not from the active production workflow.

Archived contents preserve the relative paths they had before archiving:
- `configs/hybrid_retrieval_experiment.yaml`
- `outputs/retrieval_objects.csv`
- `outputs/retrieval_audit.csv`
- `outputs/retrieval_audit.xlsx`
- `outputs/exclusion_audit.xlsx`
- `outputs/new_target_candidates.xlsx`
- `outputs/hybrid_vector_error_analysis.xlsx`
- `outputs/hybrid_vector_metrics_summary.json`
- `outputs/hybrid_retrieval_index_manifest.json`
- `outputs/metrics_summary.xlsx`
- `outputs/gold_label_template.xlsx`
- `pipeline/__init__.py`
- `pipeline/__pycache__/`
- `pipeline/hybrid_retrieval/`
- `reports/current_workflow_diagnostic.md`
- `reports/hybrid_negative_vector_experiment_design.md`
- `reports/hybrid_vector_evaluation_report.md`
- `tests/__pycache__/`
- `tests/test_hybrid_retrieval.py`
