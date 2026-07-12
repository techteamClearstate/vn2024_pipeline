#!/usr/bin/env python3
"""Compare two prediction-audit authorities and quantify realized recall change."""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

TIERS = ("Trusted", "Review", "Excluded")


def _connect(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise SystemExit(f"Audit database not found: {path}")
    con = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _rows(con: sqlite3.Connection) -> dict[tuple[str, str], sqlite3.Row]:
    records = con.execute(
        """SELECT output_file_id,source_row_id,output_tier,removal_stage_id,
                  primary_reason,COALESCE(value_usd,0) value_usd,
                  COALESCE(volume,0) volume,source_text_hash
             FROM row_fact"""
    ).fetchall()
    result = {(r["output_file_id"], r["source_row_id"]): r for r in records}
    if len(result) != len(records):
        raise SystemExit("row_fact identity is not unique by file + source row")
    return result


def _metric(rows) -> dict:
    return {"rows": len(rows), "value_usd": sum(float(r["value_usd"]) for r in rows),
            "volume": sum(float(r["volume"]) for r in rows)}


def compare(baseline: Path, candidate: Path, allow_population_change: bool = False) -> dict:
    con = _connect(baseline)
    try:
        if not candidate.exists():
            raise SystemExit(f"Audit database not found: {candidate}")
        con.execute("ATTACH DATABASE ? AS cand", (f"file:{candidate.resolve()}?mode=ro",))
        scalar = lambda sql: con.execute(sql).fetchone()[0]
        bcount = scalar("SELECT COUNT(*) FROM main.row_fact")
        ccount = scalar("SELECT COUNT(*) FROM cand.row_fact")
        common = scalar("""SELECT COUNT(*) FROM main.row_fact b JOIN cand.row_fact c
          ON c.output_file_id=b.output_file_id AND c.source_row_id=b.source_row_id""")
        missing, added = bcount-common, ccount-common
        if (missing or added) and not allow_population_change:
            raise SystemExit(f"Population differs: {missing} baseline-only, {added} candidate-only")
        changed_source = scalar("""SELECT COUNT(*) FROM main.row_fact b JOIN cand.row_fact c
          ON c.output_file_id=b.output_file_id AND c.source_row_id=b.source_row_id
          WHERE b.source_text_hash<>c.source_text_hash""")
        transition_rows = con.execute("""SELECT b.output_tier old,c.output_tier new,COUNT(*) rows,
          COALESCE(SUM(b.value_usd),0) value_usd,COALESCE(SUM(b.volume),0) volume
          FROM main.row_fact b JOIN cand.row_fact c ON c.output_file_id=b.output_file_id
          AND c.source_row_id=b.source_row_id GROUP BY old,new""").fetchall()
        transition_map = {(r["old"], r["new"]): r for r in transition_rows}
        transitions = []
        for old in TIERS:
            for new in TIERS:
                r = transition_map.get((old, new))
                transitions.append({"from": old, "to": new, "rows": int(r["rows"]) if r else 0,
                                    "value_usd": float(r["value_usd"]) if r else 0.0,
                                    "volume": float(r["volume"]) if r else 0.0})
        def transition_metric(where: str) -> dict:
            r = con.execute(f"""SELECT COUNT(*) rows,COALESCE(SUM(b.value_usd),0) value_usd,
              COALESCE(SUM(b.volume),0) volume FROM main.row_fact b JOIN cand.row_fact c
              ON c.output_file_id=b.output_file_id AND c.source_row_id=b.source_row_id WHERE {where}""").fetchone()
            return {"rows": int(r["rows"]), "value_usd": float(r["value_usd"]), "volume": float(r["volume"])}
        new_m = transition_metric("b.output_tier<>'Trusted' AND c.output_tier='Trusted'")
        lost_m = transition_metric("b.output_tier='Trusted' AND c.output_tier<>'Trusted'")
        by_gate = [dict(r) for r in con.execute("""SELECT b.removal_stage_id baseline_stage,
          b.primary_reason baseline_reason,COUNT(*) rows,COALESCE(SUM(b.value_usd),0) value_usd,
          COALESCE(SUM(b.volume),0) volume FROM main.row_fact b JOIN cand.row_fact c
          ON c.output_file_id=b.output_file_id AND c.source_row_id=b.source_row_id
          WHERE b.output_tier<>'Trusted' AND c.output_tier='Trusted'
          GROUP BY b.removal_stage_id,b.primary_reason ORDER BY value_usd DESC""")]
        files = [r[0] for r in con.execute("SELECT output_file_id FROM main.row_fact UNION SELECT output_file_id FROM cand.row_fact ORDER BY 1")]
        tier_totals = []
        for file_id in files + ["OVERALL"]:
            for tier in TIERS:
                def total(schema):
                    where, params = "output_tier=?", [tier]
                    if file_id != "OVERALL": where += " AND output_file_id=?"; params.append(file_id)
                    r = con.execute(f"SELECT COUNT(*) rows,COALESCE(SUM(value_usd),0) value_usd,COALESCE(SUM(volume),0) volume FROM {schema}.row_fact WHERE {where}", params).fetchone()
                    return {"rows": int(r["rows"]), "value_usd": float(r["value_usd"]), "volume": float(r["volume"])}
                bm, cm = total("main"), total("cand")
                tier_totals.append({"file": file_id, "tier": tier, "baseline": bm, "candidate": cm,
                                    "delta": {x: cm[x]-bm[x] for x in bm}})
    finally:
        con.close()
    return {
        "baseline": str(baseline), "candidate": str(candidate),
        "population": {"baseline_rows": bcount, "candidate_rows": ccount,
                       "common_rows": common, "baseline_only": missing,
                       "candidate_only": added, "changed_source_hash": changed_source},
        "realized_recall": {"newly_trusted": new_m, "lost_trusted": lost_m,
                            "net_trusted": {x: new_m[x] - lost_m[x] for x in new_m},
                            "recovered_by_baseline_gate": by_gate},
        "tier_totals": tier_totals, "transition_matrix": transitions,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--allow-population-change", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = compare(args.baseline, args.candidate, args.allow_population_change)
    payload = json.dumps(result, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload + "\n", encoding="utf-8")
        print(f"PASS: wrote {args.out}")
    else:
        print(payload)


if __name__ == "__main__":
    main()
