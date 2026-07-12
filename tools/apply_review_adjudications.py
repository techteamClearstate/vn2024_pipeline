"""Ingest human-Approved adjudication proposals into the governed reference/.

Counterpart of tools/build_adjudication_proposals.py (which only PROPOSES).
This tool acts exclusively on rows where a human set `Approved = Y` in an
Adjudication_Proposals_*.xlsx workbook, routing each proposal type to its
governed destination:

  family_alias           -> reference/term_mappings.csv  map_name=family_aliases
                            (alias term -> pipe-joined master 5-key; validated
                            against the master before writing)
  category_alias         -> reference/term_mappings.csv  map_name=category_qualifier_map
                            (alias phrase -> canonical Product label)
  scope_term             -> reference/term_lists.csv     (list from Target_Table;
                            a new scope_keyword_* list also gets a list_catalog
                            row and is picked up by settings automatically)
  scope_whitelist        -> reference/term_lists.csv     list must be exactly
                            surgical_context_whitelist (fail-closed)
  disambiguation_rule    -> outputs/remapped_current/reports/Rule_Spec_Backlog.xlsx
                            (documented spec backlog; rules are implemented in
                            code/config deliberately, never auto-applied)
  propose_master_addition-> outputs/remapped_current/reports/Master_Addition_Proposals.xlsx
                            (analyst-owned master workbook is NEVER edited here)
  needs_human            -> ignored (stays parked in the workbook)

Idempotent: existing (map_name, key) / (list_name, term) rows are skipped, so
re-running on the same proposals is a no-op. After any CSV change the tool
rebuilds reference.sqlite via reference/build_reference_db.py and reminds which
pipeline stages must re-run.

Run:
  PYTHONIOENCODING=utf-8 python tools/apply_review_adjudications.py \
      [--proposals "outputs/remapped_current/reports/Adjudication_Proposals_*.xlsx"] \
      [--dry-run] [--check-pending]

Both ``Adjudication_Proposals`` and ``Recovery_Proposals`` workbook schemas are
accepted. ``--check-pending`` validates every proposal row (including rows whose
Approved cell is still blank) without writing anything. Application is fail-closed:
if any Approved=Y row is invalid, the whole batch is rejected before any file write.
"""

from __future__ import annotations

import argparse
import csv
import glob
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.reference_compliance import load_master, norm_exact, norm_loose  # noqa: E402

REFERENCE_DIR = ROOT / "reference"
TERM_LISTS = REFERENCE_DIR / "term_lists.csv"
TERM_MAPS = REFERENCE_DIR / "term_mappings.csv"
CATALOG = REFERENCE_DIR / "list_catalog.csv"
REPORT_DIR = ROOT / "outputs" / "remapped_current" / "reports"
DEFAULT_GLOB = str(REPORT_DIR / "Adjudication_Proposals_*.xlsx")

SHARED_DIR_CANDIDATES = [
    Path(r"G:\Shared drives\New EIU Gateway\0. Gateway Ops & Databases"
         r"\Import Data Master\6. Workflow\Surgicals\Claude code\1. Mapped Results"),
    Path(r"G:\共享云端硬盘\New EIU Gateway\0. Gateway Ops & Databases"
         r"\Import Data Master\6. Workflow\Surgicals\Claude code\1. Mapped Results"),
]

PROVIDER = "adjudication"
PROPOSAL_SHEETS = ("Adjudication_Proposals", "Recovery_Proposals")
REQUIRED_COLUMNS = {
    "Market", "FY", "Cluster_Value_USD", "Proposal_Type", "Alias_Term",
    "Target_Table", "Proposed_Segment", "Proposed_Subsegment",
    "Proposed_Product", "Proposed_Player", "Proposed_Family", "Rationale",
    "Evidence_Quote", "Reviewer_Guidance", "Approved",
}


def _load_proposal_workbook(path: Path) -> pd.DataFrame:
    """Load either governed proposal-sheet variant and validate its contract."""
    with pd.ExcelFile(path) as book:
        sheet = next((name for name in PROPOSAL_SHEETS
                      if name in book.sheet_names), None)
        if sheet is None:
            expected = " or ".join(PROPOSAL_SHEETS)
            raise ValueError(f"{path.name}: missing {expected} sheet")
        frame = pd.read_excel(book, sheet_name=sheet, dtype=str)
    missing = sorted(REQUIRED_COLUMNS - set(frame.columns))
    if missing:
        raise ValueError(f"{path.name}/{sheet}: missing required columns: "
                         + ", ".join(missing))
    frame["_source"] = path.name
    frame["_sheet"] = sheet
    return frame


def _read_csv_rows(path: Path) -> tuple[list[str], list[dict]]:
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return list(reader.fieldnames or []), list(reader)


def _append_csv_rows(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with open(path, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def _parse_alias_entries(alias_field: str) -> list[tuple[str, str]]:
    """'a; b => fam; c' -> [(a, ''), (b, fam), (c, '')]."""
    out = []
    for chunk in str(alias_field or "").split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "=>" in chunk:
            term, _, target = chunk.partition("=>")
            out.append((term.strip().lower(), target.strip().lower()))
        else:
            out.append((chunk.lower(), ""))
    return out


def _resolve_full_key(master: dict, player: str, family: str) -> tuple[str, ...] | None:
    """Find the unique canonical master 5-key for a (player, family) pair."""
    want = (norm_loose(player), norm_loose(family))
    hits = {tuple(canon) for canon in master["full_loose"].values()
            if (norm_loose(canon[3]), norm_loose(canon[4])) == want}
    if len(hits) == 1:
        return next(iter(hits))
    return None


def _target_list_name(target_table: str) -> str:
    """'term_lists:general_consumable_cues (note)' -> 'general_consumable_cues'."""
    name = str(target_table or "").split(":", 1)[-1].strip()
    return name.split()[0].split("(")[0].strip() if name else ""


def _append_workbook(path: Path, sheet: str, frame: pd.DataFrame,
                     dedupe_cols: list[str]) -> int:
    """Append rows to a single-sheet xlsx backlog, deduplicated."""
    if path.exists():
        try:
            old = pd.read_excel(path, sheet_name=sheet, dtype=str)
        except Exception:
            old = pd.DataFrame()
    else:
        old = pd.DataFrame()
    combined = pd.concat([old, frame.astype(str)], ignore_index=True)
    before = len(combined)
    combined = combined.drop_duplicates(subset=[c for c in dedupe_cols
                                                if c in combined.columns])
    added = len(combined) - len(old)
    with pd.ExcelWriter(path, engine="xlsxwriter") as xw:
        combined.to_excel(xw, sheet_name=sheet, index=False)
        xw.sheets[sheet].freeze_panes(1, 0)
        xw.sheets[sheet].set_column(0, len(combined.columns), 28)
    del before
    return max(0, added)


def apply(proposal_paths: list[Path], dry_run: bool = False,
          shared_log: bool = True, check_pending: bool = False) -> dict:
    frames = []
    for p in proposal_paths:
        frames.append(_load_proposal_workbook(p))
    props = pd.concat(frames, ignore_index=True).fillna("")
    approved = props[props["Approved"].str.strip().str.upper().eq("Y")]
    selected = props if check_pending else approved
    stats = {"approved": len(approved), "checked": len(selected),
             "family_alias": 0, "category_alias": 0,
             "scope_term": 0, "scope_whitelist": 0,
             "rule_spec": 0, "master_proposal": 0,
             "skipped_existing": 0, "errors": 0}
    if selected.empty:
        print("[ingest] no Approved=Y rows found — nothing to do "
              f"({len(props)} proposals pending review)")
        return stats

    master = load_master()
    map_fields, map_rows = _read_csv_rows(TERM_MAPS)
    list_fields, list_rows = _read_csv_rows(TERM_LISTS)
    cat_fields, cat_rows = _read_csv_rows(CATALOG)
    existing_maps = {(r["map_name"], r["key"].strip().lower()) for r in map_rows}
    existing_terms = {(r["list_name"], r["term"].strip().lower()) for r in list_rows}
    existing_lists = {r["list_name"] for r in cat_rows}

    new_map_rows, new_list_rows, new_cat_rows = [], [], []
    rule_specs, master_props = [], []
    today = datetime.now().strftime("%Y-%m-%d")

    for _, row in selected.iterrows():
        note = (f"{row['Market']} FY{row['FY']} adjudication {today}; "
                f"cluster ${float(row['Cluster_Value_USD'] or 0):,.0f}")
        ptype = row["Proposal_Type"].strip()

        if ptype == "family_alias":
            for term, fam_override in _parse_alias_entries(row["Alias_Term"]):
                if fam_override:
                    key5 = _resolve_full_key(master, row["Proposed_Player"],
                                             fam_override)
                    if key5 is None:
                        print(f"[ingest] ERROR alias {term!r}: "
                              f"({row['Proposed_Player']!r}, {fam_override!r}) "
                              "is not a unique master family — skipped")
                        stats["errors"] += 1
                        continue
                else:
                    key5 = tuple(row[c] for c in (
                        "Proposed_Segment", "Proposed_Subsegment",
                        "Proposed_Product", "Proposed_Player",
                        "Proposed_Family"))
                    if tuple(norm_exact(v) for v in key5) not in master["full_exact"]:
                        canon = master["full_loose"].get(
                            tuple(norm_loose(v) for v in key5))
                        if canon is None:
                            print(f"[ingest] ERROR alias {term!r}: 5-key not "
                                  "in master — skipped")
                            stats["errors"] += 1
                            continue
                        key5 = tuple(canon)
                if ("family_aliases", term) in existing_maps:
                    stats["skipped_existing"] += 1
                    continue
                new_map_rows.append({"map_name": "family_aliases", "key": term,
                                     "value": "|".join(key5),
                                     "provider": PROVIDER, "notes": note})
                existing_maps.add(("family_aliases", term))
                stats["family_alias"] += 1

        elif ptype == "category_alias":
            product = row["Proposed_Product"].strip()
            for term, _ in _parse_alias_entries(row["Alias_Term"]):
                if ("category_qualifier_map", term) in existing_maps:
                    stats["skipped_existing"] += 1
                    continue
                new_map_rows.append({"map_name": "category_qualifier_map",
                                     "key": term, "value": product,
                                     "provider": PROVIDER, "notes": note})
                existing_maps.add(("category_qualifier_map", term))
                stats["category_alias"] += 1

        elif ptype in ("scope_term", "scope_whitelist"):
            list_name = _target_list_name(row["Target_Table"])
            if not list_name:
                print(f"[ingest] ERROR scope_term row without target list "
                      f"({row['Rationale'][:50]}...) — skipped")
                stats["errors"] += 1
                continue
            if ptype == "scope_whitelist" and list_name != "surgical_context_whitelist":
                print("[ingest] ERROR scope_whitelist target must be exactly "
                      "surgical_context_whitelist — skipped")
                stats["errors"] += 1
                continue
            if list_name not in existing_lists:
                domain = list_name.removeprefix("scope_keyword_")
                new_cat_rows.append({
                    "list_name": list_name, "layer": "exclusion",
                    "list_group": "scope_exclude", "content_type": "term_list",
                    "match_type": "regex",
                    "settings_symbol": f"SCOPE_EXCLUDE_CUES[{domain}]",
                    "consumed_in": "step3_map, tools/reference_compliance",
                    "purpose": f"Out-of-scope {domain.upper()} domain from "
                               f"adjudicated review clusters ({today}).",
                })
                existing_lists.add(list_name)
            for term, _ in _parse_alias_entries(row["Alias_Term"]):
                if (list_name, term) in existing_terms:
                    stats["skipped_existing"] += 1
                    continue
                new_list_rows.append({"list_name": list_name, "term": term,
                                      "provider": PROVIDER, "status": "active",
                                      "notes": note})
                existing_terms.add((list_name, term))
                stats[ptype] += 1

        elif ptype == "disambiguation_rule":
            rule_specs.append({
                "Market": row["Market"], "FY": row["FY"],
                "Rule": row["Alias_Term"], "Spec": row["Rationale"],
                "Guidance": row["Reviewer_Guidance"],
                "Target_Family": row["Proposed_Family"],
                "Cluster_Value_USD": row["Cluster_Value_USD"],
                "Approved_On": today, "Implemented": "",
            })
            stats["rule_spec"] += 1

        elif ptype in ("master_addition", "propose_master_addition"):
            master_props.append({
                "Market": row["Market"], "FY": row["FY"],
                "Proposed_Segment": row["Proposed_Segment"],
                "Proposed_Subsegment": row["Proposed_Subsegment"],
                "Proposed_Product": row["Proposed_Product"],
                "Proposed_Player": row["Proposed_Player"],
                "Proposed_Family": row["Proposed_Family"],
                "Rationale": row["Rationale"],
                "Evidence_Quote": row["Evidence_Quote"],
                "Cluster_Value_USD": row["Cluster_Value_USD"],
                "Proposed_On": today, "Analyst_Decision": "",
            })
            stats["master_proposal"] += 1

    mode = "checked" if check_pending else "approved"
    print(f"[ingest] approved={stats['approved']} {mode}={stats['checked']} -> "
          f"family_alias={stats['family_alias']} "
          f"category_alias={stats['category_alias']} "
          f"scope_term={stats['scope_term']} rule_spec={stats['rule_spec']} "
          f"scope_whitelist={stats['scope_whitelist']} "
          f"master_proposal={stats['master_proposal']} "
          f"skipped_existing={stats['skipped_existing']} "
          f"errors={stats['errors']}")
    if dry_run or check_pending:
        print("[ingest] dry-run: no files written")
        return stats

    if stats["errors"]:
        print("[ingest] ABORTED: invalid approved rows detected; no files written")
        return stats

    if new_cat_rows:
        _append_csv_rows(CATALOG, cat_fields, new_cat_rows)
        print(f"[ingest] +{len(new_cat_rows)} list_catalog rows")
    if new_list_rows:
        _append_csv_rows(TERM_LISTS, list_fields, new_list_rows)
        print(f"[ingest] +{len(new_list_rows)} term_lists rows")
    if new_map_rows:
        _append_csv_rows(TERM_MAPS, map_fields, new_map_rows)
        print(f"[ingest] +{len(new_map_rows)} term_mappings rows")
    if rule_specs:
        n = _append_workbook(REPORT_DIR / "Rule_Spec_Backlog.xlsx",
                             "Rule_Spec_Backlog", pd.DataFrame(rule_specs),
                             ["Market", "FY", "Rule"])
        print(f"[ingest] +{n} rule specs -> Rule_Spec_Backlog.xlsx")
    if master_props:
        n = _append_workbook(REPORT_DIR / "Master_Addition_Proposals.xlsx",
                             "Master_Addition_Proposals",
                             pd.DataFrame(master_props),
                             ["Proposed_Player", "Proposed_Family",
                              "Proposed_Product"])
        print(f"[ingest] +{n} master proposals -> Master_Addition_Proposals.xlsx")

    if new_map_rows or new_list_rows or new_cat_rows:
        print("[ingest] rebuilding reference.sqlite ...")
        subprocess.run([sys.executable,
                        str(REFERENCE_DIR / "build_reference_db.py")],
                       check=True, cwd=str(ROOT))
        print("[ingest] NOTE: rerun affected markets end-to-end "
              "(PK -> India -> VN last) then qc_check.py for the aliases to "
              "take effect.")

    shared = next((p for p in SHARED_DIR_CANDIDATES if p.exists()), None) \
        if shared_log else None
    if shared is not None:
        log_path = shared / "MAPPING_IMPROVEMENT_LOG.xlsx"
        entry = pd.DataFrame([{
            "Update_Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Country": ", ".join(sorted(approved["Market"].unique())),
            "Year": ", ".join(sorted(approved["FY"].unique())),
            "Output_File": "reference/term_lists.csv + term_mappings.csv",
            "Main_Change": (
                f"Ingested {stats['approved']} approved adjudications: "
                f"{stats['family_alias']} family aliases, "
                f"{stats['category_alias']} category aliases, "
                f"{stats['scope_term']} scope terms, "
                f"{stats['scope_whitelist']} scope whitelist terms, "
                f"{stats['rule_spec']} rule specs, "
                f"{stats['master_proposal']} master proposals."),
        }])
        try:
            old = pd.read_excel(log_path, sheet_name="Log", dtype=object) \
                if log_path.exists() else pd.DataFrame()
            log = pd.concat([old, entry], ignore_index=True)
            with pd.ExcelWriter(log_path, engine="xlsxwriter") as xw:
                log.to_excel(xw, sheet_name="Log", index=False)
            print(f"[ingest] logged to {log_path}")
        except Exception as exc:  # shared drive may be read-only/offline
            print(f"[ingest] WARNING could not update shared log: {exc}")
    return stats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--proposals", default=DEFAULT_GLOB,
                    help="glob of Adjudication_Proposals workbooks")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check-pending", action="store_true",
                    help="validate every row, regardless of Approved, without writes")
    ap.add_argument("--no-shared-log", action="store_true",
                    help="skip the shared-drive MAPPING_IMPROVEMENT_LOG entry")
    args = ap.parse_args()
    paths = [Path(p) for p in sorted(glob.glob(args.proposals))]
    if not paths:
        raise SystemExit(f"no proposal workbooks match {args.proposals}")
    print(f"[ingest] reading {len(paths)} proposal workbook(s)")
    stats = apply(paths, dry_run=args.dry_run,
                  shared_log=not args.no_shared_log,
                  check_pending=args.check_pending)
    if stats["errors"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
