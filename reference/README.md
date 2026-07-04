# `reference/` — governed reference tables for the mapping pipeline

The single, central home for every reference table that drives the VN/PK/India
surgical trade-data mapping: the brand/model master list, plus all exclusion and
usage lists. It exists so the data that controls matching is **queryable,
documented, versioned, and lineage-traced** — not buried as Python literals.

```
reference/
├── README.md                 ← usage · intent · storage · lineage · provenance
├── reference_lists.csv       ← HUMAN-readable canonical: ALL 13 lists in one file
├── reference.sqlite          ← MACHINE-readable: generated query DB
├── loader.py                 ← the CSV loaders config/settings.py calls at import
├── build_reference_db.py     ← rebuilds reference.sqlite from the CSV + master
├── brand_model/
│   ├── Surg_Brand_model_list_Master_03July26.xlsx   ← CANONICAL master (active)
│   └── Surg_Brand_model_list_V0.xlsx                ← superseded (provenance)
└── companies/
    └── List_of_companies_v1.0_Master.xlsx           ← earlier company/sub-OU list
```

## Two files, two jobs (human vs machine)

There are exactly two representations of the lists, and one is generated from the
other so they can never drift:

| File | Audience | Role |
|---|---|---|
| **`reference_lists.csv`** | human | **Canonical.** One editable file holding all 13 lists. Git-diffable, opens in Excel. **Edit here.** |
| **`reference.sqlite`** | machine | **Generated.** Query the lists in SQL, or join them against the 10,392-row `brand_model_master` (which a flat CSV can't do). Rebuilt from the CSV. |

```
   edit →  reference_lists.csv   (canonical, one human file)
                  │
        ┌─────────┴──────────┐
        ▼                    ▼
 config/settings.py   build_reference_db.py
 (pipeline loads,      → reference.sqlite
  stdlib csv only)       (query / join)
```

The pipeline loads the **CSV** directly (stdlib `csv`, no pandas/sqlite at
import), so a CSV edit takes effect immediately — the CSV is the source of truth,
the DB is the analytical companion. Verified **identical to the original inline
literals** (all 13 objects equal), so this reorganization changed no behavior.

## How to use it

```bash
# 1. edit a list
#    (open reference_lists.csv, add/remove a row for the relevant list_name)
# 2. refresh the query DB
python reference/build_reference_db.py
# 3. re-run affected markets + spot-check (see “Change protocol” below)
```

Query examples:

```bash
sqlite3 reference/reference.sqlite "SELECT list_name, layer, n_values, consumed_in FROM reference_lists;"
sqlite3 reference/reference.sqlite "SELECT value FROM list_entries WHERE list_name='dental_negative_cues';"
sqlite3 reference/reference.sqlite "SELECT segment, COUNT(*) FROM brand_model_master GROUP BY segment;"
```

In Python the lists are just the config attributes you already use:

```python
import config.settings as s
s.DENTAL_NEGATIVE_CUES      # from reference_lists.csv, list_name=dental_negative_cues
s.CATEGORY_QUALIFIER_MAP    # from reference_lists.csv, list_name=category_qualifier_map
```

## `reference_lists.csv` schema

One row per value. `kind` tells the loader how to reconstruct the object:

| column | meaning |
|---|---|
| `list_name` | which list this row belongs to |
| `layer` | `exclusion` \| `usage` \| `schema` |
| `kind` | `set` (unordered) \| `ordered` \| `map` (key→value) \| `alias` (key→[values]) |
| `seq` | position within the list (order for `ordered`/`alias`) |
| `key` | map/alias key (empty for `set`/`ordered`) |
| `value` | the term, or the map/alias value |

## The lists (13)

### Exclusion — terms removed from scope (narrow, to protect recall)

| list_name | symbol | n | consumed in | purpose |
|---|---|---|---|---|
| `generic_word_blacklist` | `BLACKLIST` | 206 | step1 | Generic words/materials/company names too generic to be Tier-1 keywords. |
| `category_negative_cues` | `CATEGORY_NEGATIVE_CUES` | 21 | step2 | Accessory/tool cues → instrument *around* a device; vetoes the category hit. |
| `dental_negative_cues` | `DENTAL_NEGATIVE_CUES` | 16 | step2 + step3b | Out-of-scope dental; drops dental leakage across all tiers. |
| `generic_label_blacklist` | `GENERIC_LABEL_BLACKLIST` | 5 | step1 | Vague 2-token Product labels excluded from the category lexicon. |
| `manufacturer_exclude_cues` | `MANUFACTURER_EXCLUDE_CUES` | 3 | step2 | Veterinary/animal cues excluded from maker attribution. |

### Usage / mapping — terms & maps used to place a row

| list_name | symbol | n | consumed in | purpose |
|---|---|---|---|---|
| `category_qualifier_map` | `CATEGORY_QUALIFIER_MAP` | 40 | step1/step2 | Qualifier phrase → Product label (Tier-2 high), incl. Sub-OU-safe reinstatements. |
| `manufacturer_aliases` | `MANUFACTURER_ALIASES` | 30/39 | step1/step2 | Canonical maker → distinctive cores (Tier-3). |
| `category_heads` | `CATEGORY_HEADS` | 8 | step2 | Bare heads eligible for the HS8-segment fallback. |
| `consistency_cues` | `CONSISTENCY_CUES` | 47 | step2 | Device-head + anatomy vocabulary for the consistency reranker. |
| `ambiguous_family_keywords` | `AMBIGUOUS_FAMILY_KEYWORDS` | 94 | step2 | Common-English/collision keywords released unless the row corroborates. |
| `hs_prior_fixation_products` | `HS_PRIOR_FIXATION_PRODUCTS` | 4 | step3b | Fixation names never stamped onto a joint-replacement row. |
| `arthroplasty_component_cues` | `ARTHROPLASTY_COMPONENT_CUES` | 18 | step3b | Joint-replacement cues that trigger the fixation-fill veto. |
| `column_map` | `V0_COLS` | 5 | step1 | Reference sheet column → logical output field (schema contract). |

### File-based references

| File | role | status | notes |
|---|---|---|---|
| `brand_model/…Master_03July26.xlsx` | canonical brand/model reference | active | Sheet `Updated (excl. generic)`, header row 0, 10,392 rows; drops 709 generic-flagged families. `config.settings.V0_REFERENCE_XLSX`. |
| `brand_model/…V0.xlsx` | brand/model reference | superseded | Prior reference; kept for provenance. |
| `companies/List_of_companies_v1.0_Master.xlsx` | company/sub-OU reference | reference | Not loaded by the pipeline today; retained as usage reference. |

## Provenance notes (why terms are on a list)

- **`generic_word_blacklist`** — base generic words/materials/bare device words;
  benchmark-driven additions (~0% product-correct on VN GT: `titanium, hook,
  autosuture, …`); and collision brand strings each removing a false $ line
  (`liquid`→fertilizer, `seal`→Angio-Seal, `helix` 80% wrong, `engine`→marine
  engines, `radiopaque`→material descriptor, …).
- **`dental_negative_cues`** — surgical OUs have no dental segment. Biggest leak:
  the "Root" (Masimo) keyword hit 9,410 dental rows / $17.0M in India. Catches
  22,810 rows / $41.8M with **0** legit-surgical false cuts. Deliberately excludes
  bare `tooth`/`teeth` (toothed forceps, tracheostomy hooks are real).
- **`ambiguous_family_keywords`** — common-English brand keywords released unless
  the row names the device: `trident` (hip cup→EUS), `cocoon` (occluder→blanket),
  `precision` (laparoscope→SCS), `apollo` (iodine→NV catheter), `linex`/`elite`…
  **Held out:** `onyx` (real liquid embolic, terse rows lack a cue), `legion`.
- **`category_qualifier_map`** — Sub-OU-safe reinstatements: bare heads
  `plate/suture/mesh/cannula/screw` are blacklisted, recovered only when a
  qualifier pins one clean Sub-OU (`locking plate`→Plate, `hernia mesh`→Synthetic
  Mesh, `pedicle screw`→Spinal Fusion Fixation…).
- **`arthroplasty_component_cues` + `hs_prior_fixation_products`** — 9018/9021
  carry both trauma plating and arthroplasty; the veto blocks a fixation fill when
  the row names a joint-replacement component (femoral head, acetabular cup…).

## Lineage & change protocol

```
Team master workbook (Mabel × MDT Eurasia, 03 Jul 2026)
  └─ reference/brand_model/…Master_03July26.xlsx  (drops 709 generic families)
        │ step1 loads via V0_REFERENCE_XLSX + column_map
        ▼
  Tier-1 family trie + Tier-2 category lexicon

reference_lists.csv  (canonical)
  ├─► config/settings.py  (loaded at import; feeds step1/step2/step3b guards)
  └─► reference.sqlite    (query/join)

market source (data/uploads/…) + reference tables
  ─► run_pipeline.py ─► vn_v0_mapped.csv + dashboard_<country>.csv
  ─► outputs/<Country>_ML_Map_Mapped.xlsx + Dashboard.html
```

Each mapped row carries `Match_Tier` + `Match_Confidence`, so any output cell is
traceable back to the tier and the reference list that produced it.

**To change a list (keeps lineage intact):**
1. Edit the row(s) in `reference_lists.csv` (not `config/settings.py` — it loads
   from the CSV, so an in-code edit would do nothing).
2. `python reference/build_reference_db.py` — refresh `reference.sqlite`.
3. Re-run affected markets: `python run_pipeline.py --country <C> --source <path>`.
4. Spot-check (`tools/spot_check_precision.py`); for VN, held-out eval
   (`tools/eval_benchmark.py --split test`). Record in `memory/recall_90_loop.md`.

## Kept in `config/settings.py` as code (not flat tables)

`TIER1_CONFLICT_GUARDS` (nested `{product_cue, forbid, allow}` rule dicts),
`SURGICAL_HS4` / `SCOPE_EXCLUDE_HS4` (integer HS-chapter sets), and all numeric
thresholds — these are logic/tuning, not lookup lists.
