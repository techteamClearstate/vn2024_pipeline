"""Build reference.sqlite — the central, queryable home for every reference
table that drives the mapping pipeline.

Single source of truth = the CSVs in reference/{exclusion,usage}_lists/ (loaded
via config.settings, so the DB is guaranteed identical to what the pipeline runs)
plus the brand/model master workbook in reference/brand_model/. Re-run any time a
list changes:

    python reference/build_reference_db.py

Tables
------
reference_lists        catalogue: one row per governed list (layer, kind, source,
                       row count, the settings.py symbol it feeds, where it is
                       consumed, and its purpose)
list_values            tidy long form of every flat list (exclusion + usage), one
                       (list_name, position, value) row each
category_qualifier_map qualifier_phrase → product_label (Tier-2 high-confidence)
manufacturer_aliases   canonical → core (Tier-3 maker alias; ord preserves
                       longest-first intent)
column_map             logical_name → source_column (reference→output schema)
source_files           the file-based references (master, superseded V0,
                       companies) with sheet / header / status / lineage
brand_model_master     the full canonical master brand list, exploded to rows
"""
from __future__ import annotations
import sqlite3, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import config.settings as s
from reference.loader import LISTS

REFERENCE_DIR = ROOT / "reference"
DB_PATH = REFERENCE_DIR / "reference.sqlite"

# ── governance metadata: layer / consumer / purpose for each list ───────────
META = {
    "generic_word_blacklist":     ("exclusion", "set",     "BLACKLIST",
        "step1_extract (keyword lookup)",
        "Generic English words/materials/company names in the brand list that are too generic to safely match; suppressed as Tier-1 family keywords."),
    "category_negative_cues":     ("exclusion", "set",     "CATEGORY_NEGATIVE_CUES",
        "step2_match (Tier-2 category)",
        "Accessory/tool/part cues (cutter, holder, valvulotome, stopcock…) that mean the row is an instrument AROUND a device, not the device — vetoes the category hit."),
    "dental_negative_cues":       ("exclusion", "set",     "DENTAL_NEGATIVE_CUES",
        "step2_match + step3b_hs_prior (all tiers)",
        "Out-of-scope dental substrings (root canal, gutta percha, endodont, denture…). Surgical OUs have no dental segment; drops dental leakage across Tier-1/2/3 + HS-prior."),
    "generic_label_blacklist":    ("exclusion", "set",     "GENERIC_LABEL_BLACKLIST",
        "step1_extract (category lexicon)",
        "Vague 2-token reference Product labels (hand instruments, access devices…) excluded from the label-derived category lexicon."),
    "manufacturer_exclude_cues":  ("exclusion", "set",     "MANUFACTURER_EXCLUDE_CUES",
        "step2_match (Tier-3 manufacturer)",
        "Veterinary/animal-health cues; excludes non-human-surgical trade-party rows from Tier-3 maker attribution."),
    "category_heads":             ("usage",     "set",     "CATEGORY_HEADS",
        "step2_match (Tier-2 category)",
        "Bare device heads (stent, catheter, balloon…) eligible for the HS8-dominant-segment fallback when no qualifier is present."),
    "consistency_cues":           ("usage",     "set",     "CONSISTENCY_CUES",
        "step2_match (Tier-1 consistency reranker)",
        "Curated device-head + anatomy vocabulary the reranker may weigh to release cross-area brand collisions."),
    "ambiguous_family_keywords":  ("usage",     "set",     "AMBIGUOUS_FAMILY_KEYWORDS",
        "step2_match (ambiguous-brand guard)",
        "Common-English / cross-category brand keywords whose Tier-1 hit is released unless the description carries a corroborating device token."),
    "hs_prior_fixation_products": ("usage",     "ordered", "HS_PRIOR_FIXATION_PRODUCTS",
        "step3b_hs_prior (arthroplasty veto)",
        "Fracture-fixation product names that must never be stamped onto a joint-replacement row by the HS-prior."),
    "arthroplasty_component_cues": ("usage",    "ordered", "ARTHROPLASTY_COMPONENT_CUES",
        "step3b_hs_prior (arthroplasty veto)",
        "Joint-replacement component cues (femoral head, acetabular, tibial insert…) that trigger the fixation-fill veto."),
    "category_qualifier_map":     ("usage",     "map",     "CATEGORY_QUALIFIER_MAP",
        "step1_extract / step2_match (Tier-2 high)",
        "Qualifier phrase → canonical Product label; the high-confidence Tier-2 seam incl. Sub-OU-safe reinstatements."),
    "manufacturer_aliases":       ("usage",     "alias",   "MANUFACTURER_ALIASES",
        "step1_extract / step2_match (Tier-3)",
        "Canonical manufacturer → distinctive lowercase cores searched in the Importer+Exporter blob."),
    "column_map":                 ("schema",    "map",     "V0_COLS",
        "step1_extract (reference load)",
        "Reference sheet column → logical output field (schema contract)."),
}

FLAT = {  # list_name → python object, for the tidy list_values table
    "generic_word_blacklist": s.BLACKLIST,
    "category_negative_cues": s.CATEGORY_NEGATIVE_CUES,
    "dental_negative_cues": s.DENTAL_NEGATIVE_CUES,
    "generic_label_blacklist": s.GENERIC_LABEL_BLACKLIST,
    "manufacturer_exclude_cues": s.MANUFACTURER_EXCLUDE_CUES,
    "category_heads": s.CATEGORY_HEADS,
    "consistency_cues": s.CONSISTENCY_CUES,
    "ambiguous_family_keywords": s.AMBIGUOUS_FAMILY_KEYWORDS,
    "hs_prior_fixation_products": s.HS_PRIOR_FIXATION_PRODUCTS,
    "arthroplasty_component_cues": s.ARTHROPLASTY_COMPONENT_CUES,
}


def _count(name):
    obj = {**FLAT, "category_qualifier_map": s.CATEGORY_QUALIFIER_MAP,
           "manufacturer_aliases": s.MANUFACTURER_ALIASES,
           "column_map": s.V0_COLS}[name]
    return len(obj)


def build():
    if DB_PATH.exists():
        DB_PATH.unlink()
    con = sqlite3.connect(DB_PATH)
    c = con.cursor()

    c.executescript("""
    CREATE TABLE reference_lists(
        list_name TEXT PRIMARY KEY, layer TEXT, kind TEXT, settings_symbol TEXT,
        source_csv TEXT, n_rows INTEGER, consumed_in TEXT, purpose TEXT);
    CREATE TABLE list_values(
        list_name TEXT, position INTEGER, value TEXT,
        PRIMARY KEY(list_name, position));
    CREATE TABLE category_qualifier_map(
        qualifier_phrase TEXT PRIMARY KEY, product_label TEXT);
    CREATE TABLE manufacturer_aliases(
        canonical TEXT, ord INTEGER, core TEXT, PRIMARY KEY(canonical, ord));
    CREATE TABLE column_map(logical_name TEXT PRIMARY KEY, source_column TEXT);
    CREATE TABLE source_files(
        file_id TEXT PRIMARY KEY, rel_path TEXT, sheet TEXT, header_row INTEGER,
        role TEXT, status TEXT, n_rows INTEGER, notes TEXT);
    CREATE TABLE brand_model_master(
        row_id INTEGER PRIMARY KEY, segment TEXT, sub_segment TEXT, product TEXT,
        player TEXT, family_name TEXT);
    """)

    # catalogue
    for name, (layer, kind, sym, consumed, purpose) in META.items():
        rel = LISTS[name].relative_to(ROOT).as_posix()
        c.execute("INSERT INTO reference_lists VALUES(?,?,?,?,?,?,?,?)",
                  (name, layer, kind, sym, rel, _count(name), consumed, purpose))

    # tidy flat lists
    for name, obj in FLAT.items():
        seq = sorted(obj) if isinstance(obj, (set, frozenset)) else list(obj)
        for i, v in enumerate(seq):
            c.execute("INSERT INTO list_values VALUES(?,?,?)", (name, i, v))

    for k, v in s.CATEGORY_QUALIFIER_MAP.items():
        c.execute("INSERT INTO category_qualifier_map VALUES(?,?)", (k, v))
    for canon, cores in s.MANUFACTURER_ALIASES.items():
        for i, core in enumerate(cores):
            c.execute("INSERT INTO manufacturer_aliases VALUES(?,?,?)", (canon, i, core))
    for k, v in s.V0_COLS.items():
        c.execute("INSERT INTO column_map VALUES(?,?)", (k, v))

    # brand/model master (canonical) — exploded to rows
    import pandas as pd
    master = pd.read_excel(s.V0_REFERENCE_XLSX, sheet_name=s.V0_SHEET,
                           header=s.V0_HEADER_ROW, dtype=str)
    cols = s.V0_COLS
    n_master = 0
    for i, r in master.iterrows():
        c.execute("INSERT INTO brand_model_master VALUES(?,?,?,?,?,?)",
                  (int(i), r.get(cols["segment"]), r.get(cols["sub_segment"]),
                   r.get(cols["product"]), r.get(cols["player"]),
                   r.get(cols["keyword"])))
        n_master += 1

    # source-file registry (lineage of the file-based references)
    files = [
        ("brand_model_master", "reference/brand_model/Surg_Brand_model_list_Master_03July26.xlsx",
         s.V0_SHEET, s.V0_HEADER_ROW, "canonical brand/model reference", "active", n_master,
         "Team master (03 Jul 2026). 'Updated (excl. generic)' tab already drops 709 generic-flagged families. Feeds Tier-1 family lookup + category lexicon."),
        ("brand_model_v0", "reference/brand_model/Surg_Brand_model_list_V0.xlsx",
         "Updated", None, "superseded brand/model reference", "superseded", None,
         "Prior reference, replaced by the master at iter-12. Kept for provenance."),
        ("companies_master", "reference/companies/List_of_companies_v1.0_Master.xlsx",
         "List of companies by sub-OU", 7, "companies-by-subOU reference", "reference", None,
         "Earlier company/sub-OU list. Not currently loaded by the pipeline; retained as usage reference."),
    ]
    c.executemany("INSERT INTO source_files VALUES(?,?,?,?,?,?,?,?)", files)

    con.commit()
    # report
    for t in ["reference_lists", "list_values", "category_qualifier_map",
              "manufacturer_aliases", "column_map", "source_files", "brand_model_master"]:
        n = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t:24s} {n:6d} rows")
    con.close()
    print(f"\nBuilt {DB_PATH.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    build()
