"""
Random-sample mapping-precision spot check, per market.

GOAL (user): comprehensively improve until a random spot check of ~100+ mapped
lines in EACH dataset shows precision > 90%.

Two modes:
  * VN (has ground truth): join the sampled mapped lines to benchmark_gt_2024.csv
    and auto-score Product/Family/Manufacturer against the labels, print the
    disagreements, and report precision. Sampled from MAPPED_CSV (fast).
  * PK / India (no GT): reservoir-sample N *matched* lines straight from the
    market workbook's RawData sheet (openpyxl read-only, so India's 764k rows
    stream without loading), and print description + assigned dims for human/LLM
    eyeball judgement. Nothing is scored automatically.

Usage:
  python tools/spot_check_precision.py vn            [N]
  python tools/spot_check_precision.py pakistan      [N]
  python tools/spot_check_precision.py india         [N]
  python tools/spot_check_precision.py <path.xlsx>   [N]
Nothing is written.
"""
import random
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import settings as cfg

SEED = 20260703
DIMS = ["Segment", "Sub-segment", "Product_V0", "Family", "Manufacturer",
        "Match_Tier", "Match_Scope"]


def _nd(s):
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


def _overlap(a, b):
    """True if the two labels share a 4-char-stemmed content token (same loose
    match the benchmark evaluator uses)."""
    sa = {w[:4] for w in _nd(a).split() if len(w) >= 3}
    sb = {w[:4] for w in _nd(b).split() if len(w) >= 3}
    return bool(sa & sb)


def _ok(pred, gt):
    if not str(gt).strip():
        return None                      # no GT for this dim → skip
    np_, ng = _nd(pred), _nd(gt)
    if np_ and ng and (np_ in ng or ng in np_):
        return True
    return _overlap(pred, gt)


def check_vn(n: int):
    from tools.eval_benchmark import load
    gt, mp = load()
    g1 = gt.dropna(subset=["jk"]).drop_duplicates("jk", keep="first").set_index("jk")
    mp = mp.copy()
    mp["OU_Device"] = mp["jk"].map(g1["OU_Device"])
    mp["gtFam"] = mp["jk"].map(g1["Family Name"])
    matched = mp[mp["Match_Status"].fillna("") == "Matched"].copy()
    scored = matched[matched["OU_Device"].notna()]
    idx = list(scored.index)
    random.Random(SEED).shuffle(idx)
    idx = idx[:n]
    nprod = okprod = 0
    bad = []
    for i in idx:
        r = scored.loc[i]
        v = _ok(r.get("Product_V0", ""), r.get("OU_Device", ""))
        if v is None:
            continue
        nprod += 1
        if v:
            okprod += 1
        else:
            bad.append((str(r.get(cfg.VN_DESCRIPTION_COL, ""))[:70],
                        r.get("Product_V0", ""), r.get("OU_Device", ""),
                        r.get("Match_Tier", "")))
    print(f"\n=== VN spot check — {nprod} scorable of {len(idx)} sampled matched lines ===")
    print(f"PRODUCT precision: {okprod}/{nprod} = {okprod/max(nprod,1):.1%}")
    print(f"\nfirst {min(len(bad),25)} product disagreements (pred | GT | tier):")
    for d, p, g, t in bad[:25]:
        print(f"  [{t:10s}] {d}\n       pred={p!r}  gt={g!r}")


def _market_xlsx(market: str) -> str:
    m = market.lower()
    if m.endswith(".xlsx"):
        return market
    name = {"vn": "Vietnam", "vietnam": "Vietnam", "pakistan": "Pakistan",
            "pk": "Pakistan", "india": "India", "in": "India"}.get(m, market)
    return str(cfg.OUTPUT_DIR / f"{name}_ML_Map_Mapped.xlsx") \
        if hasattr(cfg, "OUTPUT_DIR") else f"outputs/{name}_ML_Map_Mapped.xlsx"


def check_market(xlsx: str, n: int):
    import openpyxl
    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    ws = wb["RawData"]
    rows = ws.iter_rows(values_only=True)
    header = list(next(rows))
    col = {h: i for i, h in enumerate(header)}
    di = col.get(cfg.VN_DESCRIPTION_COL)
    hi = col.get("HS_Code")
    ti = col.get("Match_Tier")
    si = col.get("Match_Status")
    rng = random.Random(SEED)
    res, seen = [], 0
    for row in rows:
        if si is not None and str(row[si]).strip() != "Matched":
            continue
        seen += 1
        if len(res) < n:
            res.append(row)
        else:
            j = rng.randint(0, seen - 1)
            if j < n:
                res[j] = row
    wb.close()
    print(f"\n=== {Path(xlsx).name} — {n} random matched lines of {seen:,} matched "
          f"(NO GT — eyeball each: is the assigned Product/Family right for the desc?) ===")
    for k, row in enumerate(res, 1):
        desc = str(row[di])[:88] if di is not None else ""
        hs = row[hi] if hi is not None else ""
        dims = {d: (row[col[d]] if d in col else "") for d in DIMS}
        print(f"\n{k:3d}. HS={hs} | {desc}")
        print(f"     seg={dims['Segment']} / {dims['Sub-segment']} | "
              f"prod={dims['Product_V0']!r} | fam={dims['Family']!r} | "
              f"mfr={dims['Manufacturer']!r} | tier={dims['Match_Tier']}")


def main():
    market = sys.argv[1] if len(sys.argv) > 1 else "vn"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    if market.lower() in ("vn", "vietnam"):
        check_vn(n)
    else:
        check_market(_market_xlsx(market), n)


if __name__ == "__main__":
    main()
