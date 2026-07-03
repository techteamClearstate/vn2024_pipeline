"""
Recall-ceiling diagnostic for the >90% push.

Learns simple priors on the TRAIN split and measures, on the held-out TEST split,
how much PRODUCT recall each candidate source could add on top of the current
pipeline — i.e. the achievable ceiling before we build/rerank anything.

Priors evaluated (all learned on train GT only):
  * HS8            → dominant GT OU_Device (share, support)
  * HS4            → dominant GT OU_Device
  * (HS8, Maker)   → dominant GT OU_Device      (maker = pipeline canonical)
Then: of TEST rows the pipeline currently gets product-WRONG or misses, what
fraction would each prior label correctly (prefix-token overlap with GT device)?
"""
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import settings as cfg
from tools.eval_benchmark import load, nd, tok_overlap, test_jk


def dominant(series):
    c = Counter(x for x in series if pd.notna(x) and str(x).strip())
    if not c:
        return None, 0, 0
    (val, n), total = c.most_common(1)[0], sum(c.values())
    return val, n / total, total


def main():
    gt, mp = load()
    gt1 = gt.dropna(subset=["jk"]).drop_duplicates("jk", keep="first").set_index("jk")
    tj = test_jk() or set()

    # attach GT + pipeline fields per pipeline row, split by held-out key
    m = mp.copy()
    for col, src in [("gtDev", "OU_Device"), ("gtHS", "HS_Code")]:
        m[col] = m["jk"].map(gt1[src]) if src in gt1 else None
    m["gtDev"] = m["jk"].map(gt1["OU_Device"])
    j = m[m["gtDev"].notna()].copy()
    j["hs8"] = pd.to_numeric(j["HS_Code"], errors="coerce").astype("Int64").astype(str)
    j["hs4"] = j["HS_Code"].astype(str).str[:4]
    j["mk"] = j["Manufacturer"].fillna("").map(nd)
    j["ok"] = (j["Match_Status"] == "Matched") & [
        tok_overlap(p, d) for p, d in zip(j["Product_V0"].fillna(""), j["gtDev"])]
    j["is_test"] = j["jk"].isin(tj)

    tr, te = j[~j["is_test"]], j[j["is_test"]]
    print(f"TRAIN {len(tr):,}  TEST {len(te):,}")
    print(f"TEST currently product-correct: {te['ok'].mean():.1%}  "
          f"(need >90%)\n")

    # learn priors on TRAIN
    def learn(keycol):
        pri = {}
        for k, g in tr.groupby(keycol):
            val, share, n = dominant(g["gtDev"])
            if val:
                pri[k] = (val, share, n)
        return pri

    hs8_pri = learn("hs8")
    hs4_pri = learn("hs4")
    mk_pri = {}
    for (h, mk), g in tr.groupby(["hs8", "mk"]):
        val, share, n = dominant(g["gtDev"])
        if val:
            mk_pri[(h, mk)] = (val, share, n)

    # measure recovery on TEST rows the pipeline currently gets wrong/misses
    miss = te[~te["ok"]]
    print(f"TEST rows currently WRONG/missed: {len(miss):,}\n")
    for name, pri, keyfn in [
        ("HS8 prior", hs8_pri, lambda r: r["hs8"]),
        ("HS4 prior", hs4_pri, lambda r: r["hs4"]),
        ("HS8+Maker prior", mk_pri, lambda r: (r["hs8"], r["mk"])),
    ]:
        for thr in (0.5, 0.7, 0.9):
            rec = fire = 0
            for _, r in miss.iterrows():
                hit = pri.get(keyfn(r))
                if hit and hit[1] >= thr:
                    fire += 1
                    if tok_overlap(hit[0], r["gtDev"]):
                        rec += 1
            prec = rec / fire if fire else 0
            add = rec / len(te) if len(te) else 0
            print(f"  {name:16s} share>={thr:.1f}: fires {fire:5d}  "
                  f"correct {rec:5d}  (prec {prec:5.1%})  +{add:5.1%} recall")
        print()


if __name__ == "__main__":
    main()
