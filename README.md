# VN 2024 ML Map — Enrichment Pipeline

Maps Vietnam 2024 medical-device import trade data against a curated surgical
brand model list. Each import row's free-text product description is scanned for
known device model / family names; on a match the row is tagged with its
segment, sub-segment, product, manufacturer and family name, then exported with
matched rows highlighted light green.

---

## Folder structure

```
vn2024_pipeline/
├── run_pipeline.py          # single end-to-end runner
├── qc_check.py              # read-only regression invariants (run after pipeline)
├── requirements.txt
├── README.md
├── config/
│   └── settings.py          # paths, HS4 scope, tuning (lists load from reference/)
├── reference/               # ← CENTRAL governed reference tables (see its README)
│   ├── brand_model/         #   canonical master + superseded V0 workbooks
│   ├── companies/           #   company / sub-OU reference
│   ├── list_catalog.csv     #   dimension: one row per list (what each list is)
│   ├── term_lists.csv       #   fact: all flat lists + blacklists, provider-aware
│   ├── term_mappings.csv    #   fact: key→value maps (qualifier→product, aliases)
│   ├── reference.sqlite     #   machine-readable query DB built from the CSVs + master
│   └── loader.py, build_reference_db.py, README.md
├── src/
│   ├── step1_extract.py     # source → TSV cache + build family/category/maker lexicons
│   ├── step2_match.py       # 3-tier trie/category/manufacturer matching
│   ├── step3_map.py         # join matched keywords → reference fields
│   ├── step3b_hs_prior.py   # learned HS-prior recall re-rank (guarded)
│   └── step4_export.py      # styled .xlsx + Dashboard + Dashboard.html
├── data/
│   ├── uploads/             # ← PUT MARKET SOURCE .xlsx / .csv FILES HERE
│   └── intermediate/        # cached TSV / pickles / csv (regenerated)
└── outputs/                 # <Country>_ML_Map_Mapped.xlsx (one per market) + report
```

---

## Setup

```bash
pip install -r requirements.txt
```

Place the **market source** workbook/CSV in `data/uploads/`:

- `VN-2024_Processed-MLmap_analysis_v0.xlsx`  (the trade data, sheet `RawData`)

The **reference brand/model list** now lives under `reference/brand_model/`
(`Surg_Brand_model_list_Master_03July26.xlsx`, sheet `Updated (excl. generic)`)
and is referenced by `config.settings.V0_REFERENCE_XLSX`.

### Reference tables (central + governed)

All reference data — the brand/model master, the **exclusion lists** (generic /
dental / accessory / veterinary), and the **usage lists** (qualifier→product map,
manufacturer aliases, category heads, consistency & ambiguous-brand cues) — lives
in **`reference/`**, modelled as a small **star schema**: `list_catalog.csv`
(one row per list) over two typed fact tables — `term_lists.csv` (flat lists +
blacklists, **provider-aware**) and `term_mappings.csv` (key→value maps). These
CSVs are the **human-editable** source of truth; **`reference.sqlite`** is the
**machine-readable** query DB rebuilt from them. `config/settings.py` loads the
CSVs at import (nothing is hard-coded). Edit a CSV, then
`python reference/build_reference_db.py`. Multi-provider blacklists combine by
appending rows tagged with their `provider` (a `retired` status keeps a term on
record without applying it). Full usage, intent, storage, provenance and data
lineage are in [`reference/README.md`](reference/README.md).

---

## Run

```bash
# Full pipeline (extract → match → map → export)
python run_pipeline.py

# Reuse the cached TSV + keyword lookup (skip the slow extraction step)
python run_pipeline.py --skip-extract

# Start from a specific stage
python run_pipeline.py --from match
python run_pipeline.py --from export

# Process another market's file without editing config/settings.py — label its
# Dashboard "Country" and point at its workbook. The slice is written separately
# (dashboard_<country>.csv) and combined with any existing market slices on the
# next export.
python run_pipeline.py --country Pakistan \
    --source data/uploads/PK-2024_imports.xlsx
```

The source import file may be either an **`.xlsx`** workbook (streamed sheet-by-
row via openpyxl) or a **`.csv`** export (some markets ship processed CSVs) — the
extractor dispatches on the file extension; everything downstream is identical.
Each market's output is written to its own **`outputs/<Country>_ML_Map_Mapped.xlsx`**
so runs don't overwrite each other, while the **Dashboard sheet inside every
workbook combines all market slices** present in `data/intermediate/`.
The same export artifacts are also mirrored to
**`G:\我的云端硬盘\Working Folder\Import Data\outputs\<country-code>\vn2024_pipeline\`**
when that Google Drive folder is mounted.

A full run (stage 1) builds all three lexicons — keyword (Tier-1), category
(Tier-2) and manufacturer-alias (Tier-3) — so a from-scratch or new-market run
needs no manual lexicon step. Each stage can also be run standalone, e.g.
`python src/step2_match.py`.

Source files are validated at load: a missing workbook, sheet, or expected
column raises a clear error (listing what was found and which `config/settings.py`
name to fix) instead of a cryptic `KeyError` mid-run.

After a run, check invariants with:

```bash
python qc_check.py     # asserts Tier-1 count, cascade exclusivity, bounds
```

---

## How it works

### 1. Extraction (`step1_extract.py`)
The VN workbook is ~132 MB / 520k rows, so it is streamed row-by-row with
openpyxl `read_only=True` into a flat TSV cache (`data/intermediate/`). The V0
reference `Updated` sheet is loaded with pandas; keywords from the
`Model/ Family Name` column are cleaned (drop pure-numeric, drop `< 4` chars),
de-duplicated longest-first, blacklist-filtered, and indexed into a 4-character
prefix trie.

### 2. Matching (`step2_match.py`)
Each product description is scanned with the prefix trie. At every character
position a single O(1) dictionary lookup on the 4-char prefix decides whether
any keyword could start there; candidates are confirmed with a full string
compare and a **word-boundary check** (neighbouring chars must be
non-alphanumeric) to avoid substring false positives (e.g. "venous" inside
"intravenous"). Matching is **gated by HS4 scope** — only rows whose `HS4` is in
`{9018, 9019, 9021, 9022}` are eligible. Full dataset matches in ~8 seconds.

### 2b. Tier-2 category matching (`step2_match.py`)
After the family pass, every still-unmatched in-scope row gets a **category**
pass that recognises product *categories* (stent, catheter, balloon…) without
asserting a specific family. This recovers the ~44% of reference rows that have
no family name but do carry a Product. A small category lexicon is built in
`step1_extract.build_category_lexicon()` from two sources, matched longest-first:

- a curated **qualifier→Product** map (`coronary stent`→Drug Eluting Stents,
  `ureteral stent`→Ureteral Stents …) → confidence **high**;
- multi-word **reference Product labels** → confidence **med**.

Some otherwise-blacklisted bare heads (`plate`, `suture`, `mesh`, `cannula`)
are **reinstated only when a qualifier pins a single Sub-OU** (Sub-segment):
`locking plate`/`bone plate`→Plate (Trauma│Plate), `absorbable suture`→
Conventional Suture (Surgical Innovations│Sutures), `hernia mesh`→Synthetic Mesh
(│Hernia), `arterial`/`venous`/`femoral cannula`→Cannulae (Cardiac Surgery│
Extracorporeal Therapies). Ambiguous qualifiers are deliberately omitted
(`tibial plate` can be a knee tray; a bare `screw` has no clean Trauma Sub-OU).

A bare category head with no qualifier (just "stent") falls back to an
**HS8→dominant-segment** map derived from this run's Tier-1 matches; the segment
is only asserted when that HS8's dominant share ≥ `HS8_SEGMENT_MIN_SHARE` (0.70),
otherwise it is left blank and the row is tagged `<Head> (unspecified)` →
confidence **low**. Tier-1 family always wins the cascade.

**Precision guard.** Before any category phrase/head is accepted, the
description is checked against `CATEGORY_NEGATIVE_CUES` — accessory / tool / part
words (`cutter`, `holder`, `valve cap`, `valvulotome`, `pump for`…) that mean the
row is something *around* the device, not the device itself. Any cue present →
the row is left unmatched. The `valve` head was also dropped from
`CATEGORY_HEADS` (bare "valve" hits were dominated by caps and valvulotomes, not
implants). Together these tighten the upper bound by ~$6M while keeping ~95% of
category recall.

### 2c. Tier-3 manufacturer matching (`step2_match.py`)
Manufacturer is **not** in the description — it lives in the `Importer`/
`Exporter` trade-party columns. After the family and category passes, every
still-unmatched in-scope row is checked against a **curated manufacturer alias
map** (`cfg.MANUFACTURER_ALIASES`): canonical maker → distinctive lowercase
"cores" (e.g. `medtronic`/`covidien`→Medtronic, `b braun`/`aesculap`→B. Braun,
`johnson johnson`/`depuy`/`ethicon`→J&J), searched as whole words in the
normalized Importer+Exporter blob, longest-first. The map is **curated, not
auto-derived** — a single generic token (`ace`, `instrument`, `golden`) collides
across unrelated shippers and would mislabel the maker. A veterinary/animal
guard (`cfg.MANUFACTURER_EXCLUDE_CUES`) drops out-of-scope animal-health rows.
Tier-3 fills **Manufacturer only** (no product/segment) → confidence **low**;
Tier-1 and Tier-2 always win the cascade.

### 3. Mapping (`step3_map.py`)
Matched keywords are joined back to their V0 reference row. The cascade is
Tier-1 (family) → Tier-2 (category) → Tier-3 (manufacturer) for any given row:

| V0 reference column   | Output column      |
|-----------------------|--------------------|
| Segment               | Segment            |
| Sub-segment           | Sub-segment        |
| Product               | Product_V0         |
| Player                | Manufacturer       |
| Model/ Family Name    | Family             |
| *(derived)*           | Match_Status       |
| *(derived)*           | Match_Tier         |
| *(derived)*           | Match_Confidence   |

`Match_Tier` ∈ {`family`, `category`, `manufacturer`, ``}; `Match_Confidence` ∈
{`high`, `med`, `low`, ``}. Category rows leave `Family`/`Manufacturer` blank;
manufacturer rows fill `Manufacturer` only (Family/Segment/Product blank).

### 4. Export (`step4_export.py`)
Writes a three-sheet `.xlsx`:

- **`RawData`** — all rows; Tier-1 family rows shaded **green**, Tier-2 category
  rows **yellow** (conditional formats keep the file small and filter-aware).
- **`Summary`** — match counts by Match_Tier → Segment → Sub-segment →
  Product_V0; blank dimensions are shown as **"Unspecified"** (no blank rows).
- **`Dashboard`** — **line-item** import-value bounds at
  **Country × OU (Segment) × Sub-OU (Sub-segment) × Product × Family ×
  Manufacturer** grain:
  - **Lower bound** = value from matched **family** rows (Tier-1) only.
  - **Upper bound** = value from matched **category** rows (Tier-1 + Tier-2).
  - Tier-2 rows assert no family, so their **Family is "Unspecified"** — but each
    such line is still itemised by its **Sub-OU, Product and Manufacturer**
    rather than collapsed into one black-box lump per OU. The Manufacturer for a
    Tier-2 line is recovered from the **Importer/Exporter** trade-party blob via
    the same curated alias cores as Tier-3 (Tier-1 lines keep their reference
    Player); a line with no resolvable maker shows `Unspecified`.
  "Country" is the import market the source file represents (set by
  `cfg.IMPORT_COUNTRY` / `--country`, "Vietnam" here — not the exporter country).
  For a named-family line `lower = upper`; for an Unspecified-family line
  `lower = 0` (it is pure upper-bound gap). Summing a Country/OU/Sub-OU's lines
  gives that level's lower/upper bound, so the upper–lower gap is now traceable
  to specific Sub-OUs, Products and makers. **Tier-3 manufacturer rows are
  excluded from these $ bounds** (`cfg.DASHBOARD_BOUND_TIERS`) — they have no
  product/segment and would inflate the upper bound; they still count as Matched
  in the Summary sheet.

### Interactive dashboard site

Every export also rebuilds **`outputs/Dashboard.html`** — a self-contained,
theme-matched HTML page (no server, no build step; the whole combined Dashboard
is embedded as JSON and filtered client-side with vanilla JS). It lets you:

- flip between **all countries** or any subset via country pills, and read a
  **country comparison** table with stacked lower/gap bars;
- filter by **OU, Sub-OU, Manufacturer**, free-text **Family/Product** search,
  and a minimum upper-bound threshold;
- watch the **KPI cards** (Lower, Upper, Gap, Coverage, Line Items) and a
  sortable **line-item** table recompute live.

It is linked from the methodology page's sidebar (**Country Dashboard →**) and
links back to it, so the two form one navigable report. Because it reads the
same combined slices as the Dashboard sheet, adding a market's
`dashboard_<country>.csv` slice and re-running export folds that country into
both the sheet and the site automatically.

---

## Tuning

All knobs live in `config/settings.py`:

- **`SURGICAL_HS4`** — HS4 codes in scope. Widen cautiously: HS4 `3006`
  (pharma/dental) and `9027` (analytical instruments) were deliberately
  excluded because generic brand words (`ultimate`, `nano`, `supreme`) caused
  false matches there.
- **`BLACKLIST`** — generic words suppressed from matching. Add/remove terms
  here to trade recall vs precision.
- **`MIN_KEYWORD_LEN`**, **`PREFIX_LEN`** — matcher tuning.
- **`KEEP_COLS`** — which VN source columns carry through to the output.
- **`CATEGORY_QUALIFIER_MAP`** — curated `qualifier phrase → Product` entries
  (Tier-2 high confidence). Seed new ones from description-bigram frequencies.
- **`CATEGORY_HEADS`** — bare heads eligible for the HS8-segment fallback.
- **`CATEGORY_NEGATIVE_CUES`** — accessory/tool/part words that disqualify a
  Tier-2 category hit (precision guard against stent cutters, valve caps, etc.).
- **`GENERIC_LABEL_BLACKLIST`** — vague 2-token Product labels to suppress.
- **`HS8_SEGMENT_MIN_SHARE`** — how dominant an HS8's segment must be before a
  bare-head row inherits it (default 0.70; raise for stricter precision).
- **`IMPORT_COUNTRY`** — the import market the source file represents, used as
  the Dashboard "Country" dimension (e.g. "Vietnam"; set to "Pakistan" when
  running that market's file).
- **`OUTPUT_MIRROR_ROOT` / `OUTPUT_MIRROR_COUNTRY_FOLDERS`** — optional mirror
  target for export artifacts in the Import Data repo's `outputs/<country-code>/`
  layout.
- **`MANUFACTURER_ALIASES`** — curated canonical-maker → distinctive-core map
  for Tier-3 (matched against Importer/Exporter). Extend conservatively: verify
  a new core is not a substring of an unrelated shipper before adding.
- **`MANUFACTURER_EXCLUDE_CUES`** — trade-party words (veterinary/animal) that
  disqualify a Tier-3 manufacturer hit.
- **`DASHBOARD_BOUND_TIERS`** — which tiers feed the Dashboard $ bounds
  (`family`+`category`; manufacturer excluded).

---

## Known caveats

- **Homonym keywords** (e.g. `ranger` = 3M warming unit *and* Bard DCB balloon)
  can't be disambiguated by keyword alone; add an HS4 sub-code or manufacturer
  filter if precision matters for those.
- **HS4-null rows** are never matched even if their description contains a valid
  device name — review separately if needed.
- **Blacklisted true-positives**: some suppressed words (`needle`, `screw`,
  `trocar`) are legitimate device names; reinstate specific multi-word forms
  (e.g. "Veress needle", "pedicle screw") if you need them.
- **Single match per row** — only the first (longest) keyword is recorded.
- **Tier-2 segment can be the *dominant* one, not the exact one** — a qualifier
  whose Product label spans segments (e.g. "Diagnostic Catheter") resolves to
  that Product's most-frequent Segment in the reference, which may differ from
  the row's true clinical segment. Filter on `Match_Tier`/`Match_Confidence`
  for precision-sensitive analysis; Tier-2 `low` rows are coarse by design.

See `outputs/VN2024_Methodology.pdf` for the full methodology write-up.
