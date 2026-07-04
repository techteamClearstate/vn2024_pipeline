"""Canonical loader for the pipeline's reference tables.

The exclusion lists and usage/mapping lists that drive matching live as CSVs
under reference/exclusion_lists/ and reference/usage_lists/ — those CSVs are the
single source of truth. config/settings.py calls these helpers at import time so
the running pipeline and the reference.sqlite database are always built from the
exact same rows (no drift).

Each helper is deliberately tiny and dependency-free (stdlib csv only) so that
importing config.settings never pulls in pandas or anything heavy.
"""
from __future__ import annotations
import csv
from pathlib import Path

REFERENCE_DIR   = Path(__file__).resolve().parent
EXCLUSION_DIR   = REFERENCE_DIR / "exclusion_lists"
USAGE_DIR       = REFERENCE_DIR / "usage_lists"

# Map every logical list name → its CSV path, so callers (and build_reference_db)
# can enumerate the full catalogue from one place.
LISTS = {
    # exclusion lists
    "generic_word_blacklist":     EXCLUSION_DIR / "generic_word_blacklist.csv",
    "category_negative_cues":     EXCLUSION_DIR / "category_negative_cues.csv",
    "dental_negative_cues":       EXCLUSION_DIR / "dental_negative_cues.csv",
    "generic_label_blacklist":    EXCLUSION_DIR / "generic_label_blacklist.csv",
    "manufacturer_exclude_cues":  EXCLUSION_DIR / "manufacturer_exclude_cues.csv",
    # usage / mapping lists
    "category_heads":             USAGE_DIR / "category_heads.csv",
    "consistency_cues":           USAGE_DIR / "consistency_cues.csv",
    "ambiguous_family_keywords":  USAGE_DIR / "ambiguous_family_keywords.csv",
    "hs_prior_fixation_products": USAGE_DIR / "hs_prior_fixation_products.csv",
    "arthroplasty_component_cues": USAGE_DIR / "arthroplasty_component_cues.csv",
    "category_qualifier_map":     USAGE_DIR / "category_qualifier_map.csv",
    "manufacturer_aliases":       USAGE_DIR / "manufacturer_aliases.csv",
    "column_map":                 USAGE_DIR / "column_map.csv",
}


def _rows(name: str):
    """Yield the dict-rows of a reference CSV (utf-8, header required)."""
    path = LISTS[name]
    with open(path, newline="", encoding="utf-8") as f:
        yield from csv.DictReader(f)


def load_set(name: str) -> set[str]:
    """A single-column ``value`` CSV → a set of strings."""
    return {r["value"].strip() for r in _rows(name) if r["value"].strip()}


def load_tuple(name: str) -> tuple[str, ...]:
    """A single-column ``value`` CSV → a tuple in file order (order preserved
    for substring-scan lists where definition order was meaningful/cosmetic)."""
    return tuple(r["value"].strip() for r in _rows(name) if r["value"].strip())


def load_str_map(name: str, key: str, val: str) -> dict[str, str]:
    """A two-column CSV → an insertion-ordered ``{key: val}`` dict."""
    return {r[key].strip(): r[val].strip() for r in _rows(name)}


def load_alias_map(name: str, key: str, val: str) -> dict[str, list[str]]:
    """A (canonical, core) CSV with many rows per canonical → ``{canonical:
    [core, ...]}`` preserving core order and first-seen canonical order."""
    out: dict[str, list[str]] = {}
    for r in _rows(name):
        out.setdefault(r[key].strip(), []).append(r[val].strip())
    return out
