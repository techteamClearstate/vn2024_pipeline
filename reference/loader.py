"""Canonical loader for the pipeline's reference lists.

The reference data is a small star schema of plain CSVs (the single source of
truth); config/settings.py calls these helpers at import so the running pipeline
and the generated reference.sqlite are always built from the same rows.

    list_catalog.csv   one row per list  (list_name, layer, content_type,
                       match_type, settings_symbol, consumed_in, purpose)
    term_lists.csv     flat term lists + blacklists, provider-aware
                       (list_name, term, provider, status, notes)
    term_mappings.csv  key -> value maps
                       (map_name, key, value, provider, notes)

Only rows with status == 'active' are loaded (a 'retired' term is kept for the
record but not applied). Terms are de-duplicated across providers, so combining
several providers' blacklists is just appending their rows. Stdlib csv only, so
importing config.settings never pulls in pandas.
"""
from __future__ import annotations
import csv
from pathlib import Path

REFERENCE_DIR   = Path(__file__).resolve().parent
CATALOG_CSV     = REFERENCE_DIR / "list_catalog.csv"
TERM_LISTS_CSV  = REFERENCE_DIR / "term_lists.csv"
TERM_MAPS_CSV   = REFERENCE_DIR / "term_mappings.csv"

ACTIVE = "active"
_TERMS: dict | None = None
_MAPS: dict | None = None


def _read(path: str | Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _terms() -> dict[str, list[dict]]:
    global _TERMS
    if _TERMS is None:
        g: dict[str, list[dict]] = {}
        for r in _read(TERM_LISTS_CSV):
            g.setdefault(r["list_name"], []).append(r)
        _TERMS = g
    return _TERMS


def _maps() -> dict[str, list[dict]]:
    global _MAPS
    if _MAPS is None:
        g: dict[str, list[dict]] = {}
        for r in _read(TERM_MAPS_CSV):
            g.setdefault(r["map_name"], []).append(r)
        _MAPS = g
    return _MAPS


def _active_terms(list_name: str) -> list[str]:
    rows = _terms().get(list_name)
    if rows is None:
        raise KeyError(f"term list {list_name!r} not found in {TERM_LISTS_CSV.name}")
    return [r["term"].strip() for r in rows
            if r.get("status", ACTIVE).strip() == ACTIVE and r["term"].strip()]


def _active_map_rows(map_name: str) -> list[dict]:
    rows = _maps().get(map_name)
    if rows is None:
        raise KeyError(f"map {map_name!r} not found in {TERM_MAPS_CSV.name}")
    return [r for r in rows if r.get("status", ACTIVE).strip() == ACTIVE] if rows and "status" in rows[0] else rows


def load_set(list_name: str) -> set[str]:
    """Active terms of a flat list → a set (provider-deduplicated)."""
    return set(_active_terms(list_name))


def load_tuple(list_name: str) -> tuple[str, ...]:
    """Active terms in file order, de-duplicated (for order-significant guards)."""
    seen, out = set(), []
    for t in _active_terms(list_name):
        if t not in seen:
            seen.add(t); out.append(t)
    return tuple(out)


def load_str_map(map_name: str) -> dict[str, str]:
    """key → value (last active row wins on duplicate key)."""
    return {r["key"].strip(): r["value"].strip() for r in _active_map_rows(map_name)}


def load_alias_map(map_name: str) -> dict[str, list[str]]:
    """key → [value, ...], preserving value order and first-seen key order."""
    out: dict[str, list[str]] = {}
    for r in _active_map_rows(map_name):
        out.setdefault(r["key"].strip(), []).append(r["value"].strip())
    return out


def catalog() -> list[dict]:
    """The list_catalog rows (for tooling / the DB build)."""
    return _read(CATALOG_CSV)
