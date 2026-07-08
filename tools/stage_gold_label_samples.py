"""Stage analyst gold-label samples from the QA reports' Gold_Label_Template.

Draws a ~400-row, value-weighted, bucket-stratified labelling sample per
market-year (IMPROVEMENT_METHODS.md item A5: market-native ground truth for
PK/India) and writes `Gold_Label_Sample_<Market>_FY<yr>.xlsx` locally, plus a
copy into the shared delivery folder's `4. Manual Mapped Files/` when mounted.
Labels returned by analysts feed market-native priors and the held-out eval.

Run: PYTHONIOENCODING=utf-8 python tools/stage_gold_label_samples.py
"""

from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPORT_DIR = ROOT / "outputs" / "remapped_current" / "reports"
SHARED_ROOT_CANDIDATES = [
    Path(r"G:\Shared drives\New EIU Gateway\0. Gateway Ops & Databases"
         r"\Import Data Master\6. Workflow\Surgicals\Claude code"),
    Path(r"G:\共享云端硬盘\New EIU Gateway\0. Gateway Ops & Databases"
         r"\Import Data Master\6. Workflow\Surgicals\Claude code"),
]

TARGETS = [("Pakistan", 2024), ("India", 2024), ("India", 2025)]

# bucket -> row cap; ordered by review priority (value-descending inside each)
BUCKET_CAPS = [
    ("extended_hs_ge_25k_100pct", 60),
    ("review_queue_ge_50k_100pct", 150),
    ("excluded_surgicalish_stratified", 60),
    ("qa_bucket_review_sample", 80),
    ("clean_trusted_value_sample", 80),   # precision audit slice
]


def stage(market: str, fy: int) -> Path | None:
    report = REPORT_DIR / f"{market}_FY{fy}_Surgical_Mapping_QA_Report.xlsx"
    if not report.exists():
        print(f"[gold] SKIP {market} FY{fy}: {report.name} not found")
        return None
    g = pd.read_excel(report, sheet_name="Gold_Label_Template", dtype=str)
    g["_val"] = pd.to_numeric(g["Value_USD_num"], errors="coerce").fillna(0)
    parts = []
    for bucket, cap in BUCKET_CAPS:
        sub = (g[g["Sampling_Bucket"].eq(bucket)]
               .sort_values("_val", ascending=False).head(cap))
        parts.append(sub)
    sample = (pd.concat(parts, ignore_index=True)
              .drop_duplicates("UniqueID").drop(columns=["_val"]))
    out = REPORT_DIR / f"Gold_Label_Sample_{market}_FY{fy}.xlsx"
    with pd.ExcelWriter(out, engine="xlsxwriter") as xw:
        sample.to_excel(xw, sheet_name="Gold_Label_Sample", index=False)
        ws = xw.sheets["Gold_Label_Sample"]
        ws.freeze_panes(1, 0)
        ws.set_column(0, len(sample.columns), 24)
        pd.DataFrame([
            ("Purpose", "Analyst gold labels for market-native evaluation "
                        "and priors (fill the true_* columns)."),
            ("true_scope", "in_scope_surgical / out_of_scope / unsure"),
            ("true_segment..true_family", "Master taxonomy labels where "
                                          "known; blank if not determinable"),
            ("label_confidence", "high / medium / low"),
            ("Return to", "techteam@clearstate.com or drop in the same "
                          "folder with '_LABELLED' suffix"),
        ], columns=["Field", "Instruction"]).to_excel(
            xw, sheet_name="Instructions", index=False)
        xw.sheets["Instructions"].set_column(0, 1, 45)
    print(f"[gold] {market} FY{fy}: {len(sample)} rows -> {out.name}")
    return out


def main() -> None:
    staged = [p for m, y in TARGETS if (p := stage(m, y)) is not None]
    if not staged:
        return
    shared = next((p for p in SHARED_ROOT_CANDIDATES if p.exists()), None)
    if shared is None:
        print("[gold] shared folder not mounted; local staging only")
        return
    dest = shared / "4. Manual Mapped Files"
    dest.mkdir(exist_ok=True)
    for p in staged:
        shutil.copy2(p, dest / p.name)
        print(f"[gold] published {p.name} -> {dest}")
    log = shared / "5. Documentation" / "DATA_UPDATES_LOG.md"
    if log.exists():
        stamp = datetime.now().strftime("%Y-%m-%d")
        entry = (f"\n## {stamp} — Gold-label samples staged\n\n"
                 f"- Added {', '.join(p.name for p in staged)} to "
                 f"`4. Manual Mapped Files/` (value-weighted, bucket-stratified "
                 f"labelling samples from the Surgical Mapping QA reports; "
                 f"analysts fill the `true_*` columns to build market-native "
                 f"ground truth for Pakistan/India).\n")
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(entry)
        print(f"[gold] logged in {log.name}")


if __name__ == "__main__":
    main()
