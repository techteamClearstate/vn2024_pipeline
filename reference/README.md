# `reference/` — governed reference tables for the mapping pipeline

This folder is the **single, central home** for every reference table that drives
the VN/PK/India surgical trade-data mapping: the brand/model master list, the
exclusion lists, and the usage/mapping lists. It exists so that the data that
controls matching is **queryable, documented, versioned, and lineage-traced** —
not buried as Python literals in `config/settings.py`.

```
reference/
├── README.md                 ← you are here (usage, intent, storage, lineage)
├── registry.yml              ← machine-readable index of every reference table
├── LINEAGE.md                ← source → transform → consumer lineage
├── loader.py                 ← the CSV loaders config/settings.py calls at import
├── build_reference_db.py     ← rebuilds reference.sqlite from the CSVs + master
├── reference.sqlite          ← central queryable DB (generated; committed)
├── brand_model/
│   ├── Surg_Brand_model_list_Master_03July26.xlsx   ← CANONICAL master (active)
│   └── Surg_Brand_model_list_V0.xlsx                ← superseded (provenance)
├── companies/
│   └── List_of_companies_v1.0_Master.xlsx           ← earlier company/sub-OU list
├── exclusion_lists/          ← terms we REMOVE from scope (5 CSVs)
└── usage_lists/              ← terms/maps we USE to place a row (8 CSVs)
```

## The two-way contract: CSV is canonical, DB + config are derived

The `.csv` files under `exclusion_lists/` and `usage_lists/` are the **source of
truth**. Two consumers read them, and neither is allowed to drift:

1. **The pipeline** — `config/settings.py` calls `reference.loader` at import, so
   `BLACKLIST`, `DENTAL_NEGATIVE_CUES`, `CATEGORY_QUALIFIER_MAP`, … are loaded
   from these CSVs (verified byte-identical to the former hard-coded literals).
2. **The database** — `reference.sqlite` is rebuilt from the same CSVs (via the
   loaded config objects) by `build_reference_db.py`.

```
                 ┌────────────────────────┐
   edit here →   │ reference/*_lists/*.csv │  (canonical, human-editable)
                 └───────────┬────────────┘
                     ┌───────┴────────┐
                     ▼                ▼
        config/settings.py     build_reference_db.py
        (pipeline loads)       → reference.sqlite (query/report)
```

**To change a list:** edit the CSV, then run `python reference/build_reference_db.py`
to refresh the DB. Never edit a list in two places.

## How to use it

```bash
# rebuild the database after editing any CSV
python reference/build_reference_db.py

# query the catalogue
sqlite3 reference/reference.sqlite "SELECT list_name, layer, n_rows, consumed_in FROM reference_lists;"

# see every dental exclusion term
sqlite3 reference/reference.sqlite "SELECT value FROM list_values WHERE list_name='dental_negative_cues';"

# the master brand list, in SQL
sqlite3 reference/reference.sqlite "SELECT segment, COUNT(*) FROM brand_model_master GROUP BY segment;"
```

In Python, the lists are just the config attributes you already use:

```python
import config.settings as s
s.DENTAL_NEGATIVE_CUES      # loaded from reference/exclusion_lists/dental_negative_cues.csv
s.CATEGORY_QUALIFIER_MAP    # loaded from reference/usage_lists/category_qualifier_map.csv
```

---

## The reference tables

### File-based references (`brand_model/`, `companies/`)

| File | Role | Status | Notes |
|---|---|---|---|
| `Surg_Brand_model_list_Master_03July26.xlsx` | **canonical brand/model reference** | active | Team master (Mabel × MDT Eurasia). Sheet `Updated (excl. generic)`, header row 0, 10,392 rows. Already drops the 709 generic-flagged families. Feeds the Tier-1 family lookup + Tier-2 category lexicon. Path: `config.settings.V0_REFERENCE_XLSX`. |
| `Surg_Brand_model_list_V0.xlsx` | superseded brand/model reference | superseded | Prior reference; replaced at iter-12. Kept for provenance only. |
| `List_of_companies_v1.0_Master.xlsx` | company / sub-OU reference | reference | Earlier list (sheet `List of companies by sub-OU`, header row 7). Not loaded by the pipeline today; retained as a usage reference. |

### Exclusion lists — terms we remove from scope

> These are the "keep the map surgical" guards. Each is a plain set of terms
> checked **before** a match is accepted. Intentionally narrow to protect recall.

| CSV | `settings.py` | n | Consumed in | Purpose |
|---|---|---|---|---|
| `generic_word_blacklist.csv` | `BLACKLIST` | 206 | step1 (keyword lookup) | Generic words/materials/company names too generic to be Tier-1 family keywords. |
| `category_negative_cues.csv` | `CATEGORY_NEGATIVE_CUES` | 21 | step2 (Tier-2) | Accessory/tool cues (cutter, holder, valvulotome, stopcock) → row is an instrument *around* a device, not the device. |
| `dental_negative_cues.csv` | `DENTAL_NEGATIVE_CUES` | 16 | step2 + step3b (all tiers) | Out-of-scope dental (root canal, gutta percha, endodont, denture). No dental segment exists in the surgical OUs. |
| `generic_label_blacklist.csv` | `GENERIC_LABEL_BLACKLIST` | 5 | step1 (category lexicon) | Vague 2-token Product labels excluded from the label-derived lexicon. |
| `manufacturer_exclude_cues.csv` | `MANUFACTURER_EXCLUDE_CUES` | 3 | step2 (Tier-3) | Veterinary/animal-health cues excluded from maker attribution. |

### Usage / mapping lists — terms & maps we use to place a row

| CSV | `settings.py` | n | Consumed in | Purpose |
|---|---|---|---|---|
| `category_qualifier_map.csv` | `CATEGORY_QUALIFIER_MAP` | 40 | step1/step2 (Tier-2 high) | Qualifier phrase → canonical Product label. Includes Sub-OU-safe reinstatements. |
| `manufacturer_aliases.csv` | `MANUFACTURER_ALIASES` | 30 makers / 39 cores | step1/step2 (Tier-3) | Canonical maker → distinctive lowercase cores searched in the Importer+Exporter blob. |
| `category_heads.csv` | `CATEGORY_HEADS` | 8 | step2 (Tier-2 low) | Bare device heads eligible for the HS8-dominant-segment fallback. |
| `consistency_cues.csv` | `CONSISTENCY_CUES` | 47 | step2 (consistency reranker) | Device-head + anatomy vocabulary the reranker may weigh. |
| `ambiguous_family_keywords.csv` | `AMBIGUOUS_FAMILY_KEYWORDS` | 94 | step2 (ambiguous-brand guard) | Common-English / collision brand keywords released unless the row corroborates the device. |
| `hs_prior_fixation_products.csv` | `HS_PRIOR_FIXATION_PRODUCTS` | 4 | step3b (arthroplasty veto) | Fixation product names never stamped onto a joint-replacement row. |
| `arthroplasty_component_cues.csv` | `ARTHROPLASTY_COMPONENT_CUES` | 18 | step3b (arthroplasty veto) | Joint-replacement cues that trigger the veto. |
| `column_map.csv` | `V0_COLS` | 5 | step1 (reference load) | Reference sheet column → logical output field (schema contract). |

---

## Provenance notes (why terms are on a list)

Moved here from `config/settings.py` so the code stays lean but the reasoning is
preserved. These are the non-obvious decisions worth keeping.

**`generic_word_blacklist` (BLACKLIST)** — three provenance layers:
- Base generic English / materials / bare device words (accessories, titanium,
  balloon, valve, screw…) that appear as "families" in the reference but are too
  generic to match safely.
- Benchmark-driven additions (2026-07), each ~0% product-correct on the
  human-labeled VN ground truth: `titanium, hook, radial, step, consumables,
  peek, dynamic, surgical support, alligator, meril life, ruler, autosuture`.
- Generic-word brand strings that collide with common description words (each
  removed a false-positive product from the $ bound): `liquid` (BiOWiSH
  fertilizer), `combo` (rapid-test kits→DES), `seal` (Angio-Seal→TEVAR), `cobalt`
  (lab standards→CRT-D), `helix` (80% wrong), `export`, `cleaner` (probe
  reagents), `xpress` (immunoassay), `barb` (pancreatic stents→barbed suture),
  `engine` (marine engines→aspiration pumps; real maker still caught by Tier-3),
  `radiopaque` (material descriptor→bone cement).

**`dental_negative_cues`** — the surgical OUs have no dental segment, yet dental
rows leaked via generic tokens. The largest single leak: the family keyword
"Root" (Masimo Root monitor) hit 9,410 dental rows / $17.0M in India — all "root
canal" / "artificial tooth root", zero legit. Validated: catches 22,810 rows /
$41.8M with **0** legit-surgical false exclusions. Deliberately **excludes** bare
`tooth`/`teeth` — those hit legitimate toothed surgical instruments (2-tooth
tracheostomy hook, toothed forceps).

**`ambiguous_family_keywords`** — common-English brand keywords whose Tier-1 hit
is released unless the row names the device. Sample collisions caught:
`trident` (Stryker hip cup → wrongly hit EUS/FNB), `cocoon` (septal occluder →
forced-air blanket), `shark` (resectoscope → spinal fixation), `torque` (HI
TORQUE g-wire → pacemaker accessory), `precision` (Stryker laparoscope → SCS
recharger), `apollo` (iodine soln → NV micro-catheter), `linex` (suture → dental
x-ray), `elite` (powered inst → spirometry). **Held out:** `onyx` (the Medtronic
liquid embolic — terse "ONYX 18" rows lack an embolic token, so guarding it would
drop real recall); `legion` (distinctive S&N knee, mostly correct).

**`category_qualifier_map` — Sub-OU-safe reinstatements** — bare heads `plate` /
`suture` / `mesh` / `cannula` / `screw` are blacklisted for precision, then
recovered ONLY when a qualifier pins one clean Sub-OU: `locking/bone/compression
plate`→Plate, `hernia/surgical mesh`→Synthetic Mesh, `*cannula`→`Cannulae_*`,
`cortical/cancellous/bone screw`→Plates & Screws, `pedicle/poly/mono-axial
screw`→Spinal Fusion Fixation. Ambiguous qualifiers deliberately omitted (`tibial
plate` can be a knee tray; bare `screw` has no Trauma Sub-OU in the reference).

**`arthroplasty_component_cues` + `hs_prior_fixation_products`** — chapters
9018/9021 carry both trauma plating and hip/knee/shoulder arthroplasty. VN GT was
plating-dominant, so shared tokens (hole/shell/head) learned →Trauma_Plating and
over-fired on India's arthroplasty-heavy mix. The veto blocks a fixation fill
whenever the row names a joint-replacement component (femoral head, acetabular
cup, tibial insert…).

---

## What stayed in `config/settings.py` (and why)

Not every constant is a reference *table*. These remain code because they are
either nested rule structures or tuning scalars, not flat lookup lists:

- `TIER1_CONFLICT_GUARDS` — a list of `{product_cue, forbid, allow}` rule dicts
  (per-brand release logic), not a flat table.
- `SURGICAL_HS4`, `SCOPE_EXCLUDE_HS4` — small integer HS-chapter sets bound to
  scope logic.
- All numeric thresholds (`HS_TOKEN_MIN_SHARE`, `CORROB_MIN_N`, …) and path/flag
  constants.

See `registry.yml` for the machine-readable catalogue and `LINEAGE.md` for the
end-to-end data lineage.
