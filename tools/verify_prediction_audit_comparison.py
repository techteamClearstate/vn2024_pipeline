#!/usr/bin/env python3
"""Synthetic verification for compare_prediction_audits.py."""
from pathlib import Path
import sqlite3
import tempfile

from compare_prediction_audits import compare


def make(path: Path, rows) -> None:
    con = sqlite3.connect(path)
    con.execute("""CREATE TABLE row_fact(output_file_id TEXT,source_row_id TEXT,output_tier TEXT,
      removal_stage_id TEXT,primary_reason TEXT,value_usd REAL,volume REAL,source_text_hash TEXT)""")
    con.executemany("INSERT INTO row_fact VALUES (?,?,?,?,?,?,?,?)", rows)
    con.commit(); con.close()


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        b, c = Path(td)/"b.sqlite", Path(td)/"c.sqlite"
        make(b, [("VN_2024","1","Review","S07","Reference",100,2,"a"),
                 ("VN_2024","2","Trusted","S14","Trusted",50,1,"b"),
                 ("PK_2024","3","Excluded","S03","Dental",20,4,"c")])
        make(c, [("VN_2024","1","Trusted","S14","Trusted",100,2,"a"),
                 ("VN_2024","2","Review","S07","Reference",50,1,"b"),
                 ("PK_2024","3","Excluded","S03","Dental",20,4,"c")])
        result = compare(b, c)
        rr = result["realized_recall"]
        assert rr["newly_trusted"] == {"rows": 1, "value_usd": 100.0, "volume": 2.0}
        assert rr["lost_trusted"] == {"rows": 1, "value_usd": 50.0, "volume": 1.0}
        assert rr["net_trusted"] == {"rows": 0, "value_usd": 50.0, "volume": 1.0}
        assert rr["recovered_by_baseline_gate"][0]["baseline_stage"] == "S07"
        assert sum(x["rows"] for x in result["transition_matrix"]) == 3
    print("PASS: audit comparison synthetic recovery, regression, gates, and reconciliation")


if __name__ == "__main__":
    main()
