"""Verify the aggregate-only results-navigation site against SQLite."""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN = ROOT / "outputs/20260713_llm_adjudication"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", type=Path, default=DEFAULT_RUN / "dashboard/site")
    parser.add_argument("--db", type=Path,
                        default=DEFAULT_RUN / "raw_outputs/prediction_audit.sqlite")
    parser.add_argument("--scorecard", type=Path)
    args = parser.parse_args()
    site, db = args.site, args.db

    pages = ["index.html", "quality.html", "simulator.html", "comparison.html",
             "outputs.html", "schemas.html"]
    required = pages + ["assets/site.css", "assets/site.js", "assets/data.js"]
    for name in required:
        assert (site / name).is_file(), f"Missing {name}"
    raw = (site / "assets/data.js").read_text(encoding="utf-8")
    assert raw.startswith("window.RESULTS_DATA=")
    packed_json = raw.removeprefix("window.RESULTS_DATA=").split(";RESULTS_DATA.detail=", 1)[0]
    data = json.loads(packed_json)
    forbidden = {"source_row_id", "description", "detailed_product", "evidence_quote", "payload_json"}
    # Workbook schema metadata is intentionally documented on the schema page and
    # may name row-level columns.  The dashboard must not contain values for those
    # fields outside that metadata.
    business_payload = {key: value for key, value in data.items() if key != "schemas"}
    business_json = json.dumps(business_payload, ensure_ascii=False).lower()
    assert not (forbidden & set(business_json.split('"'))), "Dashboard contains row-level fields"
    fields = data["metadata"]["detail_fields"]
    data["detail"] = [dict(zip(fields, row)) for row in data["detail"]]
    assert len(data["schemas"]) == 6
    assert {x["dimension"] for x in data["detail"]} == {
        "family", "manufacturer", "product", "segment", "sub_segment"
    }

    conn = sqlite3.connect(f"file:{db.resolve().as_posix()}?mode=ro", uri=True)
    expected = {
        (r[0], r[1]): (r[2], r[3], r[4])
        for r in conn.execute("""SELECT output_file_id,output_tier,count(*),
                                 coalesce(sum(value_usd),0),coalesce(sum(volume),0)
                            FROM row_fact GROUP BY 1,2""")
    }
    actual = {(x["file"], x["tier"]): (x["rows"], x["value"], x["volume"])
              for x in data["totals"]}
    assert actual.keys() == expected.keys()
    for key in expected:
        for got, want in zip(actual[key], expected[key]):
            assert abs(got - want) < 0.01, (key, got, want)

    grouped = defaultdict(lambda: [0, 0.0, 0.0])
    for x in data["detail"]:
        acc = grouped[(x["dimension"], x["file"], x["tier"])]
        acc[0] += x["rows"]
        acc[1] += x["value"]
        acc[2] += x["volume"]
    for (dimension, file_id, tier), got in grouped.items():
        want = expected[(file_id, tier)]
        for value, target in zip(got, want):
            assert abs(value - target) < 0.01, (dimension, file_id, tier, value, target)

    simulator = data["simulator"]
    gates = {g["key"]: g["bit"] for g in simulator["gates"]}
    assert gates and sum(gates.values()) == simulator["mask_max"]
    sim_totals = defaultdict(lambda: [0, 0.0, 0.0])
    for group in simulator["groups"]:
        assert group["gate"] in gates
        assert 0 <= group["mask"] <= simulator["mask_max"]
        assert "examples" not in group, "Aggregate dashboard must not embed row examples"
        for i, value in enumerate(group["m"]):
            sim_totals[group["file"]][i] += value
    for file_id in {key[0] for key in expected}:
        locked = simulator["locked"][file_id]["m"]
        got = [sim_totals[file_id][i] + locked[i] for i in range(3)]
        want = [
            sum(expected.get((file_id, tier), (0, 0.0, 0.0))[i]
                for tier in ("Review", "Excluded"))
            for i in range(3)
        ]
        for value, target in zip(got, want):
            # The simulator and row totals sum the same IEEE-754 values in a
            # different order.  At India-scale totals that can create a few
            # cents of harmless floating-point drift, while row counts remain
            # exact.  Five cents is still far below the displayed precision.
            assert abs(value - target) < 0.05, ("simulator", file_id, value, target)
    conn.close()

    if args.scorecard:
        expected_score = json.loads(args.scorecard.read_text(encoding="utf-8"))
        assert data["scorecard"]["realized_recall"] == expected_score["realized_recall"]
        assert data["scorecard"]["population"] == expected_score["population"]

    comparison = (site / "comparison.html").read_text(encoding="utf-8")
    assert "&lt;Unmapped&gt;" in comparison and "Unspecified" in comparison
    quality = (site / "quality.html").read_text(encoding="utf-8")
    assert "Gross row recovery" in quality and "net change in Trusted" in quality
    assert "Value-weighted precision" in quality
    assert "Mean Average Precision" in quality and "LLM" in quality
    outputs = (site / "outputs.html").read_text(encoding="utf-8")
    assert "Raw outputs" in outputs and "All rows" in outputs
    assert "Dashboard" in outputs and "Aggregate statistics only" in outputs
    assert "href=\"" not in outputs.lower() or all(
        suffix not in outputs.lower()
        for suffix in (".sqlite\"", ".sqlite'", ".json\"", ".json'")
    ), "Business outputs page must not link SQLite or JSON backend files"
    assert "internal processing backend" in outputs.lower()
    simulator_page = (site / "simulator.html").read_text(encoding="utf-8")
    assert "Simulation only" in simulator_page and "no production change" in simulator_page
    for page in pages:
        text = (site / page).read_text(encoding="utf-8")
        assert "assets/site.css" in text and "assets/site.js" in text
        assert ".sqlite\"" not in text.lower() and ".json\"" not in text.lower(), (
            page,
            "Dashboard pages must not link backend data files",
        )
    print(f"PASS: {len(expected)} totals and {len(grouped)} dimension totals reconcile")
    print(f"PASS: {len(simulator['groups'])} what-if groups reconcile to every non-Trusted row")
    print(f"PASS: aggregate-only payload, {len(data['detail'])} comparison groups, 6 workbook schemas")


if __name__ == "__main__":
    main()
