#!/usr/bin/env python3
"""Acceptance checks for the Recall Funnel Dashboard (review-only artifact).

Re-derives the dashboard's embedded numbers straight from the SQLite authority
and asserts they reconcile, that the additive funnel and the recovery buckets
partition their populations exactly, and that the HTML is genuinely
self-contained (no external network references). Exit code 0 = all pass.

Usage:
    PYTHONIOENCODING=utf-8 python tools/verify_funnel_dashboard.py \
        [--db outputs/<run_id>/prediction_audit.sqlite] \
        [--html outputs/<run_id>/Recall_Funnel_Dashboard.html]
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

from build_funnel_dashboard import GATES, _gate_bit_case, _gate_case, _secondary_bit_case
from precision_measurement import RANDOM_SAMPLE, TARGETED_SAMPLE, build_measured_accuracy

REPO = Path(__file__).resolve().parents[1]
DEFAULT_RUN = "20260712_recall_audit_v3"
TOL_VAL = 1.0      # USD tolerance (rounding to cents in the payload)
TOL_VOL = 1.0
EXAMPLE_BUDGET = 600 * 1024

checks: list[tuple[bool, str]] = []


def check(ok: bool, msg: str) -> None:
    checks.append((bool(ok), msg))


def extract_payload(html: str) -> dict:
    i = html.index("const DATA =") + len("const DATA =")
    j = html.index("const TIERK", i)
    raw = html[i:j].strip().rstrip(";").strip()
    return json.loads(raw)


def q(cur, sql, *a):
    return list(cur.execute(sql, a))


def metric_ok(a, b) -> bool:
    return int(a[0]) == int(b[0]) and abs(float(a[1]) - float(b[1])) < TOL_VAL \
        and abs(float(a[2]) - float(b[2])) < TOL_VOL


def create_sim_rows(cur) -> None:
    cur.executescript("DROP TABLE IF EXISTS temp.verify_sim_row; DROP TABLE IF EXISTS temp.verify_secondary;")
    cur.execute(f"""
        CREATE TEMP TABLE verify_secondary AS
        SELECT rh.row_fact_id,
               SUM(DISTINCT {_secondary_bit_case('rh')}) AS mask
          FROM rule_hit rh
         WHERE rh.hit_kind='secondary'
         GROUP BY rh.row_fact_id
    """)
    cur.execute(f"""
        CREATE TEMP TABLE verify_sim_row AS
        SELECT rf.row_fact_id, rf.output_file_id, {_gate_case('rf')} AS primary_gate,
               ((COALESCE(vs.mask,0) | 0) & ~({_gate_bit_case('rf')})) AS secondary_mask,
               rf.value_usd, rf.volume
          FROM row_fact rf
          LEFT JOIN verify_secondary vs ON vs.row_fact_id=rf.row_fact_id
         WHERE rf.output_tier<>'Trusted'
    """)
    cur.execute("CREATE INDEX temp.idx_verify_sim ON verify_sim_row(output_file_id,primary_gate,secondary_mask)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(REPO / "outputs" / DEFAULT_RUN / "prediction_audit.sqlite"))
    ap.add_argument("--html", default=None)
    ap.add_argument("--skip-render", action="store_true", help="Skip the Playwright render harness")
    args = ap.parse_args()
    db = Path(args.db)
    html_path = Path(args.html) if args.html else db.parent / "Recall_Funnel_Dashboard.html"

    check(db.exists(), f"SQLite authority exists: {db}")
    check(html_path.exists(), f"Dashboard HTML exists: {html_path}")
    if not (db.exists() and html_path.exists()):
        return report()

    html = html_path.read_text(encoding="utf-8")

    # --- self-contained: no external network references --------------------
    externals = re.findall(r'(?:src|href)\s*=\s*["\']https?://[^"\']+', html)
    externals += re.findall(r'@import\s+["\']?https?://', html)
    externals += re.findall(r'url\(\s*https?://', html)
    check(not externals, f"No external network references ({len(externals)} found)")

    data = None
    try:
        data = extract_payload(html)
        check(True, "Embedded DATA payload is valid JSON")
    except Exception as e:  # noqa: BLE001
        check(False, f"Embedded DATA payload parses: {e}")
        return report()

    check(data.get("attribution", {}).get("india_reference_status") is True,
          "Dashboard declares the governed India FY2025 reference attribution fix")
    check("India FY2025 attribution fixed:" in html,
          "Dashboard template includes the corrected India FY2025 attribution explanation")

    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    cur = con.cursor()

    file_ids = [f["id"] for f in data["files"]]

    # --- measured accuracy: sample design and labels -----------------------
    accuracy = data.get("measured_accuracy", {})
    check(accuracy == build_measured_accuracy(cur, file_ids),
          "Measured-accuracy payload exactly matches the review-label authority")
    sample_counts = q(
        cur,
        """SELECT COUNT(*),
                  SUM(sample_type=?), SUM(sample_type=?),
                  SUM(CASE WHEN surgical_relevance IS NOT NULL AND TRIM(surgical_relevance)<>'' THEN 1 ELSE 0 END)
             FROM review_label""",
        RANDOM_SAMPLE, TARGETED_SAMPLE,
    )[0]
    check(int(accuracy.get("sample_rows", -1)) == int(sample_counts[0]),
          "Measured-accuracy sample count reconciles to review_label")
    check(int(accuracy.get("random_rows", -1)) == int(sample_counts[1] or 0)
          and int(accuracy.get("targeted_rows", -1)) == int(sample_counts[2] or 0),
          "Random and targeted sample populations remain separated")
    check(int(accuracy.get("labels_entered", -1)) == int(sample_counts[3] or 0),
          "Entered-label count reconciles to review_label")
    check(set(accuracy.get("by_scope", {})) == {"ALL", *file_ids},
          "Measured accuracy covers combined and every file scope")
    targeted_rows = [row for scope in accuracy.get("by_scope", {}).values()
                     for row in scope.get("targeted", [])]
    check(all(row[metric]["ci_low"] is None and row[metric]["ci_high"] is None
              for row in targeted_rows for metric in ("relevance", "mapping", "end_to_end")),
          "Targeted diagnostics are never presented with population confidence intervals")

    for scope in file_ids + ["ALL"]:
        where = "" if scope == "ALL" else " WHERE output_file_id=?"
        args_ = () if scope == "ALL" else (scope,)
        tot = q(cur, f"SELECT COUNT(*),COALESCE(SUM(value_usd),0),COALESCE(SUM(volume),0) FROM row_fact{where}", *args_)[0]
        tr = q(cur, f"SELECT COUNT(*),COALESCE(SUM(value_usd),0) FROM row_fact WHERE output_tier='Trusted'"
                    + ("" if scope == "ALL" else " AND output_file_id=?"), *args_)[0]
        F = data["funnel"][scope]
        check(F["total"][0] == tot[0] and abs(F["total"][1] - tot[1]) < TOL_VAL,
              f"[{scope}] funnel total reconciles (rows/value)")
        check(F["trusted"][0] == tr[0] and abs(F["trusted"][1] - tr[1]) < TOL_VAL,
              f"[{scope}] Trusted total reconciles")
        # additive: sum of step losses + trusted == total
        sl = [sum(s["lost"][i] for s in F["steps"]) for i in range(3)]
        check(sl[0] + F["trusted"][0] == F["total"][0]
              and abs(sl[1] + F["trusted"][1] - F["total"][1]) < TOL_VAL,
              f"[{scope}] additive funnel sums to total")
        # tiers sum to total
        ts = [F["trusted"][i] + F["review"][i] + F["excluded"][i] for i in range(3)]
        check(ts[0] == F["total"][0] and abs(ts[1] - F["total"][1]) < TOL_VAL,
              f"[{scope}] Trusted+Review+Excluded = total")
        # recovery buckets partition the non-Trusted population exactly
        held = [F["review"][i] + F["excluded"][i] for i in range(3)]
        rb = data["recovery"][scope]["buckets"]
        bs = [sum(rb[b][i] for b in rb) for i in range(3)]
        check(bs[0] == held[0] and abs(bs[1] - held[1]) < TOL_VAL,
              f"[{scope}] recovery buckets partition held-back rows/value")
        # population cube (segment) totals match file totals
        for dim in ("segment", "file"):
            pop = data["population"][scope][dim]
            ps = [sum(r["T"][i] + r["R"][i] + r["E"][i] for r in pop) for i in range(3)]
            check(ps[0] == tot[0] and abs(ps[1] - tot[1]) < TOL_VAL,
                  f"[{scope}] population[{dim}] totals reconcile")

    # --- exact gate-mask simulator ----------------------------------------
    create_sim_rows(cur)
    actual_groups = {}
    for fid, gate, mask, n, val, vol in q(cur, """
        SELECT output_file_id,primary_gate,secondary_mask,COUNT(*),
               COALESCE(SUM(value_usd),0),COALESCE(SUM(volume),0)
          FROM verify_sim_row WHERE primary_gate IS NOT NULL
         GROUP BY output_file_id,primary_gate,secondary_mask
    """):
        actual_groups[(fid, gate, int(mask))] = [n, val, vol]
    payload_groups = {(g["file"], g["gate"], int(g["mask"])): g["m"] for g in data["simulator"]["groups"]}
    check(set(payload_groups) == set(actual_groups), "Simulator group keys exactly match authority-derived primary gate × secondary mask groups")
    check(all(k in actual_groups and metric_ok(m, actual_groups[k]) for k, m in payload_groups.items()),
          "Simulator group rows/value/volume exactly reconcile")

    gate_keys = {g["key"] for g in GATES}
    gate_bits = {g["key"]: int(g["bit"]) for g in GATES}
    check(all(g["gate"] in gate_keys and not (int(g["mask"]) & gate_bits[g["gate"]])
              and 0 <= int(g["mask"]) <= int(data["simulator"]["mask_max"])
              for g in data["simulator"]["groups"]),
          "Simulator masks contain only secondary gates and exclude each row's primary gate")

    for fid in file_ids:
        toggleable = q(cur, "SELECT COUNT(*),COALESCE(SUM(value_usd),0),COALESCE(SUM(volume),0) FROM verify_sim_row WHERE output_file_id=? AND primary_gate IS NOT NULL", fid)[0]
        locked = q(cur, "SELECT COUNT(*),COALESCE(SUM(value_usd),0),COALESCE(SUM(volume),0) FROM verify_sim_row WHERE output_file_id=? AND primary_gate IS NULL", fid)[0]
        groups_sum = [sum(g["m"][i] for g in data["simulator"]["groups"] if g["file"] == fid) for i in range(3)]
        check(metric_ok(groups_sum, toggleable), f"[{fid}] simulator groups partition all toggleable non-Trusted rows")
        check(metric_ok(data["simulator"]["locked"][fid]["m"], locked), f"[{fid}] locked simulator block exactly reconciles")
        F = data["funnel"][fid]
        all_off_plus_locked = [F["trusted"][i] + groups_sum[i] + locked[i] for i in range(3)]
        check(metric_ok(all_off_plus_locked, F["total"]), f"[{fid}] baseline + all gate releases + locked = total")

    # --- examples: capped, real, and correctly keyed ----------------------
    example_payload = {"cells": data["examples"]["cells"], "rows": data["examples"]["rows"]}
    example_bytes = len(json.dumps(example_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    check(example_bytes == int(data["examples"]["payload_bytes"]), "Recorded examples payload byte count is exact")
    check(example_bytes <= EXAMPLE_BUDGET, f"Examples payload stays within {EXAMPLE_BUDGET:,}-byte budget ({example_bytes:,})")
    refs: set[int] = set()
    for by_stage in data["examples"]["cells"].values():
        for by_reason in by_stage.values():
            for ids in by_reason.values():
                refs.update(map(int, ids))
                check(len(ids) <= 10, "Each file × stage × reason example cell is capped at 10 rows")
    for g in data["simulator"]["groups"]:
        refs.update(map(int, g.get("examples", [])))
    for R in data["recovery"].values():
        for key in ("clusters_misguarded", "clusters_loose", "clusters_mfr"):
            for row in R.get(key, []):
                refs.update(map(int, row.get("examples", [])))
    stored_ids = {int(k) for k in data["examples"]["rows"]}
    check(refs <= stored_ids, "Every example reference resolves in the embedded row store")

    real_rows = {}
    for start in range(0, len(stored_ids), 800):
        chunk = list(stored_ids)[start:start + 800]
        ph = ",".join("?" for _ in chunk)
        for row in q(cur, f"SELECT row_fact_id,output_file_id,source_row_id,removal_stage_id,primary_reason,value_usd FROM row_fact WHERE row_fact_id IN ({ph})", *chunk):
            real_rows[int(row[0])] = row
    check(set(real_rows) == stored_ids, "Every embedded example is a real authority row")
    check(all(data["examples"]["rows"][str(rid)]["file"] == row[1]
              and data["examples"]["rows"][str(rid)]["source_row"] == row[2]
              and data["examples"]["rows"][str(rid)]["stage"] == row[3]
              and data["examples"]["rows"][str(rid)]["reason"] == row[4]
              and abs(float(data["examples"]["rows"][str(rid)]["value"]) - float(row[5] or 0)) < TOL_VAL
              for rid, row in real_rows.items()), "Embedded example identity, attribution, and value match row_fact")
    cell_ok = True
    for fid, by_stage in data["examples"]["cells"].items():
        for stage, by_reason in by_stage.items():
            for reason, ids in by_reason.items():
                cell_ok = cell_ok and all(real_rows[int(i)][1] == fid and real_rows[int(i)][3] == stage and real_rows[int(i)][4] == reason for i in ids)
    check(cell_ok, "Every funnel/hotspot example belongs to its declared file × stage × reason cell")
    sim_example_ok = True
    sim_lookup = set()
    stored_list = list(stored_ids)
    for start in range(0, len(stored_list), 800):
        chunk = stored_list[start:start + 800]
        ph = ",".join("?" for _ in chunk)
        sim_lookup.update((row[0], row[1], row[2], int(row[3])) for row in q(
            cur, f"SELECT row_fact_id,output_file_id,primary_gate,secondary_mask FROM verify_sim_row WHERE primary_gate IS NOT NULL AND row_fact_id IN ({ph})", *chunk))
    for g in data["simulator"]["groups"]:
        sim_example_ok = sim_example_ok and all((int(i), g["file"], g["gate"], int(g["mask"])) in sim_lookup for i in g.get("examples", []))
    check(sim_example_ok, "Every simulator example belongs to its declared primary gate × secondary mask group")

    con.close()

    # --- browser execution across tabs/scopes/toggle states ----------------
    if not args.skip_render:
        harness = REPO / "tools" / "verify_funnel_dashboard_render.py"
        proc = subprocess.run([sys.executable, str(harness), "--html", str(html_path)],
                              cwd=REPO, text=True, capture_output=True, encoding="utf-8")
        if proc.stdout.strip():
            print(proc.stdout.strip())
        if proc.stderr.strip():
            print(proc.stderr.strip(), file=sys.stderr)
        check(proc.returncode == 0, "Headless render harness passes all tabs × scopes × toggle states")
    return report()


def report() -> int:
    passed = sum(1 for ok, _ in checks if ok)
    failed = [m for ok, m in checks if not ok]
    for ok, m in checks:
        print(("  PASS " if ok else "  FAIL ") + m)
    print(f"\n{passed}/{len(checks)} checks passed.")
    if failed:
        print("FAILURES:")
        for m in failed:
            print("  -", m)
        return 1
    print("ALL CHECKS PASSED — dashboard reconciles to the authority and is self-contained.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
