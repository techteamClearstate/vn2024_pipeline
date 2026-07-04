"""
Reference-compliance pass (DQ review, 2026-07)
==============================================
Post-process a mapped market workbook so it complies with the LATEST surgical
brand/model master:

  * family tier   — validate the FULL key (Segment | Sub-segment | Product |
                    Player | Model/Family) against "Updated (excl. generic)";
                    loose (punctuation/spacing) matches are rewritten to the
                    master's exact wording; player/family pairs missing from the
                    master or listed under another category are parked as Review.
  * category tier — validate Segment | Sub-segment | Product only (Manufacturer/
                    Family may stay "Unspecified"); loose matches rewritten.
  * manufacturer  — never dashboard-included; QA = Audit - manufacturer only.
  * hs_prior      — low-confidence category-only; never dashboard-included.
  * generic rule  — rows whose full key only exists among "Generic Family Name?"
                    master rows are parked (Review - generic reference family).
  * Extended rule — reference-valid surgical products under Extended (non-core)
                    HS codes are parked pending a business include/exclude call.
  * scope rule    — irrelevant-scope keyword triggers (veterinary / dental /
                    cosmetic / lab-IVD / imaging) exclude otherwise-trusted rows
                    unless a documented surgical-context whitelist validates them.
  * anomaly rule  — generic-token families (Target, Elite, Hybrid, …) whose
                    description reads as capital / non-surgical equipment are
                    parked (Review - generic-token mapping anomaly).

Trusted dashboard rule (all must hold):
  Match_Scope=Surgical, Ref_Valid=Y, Scope_Flag blank,
  QA_Status="Mapped - reference-valid"  →  Dash_Include=Y

Outputs
  1. a compliant workbook (RawData + hard-coded Summary / Dashboard / Scope /
     Rollup / QA recomputed from the updated RawData);
  2. a DQ report workbook: Summary, Reference_Label_Fixes, Reference_Hard_Issues,
     Extended_Surgical_Review, Irrelevant_Scope_Hits,
     Unmatched_Surgical_Candidates, Final_Action_Log.

Usage:
  python tools/reference_compliance.py --workbook outputs/Pakistan_ML_Map_Mapped.xlsx \
      --country Pakistan \
      --out outputs/Pakistan_FY2024_ML_Map_Mapped.xlsx \
      --report outputs/Pakistan_FY2024_DQ_Compliance_Report.xlsx
"""
import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import settings as cfg

# ── QA vocabulary (extends cfg.QA_*) ────────────────────────────────────────
QA_MAPPED        = "Mapped - reference-valid"
QA_REVIEW_EXT    = "Review - surgical product in Extended HS scope"
QA_REVIEW_GEN    = "Review - generic reference family"
QA_REVIEW_CAT    = "Review - reference category conflict"
QA_REVIEW_NOREF  = "Review - not in latest reference"
QA_REVIEW_SCOPE  = "Review - excluded scope"          # + ": <flag>"
QA_REVIEW_UNSPEC = "Review - unspecified category"
QA_REVIEW_ANOM   = "Review - generic-token mapping anomaly"
QA_AUDIT_MFR     = "Audit - manufacturer only"
QA_AUDIT_HSPRIOR = "Audit - hs_prior category (pending validation)"
QA_UNMAPPED      = "Unmapped"

DIM_COLS = ["Segment", "Sub-segment", "Product_V0", "Manufacturer", "Family"]

# ── Rule 7: irrelevant-scope keyword triggers (description-only by design —
#    party names cause false positives, see cfg.SCOPE_EXCLUDE_COLS note). ────
SCOPE_KEYWORDS = {
    "veterinary": [r"equine", r"bovine", r"canine", r"feline", r"veterinar", r"\banimal\b"],
    "dental":     [r"dental", r"orthodont", r"\btooth\b", r"\bteeth\b"],
    "cosmetic":   [r"cosmetic", r"aesthetic", r"\bbeauty\b", r"dermal filler",
                   r"breast implant", r"botox", r"skin treatment"],
    "lab_ivd":    [r"reagent", r"\bassay\b", r"calibrator", r"\bcontrol\b",
                   r"diagnostic kit", r"\bivd\b", r"laborator"],
    "imaging":    [r"linear accelerator", r"cyclotron", r"radiotherap",
                   r"x[- ]?ray", r"\bct\b", r"\bmri\b", r"ultrasound", r"imaging"],
}
# Surgical-context whitelist: a hit on these overrides the keyword triggers
# (documented adjudications of the Pakistan FY2024 trusted-set hits).
SURGICAL_CONTEXT_WHITELIST = [
    # PTCA/NC dilatation catheters (valid PCI; tolerates common misspellings)
    r"(?:dilatation|dilation|dialation|dialatation) catheter",
    r"x[- ]?ray detectable",          # x-ray-detectable gauze/swabs (surgical consumable)
    r"electrosurgical pencil",        # named surgical device
    r"insufflator",                   # laparoscopic insufflators (FLOW50 w/ smoke evac)
    r"diagnostic catheter",           # cardiovascular diagnostic catheters
]

# ── Rule 10: generic tokens whose family match must be sanity-checked, plus
#    capital-equipment cues that contradict a consumable/device mapping. ─────
GENERIC_TOKENS = {"target", "light source", "sprinter", "essential", "unity",
                  "hybrid", "elite", "optime",
                  # observed Pakistan FY2024 false-positive drivers:
                  "therapy", "evolution", "physio", "woven", "cone"}
CAPITAL_EQUIPMENT_CUES = [
    r"\bmachine\b", r"\bequipment\b", r"\bapparatus\b", r"\blaser\b",
    r"therapy machine", r"tolerance testing", r"\bused\b.*\bmachine\b",
    r"skin treatment", r"workstation", r"\bconsole\b",
]

SURGICAL_CANDIDATE_TERMS = [
    r"suture", r"stapler", r"staple", r"trocar", r"cannula", r"catheter",
    r"stent", r"\bmesh\b", r"scalpel", r"forceps", r"laparoscop", r"arthroscop",
    r"endoscop", r"electrosurg", r"cauter", r"diathermy", r"ligat", r"clip applier",
    r"guidewire", r"guide wire", r"bone screw", r"bone plate", r"intramedullary",
    r"orthopaedic", r"orthopedic", r"\bimplant", r"prosthes", r"knee", r"\bhip\b",
    r"spinal", r"pedicle", r"vascular graft", r"heart valve", r"annuloplasty",
    r"oxygenator", r"hernia", r"haemostat", r"hemostat", r"gauze", r"drape",
    r"retractor", r"osteotomy", r"burr", r"\bdrill\b", r"\bsaw\b", r"kirschner",
    r"external fixat", r"anchor", r"shaver", r"ablation", r"balloon",
]


def norm_exact(s) -> str:
    """Trim / collapse whitespace / casefold — the strict canonical comparison."""
    return re.sub(r"\s+", " ", str(s if s is not None else "")).strip().casefold()


def norm_loose(s) -> str:
    """Exact normalization + punctuation-separator folding: underscores, hyphens,
    en/em dashes, slashes, trademark marks and repeated spaces all collapse to a
    single space, so `Conventional Suture_Absorbable` ==
    `Conventional Suture - Absorbable`."""
    t = str(s if s is not None else "")
    t = re.sub(r"[™®©]", "", t)          # ™ ® ©
    t = re.sub(r"[_\-–—/\\]+", " ", t)
    return re.sub(r"\s+", " ", t).strip().casefold()


def _sync_from_settings() -> None:
    """Use governed settings/term-list values when this tool is run standalone."""
    global QA_MAPPED, QA_REVIEW_EXT, QA_REVIEW_GEN, QA_REVIEW_CAT
    global QA_REVIEW_NOREF, QA_REVIEW_SCOPE, QA_REVIEW_UNSPEC, QA_REVIEW_ANOM
    global QA_AUDIT_MFR, QA_AUDIT_HSPRIOR, QA_UNMAPPED
    global SCOPE_KEYWORDS, SURGICAL_CONTEXT_WHITELIST, GENERIC_TOKENS
    global CAPITAL_EQUIPMENT_CUES, SURGICAL_CANDIDATE_TERMS

    QA_MAPPED = getattr(cfg, "QA_MAPPED", QA_MAPPED)
    QA_REVIEW_EXT = getattr(cfg, "QA_REVIEW_EXT", QA_REVIEW_EXT)
    QA_REVIEW_GEN = getattr(cfg, "QA_REVIEW_GEN", QA_REVIEW_GEN)
    QA_REVIEW_CAT = getattr(cfg, "QA_REVIEW_CAT", QA_REVIEW_CAT)
    QA_REVIEW_NOREF = getattr(cfg, "QA_REVIEW_NOREF", QA_REVIEW_NOREF)
    QA_REVIEW_SCOPE = getattr(cfg, "QA_REVIEW_SCOPE", QA_REVIEW_SCOPE)
    QA_REVIEW_UNSPEC = getattr(cfg, "QA_REVIEW_UNSPEC", QA_REVIEW_UNSPEC)
    QA_REVIEW_ANOM = getattr(cfg, "QA_REVIEW_ANOM", QA_REVIEW_ANOM)
    QA_AUDIT_MFR = getattr(cfg, "QA_AUDIT_MFR", QA_AUDIT_MFR)
    QA_AUDIT_HSPRIOR = getattr(cfg, "QA_AUDIT_HSPRIOR", QA_AUDIT_HSPRIOR)
    QA_UNMAPPED = getattr(cfg, "QA_UNMAPPED", QA_UNMAPPED)

    SCOPE_KEYWORDS = getattr(cfg, "SCOPE_EXCLUDE_CUES", SCOPE_KEYWORDS)
    SURGICAL_CONTEXT_WHITELIST = list(
        getattr(cfg, "SURGICAL_CONTEXT_WHITELIST", SURGICAL_CONTEXT_WHITELIST)
    )
    GENERIC_TOKENS = {
        norm_loose(value) for value in getattr(cfg, "GENERIC_TOKENS", GENERIC_TOKENS)
    }
    CAPITAL_EQUIPMENT_CUES = list(
        getattr(cfg, "CAPITAL_EQUIPMENT_CUES", CAPITAL_EQUIPMENT_CUES)
    )
    SURGICAL_CANDIDATE_TERMS = list(
        getattr(cfg, "SURGICAL_CANDIDATE_TERMS", SURGICAL_CANDIDATE_TERMS)
    )


_sync_from_settings()


def _rx(patterns):
    return re.compile("|".join(patterns), re.IGNORECASE)


def load_master():
    """Master reference keyed both ways. Returns dict of lookup structures."""
    mst = pd.read_excel(cfg.V0_REFERENCE_XLSX, sheet_name="Updated", dtype=str)
    mst = mst.fillna("")
    gen_flag = mst["Generic Family Name?"].astype(str).str.strip()
    strict = mst[gen_flag == ""]
    generic = mst[gen_flag != ""]

    def five(r):
        return (r["Segment"], r["Sub-segment"], r["Product"],
                r["Player"], r["Model/ Family Name"])

    m = {
        "full_exact": set(), "full_loose": {},          # strict (excl. generic)
        "gen_exact": {}, "gen_loose": {},               # generic-only full keys
        "cat_exact": set(), "cat_loose": {},            # categories (all master)
        "pf_cats": defaultdict(set),                    # (player,family)loose → canon triples
        "n_strict": len(strict), "n_generic": len(generic), "n_all": len(mst),
    }
    cat_word_votes = defaultdict(Counter)
    for _, r in mst.iterrows():
        trip = (r["Segment"], r["Sub-segment"], r["Product"])
        ke = tuple(norm_exact(x) for x in trip)
        kl = tuple(norm_loose(x) for x in trip)
        m["cat_exact"].add(ke)
        cat_word_votes[kl][trip] += 1
        m["pf_cats"][(norm_loose(r["Player"]), norm_loose(r["Model/ Family Name"]))].add(trip)
    m["cat_loose"] = {k: v.most_common(1)[0][0] for k, v in cat_word_votes.items()}

    for _, r in strict.iterrows():
        f = five(r)
        m["full_exact"].add(tuple(norm_exact(x) for x in f))
        m["full_loose"].setdefault(tuple(norm_loose(x) for x in f), f)
    for _, r in generic.iterrows():
        f = five(r)
        flag = r["Generic Family Name?"]
        m["gen_exact"].setdefault(tuple(norm_exact(x) for x in f), (f, flag))
        m["gen_loose"].setdefault(tuple(norm_loose(x) for x in f), (f, flag))
    return m


def scope_hit(text_lc: str):
    """(group, keyword) of the first irrelevant-scope trigger, or (None, None).
    The surgical-context whitelist suppresses all triggers."""
    for wl in SCOPE_HIT_WHITELIST_RX:
        if wl.search(text_lc):
            return None, "whitelist"
    for group, rxs in SCOPE_HIT_RX.items():
        mobj = rxs.search(text_lc)
        if mobj:
            return group, mobj.group(0)
    return None, None


SCOPE_HIT_RX = {g: _rx(p) for g, p in SCOPE_KEYWORDS.items()}
SCOPE_HIT_WHITELIST_RX = [re.compile(p, re.IGNORECASE) for p in SURGICAL_CONTEXT_WHITELIST]
CAPITAL_RX = _rx(CAPITAL_EQUIPMENT_CUES)
SURG_CAND_RX = _rx(SURGICAL_CANDIDATE_TERMS)


# ─────────────────────────────────────────────────────────────────────────────
def run(workbook: Path, country: str, out_wb: Path, out_report: Path) -> dict:
    print(f"[compliance] loading {workbook.name} …")
    df = pd.read_excel(workbook, sheet_name="RawData", dtype=str).fillna("")
    for c in ["Quantity", "Total_Value_USD", "ASP_USD"]:
        df["_" + c] = pd.to_numeric(df[c], errors="coerce")
    df["_rev"] = df["_Total_Value_USD"].fillna(0.0)
    desc_lc = df["Detailed_Product"].astype(str).str.lower()

    print(f"[compliance] loading master {cfg.V0_REFERENCE_XLSX.name} …")
    m = load_master()
    print(f"  master: {m['n_all']:,} rows ({m['n_strict']:,} strict + "
          f"{m['n_generic']:,} generic), {len(m['cat_exact']):,} exact categories")

    tier = df["Match_Tier"].fillna("")
    scope_surg = df["Match_Scope"] == cfg.SCOPE_SURGICAL_LABEL
    before = {
        "rows": len(df), "rev": float(df["_rev"].sum()),
        "trusted_rows": int(((df["Dash_Include"] == "Y") & scope_surg).sum()),
        "trusted_rev": float(df.loc[(df["Dash_Include"] == "Y") & scope_surg, "_rev"].sum()),
        "qa": df["QA_Status"].value_counts().to_dict(),
    }

    # Working state: disposition per row.
    qa       = df["QA_Status"].astype(str).copy()
    ref_valid = pd.Series("", index=df.index)
    scope_flag = df["Scope_Flag"].astype(str).fillna("").copy()

    fixes = []        # label-fix combos            → Reference_Label_Fixes
    hard = []         # unresolvable combos         → Reference_Hard_Issues
    actions = []      # every applied change        → Final_Action_Log
    scope_rows = []   # keyword hits (row level)    → Irrelevant_Scope_Hits

    def log_action(action, rule, mask_or_ids, old, new, note=""):
        if isinstance(mask_or_ids, pd.Series):
            rows, rev = int(mask_or_ids.sum()), float(df.loc[mask_or_ids, "_rev"].sum())
        else:
            rows, rev = len(mask_or_ids), float(df.loc[mask_or_ids, "_rev"].sum())
        actions.append({"Action": action, "Rule": rule, "Rows": rows,
                        "Revenue_USD": round(rev, 2), "Old": old, "New": new,
                        "Note": note})

    # ── family tier: full-key validation ────────────────────────────────────
    fam_mask = tier == "family"
    fam_groups = df[fam_mask].groupby(DIM_COLS, dropna=False, sort=False)
    n_relabel = 0
    for combo, sub in fam_groups:
        idx = sub.index
        rev = float(sub["_rev"].sum())
        ke = tuple(norm_exact(x) for x in combo)
        kl = tuple(norm_loose(x) for x in combo)
        trip_l = kl[:3]
        canon = None
        status = None
        issue = ""
        if ke in m["full_exact"]:
            status = "valid"
        elif kl in m["full_loose"]:
            canon, status = m["full_loose"][kl], "valid"
            issue = "Loose full-key match; labels updated to master wording"
        elif ke in m["gen_exact"] or kl in m["gen_loose"]:
            canon, gflag = m["gen_exact"].get(ke) or m["gen_loose"][kl]
            status, issue = "generic", f"Matches only a generic reference family ({gflag})"
        else:
            pf = m["pf_cats"].get(kl[3:5], set())
            if pf:
                status = "conflict"
                cats = "; ".join(" | ".join(t) for t in sorted(pf)[:3])
                issue = f"Player/family exists in master under other category: {cats}"
            else:
                status = "missing"
                issue = "Player/family pair not present in latest master"
            # even for hard issues, align category wording where it loose-matches
            if trip_l in m["cat_loose"] and tuple(norm_exact(x) for x in combo[:3]) not in m["cat_exact"]:
                canon = m["cat_loose"][trip_l] + (combo[3], combo[4])

        if canon is not None and tuple(canon) != tuple(combo):
            for col, old_v, new_v in zip(DIM_COLS, combo, canon):
                if str(old_v) != str(new_v):
                    df.loc[idx, col] = new_v
            n_relabel += len(idx)
            fixes.append({"Match_Tier": "family", "Rows": len(idx), "Revenue_USD": round(rev, 2),
                          **{f"Old_{c}": v for c, v in zip(DIM_COLS, combo)},
                          **{f"New_{c}": v for c, v in zip(DIM_COLS, canon)},
                          "Issue": issue or "Labels updated to master wording",
                          "Sample_UniqueID": sub["UniqueID"].iloc[0]})
        if status == "valid":
            ref_valid.loc[idx] = "Y"
            qa.loc[idx] = QA_MAPPED
        elif status == "generic":
            ref_valid.loc[idx] = "Y"
            qa.loc[idx] = QA_REVIEW_GEN
            hard.append({"Match_Tier": "family", "Issue": issue, "QA_Status": QA_REVIEW_GEN,
                         "Rows": len(idx), "Revenue_USD": round(rev, 2),
                         **{c: v for c, v in zip(DIM_COLS, combo)},
                         "Sample_UniqueID": sub["UniqueID"].iloc[0],
                         "Sample_Description": str(sub["Detailed_Product"].iloc[0])[:150]})
        else:
            qa.loc[idx] = QA_REVIEW_CAT if status == "conflict" else QA_REVIEW_NOREF
            hard.append({"Match_Tier": "family", "Issue": issue,
                         "QA_Status": str(qa.loc[idx[0]]),
                         "Rows": len(idx), "Revenue_USD": round(rev, 2),
                         **{c: v for c, v in zip(DIM_COLS, combo)},
                         "Sample_UniqueID": sub["UniqueID"].iloc[0],
                         "Sample_Description": str(sub["Detailed_Product"].iloc[0])[:150]})

    # ── category + hs_prior tiers: triple validation ────────────────────────
    for t, default_qa in [("category", QA_MAPPED), ("hs_prior", QA_AUDIT_HSPRIOR)]:
        t_mask = tier == t
        unspec = (df["Product_V0"].str.contains(re.escape(cfg.UNSPECIFIED_PRODUCT_MARK),
                                                case=False, regex=True)
                  | df["Product_V0"].str.casefold().isin(["", cfg.UNSPECIFIED_LABEL.casefold()])
                  | df["Segment"].str.casefold().isin(["", cfg.UNSPECIFIED_LABEL.casefold()])
                  | df["Sub-segment"].str.casefold().isin(["", cfg.UNSPECIFIED_LABEL.casefold()]))
        qa.loc[t_mask & unspec] = QA_REVIEW_UNSPEC
        for combo, sub in df[t_mask & ~unspec].groupby(
                ["Segment", "Sub-segment", "Product_V0"], dropna=False, sort=False):
            idx = sub.index
            rev = float(sub["_rev"].sum())
            ke = tuple(norm_exact(x) for x in combo)
            kl = tuple(norm_loose(x) for x in combo)
            if ke in m["cat_exact"]:
                ok = True
            elif kl in m["cat_loose"]:
                canon = m["cat_loose"][kl]
                for col, old_v, new_v in zip(DIM_COLS[:3], combo, canon):
                    if str(old_v) != str(new_v):
                        df.loc[idx, col] = new_v
                n_relabel += len(idx)
                fixes.append({"Match_Tier": t, "Rows": len(idx), "Revenue_USD": round(rev, 2),
                              **{f"Old_{c}": v for c, v in zip(DIM_COLS[:3], combo)},
                              **{f"New_{c}": v for c, v in zip(DIM_COLS[:3], canon)},
                              "Issue": "Loose category match; labels updated to master wording",
                              "Sample_UniqueID": sub["UniqueID"].iloc[0]})
                ok = True
            else:
                ok = False
            if ok:
                if t == "category":
                    ref_valid.loc[idx] = "Y"
                qa.loc[idx] = default_qa
            else:
                qa.loc[idx] = QA_REVIEW_NOREF
                hard.append({"Match_Tier": t, "Issue": "Category not in latest master",
                             "QA_Status": QA_REVIEW_NOREF, "Rows": len(idx),
                             "Revenue_USD": round(rev, 2),
                             **{c: v for c, v in zip(DIM_COLS[:3], combo)},
                             "Manufacturer": "", "Family": "",
                             "Sample_UniqueID": sub["UniqueID"].iloc[0],
                             "Sample_Description": str(sub["Detailed_Product"].iloc[0])[:150]})

    # ── manufacturer tier / unmatched ────────────────────────────────────────
    qa.loc[tier == "manufacturer"] = QA_AUDIT_MFR
    qa.loc[df["Match_Status"] != "Matched"] = QA_UNMAPPED

    # ── rule 7: irrelevant-scope keyword pass (matched bound tiers) ─────────
    bound_mask = tier.isin(["family", "category", "hs_prior"])
    kept_pipeline_flag = bound_mask & (scope_flag != "")
    qa.loc[kept_pipeline_flag & qa.isin([QA_MAPPED, QA_AUDIT_HSPRIOR])] = ""  # recompute below
    n_kw_excluded = 0
    for i in df.index[bound_mask]:
        group, kw = scope_hit(desc_lc.iat[i])
        prior_flag = scope_flag.iat[i]
        if (group is not None and kw and tier.iat[i] == "family"
                and ref_valid.iat[i] == "Y"
                and norm_loose(kw) in norm_loose(df["Family"].iat[i])):
            # the trigger token is part of the master-validated family name
            # (e.g. MRI-conditional pacemakers "Attesta SR MRI") — not an
            # out-of-scope signal. Validate as surgical.
            scope_rows.append(_scope_row(df, i, group, kw,
                                         "Validated surgical (token is part of "
                                         "matched family name)"))
            if prior_flag:
                scope_flag.iat[i] = ""
            continue
        if group is None and kw == "whitelist" and prior_flag:
            # pipeline had flagged it, but the surgical-context whitelist clears it
            scope_rows.append(_scope_row(df, i, prior_flag, "(pipeline cue)",
                                         "Validated surgical (context whitelist)"))
            scope_flag.iat[i] = ""
            continue
        if group is None and not prior_flag:
            continue
        flag = group or prior_flag
        disposition = "Excluded from trusted dashboard (pending review)"
        scope_rows.append(_scope_row(df, i, flag, kw or "(pipeline cue)", disposition))
        scope_flag.iat[i] = flag
        if qa.iat[i] in (QA_MAPPED, QA_AUDIT_HSPRIOR, ""):
            qa.iat[i] = f"{QA_REVIEW_SCOPE}: {flag}"
            n_kw_excluded += 1
    # rows whose pipeline flag was cleared and no new hit → restore mapped status
    restore = bound_mask & (qa == "")
    qa.loc[restore & (ref_valid == "Y")] = QA_MAPPED
    qa.loc[restore & (qa == "")] = QA_REVIEW_NOREF

    # ── rule 10: generic-token capital-equipment anomalies ──────────────────
    fam_l = df["Family"].map(norm_loose)
    anomaly = ((tier == "family") & (qa == QA_MAPPED)
               & fam_l.isin(GENERIC_TOKENS)
               & desc_lc.str.contains(CAPITAL_RX, regex=True, na=False))
    for i in df.index[anomaly]:
        scope_rows.append(_scope_row(df, i, "generic-token", "capital-equipment cue",
                                     "Excluded: generic-token mapping anomaly"))
    qa.loc[anomaly] = QA_REVIEW_ANOM
    if int(anomaly.sum()):
        log_action("Park generic-token anomaly", "Rule 10", anomaly,
                   QA_MAPPED, QA_REVIEW_ANOM,
                   "Family = generic token + capital-equipment wording in description")

    # ── rule 8: Extended demotion (after validation, before final gate) ─────
    ext = (qa == QA_MAPPED) & ~scope_surg
    qa.loc[ext] = QA_REVIEW_EXT
    log_action("Park Extended-scope surgical rows", "Rule 8", ext,
               QA_MAPPED, QA_REVIEW_EXT, "Business decision required to include")

    # ── final trusted gate (rule 6) ──────────────────────────────────────────
    include = (qa == QA_MAPPED) & scope_surg & (ref_valid == "Y") & (scope_flag == "")
    df["Ref_Valid"] = np.where(ref_valid == "Y", "Y", "")
    df["Scope_Flag"] = scope_flag
    df["Dash_Include"] = np.where(include, "Y", "")
    df["QA_Status"] = qa

    # ── acceptance self-check ────────────────────────────────────────────────
    bad = 0
    for combo, sub in df[include & (tier == "family")].groupby(DIM_COLS, sort=False):
        if tuple(norm_exact(x) for x in combo) not in m["full_exact"]:
            bad += len(sub)
    for combo, sub in df[include & (tier == "category")].groupby(DIM_COLS[:3], sort=False):
        if tuple(norm_exact(x) for x in combo) not in m["cat_exact"]:
            bad += len(sub)
    def unresolved_hit(i):
        group, kw = scope_hit(desc_lc.iat[i])
        if group is None:
            return False
        # same adjudication as the pass: token inside the validated family name
        return not (kw and tier.iat[i] == "family"
                    and norm_loose(kw) in norm_loose(df["Family"].iat[i]))

    kw_leak = sum(1 for i in df.index[include] if unresolved_hit(i))
    print(f"[self-check] trusted rows failing exact master validation: {bad}; "
          f"unresolved keyword hits in trusted set: {kw_leak}")
    assert bad == 0 and kw_leak == 0, "acceptance self-check FAILED"

    # ── action log (aggregate) ───────────────────────────────────────────────
    for fx in fixes:
        actions.append({"Action": "Relabel to master wording", "Rule": "Step 4 (loose match)",
                        "Rows": fx["Rows"], "Revenue_USD": fx["Revenue_USD"],
                        "Old": " | ".join(str(fx.get(f"Old_{c}", "")) for c in DIM_COLS),
                        "New": " | ".join(str(fx.get(f"New_{c}", "")) for c in DIM_COLS),
                        "Note": fx["Issue"]})
    for hd in hard:
        actions.append({"Action": "Park for review", "Rule": "Rule 5/9",
                        "Rows": hd["Rows"], "Revenue_USD": hd["Revenue_USD"],
                        "Old": " | ".join(str(hd.get(c, "")) for c in DIM_COLS),
                        "New": hd["QA_Status"], "Note": hd["Issue"]})
    for sr in scope_rows:
        actions.append({"Action": "Scope keyword adjudication", "Rule": "Rule 7",
                        "Rows": 1, "Revenue_USD": sr["Revenue_USD"],
                        "Old": sr["UniqueID"], "New": sr["Disposition"],
                        "Note": f"{sr['Keyword_Group']}: {sr['Keyword']}"})

    after = {
        "trusted_rows": int(include.sum()),
        "trusted_rev": float(df.loc[include, "_rev"].sum()),
        "trusted_lower_rev": float(df.loc[include & (tier == "family"), "_rev"].sum()),
        "relabelled_rows": n_relabel,
        "kw_excluded": n_kw_excluded,
        "qa": df["QA_Status"].value_counts().to_dict(),
    }

    # ── unmatched surgical candidates ────────────────────────────────────────
    um = df[df["Match_Status"] != "Matched"].copy()
    um_hit = um["Detailed_Product"].astype(str).str.lower()
    um["_kw"] = um_hit.str.extract(f"({SURG_CAND_RX.pattern})", flags=re.IGNORECASE,
                                   expand=False)
    neg = um_hit.str.contains(_rx([p for g in SCOPE_KEYWORDS.values() for p in g]),
                              regex=True, na=False)
    cand = um[um["_kw"].notna() & ~neg].sort_values("_rev", ascending=False)
    after["unmatched_candidates"] = len(cand)
    after["unmatched_candidates_rev"] = float(cand["_rev"].sum())

    print(f"[compliance] relabelled {n_relabel:,} rows; trusted "
          f"{before['trusted_rows']:,} → {after['trusted_rows']:,} rows, "
          f"${before['trusted_rev']:,.0f} → ${after['trusted_rev']:,.0f}")

    _write_workbook(out_wb, df, country, m, before, after)
    _write_report(out_report, df, country, m, before, after,
                  fixes, hard, scope_rows, actions, cand)
    return {"before": before, "after": after}


def _scope_row(df, i, group, kw, disposition):
    return {"Keyword_Group": group, "Keyword": kw, "Disposition": disposition,
            "UniqueID": df["UniqueID"].iat[i],
            "Revenue_USD": round(float(df["_rev"].iat[i]), 2),
            "Quantity": df["Quantity"].iat[i],
            "Match_Tier": df["Match_Tier"].iat[i],
            "Segment": df["Segment"].iat[i], "Sub-segment": df["Sub-segment"].iat[i],
            "Product_V0": df["Product_V0"].iat[i],
            "Manufacturer": df["Manufacturer"].iat[i], "Family": df["Family"].iat[i],
            "Detailed_Product": str(df["Detailed_Product"].iat[i])[:200]}


# ── workbook writer (hard-coded sheets) ──────────────────────────────────────
RAW_COLS = ["Month", "HS_Code", "Detailed_Product", "Importer", "Exporter",
            "Country_of_Exporters", "Quantity", "Unit_Qty", "Total_Value_USD",
            "HS4", "Year", "UniqueID", "Manufacturer", "Family", "Segment",
            "Sub-segment", "Product_V0", "Match_Status", "Match_Tier",
            "Match_Confidence", "Match_Scope", "ASP_USD", "Ref_Valid",
            "Scope_Flag", "Dash_Include", "QA_Status"]


def _fmt(wb, **kw):
    base = {"font_name": "Arial", "font_size": 9}
    base.update(kw)
    return wb.add_format(base)


def _write_df(ws, frame, hdr_fmt, formats=None, start_row=0):
    for ci, col in enumerate(frame.columns):
        ws.write(start_row, ci, str(col), hdr_fmt)
    for ri, (_, row) in enumerate(frame.iterrows(), start=start_row + 1):
        for ci, v in enumerate(row):
            fmt = (formats or {}).get(frame.columns[ci])
            if v is None or (isinstance(v, float) and np.isnan(v)):
                ws.write_blank(ri, ci, None, fmt)
            elif isinstance(v, (int, float, np.integer, np.floating)):
                ws.write_number(ri, ci, float(v), fmt)
            else:
                ws.write_string(ri, ci, str(v)[:1000], fmt)


def _write_workbook(path, df, country, m, before, after):
    import xlsxwriter
    print(f"[compliance] writing workbook {path.name} …")
    wb = xlsxwriter.Workbook(str(path), {"nan_inf_to_errors": True,
                                         "constant_memory": True})
    hdr = _fmt(wb, bold=True, bg_color="#1A4D3C", font_color="#FFFFFF", border=1)
    money = _fmt(wb, num_format="#,##0")
    asp = _fmt(wb, num_format="#,##0.00")
    note = _fmt(wb, font_size=8, italic=True, font_color="#666666")
    lbl = _fmt(wb, bold=True)

    d = df.copy()
    tier = d["Match_Tier"].fillna("")
    include = d["Dash_Include"] == "Y"

    # RawData
    ws = wb.add_worksheet("RawData")
    out = d[RAW_COLS].copy()
    for c in ["Quantity", "Total_Value_USD", "ASP_USD"]:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    _write_df(ws, out, hdr, formats={"Total_Value_USD": money, "ASP_USD": asp})
    n = len(out)
    tcol = RAW_COLS.index("Match_Tier")
    from xlsxwriter.utility import xl_col_to_name, xl_range
    tl = xl_col_to_name(tcol)
    full = xl_range(1, 0, n, len(RAW_COLS) - 1)
    ws.conditional_format(full, {"type": "formula",
                                 "criteria": f'=${tl}2="family"',
                                 "format": _fmt(wb, bg_color="#E8F1EC")})
    ws.conditional_format(full, {"type": "formula",
                                 "criteria": f'=${tl}2="category"',
                                 "format": _fmt(wb, bg_color="#FFF7DC")})
    ws.freeze_panes(1, 0)
    ws.autofilter(0, 0, n, len(RAW_COLS) - 1)

    # Summary (match counts by tier/segment/sub/product — same layout as before)
    matched = d[d["Match_Status"] == "Matched"].copy()
    for c in ["Segment", "Sub-segment", "Product_V0"]:
        matched[c] = matched[c].replace("", cfg.UNSPECIFIED_LABEL)
    summ = (matched.groupby(["Match_Tier", "Segment", "Sub-segment", "Product_V0"],
                            dropna=False).size().reset_index(name="Match_Count")
            .sort_values(["Match_Tier", "Match_Count"], ascending=[True, False]))
    ws = wb.add_worksheet("Summary")
    _write_df(ws, summ, hdr)
    ws.freeze_panes(1, 0)

    # Dashboard (hard values over Dash_Include=Y)
    t = d[include].copy()
    t["_rev"] = pd.to_numeric(t["Total_Value_USD"], errors="coerce").fillna(0.0)
    t["_vol"] = pd.to_numeric(t["Quantity"], errors="coerce").fillna(0.0)
    t["_asp"] = pd.to_numeric(t["ASP_USD"], errors="coerce")
    g = t.groupby(["Segment", "Sub-segment", "Product_V0", "Family", "Manufacturer"],
                  dropna=False)
    dash = pd.DataFrame({"Total_Revenue_USD": g["_rev"].sum(),
                         "Total_Volume": g["_vol"].sum(),
                         "Min_ASP": g["_asp"].min(), "Max_ASP": g["_asp"].max()})
    dash["Avg_ASP"] = (dash["Total_Revenue_USD"] / dash["Total_Volume"]).where(
        dash["Total_Volume"] > 0)
    dash = dash.reset_index()
    dash.insert(0, "Country", country)
    dash.columns = ["Country", "OU", "Sub_OU", "Product", "Family", "Manufacturer",
                    "Total_Revenue_USD", "Total_Volume", "Min_ASP", "Max_ASP", "Avg_ASP"]
    dash = dash.sort_values(["OU", "Sub_OU", "Product", "Family", "Manufacturer"])
    ws = wb.add_worksheet("Dashboard")
    _write_df(ws, dash, hdr, formats={"Total_Revenue_USD": money, "Total_Volume": money,
                                      "Min_ASP": asp, "Max_ASP": asp, "Avg_ASP": asp})
    ws.freeze_panes(1, 0)
    ws.autofilter(0, 0, len(dash), len(dash.columns) - 1)

    # Scope (hard values; Extended = reference-valid rows parked for the
    # business include/exclude decision, rule 8)
    ext_mask = d["QA_Status"] == QA_REVIEW_EXT
    ws = wb.add_worksheet("Scope")
    heads = ["Scope", "Lower_Revenue_USD (family)", "Upper_Revenue_USD (family+category)",
             "Total_Volume", "Matched_Shipments"]
    for ci, h in enumerate(heads):
        ws.write(0, ci, h, hdr)

    def scope_vals(mask):
        s = d[mask]
        rev = pd.to_numeric(s["Total_Value_USD"], errors="coerce").fillna(0.0)
        vol = pd.to_numeric(s["Quantity"], errors="coerce").fillna(0.0)
        fam = s["Match_Tier"] == "family"
        return [float(rev[fam].sum()), float(rev.sum()), float(vol.sum()), int(len(s))]

    rows = [("Surgical (trusted)", include),
            ("Extended (ref-valid, pending review)", ext_mask),
            ("Total", include | ext_mask)]
    for ri, (label, mask) in enumerate(rows, start=1):
        ws.write_string(ri, 0, label, lbl)
        for ci, v in enumerate(scope_vals(mask), start=1):
            ws.write_number(ri, ci, v, money)
    ws.write(len(rows) + 2, 0,
             f"DQ compliance pass vs master {cfg.V0_REFERENCE_XLSX.name}: trusted = "
             f"Match_Scope=Surgical & Ref_Valid=Y & Scope_Flag blank & "
             f"QA_Status='{QA_MAPPED}'. Extended rows are reference-valid surgical "
             f"products under non-core HS codes parked as "
             f"'{QA_REVIEW_EXT}' pending a business decision (rule 8).", note)
    ws.set_column(0, 0, 34)
    ws.set_column(1, 4, 26)
    ws.freeze_panes(1, 0)

    # Rollup (Product → Manufacturer → Family outline, values)
    ws = wb.add_worksheet("Rollup")
    heads = ["Product Category / Manufacturer / Family", "Revenue_USD", "Volume",
             "Min_ASP", "Max_ASP", "Shipments"]
    for ci, h in enumerate(heads):
        ws.write(0, ci, h, hdr)
    ws.set_column(0, 0, 52)
    ws.set_column(1, 2, 16)
    ws.set_column(3, 5, 12)
    ws.outline_settings(True, False, True, True)
    cat_f = _fmt(wb, bold=True, bg_color="#1A4D3C", font_color="#FFFFFF")
    cat_n = _fmt(wb, bold=True, bg_color="#1A4D3C", font_color="#FFFFFF", num_format="#,##0")
    mfr_f = _fmt(wb, bold=True, bg_color="#A9CCBB", font_color="#0F2E23", indent=1)
    mfr_n = _fmt(wb, bold=True, bg_color="#A9CCBB", font_color="#0F2E23", indent=1,
                 num_format="#,##0")
    fam_f = _fmt(wb, bg_color="#E8F1EC", font_color="#33453D", indent=2)
    fam_n = _fmt(wb, bg_color="#E8F1EC", font_color="#33453D", indent=2, num_format="#,##0")
    roll = t.copy()
    for k in ["Product_V0", "Manufacturer", "Family"]:
        roll[k] = roll[k].replace("", cfg.UNSPECIFIED_LABEL)
    ri = 1

    def _agg_row(ws_, ri_, label, sub, tf, nf, level, hidden=False):
        rev, vol = float(sub["_rev"].sum()), float(sub["_vol"].sum())
        mn, mx = sub["_asp"].min(), sub["_asp"].max()
        ws_.set_row(ri_, None, None, {"level": level, "hidden": hidden})
        ws_.write_string(ri_, 0, label, tf)
        ws_.write_number(ri_, 1, rev, nf)
        ws_.write_number(ri_, 2, vol, nf)
        ws_.write(ri_, 3, float(mn) if pd.notna(mn) else "", nf)
        ws_.write(ri_, 4, float(mx) if pd.notna(mx) else "", nf)
        ws_.write_number(ri_, 5, len(sub), nf)

    for cat, csub in roll.groupby("Product_V0", sort=True):
        _agg_row(ws, ri, str(cat), csub, cat_f, cat_n, 0); ri += 1
        for mfr, msub in csub.groupby("Manufacturer", sort=True):
            _agg_row(ws, ri, str(mfr), msub, mfr_f, mfr_n, 1); ri += 1
            for fam, fsub in msub.groupby("Family", sort=True):
                _agg_row(ws, ri, str(fam), fsub, fam_f, fam_n, 2, hidden=True); ri += 1
    ws.freeze_panes(1, 0)

    # QA
    ws = wb.add_worksheet("QA")
    title = _fmt(wb, bold=True, font_size=11)
    ws.write(0, 0, f"QA / Data-Quality Review — {country} (reference-compliance pass, "
                   f"master {cfg.V0_REFERENCE_XLSX.name})", title)
    d["_r"] = pd.to_numeric(d["Total_Value_USD"], errors="coerce").fillna(0.0)
    qa_tab = (d.groupby("QA_Status")
                .agg(Rows=("QA_Status", "size"), Revenue_USD=("_r", "sum"))
                .reset_index().sort_values("Revenue_USD", ascending=False))
    _write_df(ws, qa_tab, hdr, formats={"Revenue_USD": money}, start_row=2)
    r0 = len(qa_tab) + 5
    sf = d[d["Scope_Flag"] != ""]
    sf_tab = (sf.groupby("Scope_Flag")
                .agg(Rows=("Scope_Flag", "size"), Revenue_USD=("_r", "sum"))
                .reset_index().sort_values("Revenue_USD", ascending=False))
    ws.write(r0 - 1, 0, "Negative-scope flags", lbl)
    _write_df(ws, sf_tab, hdr, formats={"Revenue_USD": money}, start_row=r0)
    ws.write(r0 + len(sf_tab) + 2, 0,
             "Trusted dashboard rule: Match_Scope=Surgical AND Ref_Valid=Y AND "
             "Scope_Flag blank AND QA_Status='Mapped - reference-valid' AND no "
             "unresolved irrelevant-scope keyword hit. See the companion "
             "DQ compliance report for label fixes, hard issues, Extended review "
             "and the full action log.", note)
    ws.set_column(0, 0, 52)
    ws.set_column(1, 2, 16)
    ws.freeze_panes(3, 0)
    wb.close()


def _write_report(path, df, country, m, before, after,
                  fixes, hard, scope_rows, actions, cand):
    import xlsxwriter
    print(f"[compliance] writing report {path.name} …")
    wb = xlsxwriter.Workbook(str(path), {"nan_inf_to_errors": True})
    hdr = _fmt(wb, bold=True, bg_color="#1A4D3C", font_color="#FFFFFF", border=1)
    money = _fmt(wb, num_format="#,##0")
    title = _fmt(wb, bold=True, font_size=11)

    tier = df["Match_Tier"].fillna("")

    # 1. Summary
    ws = wb.add_worksheet("Summary")
    ws.write(0, 0, f"{country} — reference-compliance DQ pass vs "
                   f"{cfg.V0_REFERENCE_XLSX.name}", title)
    rows = [
        ("Master", "Rows — Updated (full)", m["n_all"], ""),
        ("Master", "Rows — strict (excl. generic)", m["n_strict"], ""),
        ("Master", "Rows — generic families", m["n_generic"], ""),
        ("Before", "Total RawData rows", before["rows"], round(before["rev"], 2)),
        ("Before", "Trusted dashboard rows", before["trusted_rows"],
         round(before["trusted_rev"], 2)),
        ("After", "Trusted dashboard rows", after["trusted_rows"],
         round(after["trusted_rev"], 2)),
        ("After", "Trusted lower bound (family tier)", "",
         round(after["trusted_lower_rev"], 2)),
        ("After", "Rows relabelled to master wording", after["relabelled_rows"], ""),
        ("After", "Rows excluded by scope keywords", after["kw_excluded"], ""),
        ("After", "Unmatched surgical-candidate rows", after["unmatched_candidates"],
         round(after["unmatched_candidates_rev"], 2)),
    ]
    for sec in sorted(after["qa"]):
        rev = float(pd.to_numeric(
            df.loc[df["QA_Status"] == sec, "Total_Value_USD"], errors="coerce")
            .fillna(0).sum())
        rows.append(("QA_Status (after)", sec, after["qa"][sec], round(rev, 2)))
    summary = pd.DataFrame(rows, columns=["Section", "Metric", "Value", "Revenue_USD"])
    _write_df(ws, summary, hdr, formats={"Revenue_USD": money}, start_row=2)
    ws.set_column(0, 1, 46)
    ws.set_column(2, 3, 18)

    def sheet_from(name, records, sort_key="Revenue_USD"):
        ws_ = wb.add_worksheet(name)
        if not records:
            ws_.write(0, 0, "No issues found.", title)
            return
        fr = pd.DataFrame(records)
        if sort_key in fr.columns:
            fr = fr.sort_values(sort_key, ascending=False)
        _write_df(ws_, fr, hdr, formats={"Revenue_USD": money})
        ws_.freeze_panes(1, 0)
        ws_.autofilter(0, 0, len(fr), len(fr.columns) - 1)
        for ci, c in enumerate(fr.columns):
            ws_.set_column(ci, ci, min(44, max(12, int(fr[c].astype(str).str.len()
                                                       .quantile(0.9)) + 2)))

    # 2-3. label fixes / hard issues
    sheet_from("Reference_Label_Fixes", fixes)
    sheet_from("Reference_Hard_Issues", hard)

    # 4. Extended surgical review (combo grain, for the business decision)
    ext = df[df["QA_Status"] == QA_REVIEW_EXT].copy()
    ext["_r"] = pd.to_numeric(ext["Total_Value_USD"], errors="coerce").fillna(0.0)
    ext_tab = (ext.groupby(["HS4", "Segment", "Sub-segment", "Product_V0",
                            "Manufacturer", "Family", "Match_Tier"], dropna=False)
               .agg(Rows=("_r", "size"), Revenue_USD=("_r", "sum"))
               .reset_index().sort_values("Revenue_USD", ascending=False))
    ext_tab["Revenue_USD"] = ext_tab["Revenue_USD"].round(2)
    sheet_from("Extended_Surgical_Review", ext_tab.to_dict("records"))

    # 5. scope hits
    sheet_from("Irrelevant_Scope_Hits", scope_rows)

    # 6. unmatched candidates (top 1000 by revenue)
    ctab = cand.head(1000)[["UniqueID", "HS_Code", "HS4", "_rev", "Quantity",
                            "_kw", "Detailed_Product", "Importer", "Exporter"]].copy()
    ctab.columns = ["UniqueID", "HS_Code", "HS4", "Revenue_USD", "Quantity",
                    "Keyword", "Detailed_Product", "Importer", "Exporter"]
    ctab["Revenue_USD"] = ctab["Revenue_USD"].round(2)
    ctab["Detailed_Product"] = ctab["Detailed_Product"].astype(str).str.slice(0, 200)
    sheet_from("Unmatched_Surgical_Candidates", ctab.to_dict("records"))

    # 7. final action log
    sheet_from("Final_Action_Log", actions)
    wb.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workbook", required=True, type=Path)
    ap.add_argument("--country", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--report", required=True, type=Path)
    a = ap.parse_args()
    run(a.workbook, a.country, a.out, a.report)
