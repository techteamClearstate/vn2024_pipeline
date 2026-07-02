#!/usr/bin/env python3
"""
VN 2024 ML Map Enrichment Pipeline — single-command runner
==========================================================
Runs all four stages end-to-end:

    1. extract  — VN .xlsx → TSV cache + build V0 keyword trie
    2. match    — trie keyword matching (HS4-scoped)
    3. map      — join matched keywords to V0 fields
    4. export   — styled .xlsx with green highlighting + summary

Usage:
    python run_pipeline.py                 # full run (Vietnam, default source)
    python run_pipeline.py --skip-extract  # reuse cached TSV/lookup
    python run_pipeline.py --from match     # start at a given stage

Run another market's file without editing config/settings.py — point at its
workbook and label its Dashboard "Country"; the slice is written separately and
combined with any existing market slices:

    python run_pipeline.py --country Pakistan \
        --source data/uploads/PK-2024_imports.xlsx

Place the source files in data/uploads/ first:
    VN-2024_Processed-MLmap_analysis_v0.xlsx   (or the market file you pass)
    Surg_Brand_model_list_V0.xlsx              (shared reference)
"""
import argparse
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import settings as cfg
from src import step1_extract, step2_match, step3_map, step4_export

STAGES = ["extract", "match", "map", "export"]


def _check_inputs():
    missing = [p.name for p in (cfg.VN_SOURCE_XLSX, cfg.V0_REFERENCE_XLSX)
               if not p.exists()]
    if missing:
        print("ERROR: missing source file(s) in data/uploads/:")
        for m in missing:
            print(f"   - {m}")
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description="VN 2024 ML Map pipeline")
    ap.add_argument("--from", dest="start", choices=STAGES, default="extract",
                    help="stage to start from (default: extract)")
    ap.add_argument("--skip-extract", action="store_true",
                    help="reuse cached TSV + lookup (equivalent to --from match)")
    ap.add_argument("--country", default=None,
                    help="import market for the Dashboard 'Country' dimension "
                         "(default: cfg.IMPORT_COUNTRY). Each market writes its "
                         "own dashboard slice; all slices are combined on export.")
    ap.add_argument("--source", default=None,
                    help="path to the market's import workbook "
                         "(default: cfg.VN_SOURCE_XLSX)")
    args = ap.parse_args()

    # Per-run overrides so another market can be processed without editing config.
    if args.country:
        cfg.IMPORT_COUNTRY = args.country
    if args.source:
        cfg.VN_SOURCE_XLSX = Path(args.source)

    start = "match" if args.skip_extract else args.start
    start_idx = STAGES.index(start)

    if start_idx == 0:
        _check_inputs()

    t0 = time.time()
    print("=" * 60)
    print("VN 2024 ML MAP ENRICHMENT PIPELINE")
    print(f"  market (Country) : {cfg.IMPORT_COUNTRY}")
    print(f"  source workbook  : {cfg.VN_SOURCE_XLSX.name}")
    print("=" * 60)

    if start_idx <= 0:
        print("\n[1/4] Extraction")
        step1_extract.extract_vn_to_tsv()
        step1_extract.build_keyword_lookup()
        step1_extract.build_category_lexicon()
        step1_extract.build_manufacturer_lexicon()
        step1_extract.build_product_canonical_map()

    if start_idx <= 1:
        print("\n[2/4] Matching")
        step2_match.run_matching()

    if start_idx <= 2:
        print("\n[3/4] Mapping")
        step3_map.run_mapping()

    if start_idx <= 3:
        print("\n[4/4] Export")
        out = step4_export.run_export()

    print("\n" + "=" * 60)
    print(f"DONE in {time.time() - t0:.1f}s")
    print(f"Output: {out}")
    print("=" * 60)


if __name__ == "__main__":
    main()
