"""
READ-ONLY: count, in a STALE market workbook's RawData, the exact mislabelled
rows the iter-5 precision fixes (Onyx guard, engine/radiopaque blacklist,
export/xpress blacklist) will correct on the next re-run. Quantifies the
precision gain on the delivered file without re-running the 2M-row pipeline.

Usage: python tools/measure_fix_impact.py outputs/Pakistan_ML_Map_Mapped.xlsx
Nothing is written.
"""
import sys
from pathlib import Path

import openpyxl

# (label-substring in Product_V0, trigger token in description) each fix corrects
SIGS = {
    "engine -> Aspiration Pump":           ("aspiration pump", "engine"),
    "radiopaque -> Bone Cement":           ("bone cement", "radiopaque"),
    "export/xpress generic":               (None, "export"),
}
# Onyx guard replicates TIER1_CONFLICT_GUARDS embolic rule: a Liquid-Embolic
# family hit is RELEASED (corrected) only when desc names a stent/coronary/
# endovascular cue AND lacks a genuine embolization cue.
ONYX_FORBID = ("stent", "coronary", "endovascular", " des ", "des ")
ONYX_ALLOW = ("embolization", "embolisation", "aneurysm", "avm", "fistula",
              "malformation")


def main(xlsx: str):
    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    ws = wb["RawData"]
    rows = ws.iter_rows(values_only=True)
    header = list(next(rows))
    col = {h: i for i, h in enumerate(header)}
    di = col.get("Detailed_Product")
    pi = col.get("Product_V0")
    vi = col.get("Total_Value_USD")
    si = col.get("Match_Status")

    keys = list(SIGS) + ["Onyx coronary/DES -> Liquid Embolic (guard-released)"]
    counts = {k: [0, 0.0] for k in keys}
    examples = {k: [] for k in keys}
    matched = 0
    for row in rows:
        if si is not None and str(row[si]).strip() != "Matched":
            continue
        matched += 1
        desc = str(row[di]).lower() if di is not None else ""
        prod = str(row[pi]).lower() if pi is not None else ""
        try:
            val = float(row[vi]) if row[vi] not in (None, "") else 0.0
        except (TypeError, ValueError):
            val = 0.0
        for name, (plab, tok) in SIGS.items():
            if tok in desc and (plab is None or plab in prod):
                counts[name][0] += 1
                counts[name][1] += val
                if len(examples[name]) < 3:
                    examples[name].append((str(row[di])[:70], str(row[pi])))
        if "embol" in prod and any(f in desc for f in ONYX_FORBID) \
                and not any(a in desc for a in ONYX_ALLOW):
            k = "Onyx coronary/DES -> Liquid Embolic (guard-released)"
            counts[k][0] += 1
            counts[k][1] += val
            if len(examples[k]) < 3:
                examples[k].append((str(row[di])[:70], str(row[pi])))
    wb.close()

    print(f"\n=== {Path(xlsx).name}: {matched:,} matched rows ===")
    tot_n = tot_v = 0
    for name in keys:
        n, v = counts[name]
        tot_n += n
        tot_v += v
        print(f"\n{name}: {n} rows, ${v/1e6:.2f}M")
        for d, p in examples[name]:
            print(f"    prod={p!r:34s} | {d}")
    print(f"\nTOTAL fix-corrected mislabels: {tot_n} rows, ${tot_v/1e6:.2f}M "
          f"({tot_n/max(matched,1):.2%} of matched)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1
         else "outputs/Pakistan_ML_Map_Mapped.xlsx")
