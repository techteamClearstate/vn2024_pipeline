# vn2024_pipeline — agent entry point

Surgical import-trade-data enrichment (Vietnam / Pakistan / India, FY2024+FY2025).

**Before non-trivial work, read [docs/AGENT_GUIDE.md](docs/AGENT_GUIDE.md)** —
it holds the full file map (repo + outputs + shared-drive delivery folder),
run commands, QA vocabulary, and the publish protocol. The active improvement
roadmap is [docs/REFERENCE_COMPLIANCE_PLAN.md](docs/REFERENCE_COMPLIANCE_PLAN.md).

Non-negotiables (details in the guide):

- `data/uploads/` and analyst workbooks are immutable raw sources.
- Reference lists are governed in `reference/*.csv` → edit CSV, run
  `python reference/build_reference_db.py`; never hard-code lists in code.
- Never delete rows from mapped workbooks — park them via `QA_Status`.
- Run markets end-to-end, order PK → India → VN last; then `python qc_check.py`.
- Windows: prefix `PYTHONIOENCODING=utf-8`; don't pipe `run_pipeline.py`
  through `head` (SIGPIPE) — use `| tail`.
- Publishing = delivery folder update (workbook + archive + `DATA_UPDATES_LOG.md`
  + `OUTPUT_TRACKER.md` + `index.html`), not just repo `outputs/`.
- When the workflow changes, update `docs/AGENT_GUIDE.md` (and the plan doc) in
  the same change.
