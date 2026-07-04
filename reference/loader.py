"""Canonical loader for the pipeline's reference lists.

All exclusion + usage lists live in ONE human-editable file —
``reference/reference_lists.csv`` — which is the single source of truth.
config/settings.py calls these helpers at import so the running pipeline and the
generated reference.sqlite are always built from the exact same rows.

CSV schema (one row per value):
    list_name , layer , kind , seq , key , value
    kind ∈ {set, ordered, map, alias}
      set     — unordered terms      (key empty; value = term)
      ordered — order-significant     (key empty; value = term, ordered by seq)
      map     — key → value           (key, value)
      alias   — key → [value, ...]    (key = canonical, value = core; seq order)

Stdlib csv only — importing config.settings never pulls in pandas.
"""
from __future__ import annotations
import csv
from pathlib import Path

REFERENCE_DIR = Path(__file__).resolve().parent
LISTS_CSV     = REFERENCE_DIR / "reference_lists.csv"

_CACHE: dict | None = None


def _load() -> dict[str, list[dict]]:
    """Read reference_lists.csv once, grouped by list_name (rows kept in file
    order, which is seq order)."""
    global _CACHE
    if _CACHE is None:
        groups: dict[str, list[dict]] = {}
        with open(LISTS_CSV, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                groups.setdefault(r["list_name"], []).append(r)
        _CACHE = groups
    return _CACHE


def _rows(name: str) -> list[dict]:
    rows = _load().get(name)
    if not rows:
        raise KeyError(f"reference list {name!r} not found in {LISTS_CSV.name}")
    return rows


def list_names() -> list[str]:
    """Every list_name present, in first-seen order (for tooling / the DB build)."""
    return list(_load().keys())


def load_set(name: str) -> set[str]:
    return {r["value"].strip() for r in _rows(name) if r["value"].strip()}


def load_tuple(name: str) -> tuple[str, ...]:
    return tuple(r["value"].strip() for r in _rows(name) if r["value"].strip())


def load_str_map(name: str) -> dict[str, str]:
    """key → value, insertion-ordered."""
    return {r["key"].strip(): r["value"].strip() for r in _rows(name)}


def load_alias_map(name: str) -> dict[str, list[str]]:
    """key → [value, ...], preserving core order and first-seen key order."""
    out: dict[str, list[str]] = {}
    for r in _rows(name):
        out.setdefault(r["key"].strip(), []).append(r["value"].strip())
    return out
