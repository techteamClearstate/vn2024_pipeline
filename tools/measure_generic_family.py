"""
READ-ONLY diagnostic: for each Tier-1 family KEYWORD, measure its held-out
precision against the VN ground truth, and its VN-wide $ / row blast radius.

Purpose: identify generic-English-word family keywords (export/engine/lens/...)
that are real reference brand strings but collide with common description words
and produce Tier-1 false positives in GT-less markets (PK/India). We can only
prove wrong-vs-right on VN (the only market with GT), so rank candidates by:
  * GT precision (correct / GT-joined rows that fired the keyword)
  * VN rows and $ that fired the keyword (blast radius if blacklisted)

Nothing is written. Output is a ranked table + a shortlist verdict per keyword.
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import settings as cfg
from tools.eval_benchmark import load, nd, tok_overlap

# Candidate generic-word keywords flagged during PK/India spot checks.
CANDIDATES = {
    "export", "engine", "cobalt", "lens", "barb", "combo", "cleaner",
    "modular", "seal", "liquid", "silk", "helix", "helical", "xpress",
}


def prod_correct(fam, gtFam, prod, gtDev):
    fk, gk = nd(fam), nd(gtFam)
    if fk and gk and (fk in gk or gk in fk):
        return True
    return tok_overlap(prod, gtDev)


def main():
    gt, mp = load()
    kw = json.load(open(cfg.MATCHED_KW_JSON))
    assert len(kw) == len(mp), f"kw {len(kw)} != mp {len(mp)}"
    mp = mp.reset_index(drop=True)
    mp["kw"] = pd.Series(kw)
    mp["kwn"] = mp["kw"].fillna("").map(nd)

    gt1 = gt.dropna(subset=["jk"]).drop_duplicates("jk", keep="first").set_index("jk")
    mp["gtDev"] = mp["jk"].map(gt1["OU_Device"])
    mp["gtFam"] = mp["jk"].map(gt1["Family Name"])
    mp["v"] = pd.to_numeric(mp["Total_Value_USD"], errors="coerce").fillna(0)

    t1 = mp[mp["Match_Tier"].fillna("") == "family"].copy()
    joined = t1[t1["gtDev"].notna() | t1["gtFam"].notna()].copy()
    joined["ok"] = [prod_correct(f, gf, p, gd) for f, gf, p, gd in
                    zip(joined["Family"], joined["gtFam"],
                        joined["Product_V0"], joined["gtDev"])]

    rows = []
    for k in sorted(CANDIDATES):
        vn = t1[t1["kwn"] == k]
        gj = joined[joined["kwn"] == k]
        n_vn, val = len(vn), vn["v"].sum()
        n_gt = len(gj)
        n_ok = int(gj["ok"].sum())
        prec = (n_ok / n_gt) if n_gt else float("nan")
        fams = ", ".join(sorted(vn["Family"].dropna().unique())[:2])
        rows.append((k, n_vn, val, n_gt, n_ok, prec, fams))

    df = pd.DataFrame(rows, columns=[
        "keyword", "vn_rows", "vn_value", "gt_rows", "gt_ok", "gt_prec", "family"])
    df = df.sort_values(["gt_prec", "vn_value"], ascending=[True, False])
    pd.set_option("display.width", 200)
    pd.set_option("display.max_colwidth", 40)
    print("=== Candidate generic-word family keywords (Tier-1) — VN GT ===\n")
    show = df.copy()
    show["vn_value"] = show["vn_value"].map(lambda x: f"${x/1e6:.2f}M")
    show["gt_prec"] = show["gt_prec"].map(
        lambda x: "n/a" if pd.isna(x) else f"{x:.0%}")
    print(show.to_string(index=False))

    print("\n=== Verdict (VERIFIABLE = has GT rows; UNVERIFIABLE = no GT rows) ===")
    for _, r in df.iterrows():
        if r["gt_rows"] == 0:
            v = "UNVERIFIABLE (no VN GT rows fired this kw)"
        elif r["gt_prec"] < 0.5:
            v = f"BLACKLIST — GT precision {r['gt_prec']:.0%} ({r['gt_ok']}/{r['gt_rows']})"
        elif r["gt_prec"] < 0.8:
            v = f"REVIEW — GT precision {r['gt_prec']:.0%} ({r['gt_ok']}/{r['gt_rows']})"
        else:
            v = f"KEEP — GT precision {r['gt_prec']:.0%} ({r['gt_ok']}/{r['gt_rows']})"
        print(f"  {r['keyword']:10s} {v}")

    # For UNVERIFIABLE ones, show the mapped Family + a couple descriptions so a
    # human can eyeball whether the keyword is a generic word or a real brand.
    print("\n=== UNVERIFIABLE keywords — sample VN descriptions (human eyeball) ===")
    desc_col = cfg.VN_DESCRIPTION_COL
    for _, r in df[df["gt_rows"] == 0].iterrows():
        k = r["keyword"]
        sub = t1[t1["kwn"] == k]
        if not len(sub):
            continue
        print(f"\n  [{k}]  vn_rows={r['vn_rows']}  ${r['vn_value']/1e6:.2f}M  "
              f"family={sub['Family'].iloc[0]!r}  product={sub['Product_V0'].iloc[0]!r}")
        for d in sub[desc_col].dropna().head(3):
            print(f"      - {str(d)[:110]}")


if __name__ == "__main__":
    main()
