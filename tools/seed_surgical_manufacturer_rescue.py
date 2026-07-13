"""
Seed the governed `surgical_manufacturer_rescue` term list
==========================================================
One-off (idempotent) seeder for the known-surgical-manufacturer rescue list
used by the S07/S12 gate softening in src/step3_map.py.

Sources (both from reference/reference.sqlite, i.e. the governed layer):
  * distinct `player` values from brand_model_master  -> provider=master_player
  * distinct keys of term_mappings map `manufacturer_aliases`
                                                       -> provider=manufacturer_alias

Terms are de-duplicated on step1_extract.norm_party (the same normalization the
gate applies at match time), so spelling variants ("B. Braun" / "B.Braun") seed
only once. Blank / "Unspecified" players are dropped.

    PYTHONIOENCODING=utf-8 python tools/seed_surgical_manufacturer_rescue.py
    python reference/build_reference_db.py          # rebuild after seeding

Re-running skips every term whose norm_party form is already in the list, so
analyst edits (retired terms, added makers) are never clobbered.
"""
import csv
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.step1_extract import norm_party

LIST_NAME = "surgical_manufacturer_rescue"
TERM_LISTS_CSV = ROOT / "reference" / "term_lists.csv"
DB_PATH = ROOT / "reference" / "reference.sqlite"
SEED_NOTE = "seeded 2026-07-14 from governed reference (recall rescue)"


def main() -> int:
    con = sqlite3.connect(DB_PATH)
    players = [r[0] for r in con.execute(
        "SELECT DISTINCT player FROM brand_model_master WHERE player IS NOT NULL")]
    aliases = [r[0] for r in con.execute(
        "SELECT DISTINCT key FROM term_mappings WHERE map_name='manufacturer_aliases'")]
    con.close()

    # Existing rows for this list (any status) — retired terms stay retired.
    existing_norm = set()
    with open(TERM_LISTS_CSV, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if row["list_name"] == LIST_NAME:
                existing_norm.add(norm_party(row["term"]))

    new_rows, seen = [], set(existing_norm)
    # Alias keys first: the 30 curated majors take precedence over master spellings.
    for provider, terms in (("manufacturer_alias", aliases), ("master_player", players)):
        for term in sorted({str(t).strip() for t in terms}):
            key = norm_party(term)
            if not term or not key or key in seen or key == "unspecified":
                continue
            seen.add(key)
            new_rows.append({"list_name": LIST_NAME, "term": term,
                             "provider": provider, "status": "active",
                             "notes": SEED_NOTE})

    if not new_rows:
        print(f"[seed] {LIST_NAME}: nothing to add "
              f"({len(existing_norm):,} terms already present)")
        return 0

    with open(TERM_LISTS_CSV, "a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["list_name", "term", "provider", "status", "notes"])
        writer.writerows(new_rows)

    by_provider = {}
    for row in new_rows:
        by_provider[row["provider"]] = by_provider.get(row["provider"], 0) + 1
    print(f"[seed] {LIST_NAME}: appended {len(new_rows):,} terms "
          f"({', '.join(f'{k}={v}' for k, v in sorted(by_provider.items()))}; "
          f"{len(existing_norm):,} pre-existing). "
          "Now run: python reference/build_reference_db.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
