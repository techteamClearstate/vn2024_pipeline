"""Build reference.sqlite — the machine-readable query layer for the reference
tables. Generated from the human-editable star-schema CSVs (list_catalog,
term_lists, term_mappings) plus the brand/model master workbook. Re-run after
editing any CSV:

    python reference/build_reference_db.py

Tables (mirror the CSVs, plus the master and file lineage)
----------------------------------------------------------
list_catalog        one row per list: layer, content_type, match_type, the
                    settings.py symbol it feeds, where it is consumed, purpose,
                    and live counts (active vs total terms).
term_lists          flat term lists + blacklists, provider-aware
                    (list_name, term, provider, status, notes).
term_mappings       key → value maps (map_name, key, value, provider, notes).
brand_model_master  the canonical master brand list, exploded to rows.
source_files        the file-based references, with sheet / header / status.
"""
from __future__ import annotations
import csv, sqlite3, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import config.settings as s
from reference.loader import CATALOG_CSV, TERM_LISTS_CSV, TERM_MAPS_CSV

REFERENCE_DIR = ROOT / "reference"
DB_PATH = REFERENCE_DIR / "reference.sqlite"


def build():
    if DB_PATH.exists():
        DB_PATH.unlink()
    con = sqlite3.connect(DB_PATH)
    c = con.cursor()
    c.executescript("""
    CREATE TABLE list_catalog(
        list_name TEXT PRIMARY KEY, layer TEXT, content_type TEXT, match_type TEXT,
        settings_symbol TEXT, consumed_in TEXT, purpose TEXT,
        n_active INTEGER, n_total INTEGER);
    CREATE TABLE term_lists(
        list_name TEXT, term TEXT, provider TEXT, status TEXT, notes TEXT);
    CREATE TABLE term_mappings(
        map_name TEXT, key TEXT, value TEXT, provider TEXT, notes TEXT);
    CREATE TABLE brand_model_master(
        row_id INTEGER PRIMARY KEY, segment TEXT, sub_segment TEXT, product TEXT,
        player TEXT, family_name TEXT);
    CREATE TABLE source_files(
        file_id TEXT PRIMARY KEY, rel_path TEXT, sheet TEXT, header_row INTEGER,
        role TEXT, status TEXT, n_rows INTEGER, notes TEXT);
    CREATE INDEX ix_terms_list ON term_lists(list_name);
    CREATE INDEX ix_maps_name ON term_mappings(map_name);
    """)

    active, total = {}, {}
    for r in csv.DictReader(open(TERM_LISTS_CSV, encoding="utf-8")):
        c.execute("INSERT INTO term_lists VALUES(?,?,?,?,?)",
                  (r["list_name"], r["term"], r["provider"], r["status"], r["notes"]))
        total[r["list_name"]] = total.get(r["list_name"], 0) + 1
        if r["status"].strip() == "active":
            active[r["list_name"]] = active.get(r["list_name"], 0) + 1
    for r in csv.DictReader(open(TERM_MAPS_CSV, encoding="utf-8")):
        c.execute("INSERT INTO term_mappings VALUES(?,?,?,?,?)",
                  (r["map_name"], r["key"], r["value"], r["provider"], r["notes"]))
        total[r["map_name"]] = total.get(r["map_name"], 0) + 1
        active[r["map_name"]] = active.get(r["map_name"], 0) + 1

    for r in csv.DictReader(open(CATALOG_CSV, encoding="utf-8")):
        n = r["list_name"]
        c.execute("INSERT INTO list_catalog VALUES(?,?,?,?,?,?,?,?,?)",
                  (n, r["layer"], r["content_type"], r["match_type"],
                   r["settings_symbol"], r["consumed_in"], r["purpose"],
                   active.get(n, 0), total.get(n, 0)))

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
    for t in ["list_catalog", "term_lists", "term_mappings", "brand_model_master", "source_files"]:
        n = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t:20s} {n:6d} rows")
    con.close()
    print(f"\nBuilt {DB_PATH.relative_to(ROOT).as_posix()} from the star-schema CSVs")


if __name__ == "__main__":
    build()
