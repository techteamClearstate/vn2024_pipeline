# _FOLDER_SPEC — reference/

**Purpose:** central, governed home for every reference table that drives the
mapping pipeline (brand/model master, exclusion lists, usage/mapping lists).

**Trust level:** canonical. The `*_lists/*.csv` files are the single source of
truth for the pipeline's exclusion/usage terms.

**Allowed content**
- `brand_model/`, `companies/` — the reference workbooks (raw-immutable; treat as
  source, do not hand-edit rows).
- `exclusion_lists/*.csv`, `usage_lists/*.csv` — the editable canonical lists.
- `loader.py`, `build_reference_db.py`, `reference.sqlite` — machinery + built DB.
- `README.md`, `registry.yml`, `LINEAGE.md`, this spec — documentation.

**Forbidden content**
- Market/source trade data (belongs in `data/uploads/`).
- Generated pipeline caches / pickles (belong in `data/intermediate/`).
- A second copy of any list — edit the one CSV, never fork it.

**How to update (contract)**
1. Edit the relevant CSV here (not `config/settings.py` — it loads from these).
2. Run `python reference/build_reference_db.py` to refresh `reference.sqlite`.
3. Re-run affected markets and spot-check (see `LINEAGE.md` §4).
4. Update `registry.yml` counts and `memory/recall_90_loop.md`.

**Related**
- Consumers: `config/settings.py`, `src/step1_extract.py`, `src/step2_match.py`,
  `src/step3b_hs_prior.py`.
- Catalogue: `registry.yml` · Lineage: `LINEAGE.md` · Usage: `README.md`.
