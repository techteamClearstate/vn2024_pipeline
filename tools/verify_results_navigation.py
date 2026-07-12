"""Verify the generated results-navigation site against the audit authority."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "outputs/results_navigation"
DB = ROOT / "outputs/20260712_recall_audit_v3/prediction_audit.sqlite"


def main() -> None:
    required = ["index.html", "quality.html", "comparison.html", "outputs.html", "schemas.html",
                "assets/site.css", "assets/site.js", "assets/data.js"]
    for name in required:
        assert (SITE / name).is_file(), f"Missing {name}"
    raw = (SITE / "assets/data.js").read_text(encoding="utf-8")
    assert raw.startswith("window.RESULTS_DATA=")
    packed_json = raw.removeprefix("window.RESULTS_DATA=").split(";RESULTS_DATA.detail=", 1)[0]
    data = json.loads(packed_json)
    fields = data["metadata"]["detail_fields"]
    data["detail"] = [dict(zip(fields, row)) for row in data["detail"]]
    assert len(data["schemas"]) == 6
    assert {x["dimension"] for x in data["detail"]} == {
        "family", "manufacturer", "product", "segment", "sub_segment"
    }

    conn = sqlite3.connect(f"file:{DB.resolve().as_posix()}?mode=ro", uri=True)
    expected = {
        (r[0], r[1]): (r[2], r[3], r[4])
        for r in conn.execute("""SELECT output_file_id,output_tier,count(*),
                                 coalesce(sum(value_usd),0),coalesce(sum(volume),0)
                            FROM row_fact GROUP BY 1,2""")
    }
    conn.close()
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

    comparison = (SITE / "comparison.html").read_text(encoding="utf-8")
    assert "&lt;Unmapped&gt;" in comparison and "Unspecified" in comparison
    quality = (SITE / "quality.html").read_text(encoding="utf-8")
    assert "additional Trusted rows" in quality and "$232.3M" in quality
    assert "0 / 150" in quality and "Mean Average Precision" in quality
    for page in required[:5]:
        text = (SITE / page).read_text(encoding="utf-8")
        assert "assets/site.css" in text and "assets/site.js" in text
    print(f"PASS: {len(expected)} totals and {len(grouped)} dimension totals reconcile")
    print(f"PASS: {len(data['detail'])} comparison groups; 6 workbook schemas; self-contained assets")


if __name__ == "__main__":
    main()
