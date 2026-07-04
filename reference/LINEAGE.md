# Data lineage — reference tables → mapped output

How every reference table flows from its source, through the pipeline, into the
mapped workbooks and the dashboard. Read alongside `README.md` (usage) and
`registry.yml` (catalogue).

## 1. Provenance of the reference tables themselves

```
Team master workbook (Mabel × MDT Eurasia, 03 Jul 2026)
  └─ Surg_Brand_model_list_Master_03July26.xlsx
       sheet "Updated (excl. generic)"  ── column I generic flag pre-drops 709 families
       │
       ▼
  reference/brand_model/…Master_03July26.xlsx   (active canonical)
       │  read at step1 via V0_REFERENCE_XLSX + V0_COLS (column_map.csv)
       ▼
  brand_model_master  (10,392 rows, also loaded into reference.sqlite)

Exclusion + usage lists
  originally hand-curated Python literals in config/settings.py
       │  extracted 2026-07-04, byte-verified equal
       ▼
  reference/{exclusion,usage}_lists/*.csv   (CANONICAL, human-editable)
       ├─► config/settings.py  (reference.loader loads at import)
       └─► reference.sqlite     (build_reference_db.py)
```

## 2. Where each table is consumed in the pipeline

```
step1_extract.py   V0_REFERENCE_XLSX + column_map ─► Tier-1 family trie + keyword lookup
                   BLACKLIST                       ─► drop generic family keywords
                   GENERIC_LABEL_BLACKLIST         ─► drop vague labels from category lexicon
                   CATEGORY_QUALIFIER_MAP          ─► Tier-2 high-confidence lexicon
                   MANUFACTURER_ALIASES            ─► Tier-3 alias lexicon (pkl)

step2_match.py     family trie                     ─► Tier-1 family hits
                   CONSISTENCY_CUES                ─► release cross-area collisions
                   AMBIGUOUS_FAMILY_KEYWORDS       ─► release uncorroborated brand hits
                   TIER1_CONFLICT_GUARDS (code)    ─► per-brand release rules
                   CATEGORY_HEADS + QUALIFIER_MAP  ─► Tier-2 category hits
                   CATEGORY_NEGATIVE_CUES          ─► veto accessory/tool rows
                   DENTAL_NEGATIVE_CUES            ─► veto dental rows (all tiers)
                   MANUFACTURER_ALIASES            ─► Tier-3 maker hits
                   MANUFACTURER_EXCLUDE_CUES       ─► veto veterinary rows

step3_map.py       cascade join ─► Segment / Sub-segment / Product / Manufacturer / Family

step3b_hs_prior.py HS-prior fill on product-less rows
                   DENTAL_NEGATIVE_CUES            ─► veto dental fills
                   HS_PRIOR_FIXATION_PRODUCTS
                   + ARTHROPLASTY_COMPONENT_CUES   ─► veto fixation-onto-arthroplasty fills

step4_export.py    styled workbook + Dashboard.html
                   DASHBOARD_BOUND_TIERS {family,category} ─► $ lower/upper bounds
```

## 3. Output lineage

```
market source (data/uploads/<market>.xlsx|csv)
  + reference tables (above)
       ▼  run_pipeline.py --country <C> --source <path>
  data/intermediate/vn_v0_mapped.csv        (per-row map, provenance-tagged)
  data/intermediate/dashboard_<country>.csv (bounded $ slice)
       ▼  step4_export
  outputs/<Country>_ML_Map_Mapped.xlsx      (per market)
  outputs/Dashboard.html                    (combined, all markets)
```

Each mapped row carries `Match_Tier` (family|category|manufacturer) and
`Match_Confidence` (high|med|low) so any output cell is traceable back to the
tier and the reference table that produced it.

## 4. Change protocol (keeps lineage intact)

1. Edit the CSV under `reference/exclusion_lists/` or `reference/usage_lists/`.
2. `python reference/build_reference_db.py` — refresh `reference.sqlite`.
3. Re-run the affected market(s): `python run_pipeline.py --country <C> --source <path>`.
4. Spot-check precision (`tools/spot_check_precision.py`) and, for VN, held-out
   recall/precision (`tools/eval_benchmark.py --split test`).
5. Record the change in `memory/recall_90_loop.md`.

Never edit a list in `config/settings.py` directly — it now loads from the CSVs,
so an in-code edit would be silently overwritten at import and break the DB↔config
equality this folder guarantees.
