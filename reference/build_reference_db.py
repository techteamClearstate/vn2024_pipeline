"""Build reference.sqlite — the machine-readable query layer for the reference
tables. Generated from the single human-editable source reference_lists.csv (plus
the brand/model master workbook). Re-run after editing the CSV:

    python reference/build_reference_db.py

Tables
------
reference_lists   catalogue: one row per governed list (layer, kind, the
                  settings.py symbol it feeds, where it is consumed, purpose,
                  row count).
list_entries      the full contents of reference_lists.csv, one row per value
                  (list_name, layer, kind, seq, key, value) — query any list, or
                  join across lists, in SQL.
brand_model_master  the canonical master brand list, exploded to rows.
source_files      the file-based references (master, superseded V0, companies)
                  with sheet / header / status / lineage.
"""
from __future__ import annotations
import csv, sqlite3, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import config.settings as s
from reference.loader import LISTS_CSV, list_names

REFERENCE_DIR = ROOT / "reference"
DB_PATH = REFERENCE_DIR / "reference.sqlite"

# governance metadata: settings symbol / consumer / purpose per list
META = {
    "generic_word_blacklist":     ("BLACKLIST", "step1_extract",
        "Generic words/materials/company names too generic to be Tier-1 family keywords."),
    "category_negative_cues":     ("CATEGORY_NEGATIVE_CUES", "step2_match",
        "Accessory/tool cues (cutter, holder, valvulotome) → instrument AROUND a device; vetoes the category hit."),
    "dental_negative_cues":       ("DENTAL_NEGATIVE_CUES", "step2_match, step3b_hs_prior",
        "Out-of-scope dental substrings; drops dental leakage across all tiers + HS-prior."),
    "generic_label_blacklist":    ("GENERIC_LABEL_BLACKLIST", "step1_extract",
        "Vague 2-token Product labels excluded from the label-derived category lexicon."),
    "manufacturer_exclude_cues":  ("MANUFACTURER_EXCLUDE_CUES", "step2_match",
        "Veterinary/animal-health cues excluded from Tier-3 maker attribution."),
    "category_heads":             ("CATEGORY_HEADS", "step2_match",
        "Bare device heads eligible for the HS8-dominant-segment fallback."),
    "consistency_cues":           ("CONSISTENCY_CUES", "step2_match",
        "Device-head + anatomy vocabulary the Tier-1 consistency reranker may weigh."),
    "ambiguous_family_keywords":  ("AMBIGUOUS_FAMILY_KEYWORDS", "step2_match",
        "Common-English / collision brand keywords released unless the row corroborates the device."),
    "hs_prior_fixation_products": ("HS_PRIOR_FIXATION_PRODUCTS", "step3b_hs_prior",
        "Fixation product names never stamped onto a joint-replacement row."),
    "arthroplasty_component_cues": ("ARTHROPLASTY_COMPONENT_CUES", "step3b_hs_prior",
        "Joint-replacement cues that trigger the fixation-fill veto."),
    "category_qualifier_map":     ("CATEGORY_QUALIFIER_MAP", "step1_extract, step2_match",
        "Qualifier phrase → canonical Product label (Tier-2 high confidence)."),
    "manufacturer_aliases":       ("MANUFACTURER_ALIASES", "step1_extract, step2_match",
        "Canonical manufacturer → distinctive cores searched in the Importer+Exporter blob."),
    "column_map":                 ("V0_COLS", "step1_extract",
        "Reference sheet column → logical output field (schema contract)."),
}


def build():
    if DB_PATH.exists():
        DB_PATH.unlink()
    con = sqlite3.connect(DB_PATH)
    c = con.cursor()
    c.executescript("""
    CREATE TABLE reference_lists(
        list_name TEXT PRIMARY KEY, layer TEXT, kind TEXT, settings_symbol TEXT,
        consumed_in TEXT, purpose TEXT, n_values INTEGER);
    CREATE TABLE list_entries(
        list_name TEXT, layer TEXT, kind TEXT, seq INTEGER, key TEXT, value TEXT);
    CREATE TABLE brand_model_master(
        row_id INTEGER PRIMARY KEY, segment TEXT, sub_segment TEXT, product TEXT,
        player TEXT, family_name TEXT);
    CREATE TABLE source_files(
        file_id TEXT PRIMARY KEY, rel_path TEXT, sheet TEXT, header_row INTEGER,
        role TEXT, status TEXT, n_rows INTEGER, notes TEXT);
    CREATE INDEX ix_entries_list ON list_entries(list_name);
    """)

    # full CSV → list_entries, and tally per list
    counts, meta_seen = {}, {}
    with open(LISTS_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            c.execute("INSERT INTO list_entries VALUES(?,?,?,?,?,?)",
                      (r["list_name"], r["layer"], r["kind"], int(r["seq"]),
                       r["key"], r["value"]))
            counts[r["list_name"]] = counts.get(r["list_name"], 0) + 1
            meta_seen[r["list_name"]] = (r["layer"], r["kind"])

    for name in list_names():
        layer, kind = meta_seen[name]
        sym, consumed, purpose = META[name]
        c.execute("INSERT INTO reference_lists VALUES(?,?,?,?,?,?,?)",
                  (name, layer, kind, sym, consumed, purpose, counts[name]))

    # brand/model master (canonical) — exploded to rows
    import pandas as pd
    master = pd.read_excel(s.V0_REFERENCE_XLSX, sheet_name=s.V0_SHEET,
                           header=s.V0_HEADER_ROW, dtype=str)
    cols = s.V0_COLS
    n_master = 0
    for i, row in master.iterrows():
        c.execute("INSERT INTO brand_model_master VALUES(?,?,?,?,?,?)",
                  (int(i), row.get(cols["segment"]), row.get(cols["sub_segment"]),
                   row.get(cols["product"]), row.get(cols["player"]),
                   row.get(cols["keyword"])))
        n_master += 1

    files = [
        ("brand_model_master", "reference/brand_model/Surg_Brand_model_list_Master_03July26.xlsx",
         s.V0_SHEET, s.V0_HEADER_ROW, "canonical brand/model reference", "active", n_master,
         "Team master (03 Jul 2026). 'Updated (excl. generic)' tab drops 709 generic-flagged families. Feeds Tier-1 family lookup + category lexicon."),
        ("brand_model_v0", "reference/brand_model/Surg_Brand_model_list_V0.xlsx",
         "Updated", None, "superseded brand/model reference", "superseded", None,
         "Prior reference, replaced by the master at iter-12. Kept for provenance."),
        ("companies_master", "reference/companies/List_of_companies_v1.0_Master.xlsx",
         "List of companies by sub-OU", 7, "companies-by-subOU reference", "reference", None,
         "Earlier company/sub-OU list. Not currently loaded by the pipeline; retained as usage reference."),
    ]
    c.executemany("INSERT INTO source_files VALUES(?,?,?,?,?,?,?,?)", files)

    con.commit()
    for t in ["reference_lists", "list_entries", "brand_model_master", "source_files"]:
        n = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t:22s} {n:6d} rows")
    con.close()
    print(f"\nBuilt {DB_PATH.relative_to(ROOT).as_posix()} from {LISTS_CSV.name}")


if __name__ == "__main__":
    build()
