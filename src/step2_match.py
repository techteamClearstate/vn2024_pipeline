"""
Step 2 — Matching
=================
Scan every VN product description for known device model/family names using a
4-character prefix trie with word-boundary enforcement, gated by HS4 scope.

The trie gives O(1) prefix lookups; the full 520k-row dataset matches in ~8s,
roughly 350x faster than a single compiled-regex alternation.
"""
import json
import pickle
from collections import defaultdict

import pandas as pd

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import settings as cfg
from src.step1_extract import norm_phrase, norm_party


def _load_trie():
    with open(cfg.V0_LOOKUP_PKL, "rb") as fh:
        lookup = pickle.load(fh)
    with open(cfg.PREFIX_MAP_PKL, "rb") as fh:
        prefix_map = pickle.load(fh)
    return lookup, prefix_map


def _load_consistency() -> dict:
    """Load the VN-learned cue→plausible-Segment map for the Tier-1 consistency
    reranker, or {} when disabled / not yet built (a first-ever run has no map and
    simply skips the reranker; every later run reuses the persisted, market-
    agnostic file — including GT-less PK/India)."""
    if not getattr(cfg, "USE_CONSISTENCY_RERANK", False) \
            or not cfg.CONSISTENCY_PKL.exists():
        return {}
    with open(cfg.CONSISTENCY_PKL, "rb") as fh:
        return pickle.load(fh)


def make_matcher(prefix_map):
    """Return a find_match(text, hs4) closure bound to the given trie."""
    plen = cfg.PREFIX_LEN

    def find_match(text, hs4):
        # HS4 gate — when MATCH_ALL_HS4 the gate is open (widened scope) so
        # surgical brand/model names outside the surgical HS4 codes are still
        # recovered; each hit is later tagged Surgical vs Extended by HS4.
        if not _match_allowed(hs4):
            return None

        t = text.lower()
        # iter-11: dental is out-of-scope for the surgical OUs — suppress before
        # any family-trie hit (e.g. "Root" kw over "root canal" rows).
        if any(c in t for c in cfg.DENTAL_NEGATIVE_CUES):
            return None
        for i in range(len(t) - (plen - 1)):
            pfx = t[i:i + plen]
            if pfx in prefix_map:
                for kw in prefix_map[pfx]:
                    end = i + len(kw)
                    if t[i:end] == kw:
                        # word-boundary check on both sides
                        s_ok = (i == 0) or not t[i - 1].isalnum()
                        e_ok = (end >= len(t)) or not t[end].isalnum()
                        if s_ok and e_ok:
                            return kw
        return None

    return find_match


def _in_scope(hs4) -> bool:
    """True iff the row's HS4 is one of the core SURGICAL codes (scope label)."""
    try:
        return int(float(str(hs4))) in cfg.SURGICAL_HS4
    except (ValueError, TypeError):
        return False


def _match_allowed(hs4) -> bool:
    """Gate for whether a row may be matched at all: open to every row when
    cfg.MATCH_ALL_HS4 (widened scope), otherwise restricted to SURGICAL_HS4.
    cfg.SCOPE_EXCLUDE_HS4 chapters are blocked in either mode (non-device goods)."""
    excl = getattr(cfg, "SCOPE_EXCLUDE_HS4", set())
    if excl:
        try:
            if int(float(str(hs4))) in excl:
                return False
        except (ValueError, TypeError):
            pass
    return cfg.MATCH_ALL_HS4 or _in_scope(hs4)


def build_hs8_segment(hs8_series, matched_kw, lookup) -> dict:
    """Derive an HS8 → {segment, share} map empirically from this run's Tier-1
    family matches: for each HS8 code, the most-frequent resolved Segment and
    the fraction of that code's family matches it accounts for. Used (guarded by
    cfg.HS8_SEGMENT_MIN_SHARE) to assign a Segment to bare-head category hits."""
    counts = defaultdict(lambda: defaultdict(int))
    for hs8, kw in zip(hs8_series, matched_kw):
        if not kw:
            continue
        seg = lookup.get(kw, {}).get("Segment", "")
        if seg:
            counts[str(hs8)][seg] += 1

    hs8_seg = {}
    for hs8, segs in counts.items():
        total = sum(segs.values())
        seg, n = max(segs.items(), key=lambda kv: kv[1])
        hs8_seg[hs8] = {"segment": seg, "share": n / total}

    with open(cfg.HS8_SEGMENT_PKL, "wb") as fh:
        pickle.dump(hs8_seg, fh)
    return hs8_seg


def make_category_matcher(lex, hs8_seg):
    """Return find_category(text, hs4, hs8) → record|None for the Tier-2 pass.

    Order of precedence (most specific first):
      1. longest lexicon phrase contained in the normalized description
         (confidence high/med, carries Segment/Sub-segment/Product);
      2. a bare category head with no qualifier → "<Head> (unspecified)",
         Segment from the HS8 map only when its dominant share is strong enough
         (else blank), confidence low.
    """
    phrases = sorted(lex, key=len, reverse=True)   # longest-first = most specific
    heads = cfg.CATEGORY_HEADS
    min_share = cfg.HS8_SEGMENT_MIN_SHARE
    neg_cues = cfg.CATEGORY_NEGATIVE_CUES

    def find_category(text, hs4, hs8):
        if not _match_allowed(hs4):
            return None
        low = text.lower()
        # Precision guard: accessory/tool/part cues mean this is not the device
        # itself (stent cutter, valve cap, inflation pump…) — never a category.
        if any(cue in low for cue in neg_cues):
            return None
        # iter-11: dental is out-of-scope for the surgical OUs.
        if any(cue in low for cue in cfg.DENTAL_NEGATIVE_CUES):
            return None
        padded = " " + norm_phrase(text) + " "

        for p in phrases:
            if " " + p + " " in padded:
                rec = lex[p]
                return {"Product": rec["Product"], "Segment": rec["Segment"],
                        "Sub-segment": rec["Sub-segment"],
                        "Confidence": rec["confidence"], "Phrase": p}

        toks = set(padded.split())
        for head in heads:
            if head in toks:
                hit = hs8_seg.get(str(hs8))
                seg = hit["segment"] if hit and hit["share"] >= min_share else ""
                return {"Product": f"{head.capitalize()} (unspecified)",
                        "Segment": seg, "Sub-segment": "",
                        "Confidence": "low", "Phrase": head}
        return None

    return find_category


def make_manufacturer_matcher(alias_cores):
    """Return find_manufacturer(importer, exporter, hs4) → canonical|None for
    the Tier-3 pass. Searches the curated alias cores (longest-first) as whole
    words in the normalized Importer+Exporter blob, gated by HS4 scope, with a
    veterinary/animal exclusion guard."""
    excl = cfg.MANUFACTURER_EXCLUDE_CUES

    def find_manufacturer(importer, exporter, hs4):
        if not _match_allowed(hs4):
            return None
        blob = norm_party(importer) + " " + norm_party(exporter)
        if any(cue in blob for cue in excl):
            return None
        padded = " " + blob + " "
        for core, canonical in alias_cores:
            if " " + core + " " in padded:
                return canonical
        return None

    return find_manufacturer


def run_matching() -> int:
    """Tier-1 family pass + Tier-2 category pass (cascade: category only runs on
    rows the family pass left unmatched). Persists per-row results to JSON."""
    lookup, prefix_map = _load_trie()
    find_match = make_matcher(prefix_map)
    with open(cfg.CATEGORY_LEX_PKL, "rb") as fh:
        lex = pickle.load(fh)

    # Read ONLY the columns this stage consumes (desc + HS4/HS8 gate + trade
    # parties). The full 24-col × 2M-row TSV otherwise needs several GB of commit
    # charge and OOMs on the large India dataset under memory pressure; this stage
    # never writes the frame back, so the narrow read is output-identical.
    _need = {cfg.VN_DESCRIPTION_COL, cfg.VN_HS4_COL, cfg.VN_HS_CODE_COL,
             *cfg.MANUFACTURER_PARTY_COLS}
    vn = pd.read_csv(cfg.VN_TSV, sep="\t", dtype=str,
                     usecols=lambda c: c in _need)
    desc = vn[cfg.VN_DESCRIPTION_COL].fillna("").tolist()
    hs4  = vn[cfg.VN_HS4_COL].fillna("").tolist()
    hs8  = vn[cfg.VN_HS_CODE_COL].fillna("").tolist()

    # Tier-1 family
    matched = [find_match(d, h) for d, h in zip(desc, hs4)]
    # Tier-1 conflict guard: release family hits whose resolved Product conflicts
    # with the description (e.g. a mesh-brand hit on a row that is clearly a
    # suture) so they fall through to the Tier-2 category pass. See
    # cfg.TIER1_CONFLICT_GUARDS.
    guards = getattr(cfg, "TIER1_CONFLICT_GUARDS", [])
    if guards:
        n_guard = 0
        for i, kw in enumerate(matched):
            if not kw:
                continue
            prod = lookup.get(kw, {}).get("Product", "").lower()
            low = desc[i].lower()
            for g in guards:
                if (g["product_cue"] in prod
                        and any(c in low for c in g["forbid"])
                        and not any(c in low for c in g["allow"])):
                    matched[i] = None
                    n_guard += 1
                    break
        if n_guard:
            print(f"  [match] Tier-1 conflict guard released {n_guard:,} "
                  f"family hits to Tier-2")

    # General consistency reranker: release a family hit that collided onto a
    # different device. Uses the VN-learned cue→Segment map (cfg.CONSISTENCY_PKL).
    # A hit is released iff (a) its Product's own head word is ABSENT from the
    # description (uncorroborated) AND (b) the description contains a cue whose
    # learned Segment set EXCLUDES the family Product's Segment. Data-driven
    # generalization of the per-brand guards above; see cfg.CONSISTENCY_*.
    head_seg = _load_consistency()
    if head_seg:
        from src.step3b_hs_prior import _cue_tokens
        cue_set = set(head_seg)
        floor, alien = cfg.CONSISTENCY_SEG_FLOOR, cfg.CONSISTENCY_ALIEN_MAX
        n_rr = 0
        for i, kw in enumerate(matched):
            if not kw:
                continue
            rec = lookup.get(kw, {})
            s_fam = rec.get("Segment", "")
            if not s_fam:
                continue
            dtoks = _cue_tokens(desc[i])
            own = _cue_tokens(rec.get("Product", ""))
            if own & dtoks:                      # corroborated by its own device word
                continue
            present = cue_set & dtoks
            # Keep if any present cue SUPPORTS the family Segment (desc backs it).
            if any(head_seg[c].get(s_fam, 0.0) >= floor for c in present):
                continue
            # Release only if a present cue makes the family Segment truly ALIEN.
            if any(head_seg[c].get(s_fam, 0.0) < alien for c in present):
                matched[i] = None
                n_rr += 1
        if n_rr:
            print(f"  [match] Tier-1 consistency reranker released {n_rr:,} "
                  f"collided family hits to Tier-2")

    # Ambiguous-brand corroboration guard: a common-English-word family keyword is
    # kept only when the description shares a token with the family's own Product /
    # Sub-segment / Segment label (the device/anatomy context backs the brand). This
    # catches out-of-domain collisions the reference-learned reranker cannot model
    # (intraocular lens, patient monitor, OT lamp, oxygen terminal). See
    # cfg.AMBIGUOUS_FAMILY_KEYWORDS.
    if getattr(cfg, "USE_AMBIGUOUS_FAMILY_GUARD", False):
        from src.step3b_hs_prior import _cue_tokens
        ambig = {a.lower() for a in getattr(cfg, "AMBIGUOUS_FAMILY_KEYWORDS", set())}
        n_ab = 0
        for i, kw in enumerate(matched):
            if not kw or str(kw).lower() not in ambig:
                continue
            rec = lookup.get(kw, {})
            corrob = (_cue_tokens(rec.get("Product", ""))
                      | _cue_tokens(rec.get("Sub-segment", ""))
                      | _cue_tokens(rec.get("Segment", "")))
            if corrob & _cue_tokens(desc[i]):
                continue                          # device/anatomy context backs it
            matched[i] = None
            n_ab += 1
        if n_ab:
            print(f"  [match] Tier-1 ambiguous-brand guard released {n_ab:,} "
                  f"uncorroborated common-word family hits to Tier-2")

    n1 = sum(1 for m in matched if m)
    with open(cfg.MATCHED_KW_JSON, "w") as fh:
        json.dump(matched, fh)

    # Tier-2 category (only on family-unmatched rows)
    hs8_seg = build_hs8_segment(hs8, matched, lookup)
    find_category = make_category_matcher(lex, hs8_seg)
    category = [None] * len(vn)
    for i, fam in enumerate(matched):
        if fam is None:
            category[i] = find_category(desc[i], hs4[i], hs8[i])
    n2 = sum(1 for m in category if m)
    with open(cfg.MATCHED_CATEGORY_JSON, "w") as fh:
        json.dump(category, fh)

    # Tier-3 manufacturer (only on rows still unmatched by family AND category)
    with open(cfg.MANUFACTURER_ALIAS_PKL, "rb") as fh:
        alias_cores = pickle.load(fh)
    find_manufacturer = make_manufacturer_matcher(alias_cores)
    importer = vn[cfg.MANUFACTURER_PARTY_COLS[0]].fillna("").tolist()
    exporter = vn[cfg.MANUFACTURER_PARTY_COLS[1]].fillna("").tolist()
    manufacturer = [None] * len(vn)
    dental_cues = cfg.DENTAL_NEGATIVE_CUES
    for i in range(len(vn)):
        if matched[i] is None and category[i] is None:
            # iter-11: dental rows are out-of-scope — don't tag a maker either.
            low = desc[i].lower()
            if any(c in low for c in dental_cues):
                continue
            manufacturer[i] = find_manufacturer(importer[i], exporter[i], hs4[i])
    n3 = sum(1 for m in manufacturer if m)
    with open(cfg.MATCHED_MANUFACTURER_JSON, "w") as fh:
        json.dump(manufacturer, fh)

    gate = ("ALL HS4 (widened)" if cfg.MATCH_ALL_HS4
            else f"HS4 scope {sorted(cfg.SURGICAL_HS4)}")
    print(f"  [match] Tier-1 family: {n1:,} / {len(vn):,} rows "
          f"({n1 / len(vn):.1%}) matched over {gate}")
    print(f"  [match] Tier-2 category: +{n2:,} net-new "
          f"(combined {n1 + n2:,}, {(n1 + n2) / len(vn):.1%})")
    print(f"  [match] Tier-3 manufacturer: +{n3:,} net-new "
          f"(combined {n1 + n2 + n3:,}, {(n1 + n2 + n3) / len(vn):.1%})")
    return n1 + n2 + n3


if __name__ == "__main__":
    print("Step 2 — Matching")
    run_matching()
