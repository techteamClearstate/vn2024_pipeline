"""
Step 3b — HS8×Manufacturer product prior (recall re-rank)
========================================================
A candidate-generation + re-ranking pass that recovers a PRODUCT for rows the
lexical family/category passes left product-less (Tier-3 manufacturer-only or
unmatched). Within a narrow HS8 tariff line a known manufacturer sells a
predictable device, so we learn (hs8, maker)→dominant OU_Device (and an hs8-only
fallback for maker-less rows) from the human-labeled GT and apply it under a
purity gate. It NEVER overrides a family/category hit — family (T1) and category
(T2) always win the re-rank; the prior only fills the gap below them.

Learned on the TRAIN split for honest held-out measurement; `--full` learns from
all labels for production.
"""
import math
import pickle
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import settings as cfg
from src.step1_extract import norm_party

# Generic customs-boilerplate words that carry no device signal — excluded so the
# (hs8, token) prior keys on discriminative anatomy/type words only.
_TOKEN_STOP = set(
    "the a an of for and with in to over new long term body days implant implanted "
    "device used product code hsx model type left right material diameter length size "
    "made manufactured manufacturer inc ltd co corp company two one set kit system "
    "part number ref lot sterile single use disposable "
    # customs-boilerplate filler — pure invoice/packaging words, never a device signal
    "per pcs qty invoice assorted approx item items piece pieces packing packed "
    "carton box quantity total value goods brand "
    # dimension / spec abbreviations — feature words, not device words (they rode a VN
    # data correlation: 'dia' co-occurs with trauma-screw diameter specs, then mislabels
    # 'IV FLOW REGULATOR (DIA-FLOW)' as Trauma_Plating)
    "dia od id mrp rs mm cm fixed multi self surface".split()
)


def _norm(s) -> str:
    return norm_party(s)


def _hs8(series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").astype("Int64").astype(str)


def _hs6_of(h8: str) -> str:
    """First 6 digits of an HS8 string — the internationally harmonized prefix that
    transfers across markets. '<NA>' / short codes pass through unchanged."""
    return h8[:6] if h8 and h8[0].isdigit() else h8


def _tokens(desc_key: str) -> set:
    """Discriminative alpha tokens from a normalized description key."""
    mn = cfg.HS_TOKEN_MIN_LEN
    return {t for t in re.findall(r"[a-z]+", str(desc_key).lower())
            if len(t) >= mn and t not in _TOKEN_STOP}


def _sing(t: str) -> str:
    """Crude singular: drop a trailing 's' from tokens longer than 3 chars so
    'balloons'→'balloon', 'sheaths'→'sheath', while keeping short words ('gas',
    'hip') intact. Used to align description tokens with the singular cue set."""
    return t[:-1] if len(t) > 3 and t.endswith("s") else t


def _cue_tokens(s) -> set:
    """Singular-normalized alpha tokens (>=3 chars) of a string — the shared
    tokenization for the consistency reranker's cue / head-noun matching, used
    identically at learn time (build_consistency) and apply time (step2)."""
    return {_sing(t) for t in re.findall(r"[a-z]{3,}", str(s).lower())}


def _device_vocab() -> set:
    """Tokens that name a DEVICE, ANATOMY or CLINICAL AREA — built from the curated
    reference (Product / Segment / Sub-segment labels) plus the GT device labels.
    Used ONLY to gate cross-market (hs6) transfer: within one market a brand- or
    company-name token can purely predict a product, but cross-market it is noise
    (a foreign shipper's name collides), so transferable rules must key on a real
    device word (balloon / catheter / mesh / spinal …), never a maker/filler token."""
    vocab: set = set()
    try:
        with open(cfg.V0_LOOKUP_PKL, "rb") as fh:
            lookup = pickle.load(fh)
        for rec in lookup.values():
            for field in ("Product", "Segment", "Sub-segment"):
                vocab |= _tokens(rec.get(field, ""))
    except Exception:
        pass
    return vocab


def build_consistency() -> dict:
    """Learn the head/anatomy-cue → Segment SHARE map used by the Tier-1 consistency
    reranker (see cfg.CONSISTENCY_*) from the REFERENCE TAXONOMY itself: for each
    curated cue token, the distribution of reference Segments over the distinct
    reference Products (and Sub-segments) whose label contains that cue. Learning
    from the reference — not the GT — is deliberate: the family hit's Segment (which
    the reranker tests) comes from this same reference vocabulary, so the two are
    directly comparable (the GT's OU vocabulary differs, e.g. 'SI' vs 'Surgical
    Innovations (SI)', and would make every Segment spuriously 'alien').

    A cue's map answers "which Segments does a device called <cue> belong to?". The
    reranker releases a family hit only when its Product Segment is ALIEN to a cue
    present in the description (share < ALIEN_MAX) and no present cue SUPPORTS it
    (>= SEG_FLOOR) — so 'balloon' on a spinal-fixation brand (no reference balloon
    is spinal) is released, while a legitimate minority device is kept. The map is
    market-agnostic (pure taxonomy) and persisted so GT-less markets reuse it."""
    cues = {_sing(c) for c in getattr(cfg, "CONSISTENCY_CUES", set())}
    if not cues:
        return {}
    with open(cfg.V0_LOOKUP_PKL, "rb") as fh:
        lookup = pickle.load(fh)
    # distinct (Product|Sub-segment label, Segment) pairs → one vote each, so the
    # map reflects the taxonomy rather than per-brand keyword popularity.
    seen, seg_counts = set(), {c: Counter() for c in cues}
    for rec in lookup.values():
        seg = str(rec.get("Segment", "")).strip()
        if not seg:
            continue
        for field in ("Product", "Sub-segment"):
            label = str(rec.get(field, "")).strip()
            if not label or (label, seg) in seen:
                continue
            seen.add((label, seg))
            for c in cues & _cue_tokens(label):
                seg_counts[c][seg] += 1

    eps = cfg.CONSISTENCY_STORE_EPS
    head_seg = {}
    for c, cnt in seg_counts.items():
        total = sum(cnt.values())
        if total < cfg.CONSISTENCY_MIN_PRODUCTS:
            continue
        head_seg[c] = {s: n / total for s, n in cnt.items() if n / total >= eps}

    with open(cfg.CONSISTENCY_PKL, "wb") as fh:
        pickle.dump(head_seg, fh)
    print(f"  [consistency] learned Segment-share map for {len(head_seg)}/{len(cues)} "
          f"cues from reference taxonomy (>= {cfg.CONSISTENCY_MIN_PRODUCTS} products each)")
    return head_seg


def _dominant(vals):
    c = Counter(v for v in vals if pd.notna(v) and str(v).strip())
    if not c:
        return None
    (val, n), total = c.most_common(1)[0], sum(c.values())
    return val, n, total


def _blank(s) -> bool:
    return str(s).strip().lower() in ("", "unspecified", "nan")


# ── Family (brand/model) classifier ───────────────────────────────────────────
# Family = the brand/model. Where the lexical Tier-1 pass leaves it blank we predict
# the brand with a per-HS8 nearest-family TF-IDF classifier: unigrams + word bigrams
# + model-code tokens (mixed alnum / long numeric), the codes and bigrams up-weighted
# because they identify a specific product line far more sharply than a stray word.
def _fam_feats(desc_key: str) -> list:
    s = str(desc_key).lower()
    words = [w for w in re.findall(r"[a-z]{3,}", s) if w not in _TOKEN_STOP]
    out = list(words)
    for i in range(len(words) - 1):
        out.append(words[i] + "_" + words[i + 1])              # bigram
    for t in re.findall(r"[a-z0-9]{3,}", s):
        if any(c.isalpha() for c in t) and any(c.isdigit() for c in t):
            out.append("C_" + t)                               # mixed-alnum code
    for t in re.findall(r"\d{5,}", s):
        out.append("C_" + t)                                   # long numeric code
    return out


def _build_family_model(jf: pd.DataFrame) -> dict:
    """Per-HS8 inverted index of family→feature counts for fast scoring at apply
    time. Skips HS8s with too few labeled rows to model reliably."""
    tmp = {}
    for desc_key, h, fn in zip(jf["desc_key"], jf["hs8"], jf["gtFam"]):
        d = tmp.setdefault(h, {"fams": defaultdict(Counter), "famn": Counter()})
        d["famn"][fn] += 1
        cnt = d["fams"][fn]
        for t in _fam_feats(desc_key):
            cnt[t] += 1
    model = {}
    for h, d in tmp.items():
        if sum(d["famn"].values()) < cfg.FAMILY_PRIOR_MIN_HS_ROWS:
            continue
        post, df = defaultdict(list), Counter()
        for fn, cnt in d["fams"].items():
            for t, c in cnt.items():
                post[t].append((fn, c))
                df[t] += 1
        model[h] = {"post": dict(post), "df": dict(df),
                    "famn": dict(d["famn"]), "nf": len(d["fams"])}
    return model


def _score_family(model: dict, feats):
    """Highest-scoring family for a row's features, or the HS8's dominant family if
    no feature fires (recall-first — always returns a candidate when the HS8 is
    modeled). Score = Σ w·log(1+count)·idf, codes×4 / bigrams×2 / words×1."""
    post, df, famn, nf = model["post"], model["df"], model["famn"], model["nf"]
    scores = defaultdict(float)
    for t in feats:
        pl = post.get(t)
        if not pl:
            continue
        w = 4.0 if t.startswith("C_") else (2.0 if "_" in t else 1.0)
        idf = math.log((nf + 1) / (df[t] + 1)) + 0.1
        wt = w * idf
        for fn, c in pl:
            scores[fn] += wt * math.log(1 + c)
    if not scores:
        return max(famn, key=famn.get) if famn else None
    for fn in scores:
        scores[fn] += 0.01 * math.log(1 + famn.get(fn, 0))     # dominance tiebreak
    return max(scores, key=scores.get)


def build_prior(full: bool = False) -> dict:
    """Learn the priors from the current mapped output joined to the GT labels.

    Keyed by the PIPELINE's own Manufacturer (canonical) so the key exists at
    apply time. Restricts to the TRAIN split unless `full`.
    """
    gt = pd.read_csv(cfg.INTERMEDIATE / "benchmark_gt_2024.csv", dtype=str)
    gt["value"] = pd.to_numeric(gt["value"], errors="coerce").astype("Int64")
    gt["hs_code"] = pd.to_numeric(gt["hs_code"], errors="coerce").astype("Int64")
    gt["jk"] = (gt["desc_key"] + "|" + gt["hs_code"].astype(str)
                + "|" + gt["value"].astype(str))
    gt1 = gt.dropna(subset=["jk"]).drop_duplicates("jk", keep="first").set_index("jk")

    mp = pd.read_csv(cfg.MAPPED_CSV, dtype=str)
    mp["desc_key"] = mp["Detailed_Product"].map(
        lambda s: __import__("re").sub(r"\s+", " ",
            __import__("re").sub(r"[^a-z0-9]+", " ", str(s).lower())).strip())
    mp["value"] = pd.to_numeric(mp["Total_Value_USD"], errors="coerce").round(0).astype("Int64")
    mp["hs_code"] = pd.to_numeric(mp["HS_Code"], errors="coerce").astype("Int64")
    mp["jk"] = mp["desc_key"] + "|" + mp["hs_code"].astype(str) + "|" + mp["value"].astype(str)
    mp["gtDev"] = mp["jk"].map(gt1["OU_Device"])
    mp["gtOU"] = mp["jk"].map(gt1["OU"])
    mp["gtMfr"] = mp["jk"].map(gt1["Manufacturer Name"])
    mp["gtFam"] = mp["jk"].map(gt1["Family Name"])

    tj = set()
    if not full and cfg.BENCHMARK_TEST_JK.exists():
        tj = set(pd.read_csv(cfg.BENCHMARK_TEST_JK, dtype=str)["jk"])

    # Market-agnostic head/anatomy-cue → Segment consistency map (reference-taxonomy
    # based) for the Tier-1 reranker; persisted here for GT-less-market reuse.
    if getattr(cfg, "USE_CONSISTENCY_RERANK", False):
        build_consistency()

    def _train(col: str) -> pd.DataFrame:
        f = mp[mp[col].notna()].copy()
        if tj:
            f = f[~f["jk"].isin(tj)]
        f["hs8"] = _hs8(f["HS_Code"])
        return f

    j = _train("gtDev")
    j["mk"] = j["Manufacturer"].fillna("").map(_norm)

    seg_of = {}                                   # device → dominant OU (segment)
    for dev, g in j.groupby("gtDev"):
        d = _dominant(g["gtOU"])
        seg_of[dev] = d[0] if d else ""

    hs_maker = {}
    for (h, mk), g in j.groupby(["hs8", "mk"]):
        if not mk:
            continue
        d = _dominant(g["gtDev"])
        if not d:
            continue
        dev, n, total = d
        if n >= cfg.HS_MAKER_MIN_N and n / total >= cfg.HS_MAKER_MIN_SHARE:
            hs_maker[(h, mk)] = {"Product": str(dev), "Segment": seg_of.get(dev, ""),
                                 "share": n / total, "n": n}

    hs_only = {}
    for h, g in j.groupby("hs8"):
        d = _dominant(g["gtDev"])
        if not d:
            continue
        dev, n, total = d
        if n >= cfg.HS_ONLY_MIN_N and n / total >= cfg.HS_ONLY_MIN_SHARE:
            hs_only[h] = {"Product": str(dev), "Segment": seg_of.get(dev, ""),
                          "share": n / total, "n": n}

    # Token-conditioned prior: (hs8, description-token) → dominant OU_Device. The
    # discriminative word in the text (spinal / brace / gamma …) resolves the
    # maker-level ambiguity, so this ranks ABOVE hs_maker/hs_only at apply time.
    tok_counts = defaultdict(Counter)
    for desc_key, h, dev in zip(j["desc_key"], j["hs8"], j["gtDev"]):
        for t in _tokens(desc_key):
            tok_counts[(h, t)][dev] += 1
    hs_token = {}
    for (h, t), c in tok_counts.items():
        (dev, n), total = c.most_common(1)[0], sum(c.values())
        if n >= cfg.HS_TOKEN_MIN_N and n / total >= cfg.HS_TOKEN_MIN_SHARE:
            hs_token[(h, t)] = {"Product": str(dev), "Segment": seg_of.get(dev, ""),
                                "share": n / total, "n": n}

    # (hs6, token) → device: coarser, harmonized-prefix key that TRANSFERS to GT-less
    # markets (PK/India share HS6 with VN even when the national HS8 tail differs).
    # GATE: the token must be a real DEVICE word — a company/brand/filler token can be
    # pure within VN but collides with a foreign shipper's name cross-market (measured:
    # 'prime'/'landanger'/'license' mislabelled PK exam-lights as PTCA Balloon).
    dvocab = _device_vocab()
    for dev in seg_of:
        dvocab |= _tokens(dev)
    # GLOBAL specificity: across ALL VN GT, does this device token map to ONE device?
    # Only globally-specific tokens are safe to transfer (multi-referent device words
    # like "tube"/"valve"/"pressure" are locally pure in VN but collide abroad).
    glob = defaultdict(Counter)
    for desc_key, dev in zip(j["desc_key"], j["gtDev"]):
        for t in _tokens(desc_key) & dvocab:
            glob[t][dev] += 1
    tok_ok = set()
    for t, c in glob.items():
        (dev, n), total = c.most_common(1)[0], sum(c.values())
        if n >= cfg.HS6_TOKEN_GLOBAL_N and n / total >= cfg.HS6_TOKEN_GLOBAL_SHARE:
            tok_ok.add(t)
    tok6 = defaultdict(Counter)
    for desc_key, h, dev in zip(j["desc_key"], j["hs8"], j["gtDev"]):
        h6 = _hs6_of(h)
        for t in _tokens(desc_key) & tok_ok:
            tok6[(h6, t)][dev] += 1
    hs6_token = {}
    for (h6, t), c in tok6.items():
        (dev, n), total = c.most_common(1)[0], sum(c.values())
        if n < cfg.HS6_TOKEN_MIN_N or n / total < cfg.HS6_TOKEN_MIN_SHARE:
            continue
        # CONTAINMENT gate: the token must literally appear in the device it predicts
        # (balloon→…Balloon, cannula→Cannula_Venous). A token that predicts a device
        # whose NAME it is absent from ("pressure"→PTCA Balloon) rode a VN-only data
        # correlation that breaks abroad (fires on BP monitors) — reject it.
        if t not in _tokens(dev):
            continue
        hs6_token[(h6, t)] = {"Product": str(dev), "Segment": seg_of.get(dev, ""),
                              "share": n / total, "n": n}
    # Tokens that survived every gate — the proven cross-market device words. Restrict
    # the maker transfer to these too (a maker keyed on a leaky token is just as unsafe).
    safe_tok = {t for (_h6, t) in hs6_token}

    # (hs8, token) → dominant GT Manufacturer. Fills makers the lexical alias
    # derivation (party + description) missed. Recall-first purity gate.
    jm = _train("gtMfr")
    tok_mfr = defaultdict(Counter)
    for desc_key, h, mfr in zip(jm["desc_key"], jm["hs8"], jm["gtMfr"]):
        for t in _tokens(desc_key):
            tok_mfr[(h, t)][mfr] += 1
    hs_token_mfr = {}
    for (h, t), c in tok_mfr.items():
        (mfr, n), total = c.most_common(1)[0], sum(c.values())
        if n >= cfg.HS_TOKEN_MFR_MIN_N and n / total >= cfg.HS_TOKEN_MFR_MIN_SHARE:
            hs_token_mfr[(h, t)] = {"Manufacturer": str(mfr), "share": n / total, "n": n}

    # (hs6, token) → maker: harmonized-prefix fallback for cross-market transfer.
    # Same device-word gate — a maker keyed on a company/filler token is noise abroad.
    tok6_mfr = defaultdict(Counter)
    for desc_key, h, mfr in zip(jm["desc_key"], jm["hs8"], jm["gtMfr"]):
        h6 = _hs6_of(h)
        for t in _tokens(desc_key) & safe_tok:
            tok6_mfr[(h6, t)][mfr] += 1
    hs6_token_mfr = {}
    for (h6, t), c in tok6_mfr.items():
        (mfr, n), total = c.most_common(1)[0], sum(c.values())
        if n >= cfg.HS6_TOKEN_MFR_MIN_N and n / total >= cfg.HS6_TOKEN_MFR_MIN_SHARE:
            hs6_token_mfr[(h6, t)] = {"Manufacturer": str(mfr), "share": n / total, "n": n}

    # Per-HS8 nearest-family TF-IDF classifier (brand/model prediction).
    fam_model = _build_family_model(_train("gtFam"))

    # CORROBORATION VOCABULARY per predicted device: the discriminative description
    # tokens that genuinely co-occur (>= CORROB_MIN_N times) with the device in the GT,
    # singular-normalized, unioned with the device's own name tokens. At apply time an
    # hs_prior product fill is kept only if the row's description shares one of these —
    # so a device is never stamped on text that lexically supports nothing about it.
    # Learned from VN GT descriptions but the surviving tokens (screw/stent/balloon/
    # coil/catheter/mesh…) are language-agnostic, so it transfers to GT-less markets.
    dev_corrob = {}
    if getattr(cfg, "USE_HS_PRIOR_CORROB", False):
        gtok = defaultdict(Counter)          # token → device distribution (all GT rows)
        dev_tok = defaultdict(Counter)       # device → its own token counts
        for desc_key, dev in zip(j["desc_key"], j["gtDev"]):
            for t in _tokens(desc_key):
                st = _sing(t)
                gtok[st][dev] += 1
                dev_tok[dev][st] += 1
        # A token corroborates a device only if that device is the token's GLOBAL
        # MAJORITY referent — device words (screw→Trauma_Plating, coil→Embolization
        # Coils) qualify, customs boilerplate that co-occurs with every implant row
        # (artificial / parts / goods) does not, since it has no majority device.
        tok_dom = {}
        for t, c in gtok.items():
            (dev, n), tot = c.most_common(1)[0], sum(c.values())
            tok_dom[t] = (dev, n / tot)
        min_n, share = cfg.CORROB_MIN_N, cfg.CORROB_MIN_SHARE
        for dev in set(seg_of) | set(dev_tok):
            kws = {t for t, c in dev_tok.get(dev, {}).items()
                   if c >= min_n and tok_dom.get(t, ("", 0.0))[0] == dev
                   and tok_dom[t][1] >= share}
            dev_corrob[dev] = kws | _cue_tokens(dev)

    prior = {"hs_maker": hs_maker, "hs_only": hs_only, "hs_token": hs_token,
             "hs_token_mfr": hs_token_mfr, "fam_model": fam_model,
             "hs6_token": hs6_token, "hs6_token_mfr": hs6_token_mfr,
             "dev_corrob": dev_corrob}

    # GT-less market (nothing joined): the working prior would be empty and no-op.
    # Fall back to the persisted cross-market transfer prior (VN-learned) so PK/India
    # still recover product/maker via the harmonized (hs6, token) rules.
    if len(j) == 0 and getattr(cfg, "USE_HS6_TRANSFER", False) \
            and cfg.TRANSFER_PRIOR_PKL.exists():
        with open(cfg.TRANSFER_PRIOR_PKL, "rb") as fh:
            prior = pickle.load(fh)
        # Mark as a cross-market apply. The coarse hs8-only / (hs8,maker) fills are a
        # per-country HS→device mapping that does NOT transfer (a tariff line's product
        # mix differs by market: VN's 90213100 is dominated by trauma plating, so it
        # stamps Trauma_Plating onto PK's hip cups / knee joints / screwdrivers under
        # the same code). Only a discriminative DESCRIPTION token transfers, so apply
        # restricts to the token-conditioned paths (hs8_token collision + hs6_token).
        prior["cross_market"] = True
        with open(cfg.HS_PRODUCT_PRIOR_PKL, "wb") as fh:
            pickle.dump(prior, fh)
        print(f"  [hs_prior] GT-less market → loaded cross-market transfer prior "
              f"({len(prior.get('hs6_token', {})):,} (hs6,token) product + "
              f"{len(prior.get('hs6_token_mfr', {})):,} (hs6,token) maker rules)")
        return prior

    with open(cfg.HS_PRODUCT_PRIOR_PKL, "wb") as fh:
        pickle.dump(prior, fh)
    # Persist the country-agnostic copy from any real-GT build (train or full) so a
    # later GT-less market can reuse it. Full builds are the production reference.
    if getattr(cfg, "USE_HS6_TRANSFER", False) and len(j) > 0:
        with open(cfg.TRANSFER_PRIOR_PKL, "wb") as fh:
            pickle.dump(prior, fh)
    mode = "FULL" if full else "TRAIN"
    print(f"  [hs_prior] learned [{mode}] {len(hs_maker):,} (hs8,maker) + "
          f"{len(hs_only):,} hs8-only + {len(hs_token):,} (hs8,token) + "
          f"{len(hs6_token):,} (hs6,token) product priors, "
          f"{len(hs_token_mfr):,} (hs8,token) + {len(hs6_token_mfr):,} (hs6,token) maker "
          f"priors, {len(fam_model):,} HS8 family models")
    return prior


def apply_prior() -> int:
    """Re-rank pass: fill Product/Segment on product-less rows from the prior.
    Rewrites MAPPED_CSV in place. Returns the number of rows enriched."""
    if not getattr(cfg, "USE_HS_PRIOR", False) or not cfg.HS_PRODUCT_PRIOR_PKL.exists():
        return 0
    with open(cfg.HS_PRODUCT_PRIOR_PKL, "rb") as fh:
        prior = pickle.load(fh)
    hs_maker, hs_only = prior["hs_maker"], prior["hs_only"]
    hs_token = prior.get("hs_token", {})
    hs_token_mfr = prior.get("hs_token_mfr", {})
    fam_model = prior.get("fam_model", {})
    hs6_token = prior.get("hs6_token", {}) if getattr(cfg, "USE_HS6_TRANSFER", False) else {}
    hs6_token_mfr = prior.get("hs6_token_mfr", {}) if getattr(cfg, "USE_HS6_TRANSFER", False) else {}
    dev_corrob = prior.get("dev_corrob", {}) if getattr(cfg, "USE_HS_PRIOR_CORROB", False) else {}
    cross_market = bool(prior.get("cross_market"))

    mp = pd.read_csv(cfg.MAPPED_CSV, dtype=str)
    hs8 = _hs8(mp["HS_Code"])
    mk = mp["Manufacturer"].fillna("").map(_norm)
    tier = mp[cfg.TIER_COL].fillna("")
    prod = mp["Product_V0"].fillna("")
    dk = mp["Detailed_Product"].map(
        lambda s: re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(s).lower())).strip())
    # Re-rank scope = everything the audited lexical tiers left alone. We NEVER touch
    # family/category rows, so the dashboard $ bounds and the curated tiers are intact.
    scope = ~tier.isin(["family", "category"])
    empty = prod.str.strip() == ""

    def _best_token(i):
        """Highest-purity (hs8, token) candidate for row i; if the national HS8 key
        never fires (e.g. a foreign market's HS8 tail), fall back to the harmonized
        (hs6, token) transfer rule."""
        toks = _tokens(dk[i])
        best = None
        for t in toks:
            rec = hs_token.get((hs8[i], t))
            if rec and (best is None or rec["share"] > best["share"]):
                best = rec
        if best is not None:
            return best
        h6 = _hs6_of(hs8[i])
        for t in toks:
            rec = hs6_token.get((h6, t))
            if rec and (best is None or rec["share"] > best["share"]):
                best = rec
        return best

    def _corroborated(i, product) -> bool:
        """The row's description must share a discriminative token with the predicted
        device's learned vocabulary — else the fill is a pure HS-code guess with no
        lexical support (dental→Forceps, ultrasound→PTCA Balloon) and is rejected."""
        if not dev_corrob:
            return True
        cset = dev_corrob.get(product) or _cue_tokens(product)
        return bool({_sing(t) for t in _tokens(dk[i])} & cset)

    n_tok = n_coarse = n_reject = 0
    dental_cues = getattr(cfg, "DENTAL_NEGATIVE_CUES", ())
    for i in mp.index[scope]:
        # iter-11: never HS-prior-fill a dental (out-of-scope) row.
        if any(c in dk[i] for c in dental_cues):
            continue
        # 1) token prior takes priority — it CORRECTS a coarse fill (e.g. a spinal
        #    screw the (hs8,maker) prior mislabeled Trauma_Plating) and fills gaps.
        rec = _best_token(i)
        via_tok = rec is not None
        if not rec and empty[i] and not cross_market:
            # 2) fall back to the coarse (hs8,maker)/hs8-only fill for product-less rows.
            #    Skipped cross-market: the coarse HS→device map is market-specific and
            #    mislabels a foreign market's differently-mixed tariff line.
            rec = hs_maker.get((hs8[i], mk[i])) or hs_only.get(hs8[i])
        if not rec:
            continue
        # ARTHROPLASTY VETO: a joint-replacement component (femoral/humeral head,
        # acetabular cup/shell, tibial insert, glenoid) must never be labelled a
        # fracture-fixation device just because a generic token (hole/shell/head)
        # fired the plating/screw/nail prior on a shared ortho HS8.
        pl = rec["Product"].lower()
        if any(f in pl for f in getattr(cfg, "HS_PRIOR_FIXATION_PRODUCTS", ())) and \
           any(c in dk[i] for c in getattr(cfg, "ARTHROPLASTY_COMPONENT_CUES", ())):
            n_reject += 1
            continue
        # CORROBORATION GATE: keep the fill only when the description lexically supports
        # the predicted device (kills VN's dominant device stamped on unrelated rows).
        if not _corroborated(i, rec["Product"]):
            n_reject += 1
            continue
        if via_tok:
            n_tok += 1
        else:
            n_coarse += 1
        mp.at[i, "Product_V0"] = rec["Product"]
        if not str(mp.at[i, "Segment"]).strip():
            mp.at[i, "Segment"] = rec["Segment"]
        mp.at[i, "Match_Status"] = "Matched"
        mp.at[i, cfg.TIER_COL] = "hs_prior"
        mp.at[i, cfg.CONFIDENCE_COL] = "high" if rec["share"] >= 0.85 else "med"

    # ── Manufacturer re-rank: fill still-blank makers from (hs8, token) prior. ──
    n_mfr = 0
    if getattr(cfg, "USE_MFR_PRIOR", False) and (hs_token_mfr or hs6_token_mfr):
        need_mk = mp["Manufacturer"].map(_blank)
        for i in mp.index[need_mk]:
            if any(c in dk[i] for c in dental_cues):   # iter-11: skip dental
                continue
            toks = _tokens(dk[i])
            best = None
            for t in toks:
                rec = hs_token_mfr.get((hs8[i], t))
                if rec and (best is None or rec["share"] > best["share"]):
                    best = rec
            if best is None:                       # hs6 transfer fallback
                h6 = _hs6_of(hs8[i])
                for t in toks:
                    rec = hs6_token_mfr.get((h6, t))
                    if rec and (best is None or rec["share"] > best["share"]):
                        best = rec
            if best:
                mp.at[i, "Manufacturer"] = best["Manufacturer"]
                n_mfr += 1

    # ── Family re-rank: predict the brand where the lexical family is blank. ──
    # Skipped cross-market: the per-HS8 TF-IDF brand classifier is trained on VN model
    # codes, so on a foreign market it stamps a VN brand onto every product-less row by
    # HS8 collision (hip cups / knee joints → 'Trauma Plates And Screws'; monitors /
    # lamps / endotracheal tubes → 'Forceps'). Those rows keep the correct maker tag and
    # an honest blank Family instead of a fabricated brand.
    n_fam = 0
    if getattr(cfg, "USE_FAMILY_PRIOR", False) and fam_model and not cross_market:
        need_fam = (tier != "family") & mp["Family"].map(_blank)
        for i in mp.index[need_fam]:
            model = fam_model.get(hs8[i])
            if not model:
                continue
            fn = _score_family(model, _fam_feats(dk[i]))
            if fn:
                mp.at[i, "Family"] = fn
                n_fam += 1

    mp.to_csv(cfg.MAPPED_CSV, index=False)
    print(f"  [hs_prior] enriched {n_tok + n_coarse:,} product rows "
          f"({n_tok:,} via (hs8,token), {n_coarse:,} via (hs8,maker)/hs8-only); "
          f"corroboration gate rejected {n_reject:,} uncorroborated guesses; "
          f"{n_mfr:,} makers + {n_fam:,} families predicted")
    return n_tok + n_coarse


def run(full: bool = False) -> int:
    build_prior(full=full)
    return apply_prior()


if __name__ == "__main__":
    run(full="--full" in sys.argv)
