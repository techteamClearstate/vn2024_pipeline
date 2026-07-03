"""
Build a cached ground-truth benchmark table from the human-labeled
"Client Ready" VN import files (one per Medtronic OU), filtered to CAL_FY 2024.

Output: data/intermediate/benchmark_gt_2024.csv with the columns the evaluation
harness needs: a normalized description + HS + value join key plus the human
labels (OU / OU_Device / Family Name / Manufacturer Name).
"""
import os
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import settings as cfg

BENCH_DIR = Path(
    r"G:\共享云端硬盘\CS Shared Drive\Projects\2024"
    r"\(2405) 347643 Medtronic Vietnam Import Data\Working\5. Cleaning\SI\Client Ready"
)

# Latest version per OU (skip superseded v3/v4/v1 duplicates).
PICKS = [
    "VN Import Data_FY20-24_CRDN_v3.0.xlsb",
    "VN Import Data_FY20-24_CRM_v4.0.xlsb",
    "VN Import Data_FY20-24_CSF_v1.0.xlsx",
    "VN Import Data_FY20-24_CST_Spine_v1.0.xlsb",
    "VN Import Data_FY20-24_CST_Trauma v1.0.xlsb",
    "VN Import Data_FY20-24_CST_v2.0.xlsx",
    "VN Import Data_FY20-24_CS_V2.0.xlsb",
    "VN Import Data_FY20-24_NV_v4.0.xlsb",
    "VN Import Data_FY20-24_SH_v1.0.xlsb",
    "VN Import Data_FY20-24_SI_v5.0.xlsx",
]

KEEP = ["Detailed_Product_EN", "Detailed_Product", "HS_Code", "Total_Value_USD",
        "OU", "OU_Device", "Family Name", "Manufacturer Name", "CAL_FY"]

OUT = cfg.INTERMEDIATE / "benchmark_gt_2024.csv"


def norm_desc(s) -> str:
    """Normalized join key from a description: lowercase alnum, collapse space."""
    s = re.sub(r"[^a-z0-9]+", " ", str(s).lower())
    return re.sub(r"\s+", " ", s).strip()


def main():
    frames = []
    for fname in PICKS:
        path = BENCH_DIR / fname
        eng = "pyxlsb" if fname.lower().endswith(".xlsb") else None
        df = pd.read_excel(path, sheet_name="Raw Data", engine=eng)
        df = df[[c for c in KEEP if c in df.columns]].copy()
        df["src_file"] = fname
        # CAL_FY may be float in some files
        df["CAL_FY"] = pd.to_numeric(df["CAL_FY"], errors="coerce")
        df = df[df["CAL_FY"] == 2024]
        frames.append(df)
        print(f"  {fname[19:]:34s} 2024 rows: {len(df):6d}")

    gt = pd.concat(frames, ignore_index=True)
    gt["hs_code"] = pd.to_numeric(gt["HS_Code"], errors="coerce").astype("Int64")
    gt["value"] = pd.to_numeric(gt["Total_Value_USD"], errors="coerce").round(0).astype("Int64")
    gt["desc_key"] = gt["Detailed_Product_EN"].map(norm_desc)
    gt.to_csv(OUT, index=False, encoding="utf-8")
    print(f"\n  TOTAL 2024 ground-truth rows: {len(gt):,} -> {OUT.name}")
    print("  OU distribution:")
    print(gt["OU"].value_counts().to_string())


if __name__ == "__main__":
    main()
