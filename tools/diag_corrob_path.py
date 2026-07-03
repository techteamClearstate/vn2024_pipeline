"""READ-ONLY: for probe descriptions, replicate step3b apply logic against the
loaded prior and print which PATH fired (hs8_token / hs6_token / coarse hs_only /
hs_maker) and which token corroborated. Nothing written."""
import pickle
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import settings as cfg
from src.step3b_hs_prior import _tokens, _hs6_of, _sing, _cue_tokens

with open(cfg.HS_PRODUCT_PRIOR_PKL, "rb") as fh:
    P = pickle.load(fh)
print("prior keys:", list(P.keys()), "| cross_market:", P.get("cross_market"))
hs_token = P.get("hs_token", {})
hs6_token = P.get("hs6_token", {})
hs_only = P.get("hs_only", {})
hs_maker = P.get("hs_maker", {})
dev_corrob = P.get("dev_corrob", {})

# (desc, hs8) probes pulled from the PK mapped errors
probes = [
    ("JMS BLOOD BAG SINGLE 500ML WITH BLOOD TRANSFUSION SET", "90189099"),
    ("DISPOSABLE ECG ELECTRODE 302E FOR CARDIOLOGY", "90189099"),
    ("PLASTIC CLIPS AS PER INVOICE", "90189099"),
    ("SURGICAL INSTRUMENTS FOR REPAIR QTY 1600 PCS", "90189099"),
    ("F/M ACET SHELL 52MMOD", "90213100"),
    ("LPS-FLEX AS PRV CD 3-4 14", "90213100"),
]

def best_token(toks, hs8):
    best = None
    for t in toks:
        rec = hs_token.get((hs8, t))
        if rec and (best is None or rec["share"] > best["share"]):
            best = (rec, t, "hs8_token")
    if best:
        return best
    h6 = _hs6_of(hs8)
    for t in toks:
        rec = hs6_token.get((h6, t))
        if rec and (best is None or rec["share"] > best["share"]):
            best = (rec, t, "hs6_token")
    return best

for desc, hs8 in probes:
    dk = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", desc.lower())).strip()
    toks = _tokens(dk)
    rec = best_token(toks, hs8)
    path = rec[2] if rec else None
    r = rec[0] if rec else None
    if not r:
        r = hs_maker.get((hs8, "")) or hs_only.get(hs8)
        path = "coarse_hs_only/maker" if r else None
    print(f"\n--- {desc[:50]}  (hs8={hs8})")
    if not r:
        print("   NO PRIOR FIRES")
        continue
    prod = r["Product"]
    cset = dev_corrob.get(prod) or _cue_tokens(prod)
    dtok = {_sing(t) for t in toks}
    corrob = dtok & cset
    print(f"   path={path}  -> {prod}  (share={r['share']:.2f})"
          + (f"  via='{rec[1]}'" if rec else ""))
    print(f"   corrob tokens = {sorted(corrob)}   (kept={bool(corrob)})")
