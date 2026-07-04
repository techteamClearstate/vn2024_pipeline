# `reference/` — governed reference tables for the mapping pipeline

The single, central home for every reference table that drives the VN/PK/India
surgical trade-data mapping. The lists are modelled as a small **star schema** —
one *catalog* dimension describing each list, over two *typed* fact tables (flat
term lists, and key→value maps) — so the data is queryable, documented, versioned,
lineage-traced, and easy to extend (e.g. blacklists from multiple providers).

```
reference/
├── README.md            ← usage · intent · storage · lineage · provenance
├── list_catalog.csv     ← DIMENSION: one row per list (what each list is)
├── term_lists.csv       ← FACT: all flat term lists + blacklists, provider-aware
├── term_mappings.csv    ← FACT: key → value maps
├── reference.sqlite     ← MACHINE-readable: generated query DB (mirrors the CSVs)
├── loader.py            ← the CSV loaders config/settings.py calls at import
├── build_reference_db.py← rebuilds reference.sqlite from the CSVs + master
├── brand_model/         ← canonical master (active) + V0 (superseded) workbooks
└── companies/           ← earlier company/sub-OU reference
```

## Why a star schema (not one generic table)

Each table holds only the columns that make sense for its content type, so it is
self-documenting. The catalog is the parent; the two fact tables are children
keyed by `list_name` / `map_name`. This is the same hierarchy a single table
would give, but typed — which is what makes `term_lists` a natural home for the
`provider` and `status` columns.

| table | grain | key columns |
|---|---|---|
| `list_catalog` | one row per list | `list_name`, `layer`, `content_type`, `match_type`, `settings_symbol`, `consumed_in`, `purpose` |
| `term_lists` | one row per term (per provider) | `list_name`, `term`, `provider`, `status`, `notes` |
| `term_mappings` | one row per mapping | `map_name`, `key`, `value`, `provider`, `notes` |

Plus `brand_model_master` (the 10,392-row canonical brand list) and `source_files`
(file lineage) in the DB.

### List families (`list_group`)

Each catalog row also carries a `list_group` so related lists form a queryable
family — combined *where it makes sense*, without physically merging lists that
apply differently:

| `list_group` | lists | meaning |
|---|---|---|
| `scope_exclude` | dental, veterinary, cosmetic, imaging, lab_ivd, general | **the general out-of-scope negative cues** — different domains, one family; extend by adding a new list here or rows to an existing one |
| `accessory` | category_negative_cues | in-scope but an instrument *around* the device (kept separate — a different kind of negative) |
| `generic` | generic_word_blacklist, generic_label_blacklist | generic-word / vague-label suppression |
| `reranker` · `hs_prior_guard` · `mapping` | the usage lists | matching vocab, HS-prior guards, key→value maps |

```sql
-- the whole out-of-scope negative-cue family, in one query
SELECT list_group, list_name, n_active FROM list_catalog WHERE list_group='scope_exclude';
```

The out-of-scope domains are grouped as one family but stay separate lists because
they can apply to different fields/stages (e.g. dental across all tiers, veterinary
also on the trade-party blob at Tier-3); `SCOPE_EXCLUDE_CUES` in `config/settings.py`
is the runtime dict over the same six.

## Human file vs machine file

The **CSVs are canonical** (git-diffable, open in Excel — edit here).
**`reference.sqlite` is generated** from them (`python reference/build_reference_db.py`)
and is the machine/query layer — it can join the lists against the brand master,
which flat CSVs can't. `config/settings.py` loads the CSVs directly at import
(stdlib `csv`, no pandas), so a CSV edit takes effect immediately.

Verified **identical to the original inline literals** (all 13 loaded objects
equal `dc7776f`), so this reorganization changed no matching behavior.

## Multi-provider blacklists

`term_lists` is provider-aware, which is how lists from different sources combine
without losing attribution:

- **Combine** — append each provider's rows. The loader returns
  `active` terms de-duplicated, so the same term from two providers collapses to
  one effective entry (both rows are kept for the record).
- **Attribution** — every term carries its `provider`; audit or remove one
  provider's whole contribution with a single filter
  (`… WHERE provider='client_X'`).
- **Lifecycle** — `status ∈ {active, candidate, retired}`. A term you don't want
  applied (a known false positive, or a not-yet-approved candidate) is set to
  `retired`/`candidate` — kept for provenance but excluded from the pipeline.

```
# combine a new provider's dental blacklist: just add rows
list_name,term,provider,status,notes
dental_negative_cues,veneer,client_X,active,client-supplied
dental_negative_cues,implant,vendor_Y,retired,false positive — kept out
```

All current terms are tagged `provider=internal, status=active`.

## How to use it

```bash
# 1. edit a list  (add/retire rows in term_lists.csv or term_mappings.csv)
# 2. refresh the query DB
python reference/build_reference_db.py
# 3. re-run affected markets + spot-check (see “Change protocol” below)
```

Query examples:

```sql
-- the catalogue, with live active/total counts
SELECT list_name, layer, content_type, n_active, n_total, consumed_in FROM list_catalog;
-- one blacklist, with provenance
SELECT term, provider, status FROM term_lists WHERE list_name='dental_negative_cues';
-- everything one provider contributed
SELECT list_name, term FROM term_lists WHERE provider='client_X' AND status='active';
-- the brand master
SELECT segment, COUNT(*) FROM brand_model_master GROUP BY segment;
```

In Python the lists are the config attributes you already use:

```python
import config.settings as s
s.DENTAL_NEGATIVE_CUES      # term_lists.csv, list_name=dental_negative_cues (active terms)
s.CATEGORY_QUALIFIER_MAP    # term_mappings.csv, map_name=category_qualifier_map
```

## The lists

**Exclusion — terms removed from scope** (narrow, to protect recall):
`generic_word_blacklist` (206), `category_negative_cues` (21),
`dental_negative_cues` (16), `generic_label_blacklist` (5),
`manufacturer_exclude_cues` (3).

**Usage / mapping — terms & maps used to place a row:**
`category_qualifier_map` (40) and `manufacturer_aliases` (30/39) in
`term_mappings.csv`; `category_heads` (8), `consistency_cues` (47),
`ambiguous_family_keywords` (94), `hs_prior_fixation_products` (4),
`arthroplasty_component_cues` (18) in `term_lists.csv`.

See `list_catalog.csv` for each list's layer, match type, the `settings.py` symbol
it feeds, and where it is consumed.

### File-based references

| File | role | status |
|---|---|---|
| `brand_model/…Master_03July26.xlsx` | canonical brand/model reference (`V0_REFERENCE_XLSX`, sheet `Updated (excl. generic)`, 10,392 rows) | active |
| `brand_model/…V0.xlsx` | prior brand/model reference | superseded |
| `companies/List_of_companies_v1.0_Master.xlsx` | company/sub-OU reference (not loaded by the pipeline) | reference |

## Provenance notes (why terms are on a list)

- **`generic_word_blacklist`** — base generic words/materials/bare device words;
  benchmark-driven additions (~0% product-correct on VN GT: `titanium, hook,
  autosuture…`); collision brand strings each removing a false $ line (`liquid`→
  fertilizer, `seal`→Angio-Seal, `helix` 80% wrong, `engine`→marine engines…).
- **`dental_negative_cues`** — surgical OUs have no dental segment. Biggest leak:
  the "Root" (Masimo) keyword hit 9,410 dental rows / $17.0M in India. Catches
  22,810 rows / $41.8M with **0** legit-surgical false cuts. Excludes bare
  `tooth`/`teeth` (toothed forceps are real).
- **`ambiguous_family_keywords`** — common-English brand keywords released unless
  the row names the device (`trident`, `cocoon`, `precision`, `apollo`, `linex`,
  `elite`…). Held out: `onyx`, `legion`.
- **`category_qualifier_map`** — Sub-OU-safe reinstatements: blacklisted bare
  heads `plate/suture/mesh/cannula/screw` recovered only when a qualifier pins one
  clean Sub-OU (`locking plate`→Plate, `hernia mesh`→Synthetic Mesh…).
- **`arthroplasty_component_cues` + `hs_prior_fixation_products`** — the veto that
  blocks a fixation fill when the row names a joint-replacement component.

## Lineage & change protocol

```
Team master workbook (Mabel × MDT Eurasia, 03 Jul 2026)
  └─ reference/brand_model/…Master_03July26.xlsx  (drops 709 generic families)
        │ step1 loads via V0_REFERENCE_XLSX + V0_COLS
        ▼
  Tier-1 family trie + Tier-2 category lexicon

list_catalog.csv · term_lists.csv · term_mappings.csv  (canonical)
  ├─► config/settings.py  (loaded at import; feeds step1/step2/step3b guards)
  └─► reference.sqlite    (query / join)

market source (data/uploads/…) + reference tables
  ─► run_pipeline.py ─► vn_v0_mapped.csv + dashboard_<country>.csv
  ─► outputs/<Country>_ML_Map_Mapped.xlsx + Dashboard.html
```

**To change a list (keeps lineage intact):**
1. Edit `term_lists.csv` / `term_mappings.csv` (not `config/settings.py` — it
   loads from these). Add a new list → also add its `list_catalog.csv` row.
2. `python reference/build_reference_db.py` — refresh `reference.sqlite`.
3. Re-run affected markets: `python run_pipeline.py --country <C> --source <path>`.
4. Spot-check (`tools/spot_check_precision.py`); for VN, held-out eval
   (`tools/eval_benchmark.py --split test`). Record in `memory/recall_90_loop.md`.

## Kept in `config/settings.py` as code (not reference data)

`V0_COLS` (a 5-row reference→output schema contract), `TIER1_CONFLICT_GUARDS`
(nested `{product_cue, forbid, allow}` rule dicts), `SURGICAL_HS4` /
`SCOPE_EXCLUDE_HS4` (integer HS-chapter sets), and all numeric thresholds — these
are logic/tuning/schema, not provider-editable lookup lists.
