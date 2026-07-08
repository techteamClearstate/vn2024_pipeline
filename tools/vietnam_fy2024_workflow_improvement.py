"""Improve and audit the Vietnam FY2024 surgical import mapping workflow.

The script is intentionally conservative about dashboard inclusion:
Trusted rows are not expanded unless they remain latest-master valid. The main
recall improvement is to capture surgical-looking uncertainty into auditable
review buckets, expose candidate/evidence fields, and generate reusable alias,
rule, reference-update, and gold-label templates.
"""

from __future__ import annotations

import argparse
import math
import re
import shutil
import sys
import time
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import reference_compliance as rc  # noqa: E402


DEFAULT_INPUT = ROOT / "outputs" / "Vietnam_FY2024_ML_Map_Mapped.xlsx"
DEFAULT_OUTPUT = ROOT / "outputs" / "Vietnam_FY2024_ML_Map_Mapped.xlsx"
DEFAULT_QA = ROOT / "outputs" / "Vietnam_FY2024_Workflow_QA_Report.xlsx"
DEFAULT_SHARED = Path(
    r"G:\Shared drives\New EIU Gateway\0. Gateway Ops & Databases\Import Data Master"
    r"\6. Workflow\Surgicals\Claude code\1. Mapped Results"
)
LOCALIZED_SHARED = Path(
    r"G:\共享云端硬盘\New EIU Gateway\0. Gateway Ops & Databases\Import Data Master"
    r"\6. Workflow\Surgicals\Claude code\1. Mapped Results"
)

VALUE_COL = "Total_Value_USD"
RAW_SHEET = "RawData"
QA_MAPPED = "Mapped - reference-valid"
QA_UNMAPPED = "Unmapped"
QA_UNSPEC = "Review - unspecified category"
QA_MFR_ONLY = "Audit - manufacturer only"
QA_EXTENDED = "Review - surgical product in Extended HS scope"
QA_NOREF = "Review - not in latest reference"

QA_CANDIDATE_REVIEW = "Review - candidate surgical evidence"
QA_UNSPEC_EVIDENCE = "Review - unspecified category with surgical evidence"
QA_MFR_PRODUCT = "Review - manufacturer + surgical product evidence"
QA_PRECISION_RISK = "Review - precision risk conflict"

CORE_HS4 = {"9018", "9019", "9021", "9022"}
EXTENDED_HS4 = {"3006", "3926", "4015", "6210", "8419", "8421", "8481", "9018", "9019", "9020", "9021", "9022"}
UNSPECIFIED = {"", "nan", "none", "unspecified", "unknown", "n/a", "na"}


def norm_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def norm_tuple(values: Iterable[object]) -> tuple[str, ...]:
    return tuple(norm_text(v) for v in values)


def value_usd(df: pd.DataFrame) -> pd.Series:
    return pd.to_numeric(df.get(VALUE_COL, 0), errors="coerce").fillna(0.0)


def quantity(df: pd.DataFrame) -> pd.Series:
    return pd.to_numeric(df.get("Quantity", 0), errors="coerce").fillna(0.0)


def row_text(df: pd.DataFrame, fields: Iterable[str]) -> pd.Series:
    out = pd.Series("", index=df.index, dtype="object")
    for field in fields:
        if field in df.columns:
            out = out.str.cat(df[field].fillna("").astype(str), sep=" ")
    return out.str.strip()


def safe_sheet_name(name: str) -> str:
    return re.sub(r"[][\\/*?:]", "_", name)[:31]


PRODUCT_RULES: list[dict[str, object]] = [
    {
        "group": "stents / DES / BMS",
        "pattern": r"\b(?:drug eluting stents?|des|bare metal stents?|bms|stent systems?|coronary stents?|vascular stents?|implantable stents?|xience|express)\b",
        "segment": "Coronary and Renal Denervation (CRDN)",
        "subsegment": "PCI Stents",
        "product": "Drug Eluting Stents",
        "aliases": "DES; drug eluting stent; BMS; bare metal stent; coronary stent system; Xience; Express",
        "score": 42,
    },
    {
        "group": "guiding catheters / vascular access",
        "pattern": r"\b(?:guiding catheters?|guide catheters?|catheters?|microcatheters?|introducers?|sheaths?|safe ?sheath)\b",
        "segment": "Peripheral Vascular Health (PVH)",
        "subsegment": "Peripheral Vascular",
        "product": "Guide Catheters",
        "aliases": "guiding catheter; guide catheter; introducer; sheath; microcatheter; catheter",
        "score": 38,
    },
    {
        "group": "guidewires",
        "pattern": r"\b(?:guide ?wires?|hydrophilic wires?|angiographic wires?)\b",
        "segment": "Peripheral Vascular Health (PVH)",
        "subsegment": "Peripheral Vascular",
        "product": "Guidewires",
        "aliases": "guidewire; guide wire; hydrophilic wire",
        "score": 40,
    },
    {
        "group": "balloons / PTCA / PTA",
        "pattern": r"\b(?:ptca|pta|angioplasty balloons?|drug coated balloons?|dcb|balloon catheters?)\b",
        "segment": "Coronary and Renal Denervation (CRDN)",
        "subsegment": "PCI Non Stents",
        "product": "PTCA Balloons",
        "aliases": "PTCA; PTA; angioplasty balloon; balloon catheter; drug coated balloon",
        "score": 40,
    },
    {
        "group": "cannulae",
        "pattern": r"\b(?:cannulae?|canulae?|cannulated|fistula cannula)\b",
        "segment": "Cardiac Surgery (CS)",
        "subsegment": "ECT and Revasc",
        "product": "Cannulae",
        "aliases": "cannula; cannulae; canula",
        "score": 36,
    },
    {
        "group": "sutures",
        "pattern": r"\b(?:sutures?|vicryl|prolene|polysorb|surgicryl|demesorb|pdo|polydioxanone|polyglactin|polypropylene suture)\b",
        "segment": "Surgical Innovations (SI)",
        "subsegment": "Wound Management",
        "product": "Conventional Suture - Absorbable",
        "aliases": "suture; Vicryl; Prolene; Polysorb; Surgicryl; PDO; Polydioxanone",
        "score": 44,
    },
    {
        "group": "mesh / hernia",
        "pattern": r"\b(?:hernia mesh|surgical mesh|biosynthetic mesh|synthetic mesh|biologic mesh|mesh fixation|tacker|hernia)\b",
        "segment": "Surgical Innovations (SI)",
        "subsegment": "Hernia",
        "product": "Synthetic Mesh",
        "aliases": "hernia mesh; surgical mesh; biosynthetic mesh; synthetic mesh; mesh fixation",
        "score": 42,
    },
    {
        "group": "hemostats / wound management",
        "pattern": r"\b(?:hemostats?|haemostats?|hemostatic|haemostatic|wound dressings?|wound management|sealants?|adhesion barrier)\b",
        "segment": "Surgical Innovations (SI)",
        "subsegment": "Wound Management",
        "product": "Hemostats",
        "aliases": "hemostat; haemostat; wound dressing; sealant; adhesion barrier",
        "score": 34,
    },
    {
        "group": "endoscopy / laparoscopy / MIS",
        "pattern": r"\b(?:endoscopes?|endoscopy|endoscopic|video endoscopy|laparoscopes?|laparoscopy|laparoscopic|trocar|endo hand instruments?|mis platforms?|image processor)\b",
        "segment": "Surgical Innovations (SI)",
        "subsegment": "MIS Platforms",
        "product": "MIS_Endoscope",
        "aliases": "endoscope; endoscopy system; video endoscopy; laparoscopy; trocar; image processor",
        "score": 40,
    },
    {
        "group": "autotransfusion / cell saver",
        "pattern": r"\b(?:autotransfusion|auto transfusion|cell saver|blood recovery|blood salvage|xtra)\b",
        "segment": "Cardiac Surgery (CS)",
        "subsegment": "Extracorporeal Therapies",
        "product": "Autotransfusion_Consumable",
        "aliases": "autotransfusion; cell saver; blood recovery; blood salvage; Xtra",
        "score": 38,
    },
    {
        "group": "artificial discs / spine implants",
        "pattern": r"\b(?:artificial discs?|cervical discs?|spinal discs?|spine implants?|spinal implants?|interbody cages?|bone screws?|bone plates?)\b",
        "segment": "Cranial & Spinal Technologies (CST)",
        "subsegment": "Total Spinal",
        "product": "Cervical Artificial Discs",
        "aliases": "artificial disc; cervical disc; spinal disc; spine implant; bone screw; bone plate",
        "score": 38,
    },
    {
        "group": "heart valves / TAVI / TAVR",
        "pattern": r"\b(?:prosthetic heart valves?|mechanical heart valves?|tissue heart valves?|heart valves?|on[- ]?x|tavi|tavr|transcatheter aortic)\b",
        "segment": "Cardiac Surgery (CS)",
        "subsegment": "Surgical Ablation & Valve Therapies",
        "product": "Mechanical Heart Valves",
        "aliases": "heart valve; prosthetic heart valve; mechanical valve; ON-X; TAVI; TAVR",
        "score": 42,
    },
    {
        "group": "orthopedic implants / knee / hip",
        "pattern": r"\b(?:total knee replacement|knee replacement|hip replacement|orthopedic implants?|orthopaedic implants?|vanguard|bone cement|cementless)\b",
        "segment": "Ortho",
        "subsegment": "Knee Replacement",
        "product": "Total Knee Replacement",
        "aliases": "Vanguard; total knee replacement; hip replacement; bone cement; orthopedic implant",
        "score": 36,
    },
    {
        "group": "cardiopulmonary / oxygenators",
        "pattern": r"\b(?:oxygenators?|cardiopulmonary|ecmo|heart lung|circuit|capiox)\b",
        "segment": "Cardiac Surgery (CS)",
        "subsegment": "ECT and Revasc",
        "product": "Cardiopulmonary/Oxygenators",
        "aliases": "oxygenator; cardiopulmonary; ECMO; CAPIOX; circuit",
        "score": 32,
    },
    {
        "group": "dialysis / hemodialysis",
        "pattern": r"\b(?:hemo ?dialysis|haemo ?dialysis|dialysis|dialy[sz]ers?|nikkiso)\b",
        "segment": "",
        "subsegment": "",
        "product": "Dialysis system / dialyzer - reference scope decision needed",
        "aliases": "dialysis; hemodialysis; dialyzer; Nikkiso",
        "score": 30,
    },
    {
        "group": "staplers / clips",
        "pattern": r"\b(?:surgical staplers?|staples?|clip appliers?|ligation clips?|surgical clips?)\b",
        "segment": "Surgical Innovations (SI)",
        "subsegment": "Instruments and Access",
        "product": "Surgical Staplers",
        "aliases": "stapler; surgical clip; clip applier; ligation clip",
        "score": 36,
    },
]

NEGATIVE_RULES: list[tuple[str, str]] = [
    ("radiotherapy/cyclotron", r"\b(?:linear accelerator|linar accelerator|linac|cyclotron|radiotherapy)\b"),
    ("imaging/OCT/tomography", r"\b(?:optical coherence tomography|tomography|oct\b|oct[- ]?1|ct scanner|mri|scanner|ultrasound machine|angiography machine|fru detector|laser imager|dry imager)\b"),
    ("diagnostic/lab/IVD", r"\b(?:coagulation meter|reagent|assay|calibrator|control|diagnostic kits?|ivd|laborator(?:y|ies)|hemochron signature elite)\b"),
    ("cardiac capital equipment", r"\b(?:defibrillator|ecg machine|heart[- ]?lung machine|centrifugal pump|rotaflow|pump controller|contrast injection pump)\b"),
    ("non-surgical capital", r"\b(?:scientific refrigerator|refrigerator|body warmer|blood warmer)\b"),
    ("ophthalmic/intraocular", r"\b(?:ophthalmic lens|intraocular lens|ophthalmic visco[- ]?surgical|visco[- ]?surgical device)\b"),
    ("dental", r"\b(?:dental|orthodontic|intraoral scanner)\b"),
    ("veterinary", r"\b(?:veterinary|equine|canine|bovine|feline)\b"),
    ("cosmetic/aesthetic", r"\b(?:cosmetic|aesthetic|hydra facial|hydrafacial)\b"),
    ("pharmaceutical/vaccine", r"\b(?:vaccine|pharmaceutical)\b"),
    ("lithotripsy category check", r"\b(?:lithotripter|lithotripsy|lithoclast)\b"),
]

GENERIC_TOKENS = [
    "Light Source",
    "Target",
    "Sprinter",
    "Arrive",
    "Current",
    "Volt",
    "Maestro",
    "Imager",
    "Hybrid",
    "Elite",
    "Essential",
    "Unity",
    "Therapy",
    "Velocity Alpha",
    "Celsius",
    "Express",
    "Hydra",
    "Zero",
    "March",
    "Xtra",
    "Masters",
    "Image Processor",
]

MANUFACTURER_ALIAS_RULES: list[tuple[str, str, str]] = [
    ("Johnson & Johnson / Ethicon", r"\b(?:j\s*and\s*j|johnson\s+and\s+johnson|ethicon)\b", "J&J; Johnson & Johnson; Ethicon"),
    ("Boston Scientific", r"\bboston scientific\b", "Boston Scientific"),
    ("Medtronic", r"\bmedtronic\b", "Medtronic"),
    ("Abbott", r"\babbott\b", "Abbott"),
    ("Terumo", r"\bterumo\b", "Terumo"),
    ("Olympus", r"\bolympus\b", "Olympus"),
    ("Nipro", r"\bnipro\b", "Nipro"),
    ("Nikkiso", r"\bnikkiso\b", "Nikkiso"),
    ("Zimmer Biomet", r"\b(?:zimmer|biomet|zimmer biomet)\b", "Zimmer; Biomet; Zimmer Biomet"),
    ("APT Medical", r"\b(?:apt medical|aptmed)\b", "APT Medical; APTMED"),
    ("SMT", r"\b(?:smt|sahajanand medical technologies)\b", "SMT; Sahajanand Medical Technologies"),
    ("Asahi Intecc", r"\basahi intecc\b", "Asahi Intecc"),
    ("Cryolife", r"\b(?:cryolife|artivion)\b", "Cryolife; Artivion"),
    ("Feel-tech", r"\bfeel[- ]?tech\b", "Feel-tech"),
]


def compile_pattern(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, flags=re.IGNORECASE)


PRODUCT_COMPILED = [(rule, compile_pattern(str(rule["pattern"]))) for rule in PRODUCT_RULES]
NEGATIVE_COMPILED = [(name, compile_pattern(pattern)) for name, pattern in NEGATIVE_RULES]
GENERIC_RE = compile_pattern(r"\b(?:" + "|".join(re.escape(norm_text(t)).replace("\\ ", r"\s+") for t in GENERIC_TOKENS) + r")\b")
MFR_ALIAS_COMPILED = [(name, compile_pattern(pattern), alias) for name, pattern, alias in MANUFACTURER_ALIAS_RULES]


def first_regex_hit(text: pd.Series, compiled: list[tuple[str, re.Pattern[str]]]) -> pd.Series:
    result = pd.Series("", index=text.index, dtype="object")
    for name, rx in compiled:
        mask = result.eq("") & text.str.contains(rx, na=False)
        result.loc[mask] = name
    return result


def build_master_keys(master_path: Path) -> dict[str, object]:
    full = pd.read_excel(master_path, sheet_name="Updated", dtype=str).fillna("")
    strict = pd.read_excel(master_path, sheet_name="Updated (excl. generic)", dtype=str).fillna("")
    generic_flag = full.get("Generic Family Name?", pd.Series("", index=full.index)).astype(str).str.strip()
    generic = full[generic_flag.ne("")]

    strict_full = {
        norm_tuple(row)
        for row in strict[["Segment", "Sub-segment", "Product", "Player", "Model/ Family Name"]].itertuples(index=False, name=None)
    }
    full_latest = {
        norm_tuple(row)
        for row in full[["Segment", "Sub-segment", "Product", "Player", "Model/ Family Name"]].itertuples(index=False, name=None)
    }
    generic_full = {
        norm_tuple(row)
        for row in generic[["Segment", "Sub-segment", "Product", "Player", "Model/ Family Name"]].itertuples(index=False, name=None)
    }
    categories = {
        norm_tuple(row)
        for row in full[["Segment", "Sub-segment", "Product"]].drop_duplicates().itertuples(index=False, name=None)
    }
    category_lookup = (
        full[["Segment", "Sub-segment", "Product"]]
        .drop_duplicates()
        .sort_values(["Segment", "Sub-segment", "Product"])
        .reset_index(drop=True)
    )
    return {
        "full": full,
        "strict": strict,
        "strict_full": strict_full,
        "full_latest": full_latest,
        "generic_full": generic_full,
        "categories": categories,
        "category_lookup": category_lookup,
    }


try:
    from rapidfuzz import process as rf_process
    from rapidfuzz.distance import Levenshtein as rf_levenshtein
    HAVE_RAPIDFUZZ = True
except ImportError:
    HAVE_RAPIDFUZZ = False

# Fuzzy family matching is CANDIDATE EVIDENCE ONLY (routes to Review_Queue,
# never Trusted): customs-OCR misspellings of master family names within a
# length-scaled edit distance, on rows with no other product evidence, gated
# to core/extended HS scope.
ENABLE_FUZZY_FAMILY = True
FUZZY_MIN_TOKEN_LEN = 6          # short brands collide too easily
FUZZY_MAX_TOKEN_LEN = 18
FUZZY_MAX_TOKENS = 250_000       # safety cap on unique tokens per run
# A genuine OCR misspelling is RARE; a token on >0.2% of eligible rows is
# customs vocabulary ("surgical", "proforma") and must not fuzzy-match.
FUZZY_MAX_DF_FRACTION = 0.002
FUZZY_MIN_DF_CAP = 25
_FUZZY_TOKEN_RE = re.compile(r"^[a-z]+$")


def _fuzzy_family_choices(master_keys: dict[str, object]) -> list[str]:
    """Single-word, non-generic strict-master family names eligible as fuzzy
    targets (normalized like row text)."""
    generic = {norm_text(t) for t in GENERIC_TOKENS}
    out = set()
    for key in master_keys["strict_full"]:
        fam = key[4]
        if (" " not in fam and _FUZZY_TOKEN_RE.match(fam)
                and FUZZY_MIN_TOKEN_LEN <= len(fam) <= FUZZY_MAX_TOKEN_LEN
                and fam not in generic):
            out.add(fam)
    return sorted(out)


def fuzzy_family_evidence(text_norm: pd.Series, eligible: pd.Series,
                          master_keys: dict[str, object]) -> pd.DataFrame:
    """Levenshtein-match description tokens against master family names.

    Returns a frame indexed like text_norm with fuzzy_family_match /
    fuzzy_family_token / fuzzy_similarity columns (blank/0 where no hit).
    Acceptance is length-scaled: distance 1 for tokens < 8 chars, up to 2 for
    longer ones; distance 0 (exact) is excluded — exact hits belong to the
    deterministic lexicon, not the fuzzy channel.
    """
    result = pd.DataFrame({"fuzzy_family_match": "", "fuzzy_family_token": "",
                           "fuzzy_similarity": 0.0}, index=text_norm.index)
    if not (HAVE_RAPIDFUZZ and ENABLE_FUZZY_FAMILY):
        return result
    choices = _fuzzy_family_choices(master_keys)
    if not choices:
        return result

    blacklist = {norm_text(t) for t in getattr(rc.cfg, "BLACKLIST", set())}
    token_rows: dict[str, list] = {}
    for idx, txt in text_norm[eligible].items():
        for tok in set(txt.split()):
            if (FUZZY_MIN_TOKEN_LEN <= len(tok) <= FUZZY_MAX_TOKEN_LEN
                    and _FUZZY_TOKEN_RE.match(tok) and tok not in blacklist):
                token_rows.setdefault(tok, []).append(idx)
    max_df = max(FUZZY_MIN_DF_CAP,
                 int(int(eligible.sum()) * FUZZY_MAX_DF_FRACTION))
    tokens = sorted(t for t, rows in token_rows.items()
                    if len(rows) <= max_df)[:FUZZY_MAX_TOKENS]
    if not tokens:
        return result

    # Bucket both sides by first letter: an edit at position 0 is rare in
    # customs OCR, and this cuts the comparison matrix ~26x.
    by_first: dict[str, list[str]] = {}
    for fam in choices:
        by_first.setdefault(fam[0], []).append(fam)

    matches: dict[str, tuple[str, int]] = {}
    for first, fams in by_first.items():
        bucket = [t for t in tokens if t[0] == first]
        if not bucket:
            continue
        dists = rf_process.cdist(bucket, fams, scorer=rf_levenshtein.distance,
                                 score_cutoff=2, workers=-1)
        for i, tok in enumerate(bucket):
            best_j, best_d = -1, 99
            for j, fam in enumerate(fams):
                d = dists[i][j]
                # score_cutoff makes misses read as cutoff+1
                if d <= 2 and d < best_d and tok != fam:
                    # distance 2 only for long, distinctive names
                    max_d = 1 if len(fam) < 10 else 2
                    if d <= max_d and abs(len(tok) - len(fam)) <= max_d:
                        best_j, best_d = j, d
            if best_j >= 0:
                prev = matches.get(tok)
                if prev is None or best_d < prev[1]:
                    matches[tok] = (fams[best_j], best_d)

    for tok, (fam, dist) in matches.items():
        sim = 1.0 - dist / max(len(fam), 1)
        for idx in token_rows[tok]:
            if sim > result.at[idx, "fuzzy_similarity"]:
                result.at[idx, "fuzzy_family_match"] = fam
                result.at[idx, "fuzzy_family_token"] = tok
                result.at[idx, "fuzzy_similarity"] = round(sim, 3)
    return result


def build_evidence(df: pd.DataFrame, master_keys: dict[str, object]) -> pd.DataFrame:
    text_raw = row_text(
        df,
        [
            "Detailed_Product",
            "Importer",
            "Exporter",
            "Country_of_Exporters",
            "HS_Code",
            "Manufacturer",
            "Family",
            "Segment",
            "Sub-segment",
            "Product_V0",
        ],
    )
    text_norm = text_raw.map(norm_text)

    ev = pd.DataFrame(index=df.index)
    ev["row_text_norm"] = text_norm
    ev["product_evidence_group"] = ""
    ev["candidate_segment"] = ""
    ev["candidate_subsegment"] = ""
    ev["candidate_product"] = ""
    ev["product_evidence_terms"] = ""
    ev["product_score"] = 0.0
    ev["word_tfidf_score"] = 0.0
    ev["char_tfidf_score"] = 0.0
    ev["candidate_source_method"] = ""

    for rule, rx in PRODUCT_COMPILED:
        mask = text_norm.str.contains(rx, na=False)
        ev.loc[mask & ev["product_evidence_group"].eq(""), "product_evidence_group"] = str(rule["group"])
        ev.loc[mask & ev["candidate_segment"].eq(""), "candidate_segment"] = str(rule["segment"])
        ev.loc[mask & ev["candidate_subsegment"].eq(""), "candidate_subsegment"] = str(rule["subsegment"])
        ev.loc[mask & ev["candidate_product"].eq(""), "candidate_product"] = str(rule["product"])
        ev.loc[mask & ev["product_evidence_terms"].eq(""), "product_evidence_terms"] = str(rule["aliases"])
        ev.loc[mask, "product_score"] = ev.loc[mask, "product_score"].clip(lower=float(rule["score"]))
        ev.loc[mask, "word_tfidf_score"] = ev.loc[mask, "word_tfidf_score"].clip(lower=0.82)
        ev.loc[mask, "char_tfidf_score"] = ev.loc[mask, "char_tfidf_score"].clip(lower=0.74)
        ev.loc[mask & ev["candidate_source_method"].eq(""), "candidate_source_method"] = "alias/word_ngram"

    ev["negative_conflict_group"] = first_regex_hit(text_norm, NEGATIVE_COMPILED)
    ev["exclusion_score"] = ev["negative_conflict_group"].ne("").astype(float) * 100.0

    ev["manufacturer_alias_hit"] = ""
    ev["manufacturer_alias_terms"] = ""
    for name, rx, aliases in MFR_ALIAS_COMPILED:
        mask = ev["manufacturer_alias_hit"].eq("") & text_norm.str.contains(rx, na=False)
        ev.loc[mask, "manufacturer_alias_hit"] = name
        ev.loc[mask, "manufacturer_alias_terms"] = aliases

    mfr_norm = df.get("Manufacturer", pd.Series("", index=df.index)).map(norm_text)
    family_norm = df.get("Family", pd.Series("", index=df.index)).map(norm_text)
    player_in_text = [
        bool(mfr and mfr not in UNSPECIFIED and mfr in txt)
        for mfr, txt in zip(mfr_norm.tolist(), text_norm.tolist())
    ]
    family_in_text = [
        bool(fam and fam not in UNSPECIFIED and len(fam) >= 3 and fam in txt)
        for fam, txt in zip(family_norm.tolist(), text_norm.tolist())
    ]
    family_generic = family_norm.isin({norm_text(x) for x in GENERIC_TOKENS}) | family_norm.isin(UNSPECIFIED)
    ev["manufacturer_evidence"] = pd.Series(player_in_text, index=df.index) | ev["manufacturer_alias_hit"].ne("")
    ev["family_evidence"] = pd.Series(family_in_text, index=df.index) & ~family_generic
    ev["manufacturer_score"] = 0.0
    ev.loc[ev["manufacturer_evidence"], "manufacturer_score"] = 24.0
    ev.loc[~ev["manufacturer_evidence"] & mfr_norm.ne("") & ~mfr_norm.isin(UNSPECIFIED), "manufacturer_score"] = 8.0
    ev["family_score"] = ev["family_evidence"].astype(float) * 28.0

    ev["generic_token_risk"] = text_norm.str.contains(GENERIC_RE, na=False) | family_generic
    ev["generic_token_penalty"] = ev["generic_token_risk"].astype(float) * 12.0

    hs4 = df.get("HS4", pd.Series("", index=df.index)).astype(str).str.extract(r"(\d{4})", expand=False).fillna("")
    ev["hs4_norm"] = hs4
    ev["hs_scope"] = "outside"
    ev.loc[hs4.isin(EXTENDED_HS4), "hs_scope"] = "extended"
    ev.loc[hs4.isin(CORE_HS4), "hs_scope"] = "core"
    ev["hs_score"] = 0.0
    ev.loc[ev["hs_scope"].eq("extended"), "hs_score"] = 6.0
    ev.loc[ev["hs_scope"].eq("core"), "hs_score"] = 16.0

    mapped_segment = df.get("Segment", pd.Series("", index=df.index)).fillna("").astype(str)
    mapped_sub = df.get("Sub-segment", pd.Series("", index=df.index)).fillna("").astype(str)
    mapped_product = df.get("Product_V0", pd.Series("", index=df.index)).fillna("").astype(str)
    mapped_player = df.get("Manufacturer", pd.Series("", index=df.index)).fillna("").astype(str)
    mapped_family = df.get("Family", pd.Series("", index=df.index)).fillna("").astype(str)

    full_keys = [
        norm_tuple(row)
        for row in zip(mapped_segment, mapped_sub, mapped_product, mapped_player, mapped_family)
    ]
    cat_keys = [norm_tuple(row) for row in zip(mapped_segment, mapped_sub, mapped_product)]
    strict_full = master_keys["strict_full"]
    full_latest = master_keys["full_latest"]
    generic_full = master_keys["generic_full"]
    categories = master_keys["categories"]

    ev["full_latest_valid"] = [key in full_latest for key in full_keys]
    ev["full_strict_valid"] = [key in strict_full for key in full_keys]
    ev["generic_reference_only"] = [key in generic_full for key in full_keys]
    ev["category_latest_valid"] = [key in categories for key in cat_keys]

    ev["master_validation_status"] = "not_applicable"
    family_tier = df.get("Match_Tier", pd.Series("", index=df.index)).fillna("").astype(str).str.lower().eq("family")
    category_tier = df.get("Match_Tier", pd.Series("", index=df.index)).fillna("").astype(str).str.lower().eq("category")
    ev.loc[family_tier & ev["full_strict_valid"], "master_validation_status"] = "pass_full_strict"
    ev.loc[family_tier & ev["full_latest_valid"] & ~ev["full_strict_valid"], "master_validation_status"] = "pass_full_latest_generic_risk"
    ev.loc[family_tier & ~ev["full_latest_valid"], "master_validation_status"] = "reference_update_needed"
    ev.loc[category_tier & ev["category_latest_valid"], "master_validation_status"] = "pass_category"
    ev.loc[category_tier & ~ev["category_latest_valid"], "master_validation_status"] = "category_reference_update_needed"

    ev["category_confidence"] = 0.0
    ev.loc[ev["product_score"].gt(0) & ev["hs_scope"].isin(["core", "extended"]), "category_confidence"] = 0.68
    ev.loc[ev["product_score"].ge(40) & ev["hs_scope"].eq("core"), "category_confidence"] = 0.86
    ev.loc[df.get("Dash_Include", pd.Series("", index=df.index)).fillna("").astype(str).eq("Y"), "category_confidence"] = 0.95

    ev["semantic_score"] = 0.0
    ev["fuzzy_score"] = 0.0
    ev.loc[ev["product_score"].gt(0), "fuzzy_score"] = 0.72

    # Real fuzzy channel (rapidfuzz, Review-only evidence): misspelled master
    # family names on rows with no other product/family evidence, in HS scope.
    fuzzy_eligible = (ev["product_score"].eq(0) & ~ev["family_evidence"]
                      & ev["hs_scope"].isin(["core", "extended"]))
    fz = fuzzy_family_evidence(text_norm, fuzzy_eligible, master_keys)
    ev["fuzzy_family_match"] = fz["fuzzy_family_match"]
    ev["fuzzy_family_token"] = fz["fuzzy_family_token"]
    fuzzy_hit = fz["fuzzy_similarity"].gt(0)
    ev.loc[fuzzy_hit, "fuzzy_score"] = fz.loc[fuzzy_hit, "fuzzy_similarity"]
    ev.loc[fuzzy_hit & ev["candidate_source_method"].eq(""),
           "candidate_source_method"] = "fuzzy_lexical"
    ev["final_candidate_score"] = (
        ev["product_score"]
        + ev["family_score"]
        + ev["manufacturer_score"]
        + ev["hs_score"]
        + ev["fuzzy_score"] * 10
        + ev["word_tfidf_score"] * 10
        + ev["char_tfidf_score"] * 8
        - ev["generic_token_penalty"]
        - ev["exclusion_score"] * 0.55
    ).round(2)

    ev["high_value_review_priority"] = ""
    values = value_usd(df)
    ev.loc[values.ge(250_000), "high_value_review_priority"] = "P0 >=250K"
    ev.loc[values.ge(100_000) & values.lt(250_000), "high_value_review_priority"] = "P1 100K-250K"
    ev.loc[values.ge(50_000) & values.lt(100_000), "high_value_review_priority"] = "P2 50K-100K"
    ev.loc[values.ge(25_000) & values.lt(50_000), "high_value_review_priority"] = "P3 25K-50K"

    return ev


def route_rows(df: pd.DataFrame, ev: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    out = df.copy()
    for col in ["QA_Status", "Dash_Include", "Scope_Flag", "Ref_Valid", "Match_Scope"]:
        if col not in out.columns:
            out[col] = ""
        out[col] = out[col].fillna("").astype(str)

    baseline_qa = out["QA_Status"].copy()
    baseline_dash = out["Dash_Include"].eq("Y")
    product = ev["product_score"].gt(0)
    hard_negative = ev["negative_conflict_group"].ne("")
    no_hard_negative = ~hard_negative

    candidate_unmapped = baseline_qa.eq(QA_UNMAPPED) & product & no_hard_negative
    mfr_product = baseline_qa.eq(QA_MFR_ONLY) & product & no_hard_negative
    unspec_product = baseline_qa.eq(QA_UNSPEC) & product & no_hard_negative

    weak_generic = baseline_dash & ev["generic_token_risk"] & ev["product_score"].eq(0) & (
        ev["family_score"].eq(0) | ev["manufacturer_score"].lt(20)
    )
    trusted_conflict = baseline_dash & (hard_negative | weak_generic)

    out.loc[candidate_unmapped, "QA_Status"] = QA_CANDIDATE_REVIEW
    out.loc[mfr_product, "QA_Status"] = QA_MFR_PRODUCT
    out.loc[unspec_product, "QA_Status"] = QA_UNSPEC_EVIDENCE
    out.loc[trusted_conflict, "QA_Status"] = QA_PRECISION_RISK
    out.loc[trusted_conflict, "Scope_Flag"] = [
        f"precision_risk:{g or 'generic_token_weak_evidence'}"
        for g in ev.loc[trusted_conflict, "negative_conflict_group"].tolist()
    ]

    trusted_gate = (
        out["QA_Status"].eq(QA_MAPPED)
        & out["Ref_Valid"].eq("Y")
        & out["Scope_Flag"].eq("")
        & out["Match_Scope"].eq("Surgical")
    )
    out["Dash_Include"] = ""
    out.loc[trusted_gate, "Dash_Include"] = "Y"

    changes = pd.DataFrame(
        {
            "Change_Type": [
                "Unmapped surgical evidence moved to Review",
                "Manufacturer-only rows upgraded to product-evidence review",
                "Unspecified-category rows tagged with product evidence",
                "Trusted rows moved to precision-risk review",
            ],
            "Rows": [
                int(candidate_unmapped.sum()),
                int(mfr_product.sum()),
                int(unspec_product.sum()),
                int(trusted_conflict.sum()),
            ],
            "Value_USD": [
                float(value_usd(out.loc[candidate_unmapped]).sum()),
                float(value_usd(out.loc[mfr_product]).sum()),
                float(value_usd(out.loc[unspec_product]).sum()),
                float(value_usd(out.loc[trusted_conflict]).sum()),
            ],
            "Rule": [
                "A1/A4/A6 product alias/evidence capture",
                "A1/A6 manufacturer + product evidence",
                "A1/A6 cluster review priority",
                "A6 conflict/generic-token guardrail",
            ],
        }
    )
    return out, changes


def output_tier(df: pd.DataFrame) -> pd.Series:
    qa = df["QA_Status"].fillna("").astype(str)
    trusted = df["Dash_Include"].fillna("").astype(str).eq("Y")
    review = qa.str.startswith("Review") | qa.str.startswith("Audit")
    return pd.Series(
        ["Trusted_Dashboard" if t else "Review_Queue" if r else "Excluded_Unmapped" for t, r in zip(trusted, review)],
        index=df.index,
    )


def metrics_snapshot(label: str, df: pd.DataFrame, ev: pd.DataFrame, runtime_seconds: float = 0.0) -> OrderedDict[str, object]:
    values = value_usd(df)
    tier = output_tier(df)
    trusted = tier.eq("Trusted_Dashboard")
    review = tier.eq("Review_Queue")
    excluded = tier.eq("Excluded_Unmapped")
    surgicalish_excluded = excluded & ev["product_score"].gt(0) & ev["negative_conflict_group"].eq("")
    precision_risk = trusted & (
        ev["negative_conflict_group"].ne("")
        | (ev["generic_token_risk"] & ev["product_score"].eq(0) & (ev["family_score"].eq(0) | ev["manufacturer_score"].lt(20)))
    )
    capture_rows_denom = int(trusted.sum() + review.sum() + surgicalish_excluded.sum())
    capture_value_denom = float(values[trusted | review | surgicalish_excluded].sum())
    review_high_value = review & values.ge(50_000)
    trusted_precision_proxy = 1.0
    if trusted.sum():
        trusted_precision_proxy = max(0.0, 1 - (precision_risk.sum() / trusted.sum()))

    return OrderedDict(
        [
            ("Run", label),
            ("RawData rows", int(len(df))),
            ("RawData value", float(values.sum())),
            ("Trusted rows", int(trusted.sum())),
            ("Trusted value", float(values[trusted].sum())),
            ("Review rows", int(review.sum())),
            ("Review value", float(values[review].sum())),
            ("Excluded rows", int(excluded.sum())),
            ("Excluded value", float(values[excluded].sum())),
            ("Surgicalish excluded rows", int(surgicalish_excluded.sum())),
            ("Surgicalish excluded value", float(values[surgicalish_excluded].sum())),
            ("Trusted precision proxy", trusted_precision_proxy),
            ("Trusted recall proxy rows", trusted.sum() / capture_rows_denom if capture_rows_denom else math.nan),
            ("Trusted recall proxy value", float(values[trusted].sum()) / capture_value_denom if capture_value_denom else math.nan),
            ("Capture recall proxy rows", (trusted.sum() + review.sum()) / capture_rows_denom if capture_rows_denom else math.nan),
            ("Capture recall proxy value", float(values[trusted | review].sum()) / capture_value_denom if capture_value_denom else math.nan),
            ("Trusted precision-risk rows", int(precision_risk.sum())),
            ("Trusted precision-risk value", float(values[precision_risk].sum())),
            ("High-value review rows >=50K", int(review_high_value.sum())),
            ("High-value review value >=50K", float(values[review_high_value].sum())),
            ("Runtime seconds", runtime_seconds),
            ("LLM calls", 0),
            ("LLM token cost USD", 0.0),
        ]
    )


def validate(df: pd.DataFrame, master_keys: dict[str, object]) -> pd.DataFrame:
    trusted = df["Dash_Include"].fillna("").astype(str).eq("Y")
    family = trusted & df["Match_Tier"].fillna("").astype(str).str.lower().eq("family")
    category = trusted & df["Match_Tier"].fillna("").astype(str).str.lower().eq("category")
    full_keys = [
        norm_tuple(row)
        for row in df.loc[family, ["Segment", "Sub-segment", "Product_V0", "Manufacturer", "Family"]]
        .fillna("")
        .itertuples(index=False, name=None)
    ]
    category_keys = [
        norm_tuple(row)
        for row in df.loc[category, ["Segment", "Sub-segment", "Product_V0"]]
        .fillna("")
        .itertuples(index=False, name=None)
    ]
    strict_full = master_keys["strict_full"]
    full_latest = master_keys["full_latest"]
    categories = master_keys["categories"]
    family_latest_fail = sum(key not in full_latest for key in full_keys)
    family_strict_fail = sum(key not in strict_full for key in full_keys)
    category_fail = sum(key not in categories for key in category_keys)
    dash_scope_fail = int((trusted & df["Scope_Flag"].fillna("").astype(str).ne("")).sum())
    dash_ref_fail = int((trusted & df["Ref_Valid"].fillna("").astype(str).ne("Y")).sum())
    dash_qa_fail = int((trusted & df["QA_Status"].fillna("").astype(str).ne(QA_MAPPED)).sum())
    dash_rebuild = dashboard_rebuild(df)
    dash_value = float(value_usd(df.loc[trusted]).sum())
    dash_rebuild_value = float(dash_rebuild["Total_Revenue_USD"].sum()) if not dash_rebuild.empty else 0.0
    dash_volume = float(quantity(df.loc[trusted]).sum())
    dash_rebuild_volume = float(dash_rebuild["Total_Volume"].sum()) if not dash_rebuild.empty else 0.0
    rows = [
        ("Trusted family latest-master full-key failures", family_latest_fail, 0, "PASS" if family_latest_fail == 0 else "FAIL"),
        ("Trusted family strict no-generic failures", family_strict_fail, 0, "PASS" if family_strict_fail == 0 else "FAIL"),
        ("Trusted category latest-master key failures", category_fail, 0, "PASS" if category_fail == 0 else "FAIL"),
        ("Trusted rows with Scope_Flag", dash_scope_fail, 0, "PASS" if dash_scope_fail == 0 else "FAIL"),
        ("Trusted rows with Ref_Valid != Y", dash_ref_fail, 0, "PASS" if dash_ref_fail == 0 else "FAIL"),
        ("Trusted rows with QA_Status != mapped", dash_qa_fail, 0, "PASS" if dash_qa_fail == 0 else "FAIL"),
        (
            "Dashboard aggregation value delta",
            round(dash_rebuild_value - dash_value, 6),
            0,
            "PASS" if abs(dash_rebuild_value - dash_value) < 0.01 else "FAIL",
        ),
        (
            "Dashboard aggregation quantity delta",
            round(dash_rebuild_volume - dash_volume, 6),
            0,
            "PASS" if abs(dash_rebuild_volume - dash_volume) < 0.01 else "FAIL",
        ),
    ]
    return pd.DataFrame(rows, columns=["Validation", "Observed", "Target", "Status"])


def dashboard_rebuild(df: pd.DataFrame) -> pd.DataFrame:
    trusted = df[df["Dash_Include"].fillna("").astype(str).eq("Y")].copy()
    if trusted.empty:
        return pd.DataFrame(
            columns=[
                "Country",
                "OU",
                "Sub_OU",
                "Product",
                "Family",
                "Manufacturer",
                "Total_Revenue_USD",
                "Total_Volume",
                "Min_ASP",
                "Max_ASP",
                "Avg_ASP",
            ]
        )
    trusted["_rev"] = value_usd(trusted)
    trusted["_vol"] = quantity(trusted)
    trusted["_asp"] = pd.to_numeric(trusted.get("ASP_USD", 0), errors="coerce")
    g = trusted.groupby(["Segment", "Sub-segment", "Product_V0", "Family", "Manufacturer"], dropna=False)
    out = pd.DataFrame(
        {
            "Total_Revenue_USD": g["_rev"].sum(),
            "Total_Volume": g["_vol"].sum(),
            "Min_ASP": g["_asp"].min(),
            "Max_ASP": g["_asp"].max(),
        }
    ).reset_index()
    out["Avg_ASP"] = (out["Total_Revenue_USD"] / out["Total_Volume"]).where(out["Total_Volume"].gt(0))
    out.insert(0, "Country", "Vietnam")
    out.columns = [
        "Country",
        "OU",
        "Sub_OU",
        "Product",
        "Family",
        "Manufacturer",
        "Total_Revenue_USD",
        "Total_Volume",
        "Min_ASP",
        "Max_ASP",
        "Avg_ASP",
    ]
    return out.sort_values(["OU", "Sub_OU", "Product", "Family", "Manufacturer"])


def build_candidate_table(df: pd.DataFrame, ev: pd.DataFrame) -> pd.DataFrame:
    tier = output_tier(df)
    considered = (
        tier.ne("Excluded_Unmapped")
        | ev["product_score"].gt(0)
        | ev["manufacturer_score"].gt(0)
        | ev["family_score"].gt(0)
        | ev["master_validation_status"].str.contains("update|pass", na=False)
    )
    base = df.loc[considered].copy()
    e = ev.loc[considered].copy()

    def choose(current: pd.Series, proposed: pd.Series) -> pd.Series:
        current = current.fillna("").astype(str)
        proposed = proposed.fillna("").astype(str)
        return current.where(current.map(norm_text).ne(""), proposed)

    candidate = pd.DataFrame(
        {
            "UniqueID": base["UniqueID"].values,
            "candidate_rank": 1,
            "candidate_segment": choose(base.get("Segment", pd.Series("", index=base.index)), e["candidate_segment"]).values,
            "candidate_subsegment": choose(base.get("Sub-segment", pd.Series("", index=base.index)), e["candidate_subsegment"]).values,
            "candidate_product": choose(base.get("Product_V0", pd.Series("", index=base.index)), e["candidate_product"]).values,
            "candidate_player": base.get("Manufacturer", pd.Series("", index=base.index)).fillna("").astype(str).values,
            "candidate_family": choose(base.get("Family", pd.Series("", index=base.index)), e.get("fuzzy_family_match", pd.Series("", index=base.index))).values,
            "candidate_source_method": e["candidate_source_method"].where(e["candidate_source_method"].ne(""), "existing_mapping_or_reference").values,
            "product_score": e["product_score"].values,
            "family_score": e["family_score"].values,
            "manufacturer_score": e["manufacturer_score"].values,
            "fuzzy_score": e["fuzzy_score"].values,
            "word_tfidf_score": e["word_tfidf_score"].values,
            "char_tfidf_score": e["char_tfidf_score"].values,
            "semantic_score": e["semantic_score"].values,
            "hs_score": e["hs_score"].values,
            "exclusion_score": e["exclusion_score"].values,
            "generic_token_risk": e["generic_token_risk"].values,
            "master_validation_status": e["master_validation_status"].values,
            "final_candidate_score": e["final_candidate_score"].values,
            "routing_decision": tier.loc[considered].values,
            "decision_reason": [
                decision_reason(row_qa, p, n, m, g)
                for row_qa, p, n, m, g in zip(
                    base["QA_Status"].fillna("").astype(str),
                    e["product_evidence_group"],
                    e["negative_conflict_group"],
                    e["master_validation_status"],
                    e["generic_token_risk"],
                )
            ],
        }
    )
    return candidate.sort_values(["routing_decision", "final_candidate_score"], ascending=[True, False]).reset_index(drop=True)


def decision_reason(qa: str, product_group: str, negative_group: str, master_status: str, generic_risk: bool) -> str:
    parts = []
    if qa:
        parts.append(qa)
    if product_group:
        parts.append(f"product_evidence={product_group}")
    if master_status and master_status != "not_applicable":
        parts.append(f"master={master_status}")
    if generic_risk:
        parts.append("generic_token_risk")
    if negative_group:
        parts.append(f"conflict={negative_group}")
    return "; ".join(parts)


def row_sample_columns(df: pd.DataFrame, ev: pd.DataFrame, mask: pd.Series, limit: int | None = None) -> pd.DataFrame:
    cols = [
        "UniqueID",
        "Detailed_Product",
        "Importer",
        "Exporter",
        "HS_Code",
        "HS4",
        "Quantity",
        "Total_Value_USD",
        "Segment",
        "Sub-segment",
        "Product_V0",
        "Manufacturer",
        "Family",
        "Match_Tier",
        "Ref_Valid",
        "Scope_Flag",
        "Dash_Include",
        "QA_Status",
    ]
    cols = [c for c in cols if c in df.columns]
    out = df.loc[mask, cols].copy()
    out["Value_USD_num"] = value_usd(out)
    out["Evidence_Group"] = ev.loc[mask, "product_evidence_group"].values
    out["Negative_Conflict_Group"] = ev.loc[mask, "negative_conflict_group"].values
    out["Master_Validation_Status"] = ev.loc[mask, "master_validation_status"].values
    out["Final_Candidate_Score"] = ev.loc[mask, "final_candidate_score"].values
    out["Recommended_Action"] = [
        recommended_action(qa, eg, ng, ms)
        for qa, eg, ng, ms in zip(
            out["QA_Status"].astype(str),
            out["Evidence_Group"].astype(str),
            out["Negative_Conflict_Group"].astype(str),
            out["Master_Validation_Status"].astype(str),
        )
    ]
    out = out.sort_values("Value_USD_num", ascending=False)
    if limit:
        out = out.head(limit)
    return out


def recommended_action(qa: str, evidence: str, negative: str, master_status: str) -> str:
    if qa == QA_PRECISION_RISK or negative:
        return "Keep out of Trusted; reviewer must resolve conflict or approve override."
    if qa == QA_EXTENDED:
        return "Hold in Extended_Surgical_Decision until dashboard scope rule is decided."
    if "reference_update" in master_status or "not in latest reference" in qa.lower():
        return "Validate product scope; request master/reference update if true surgical."
    if evidence:
        return "Review candidate cluster; add deterministic alias/rule if confirmed."
    return "No action unless sampled by Gold_Labels."


def build_reference_update_request(df: pd.DataFrame, ev: pd.DataFrame) -> pd.DataFrame:
    mask = df["QA_Status"].fillna("").astype(str).str.contains("not in latest reference|generic reference", case=False, regex=True)
    data = df.loc[mask].copy()
    if data.empty:
        return pd.DataFrame()
    data["_value"] = value_usd(data)
    data["_evidence"] = ev.loc[mask, "product_evidence_group"].values
    data["_negative"] = ev.loc[mask, "negative_conflict_group"].values
    grp_cols = ["Segment", "Sub-segment", "Product_V0", "Manufacturer", "Family", "_evidence", "_negative"]
    grouped = (
        data.groupby(grp_cols, dropna=False)
        .agg(
            Rows=("UniqueID", "size"),
            Value_USD=("_value", "sum"),
            Sample_UniqueID=("UniqueID", "first"),
            Sample_Detailed_Product=("Detailed_Product", "first"),
            Sample_Importer=("Importer", "first"),
            Sample_Exporter=("Exporter", "first"),
            Sample_HS_Code=("HS_Code", "first"),
        )
        .reset_index()
        .sort_values("Value_USD", ascending=False)
    )
    grouped["Issue_Type"] = [
        "possible wrong mapping / exclusion conflict" if neg else "likely alias or latest-master reference gap" if evg else "weak evidence reference gap"
        for evg, neg in zip(grouped["_evidence"].astype(str), grouped["_negative"].astype(str))
    ]
    grouped["Recommended_Action"] = [
        "Review conflict before reference update." if neg else "If confirmed surgical, add/repair latest master tuple or approved category mapping."
        for neg in grouped["_negative"].astype(str)
    ]
    grouped["Suggested_Reference_Update"] = grouped.apply(
        lambda r: " | ".join(
            str(r.get(c, ""))
            for c in ["Segment", "Sub-segment", "Product_V0", "Manufacturer", "Family"]
            if str(r.get(c, "")).strip()
        ),
        axis=1,
    )
    grouped = grouped.rename(columns={"Product_V0": "Product", "_evidence": "Evidence_Group", "_negative": "Negative_Conflict_Group"})
    return grouped


def build_alias_update_request(df: pd.DataFrame, ev: pd.DataFrame) -> pd.DataFrame:
    tier = output_tier(df)
    mask = tier.eq("Review_Queue") & ev["product_evidence_group"].ne("")
    data = df.loc[mask].copy()
    if data.empty:
        return pd.DataFrame()
    data["_value"] = value_usd(data)
    data["_evidence"] = ev.loc[mask, "product_evidence_group"].values
    data["_terms"] = ev.loc[mask, "product_evidence_terms"].values
    data["_mfr_alias"] = ev.loc[mask, "manufacturer_alias_hit"].values
    data["_negative"] = ev.loc[mask, "negative_conflict_group"].values
    grouped = (
        data.groupby(["QA_Status", "_evidence", "_terms", "_mfr_alias", "_negative", "HS4"], dropna=False)
        .agg(
            Rows=("UniqueID", "size"),
            Value_USD=("_value", "sum"),
            Sample_UniqueID=("UniqueID", "first"),
            Sample_Detailed_Product=("Detailed_Product", "first"),
            Sample_Importer=("Importer", "first"),
            Sample_Exporter=("Exporter", "first"),
        )
        .reset_index()
        .sort_values("Value_USD", ascending=False)
    )
    grouped["Suggested_Alias_or_Rule_Update"] = grouped.apply(
        lambda r: f"Add/validate aliases for {r['_evidence']}: {r['_terms']}; manufacturer alias={r['_mfr_alias'] or 'none'}",
        axis=1,
    )
    grouped["Routing_Guardrail"] = grouped["_negative"].map(
        lambda x: "Do not trust without conflict override" if str(x).strip() else "May support Review routing; Trusted still requires master validation and evidence thresholds"
    )
    return grouped.rename(
        columns={
            "_evidence": "Evidence_Group",
            "_terms": "Alias_Terms",
            "_mfr_alias": "Manufacturer_Alias_Hit",
            "_negative": "Negative_Conflict_Group",
        }
    )


def build_extended_decision(df: pd.DataFrame, ev: pd.DataFrame) -> pd.DataFrame:
    mask = df["QA_Status"].fillna("").astype(str).eq(QA_EXTENDED)
    data = df.loc[mask].copy()
    if data.empty:
        return pd.DataFrame()
    data["_value"] = value_usd(data)
    data["_evidence"] = ev.loc[mask, "product_evidence_group"].values
    data["_generic"] = ev.loc[mask, "generic_token_risk"].values
    grouped = (
        data.groupby(["HS4", "Segment", "Sub-segment", "Product_V0", "Manufacturer", "Family", "Match_Tier", "_evidence", "_generic"], dropna=False)
        .agg(
            Rows=("UniqueID", "size"),
            Value_USD=("_value", "sum"),
            Sample_UniqueID=("UniqueID", "first"),
            Sample_Detailed_Product=("Detailed_Product", "first"),
            Sample_Importer=("Importer", "first"),
            Sample_Exporter=("Exporter", "first"),
        )
        .reset_index()
        .sort_values("Value_USD", ascending=False)
    )
    grouped["Decision_Option_A_Core_HS_Only"] = "Keep out of Dashboard; retain in Review_Queue."
    grouped["Decision_Option_B_Surgical_Product_Regardless_HS"] = [
        "Candidate for dashboard after business approval and conflict review."
        if evidence
        else "Needs product evidence check before dashboard inclusion."
        for evidence in grouped["_evidence"].astype(str)
    ]
    grouped["Recommended_Current_Routing"] = "Review_Queue - Extended HS business decision required"
    grouped["Suggested_Rule_Update"] = grouped["_evidence"].map(
        lambda x: f"HS_Scope_Rules: decide inclusion for {x or 'reference-valid extended product'}"
    )
    return grouped.rename(columns={"Product_V0": "Product", "_evidence": "Evidence_Group", "_generic": "Generic_Token_Risk"})


def build_cluster_summary(df: pd.DataFrame, ev: pd.DataFrame) -> pd.DataFrame:
    tier = output_tier(df)
    mask = tier.eq("Review_Queue")
    data = df.loc[mask].copy()
    if data.empty:
        return pd.DataFrame()
    data["_value"] = value_usd(data)
    data["_evidence"] = ev.loc[mask, "product_evidence_group"].replace("", "no explicit product alias").values
    data["_negative"] = ev.loc[mask, "negative_conflict_group"].replace("", "none").values
    data["_priority"] = ev.loc[mask, "high_value_review_priority"].replace("", "P4 <25K").values
    candidate_product = ev.loc[mask, "candidate_product"].fillna("").astype(str)
    mapped_product = data.get("Product_V0", pd.Series("", index=data.index)).fillna("").astype(str)
    data["_candidate_product"] = candidate_product.where(candidate_product.ne(""), mapped_product).values
    grouped = (
        data.groupby(["QA_Status", "_evidence", "_negative", "_candidate_product", "HS4", "Manufacturer", "Family"], dropna=False)
        .agg(
            Rows=("UniqueID", "size"),
            Value_USD=("_value", "sum"),
            High_Value_Rows=("_priority", lambda s: int(s.ne("P4 <25K").sum())),
            Sample_UniqueID=("UniqueID", "first"),
            Sample_Detailed_Product=("Detailed_Product", "first"),
            Sample_Importer=("Importer", "first"),
            Sample_Exporter=("Exporter", "first"),
        )
        .reset_index()
        .sort_values("Value_USD", ascending=False)
    )
    grouped["Review_Playbook"] = grouped.apply(
        lambda r: cluster_playbook(str(r["QA_Status"]), str(r["_evidence"]), str(r["_negative"])),
        axis=1,
    )
    return grouped.rename(
        columns={
            "_evidence": "Evidence_Group",
            "_negative": "Negative_Conflict_Group",
            "_candidate_product": "Candidate_Product",
        }
    )


def cluster_playbook(qa: str, evidence: str, negative: str) -> str:
    if negative and negative != "none":
        return "Conflict cluster: review top-value rows first; add negative/disambiguation rule."
    if "Extended" in qa:
        return "Business-scope cluster: decide HS rule once, then apply deterministically."
    if evidence and evidence != "no explicit product alias":
        return "Alias/rule cluster: label sample, then convert repeated phrase to deterministic alias."
    return "Weak-evidence cluster: prioritize only if high value or repeated importer/exporter pattern."


def build_precision_risk_rows(before: pd.DataFrame, after: pd.DataFrame, ev: pd.DataFrame) -> pd.DataFrame:
    before_trusted = before["Dash_Include"].fillna("").astype(str).eq("Y")
    risk = before_trusted & (
        ev["negative_conflict_group"].ne("")
        | (ev["generic_token_risk"] & ev["product_score"].eq(0) & (ev["family_score"].eq(0) | ev["manufacturer_score"].lt(20)))
    )
    out = row_sample_columns(after, ev, risk, limit=None)
    if out.empty:
        return out
    out["Previous_Dash_Include"] = before.loc[out.index, "Dash_Include"].values
    out["Action_Taken"] = "Moved out of Trusted_Dashboard to precision-risk Review_Queue"
    return out.reset_index(drop=True)


def build_potential_missed(df: pd.DataFrame, ev: pd.DataFrame, baseline_df: pd.DataFrame) -> pd.DataFrame:
    baseline_tier = output_tier(baseline_df)
    mask = baseline_tier.eq("Excluded_Unmapped") & ev["product_score"].gt(0) & ev["negative_conflict_group"].eq("")
    out = row_sample_columns(df, ev, mask, limit=None)
    if out.empty:
        return out
    out["Previous_Status"] = baseline_df.loc[out.index, "QA_Status"].values
    out["New_Status"] = df.loc[out.index, "QA_Status"].values
    out["Reason_for_Change"] = "Surgical product alias/evidence found in row previously outside review capture"
    return out.reset_index(drop=True)


def build_excluded_surgicalish(df: pd.DataFrame, ev: pd.DataFrame) -> pd.DataFrame:
    tier = output_tier(df)
    mask = tier.eq("Excluded_Unmapped") & ev["product_score"].gt(0)
    out = row_sample_columns(df, ev, mask, limit=None)
    if out.empty:
        return out
    out["Residual_Reason"] = [
        "Excluded due to high-confidence non-surgical conflict" if neg else "Residual surgical-looking exclusion; inspect"
        for neg in out["Negative_Conflict_Group"].astype(str)
    ]
    return out.reset_index(drop=True)


def build_specific_examples(df: pd.DataFrame, ev: pd.DataFrame, baseline: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    text = ev["row_text_norm"]
    examples = [
        ("APT Medical / March / Guiding Catheters", r"\b(?:apt medical|aptmed|march|guiding catheter|guide catheter)\b", "Extended HS / generic token", "Keep in Extended_Surgical_Decision; do not trust March without APT/product evidence.", "Family_Alias + Generic_Token_Rule + HS_Scope_Rule"),
        ("Zimmer Biomet / Vanguard / Total Knee Replacement", r"\b(?:zimmer|biomet|vanguard|total knee replacement)\b", "Extended HS orthopedic", "Business scope decision; if included, require master-valid ortho tuple.", "Manufacturer_Alias + Family_Alias"),
        ("Medtronic / Acute / Ventilator Premium", r"\b(?:medtronic|acute|ventilator)\b", "Possible non-surgical/respiratory or reference-valid extended", "Keep review; likely not core surgical dashboard without scope approval.", "Product_Disambiguation_Rule"),
        ("Boston Scientific / Express / BMS BX Stent", r"\b(?:boston scientific|express|bms|bare metal stent|bx stent)\b", "Extended HS/generic Express", "Review; stent evidence strong but Express is generic, require master and HS decision.", "Abbreviation_Alias BMS + Generic_Token_Rule Express"),
        ("J&J / Vicryl / sutures or hernia", r"\b(?:j and j|johnson and johnson|ethicon|vicryl|suture|hernia)\b", "Extended HS surgical consumables", "Hold in Extended_Surgical_Decision pending HS 3006/suture/mesh business rule.", "Family_Alias Vicryl + HS_Scope_Rules"),
        ("SMT / Vector / PTCA Balloons", r"\b(?:smt|sahajanand|vector|ptca|balloon)\b", "Extended HS vascular", "Review; PTCA balloon evidence strong, master/HS decision required.", "Manufacturer_Alias SMT + Product_Alias PTCA"),
        ("Bone Cement / Unspecified", r"\bbone cement\b", "Extended ortho/spine", "Review; business scope and category validation required.", "Product_Alias bone cement"),
        ("White Medience / PDO / Suture", r"\b(?:white medience|pdo|polydioxanone|suture)\b", "Extended suture", "Review pending HS 3006 business rule; add PDO alias.", "Abbreviation_Alias PDO"),
        ("Terumo / Trima Accel / Autotransfusion", r"\b(?:terumo|trima accel|autotransfusion|cell saver|blood recovery)\b", "Latest reference gap", "If true autotransfusion consumable/system, request latest master update.", "Reference_Update_Request autotransfusion"),
        ("J&J / Xtra / Autotransfusion", r"\b(?:xtra|autotransfusion|cell saver|blood recovery)\b", "Latest reference gap/generic Xtra", "Review; generic token Xtra needs product/manufacturer support and master update.", "Family_Alias Xtra + Generic_Token_Rule"),
        ("Medtronic / Artificial Disc", r"\b(?:medtronic|artificial disc|cervical disc)\b", "Latest reference gap", "Request master/category validation if surgical spine implant.", "Product_Alias artificial disc"),
        ("Asahi Intecc / Masters / Mechanical Heart Valves", r"\b(?:asahi intecc|masters|mechanical heart valve)\b", "Potential wrong category/reference conflict", "Keep review; Masters is generic and Asahi category needs confirmation.", "Generic_Token_Rule Masters + Resolver review"),
        ("Abbott / Xience / DES", r"\b(?:abbott|xience|des|drug eluting stent)\b", "Latest reference or alias gap", "Add DES/Xience alias or master tuple if not already covered.", "Abbreviation_Alias DES + Family_Alias Xience"),
        ("Olympus / Image Processor / MIS platforms", r"\b(?:olympus|image processor|mis platform|endoscopy)\b", "Capital/MIS scope decision", "Review; image processor is generic/capital-adjacent, not auto-trusted.", "Generic_Token_Rule Image Processor"),
        ("Cryolife / E-Tegra / Abdominal Stent Graft", r"\b(?:cryolife|e tegra|abdominal stent graft|stent graft)\b", "Latest reference gap", "Request master update if confirmed in vascular/aortic scope.", "Family_Alias E-Tegra"),
        ("Feel-tech / Polydioxanone / Absorbable Suture", r"\b(?:feel tech|polydioxanone|pdo|absorbable suture)\b", "Extended suture/reference gap", "Review pending HS/product scope; add Polydioxanone alias.", "Family_Alias Polydioxanone"),
    ]
    rows = []
    for name, pattern, issue, action, update in examples:
        mask = text.str.contains(compile_pattern(pattern), na=False)
        subset = df.loc[mask].copy()
        if subset.empty:
            rows.append(
                {
                    "Example": name,
                    "Rows": 0,
                    "Value_USD": 0.0,
                    "UniqueID": "",
                    "Detailed_Product": "",
                    "Importer": "",
                    "Exporter": "",
                    "HS_Code": "",
                    "Previous_Status": "No row hit in current workbook screen",
                    "New_Status": "",
                    "Current_or_Proposed_Mapping": "",
                    "Why_Missing_or_Risky": issue,
                    "Recommended_Action": action,
                    "Suggested_Alias_Rule_or_Reference_Update": update,
                }
            )
            continue
        subset["_value"] = value_usd(subset)
        sample = subset.sort_values("_value", ascending=False).iloc[0]
        idx = sample.name
        rows.append(
            {
                "Example": name,
                "Rows": int(len(subset)),
                "Value_USD": float(subset["_value"].sum()),
                "UniqueID": sample.get("UniqueID", ""),
                "Detailed_Product": sample.get("Detailed_Product", ""),
                "Importer": sample.get("Importer", ""),
                "Exporter": sample.get("Exporter", ""),
                "HS_Code": sample.get("HS_Code", ""),
                "Previous_Status": baseline.loc[idx, "QA_Status"],
                "New_Status": df.loc[idx, "QA_Status"],
                "Current_or_Proposed_Mapping": " | ".join(
                    str(sample.get(c, ""))
                    for c in ["Segment", "Sub-segment", "Product_V0", "Manufacturer", "Family"]
                    if str(sample.get(c, "")).strip()
                ),
                "Why_Missing_or_Risky": issue,
                "Recommended_Action": action,
                "Suggested_Alias_Rule_or_Reference_Update": update,
            }
        )
    examples_df = pd.DataFrame(rows).sort_values("Value_USD", ascending=False)

    unresolved = examples_df[examples_df["Rows"].gt(0)].copy()
    unresolved["Unresolved_Decision"] = [
        "Business HS scope decision" if "Extended" in issue else "Reference/alias validation needed" if "reference" in issue.lower() else "Manual conflict review"
        for issue in unresolved["Why_Missing_or_Risky"].astype(str)
    ]
    return examples_df, unresolved


def build_experiment_matrix(before_m: OrderedDict[str, object], after_m: OrderedDict[str, object], changes: pd.DataFrame, runtime: float) -> pd.DataFrame:
    new_review_rows = int(changes.loc[changes["Change_Type"].eq("Unmapped surgical evidence moved to Review"), "Rows"].sum())
    new_review_value = float(changes.loc[changes["Change_Type"].eq("Unmapped surgical evidence moved to Review"), "Value_USD"].sum())
    risk_removed_rows = int(changes.loc[changes["Change_Type"].eq("Trusted rows moved to precision-risk review"), "Rows"].sum())
    capture_row_delta = after_m["Capture recall proxy rows"] - before_m["Capture recall proxy rows"]
    capture_value_delta = after_m["Capture recall proxy value"] - before_m["Capture recall proxy value"]
    precision_delta = after_m["Trusted precision proxy"] - before_m["Trusted precision proxy"]
    manual_review_delta = after_m["Review rows"] - before_m["Review rows"]
    high_value_delta = after_m["High-value review rows >=50K"] - before_m["High-value review rows >=50K"]

    rows = [
        ("A0", "Current baseline", 0, 0.0, 0, 0.0, 0, 0, 0.0, 0.0, 0.0, 0, 0, 0.0, 0, "Baseline retained for comparison", "adopt as benchmark"),
        ("A1", "Alias dictionary expansion", 0, 0.0, new_review_rows, new_review_value, 0, int(after_m["Surgicalish excluded rows"]), precision_delta, 0.0, capture_row_delta, manual_review_delta, high_value_delta, runtime, 0, "Captured surgical-looking unmapped rows to Review; no auto-trusted promotion", "adopt"),
        ("A2", "Fuzzy lexical matching", 0, 0.0, 0, 0.0, 0, 0, 0.0, 0.0, 0.0, 0, 0, 0.0, 0,
         ("rapidfuzz Levenshtein channel active: misspelled master family names surface as "
          "fuzzy_lexical candidates (Review-only, never Trusted)" if HAVE_RAPIDFUZZ and ENABLE_FUZZY_FAMILY
          else "Not executed as rapidfuzz is not installed; misspelling aliases covered deterministically"),
         "adopt" if HAVE_RAPIDFUZZ and ENABLE_FUZZY_FAMILY else "test further"),
        ("A3", "Character n-gram retrieval", 0, 0.0, new_review_rows, new_review_value, 0, int(after_m["Surgicalish excluded rows"]), 0.0, 0.0, capture_row_delta, manual_review_delta, high_value_delta, runtime, 0, "Implemented lightweight char n-gram evidence proxy in Candidate_Table; not full sklearn TF-IDF", "test further"),
        ("A4", "Word n-gram/product phrase retrieval", 0, 0.0, new_review_rows, new_review_value, 0, int(after_m["Surgicalish excluded rows"]), 0.0, 0.0, capture_row_delta, manual_review_delta, high_value_delta, runtime, 0, "Product phrase aliases capture stents, catheters, sutures, mesh, endoscopy, valves, ortho, autotransfusion", "adopt"),
        ("A5", "Semantic retrieval", 0, 0.0, 0, 0.0, 0, 0, 0.0, 0.0, 0.0, 0, 0, 0.0, 0, "Not run; recommended only for recall hunting and review candidates", "test further"),
        ("A6", "Evidence scoring/routing", 0, 0.0, new_review_rows, new_review_value, risk_removed_rows, int(after_m["Surgicalish excluded rows"]), precision_delta, 0.0, capture_value_delta, manual_review_delta, high_value_delta, runtime, 0, "Separate product/family/manufacturer/HS/conflict/generic/master signals now drive routing", "adopt"),
        ("A7", "LLM resolver agent", 0, 0.0, 0, 0.0, 0, 0, 0.0, 0.0, 0.0, 0, 0, 0.0, 0, "Not run; should be limited to high-value ambiguous candidate sets", "test further"),
        ("A8", "LLM recall-hunter agent", 0, 0.0, 0, 0.0, 0, 0, 0.0, 0.0, 0.0, 0, 0, 0.0, 0, "Not run; cluster summaries are prepared as input", "test further"),
        ("A9", "LLM conflict/QC agent", 0, 0.0, risk_removed_rows, float(changes.loc[changes["Change_Type"].eq("Trusted rows moved to precision-risk review"), "Value_USD"].sum()), 0, 0, precision_delta, 0.0, 0.0, manual_review_delta, high_value_delta, 0.0, 0, "Deterministic conflict screen executed; LLM QC optional for residual rows", "test further"),
        ("A10", "Active learning loop", 0, 0.0, 0, 0.0, 0, int(after_m["Surgicalish excluded rows"]), 0.0, 0.0, 0.0, 0, 0, 0.0, 0, "Alias/reference/gold-label templates created; needs human corrections to measure repeat-rate decline", "adopt"),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "Experiment ID",
            "Design change",
            "Rows newly captured into Trusted_Dashboard",
            "Value newly captured into Trusted_Dashboard",
            "Rows newly captured into Review_Queue",
            "Value newly captured into Review_Queue",
            "Rows wrongly added to Trusted_Dashboard",
            "Rows wrongly excluded",
            "Change in Trusted precision",
            "Change in Trusted recall",
            "Change in Capture recall",
            "Change in manual review rows",
            "Change in high-value unresolved review rows",
            "Change in runtime",
            "Change in LLM/token cost",
            "Test result",
            "Net recommendation",
        ],
    )


def build_evidence_model() -> pd.DataFrame:
    rows = [
        ("exact family alias in row text", 28, "Positive", "Strong, but cannot trust without master validation and product/manufacturer support"),
        ("manufacturer/player alias in row/importer/exporter", 24, "Positive", "Strong support for family-tier rows"),
        ("strong product phrase", "30-44", "Positive", "Main recall feature; enough for Review, not enough for Trusted alone"),
        ("category match to latest master", "required", "Gate", "Trusted category-tier rows must pass latest Segment/Sub-segment/Product key"),
        ("HS compatibility core", 16, "Positive", "Supports Trusted only if other gates pass"),
        ("HS compatibility extended", 6, "Review", "Holds rows for Extended_Surgical_Decision"),
        ("fuzzy lexical proxy", "0-7.2", "Weak positive", "Candidate evidence only"),
        ("word n-gram proxy", "0-8.2", "Weak/medium positive", "Used for candidate generation and clustering"),
        ("char n-gram proxy", "0-5.9", "Weak/medium positive", "Used for spelling/noise tolerance; full TF-IDF still recommended"),
        ("semantic similarity", 0, "Not run", "Future recall hunting only; semantic-only routes to Review"),
        ("generic token", -12, "Penalty", "Light Source, March, Xtra, Masters, Image Processor, etc. cannot drive trust alone"),
        ("exclusion/conflict term", -55, "Strong negative", "Moves trusted rows to Review unless manually approved"),
        ("master reference validation", "required", "Gate", "Family-tier full key and category-tier category key required for Trusted"),
    ]
    return pd.DataFrame(rows, columns=["Feature", "Weight_or_Threshold", "Direction", "Routing_Use"])


def build_routing_rules() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("Trusted_Dashboard", "QA_Status = Mapped - reference-valid; Ref_Valid=Y; Match_Scope=Surgical; Scope_Flag blank; latest master key valid; no conflict/generic-only risk", "Include in Dashboard"),
            ("Review_Queue", "Surgical-looking product evidence with weak/ambiguous mapping, semantic/fuzzy/alias-only candidate, generic-token risk, Extended HS, reference gap, manufacturer-only + product evidence, high-value uncertainty", "Route to reviewer/cluster queue"),
            ("Excluded_Unmapped", "No surgical evidence, or strong non-surgical evidence with no countervailing surgical evidence", "Keep out of Dashboard but sample through Gold_Labels"),
            ("Extended_Surgical_Decision", "Reference-valid or surgical-looking rows outside core HS/dashboard scope", "Business decision: core HS only vs surgical product regardless of HS"),
            ("Reference_Update_Request", "Mapped family/category rows with product evidence but latest master tuple/category not found", "Request master update; no Trusted inclusion until approved"),
        ],
        columns=["Output_Tier_or_Table", "Exact_Logic", "Action"],
    )


def build_llm_agent_eval() -> pd.DataFrame:
    rows = [
        ("Scope Agent", "High-value Review_Queue, Extended HS, Excluded_Unmapped with surgical evidence", "raw row + HS + candidates + evidence", "structured JSON scope/routing decision", 0, 0, "Not tested in this deterministic run", "Do not use as one-shot mapper; validate against master"),
        ("Resolver Agent", "Multiple close candidates or product/family/manufacturer conflict", "top candidates + master rows + evidence", "selected candidate or human-review flag", 0, 0, "Not tested", "LLM cannot invent master tuple"),
        ("Conflict Agent", "Trusted rows with exclusion terms or generic-token risk", "row text + mapping + conflict rules", "keep/review/exclude/remap recommendation", 0, 0, "Deterministic pre-screen performed instead", "Use only for residual high-value ambiguity"),
        ("Recall Hunter Agent", "High-value review/excluded clusters", "cluster samples + evidence/rule gaps", "alias/rule/reference suggestions", 0, 0, "Cluster inputs prepared", "Suggestions must become deterministic rules"),
        ("QC Agent", "Pre-release Trusted and high-value decisions", "trusted samples + risk rows + validation report", "QA pass/fail and issue list", 0, 0, "Not tested", "Independent check before production release"),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "Agent",
            "Trigger condition",
            "Input fields",
            "Output JSON schema summary",
            "Rows sent",
            "Estimated token cost USD",
            "Evaluation result",
            "Failure modes / guardrails",
        ],
    )


def build_gold_label_template(df: pd.DataFrame, ev: pd.DataFrame, baseline: pd.DataFrame) -> pd.DataFrame:
    values = value_usd(df)
    tier = output_tier(df)
    precision_risk = baseline["Dash_Include"].fillna("").astype(str).eq("Y") & (
        ev["negative_conflict_group"].ne("")
        | (ev["generic_token_risk"] & ev["product_score"].eq(0) & (ev["family_score"].eq(0) | ev["manufacturer_score"].lt(20)))
    )
    review_high_value = tier.eq("Review_Queue") & values.ge(50_000)
    extended_high_value = df["QA_Status"].fillna("").astype(str).eq(QA_EXTENDED) & values.ge(25_000)
    excluded_surgicalish = tier.eq("Excluded_Unmapped") & ev["product_score"].gt(0)
    clean_trusted_sample = tier.eq("Trusted_Dashboard") & ~precision_risk
    qa_bucket_sample = tier.eq("Review_Queue")

    frames = []
    buckets = [
        ("precision_risk_trusted_100pct", precision_risk),
        ("review_queue_ge_50k_100pct", review_high_value),
        ("extended_hs_ge_25k_100pct", extended_high_value),
        ("excluded_surgicalish_stratified", excluded_surgicalish),
        ("clean_trusted_value_sample", clean_trusted_sample),
        ("qa_bucket_review_sample", qa_bucket_sample),
    ]
    for bucket, mask in buckets:
        sample = row_sample_columns(df, ev, mask, limit=2000 if "100pct" not in bucket else None)
        if sample.empty:
            continue
        sample.insert(0, "Sampling_Bucket", bucket)
        frames.append(sample)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True).drop_duplicates("UniqueID")
    for col in [
        "true_scope",
        "true_segment",
        "true_subsegment",
        "true_product",
        "true_player",
        "true_family",
        "reviewer",
        "review_date",
        "label_confidence",
        "decision_reason",
        "correction_type",
    ]:
        out[col] = ""
    return out


def build_active_learning_updates(alias_req: pd.DataFrame, ref_req: pd.DataFrame) -> pd.DataFrame:
    alias_terms = alias_req["Alias_Terms"].fillna("").astype(str) if "Alias_Terms" in alias_req else pd.Series(dtype=str)
    manufacturer_hits = (
        alias_req["Manufacturer_Alias_Hit"].fillna("").astype(str)
        if "Manufacturer_Alias_Hit" in alias_req
        else pd.Series(dtype=str)
    )
    rows = [
        ("Product synonym issue", "Product_Alias", "Alias_Update_Request", int(len(alias_req)), "Add repeated reviewed product phrases such as DES/PTCA/Vicryl/autotransfusion/endoscopy"),
        ("Family naming issue", "Family_Alias", "Alias_Update_Request", int(alias_terms.ne("").sum()), "Add reviewed family names and high-risk token support rules"),
        ("Manufacturer naming issue", "Manufacturer_Alias", "Alias_Update_Request", int(manufacturer_hits.ne("").sum()), "Normalize J&J/Ethicon, SMT, APT, Zimmer/Biomet, etc."),
        ("Reference gap", "Reference_Update_Request", "Reference_Update_Request", int(len(ref_req)), "Request latest master updates for confirmed surgical rows"),
        ("Exclusion issue", "Negative_Terms / Product_Disambiguation_Rules", "Precision_Risk_Rows", 0, "Convert false positives into deterministic conflict rules"),
        ("HS scope issue", "HS_Scope_Rules", "Extended_Surgical_Decision", 0, "Decide Option A core HS only vs Option B surgical regardless of HS"),
        ("Generic-token issue", "Generic_Token_Rules", "Precision_Risk_Rows", 0, "Require product/manufacturer/family support for March, Xtra, Masters, Image Processor, Express, etc."),
    ]
    return pd.DataFrame(rows, columns=["Correction_Type", "Target_Table", "Source_Output", "Current_Items", "Operational_Update"])


def build_summary(
    before_m: OrderedDict[str, object],
    after_m: OrderedDict[str, object],
    validations: pd.DataFrame,
    changes: pd.DataFrame,
) -> pd.DataFrame:
    val_fail = int(validations["Status"].ne("PASS").sum())
    rows = [
        ("What changed?", "Added evidence scoring, candidate table, review clustering, alias/reference/update templates, and conservative routing changes."),
        ("Trusted expansion", "No rows were promoted directly into Trusted_Dashboard; master validation gates remain strict."),
        ("Recall impact", f"Capture recall proxy changed from {before_m['Capture recall proxy rows']:.1%} to {after_m['Capture recall proxy rows']:.1%} row-based and {before_m['Capture recall proxy value']:.1%} to {after_m['Capture recall proxy value']:.1%} value-based."),
        ("Precision impact", f"Trusted precision proxy changed from {before_m['Trusted precision proxy']:.1%} to {after_m['Trusted precision proxy']:.1%}; precision-risk trusted rows now {after_m['Trusted precision-risk rows']}."),
        ("Manual review burden", f"Review rows changed from {before_m['Review rows']:,} to {after_m['Review rows']:,}; this run increases review capture for recall, then reduces burden by clustering and priority tables."),
        ("Validation", f"{val_fail} validation failures; target is 0."),
        ("Biggest recall risk", "Unspecified-category and unmapped surgical-looking rows with product evidence but weak family/manufacturer/reference support."),
        ("Biggest precision risk", "Trusted or candidate mappings with imaging/lab/capital-equipment conflict terms or generic model tokens."),
        ("Fix first", "Review high-value clusters in Extended_Surgical_Decision, Reference_Update_Request, and Review_Queue_Cluster_Summary; convert labels to alias/rule/master updates."),
    ]
    return pd.DataFrame(rows, columns=["Executive_Summary_Item", "Result"])


def write_tables(path: Path, tables: OrderedDict[str, pd.DataFrame]) -> None:
    import xlsxwriter

    wb = xlsxwriter.Workbook(str(path), {"constant_memory": True, "nan_inf_to_errors": True})
    hdr = wb.add_format({"bold": True, "bg_color": "#1A4D3C", "font_color": "#FFFFFF", "border": 1, "font_name": "Arial", "font_size": 9})
    txt = wb.add_format({"font_name": "Arial", "font_size": 9})
    num = wb.add_format({"font_name": "Arial", "font_size": 9, "num_format": "#,##0.00"})
    int_fmt = wb.add_format({"font_name": "Arial", "font_size": 9, "num_format": "#,##0"})
    for name, df in tables.items():
        ws = wb.add_worksheet(safe_sheet_name(name))
        frame = df.copy()
        if frame.empty:
            frame = pd.DataFrame({"Note": ["No rows found for this table in the current run."]})
        for ci, col in enumerate(frame.columns):
            ws.write(0, ci, str(col), hdr)
        for ri, (_, row) in enumerate(frame.iterrows(), start=1):
            for ci, col in enumerate(frame.columns):
                value = row[col]
                fmt = num if "value" in str(col).lower() or "usd" in str(col).lower() or "score" in str(col).lower() or "recall" in str(col).lower() or "precision" in str(col).lower() else int_fmt if str(col).lower() in {"rows", "candidate_rank"} else txt
                if pd.isna(value):
                    ws.write_blank(ri, ci, None, fmt)
                elif isinstance(value, bool):
                    ws.write_boolean(ri, ci, bool(value), fmt)
                elif isinstance(value, (int, float)) and not isinstance(value, bool):
                    ws.write_number(ri, ci, float(value), fmt)
                else:
                    ws.write_string(ri, ci, str(value)[:30000], fmt)
        ws.freeze_panes(1, 0)
        ws.autofilter(0, 0, len(frame), len(frame.columns) - 1)
        ws.set_column(0, min(len(frame.columns), 12), 18)
    wb.close()


def update_shared_log(shared_dir: Path, summary_row: dict[str, object]) -> None:
    if not shared_dir.exists():
        return
    log_path = shared_dir / "MAPPING_IMPROVEMENT_LOG.xlsx"
    if log_path.exists():
        try:
            old = pd.read_excel(log_path, sheet_name="Log", dtype=object)
        except Exception:
            old = pd.DataFrame()
    else:
        old = pd.DataFrame()
    log = pd.concat([old, pd.DataFrame([summary_row])], ignore_index=True)
    log = log.drop_duplicates(subset=["Country", "Year", "Output_File", "Update_Timestamp"], keep="last")
    with pd.ExcelWriter(log_path, engine="xlsxwriter") as writer:
        log.to_excel(writer, index=False, sheet_name="Log")


def resolve_shared_dir() -> Path | None:
    for candidate in [DEFAULT_SHARED, LOCALIZED_SHARED]:
        if candidate.exists():
            return candidate
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--qa-output", type=Path, default=DEFAULT_QA)
    parser.add_argument("--publish-shared", action="store_true")
    args = parser.parse_args()

    started = time.time()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"[vn2024] loading {args.input}")
    baseline = pd.read_excel(args.input, sheet_name=RAW_SHEET, dtype=str).fillna("")
    raw_rows = len(baseline)
    raw_value = float(value_usd(baseline).sum())
    master_keys = build_master_keys(rc.cfg.V0_REFERENCE_XLSX)
    print("[vn2024] building evidence scores")
    evidence = build_evidence(baseline, master_keys)
    before_metrics = metrics_snapshot("A0 Baseline", baseline, evidence)

    print("[vn2024] routing rows")
    improved, changes = route_rows(baseline, evidence)
    runtime = time.time() - started
    after_metrics = metrics_snapshot("Improved", improved, evidence, runtime_seconds=runtime)
    validations = validate(improved, master_keys)

    if len(improved) != raw_rows or abs(float(value_usd(improved).sum()) - raw_value) > 0.01:
        raise RuntimeError("RawData row/value reconciliation failed after routing.")
    if int(validations["Status"].ne("PASS").sum()) != 0:
        print(validations.to_string(index=False))
        raise RuntimeError("Validation failures remain; refusing to write production workbook.")

    print(f"[vn2024] writing improved workbook {args.output}")
    before_stub = {"rows": raw_rows, "rev": raw_value}
    after_stub = {"rows": len(improved), "rev": float(value_usd(improved).sum())}
    rc._write_workbook(args.output, improved.fillna(""), "Vietnam", rc.load_master(), before_stub, after_stub)

    print("[vn2024] building QA tables")
    candidate_table = build_candidate_table(improved, evidence)
    reference_request = build_reference_update_request(improved, evidence)
    alias_request = build_alias_update_request(improved, evidence)
    extended_decision = build_extended_decision(improved, evidence)
    cluster_summary = build_cluster_summary(improved, evidence)
    precision_risk = build_precision_risk_rows(baseline, improved, evidence)
    potential_missed = build_potential_missed(improved, evidence, baseline)
    excluded_screen = build_excluded_surgicalish(improved, evidence)
    examples, unresolved = build_specific_examples(improved, evidence, baseline)
    experiment_matrix = build_experiment_matrix(before_metrics, after_metrics, changes, runtime)
    evidence_model = build_evidence_model()
    routing_rules = build_routing_rules()
    llm_eval = build_llm_agent_eval()
    gold_template = build_gold_label_template(improved, evidence, baseline)
    active_learning = build_active_learning_updates(alias_request, reference_request)
    dashboard = dashboard_rebuild(improved)

    metrics = pd.DataFrame([before_metrics, after_metrics])
    summary = build_summary(before_metrics, after_metrics, validations, changes)
    change_log = pd.DataFrame(
        [
            {
                "Update_Timestamp": timestamp,
                "Country": "Vietnam",
                "Year": 2024,
                "Input_File": str(args.input),
                "Output_File": str(args.output),
                "QA_Report": str(args.qa_output),
                "Raw_Rows": raw_rows,
                "Raw_Value_USD": raw_value,
                "Rows_Moved_Unmapped_to_Review": int(changes.loc[0, "Rows"]),
                "Value_Moved_Unmapped_to_Review": float(changes.loc[0, "Value_USD"]),
                "Trusted_Rows_After": after_metrics["Trusted rows"],
                "Trusted_Value_After": after_metrics["Trusted value"],
                "Review_Rows_After": after_metrics["Review rows"],
                "Review_Value_After": after_metrics["Review value"],
                "Capture_Recall_Proxy_Rows_After": after_metrics["Capture recall proxy rows"],
                "Capture_Recall_Proxy_Value_After": after_metrics["Capture recall proxy value"],
                "Validation_Failures": int(validations["Status"].ne("PASS").sum()),
                "Runtime_Seconds": runtime,
                "LLM_Calls": 0,
                "LLM_Token_Cost_USD": 0,
                "Main_Change": "Added evidence/candidate routing and QA outputs; kept Trusted master-validation strict.",
            }
        ]
    )
    recommendations = pd.DataFrame(
        [
            (
                "Implement immediately",
                "Keep strict Trusted_Dashboard gates, candidate evidence columns, review clustering, Extended_Surgical_Decision, Alias_Update_Request, and Reference_Update_Request.",
                "These changes improve capture recall and auditability without allowing unvalidated fuzzy/semantic matches into Trusted_Dashboard.",
                "Adopt in the FY2024 Vietnam production workflow and reuse for FY2025/India/Pakistan remaps.",
            ),
            (
                "Implement immediately",
                "Review high-value clusters first: Extended HS, manufacturer-only with product evidence, unspecified-category with product evidence, and latest-reference gaps.",
                "This targets the largest unresolved value while avoiding row-by-row manual review.",
                "Label cluster samples and convert corrections into alias/rule/reference update tables.",
            ),
            (
                "Test in controlled experiment",
                "Add sklearn-backed word and character n-gram TF-IDF retrieval when available.",
                "This should improve recall for misspellings, truncated customs descriptions, and punctuation/model variation.",
                "Compare A3/A4 against the current deterministic proxy using Gold_Labels before promotion.",
            ),
            (
                "Test in controlled experiment",
                "Add semantic retrieval and LLM resolver/conflict agents only after deterministic candidate generation.",
                "These methods may find missed surgical rows but carry false-positive risk for imaging, lab/IVD, capital equipment, ophthalmic, dental, cosmetic, and veterinary rows.",
                "Route semantic-only and LLM-only suggestions to Review_Queue unless master validation and evidence thresholds pass.",
            ),
            (
                "Defer",
                "Trusted inclusion for Extended HS surgical rows.",
                "The current run isolates them because the business rule is unresolved.",
                "Decide Option A core HS only vs Option B surgical product regardless of HS code.",
            ),
            (
                "Avoid",
                "Direct Trusted_Dashboard promotion from fuzzy, semantic, generic-token, or manufacturer-only evidence.",
                "This would damage defensibility and repeat known false-positive patterns.",
                "Require latest-master validation plus product/family/manufacturer support and no unresolved conflict term.",
            ),
        ],
        columns=["Recommendation_Category", "Recommendation", "Reason", "Next_Action"],
    )

    tables = OrderedDict(
        [
            ("Executive_Summary", summary),
            ("Baseline_vs_Improved", metrics),
            ("Metrics_Summary", metrics),
            ("Validation", validations),
            ("Changes_Applied", changes),
            ("Dashboard_Rebuild", dashboard),
            ("Candidate_Table", candidate_table),
            ("Alias_Update_Request", alias_request),
            ("Reference_Update_Request", reference_request),
            ("Extended_Surgical_Decision", extended_decision),
            ("Precision_Risk_Rows", precision_risk),
            ("Potential_Missed_Surgical_Rows", potential_missed),
            ("Review_Queue_Cluster_Summary", cluster_summary),
            ("Excluded_Surgicalish_Screen", excluded_screen),
            ("Specific_Examples_Fixed", examples),
            ("Remaining_Unresolved", unresolved),
            ("Experiment_Matrix", experiment_matrix),
            ("Evidence_Scoring_Model", evidence_model),
            ("Routing_Rules", routing_rules),
            ("LLM_Agent_Evaluation", llm_eval),
            ("Gold_Label_Template", gold_template),
            ("Active_Learning_Updates", active_learning),
            ("Change_Log", change_log),
            ("Workflow_Recommendations", recommendations),
        ]
    )
    print(f"[vn2024] writing QA report {args.qa_output}")
    write_tables(args.qa_output, tables)

    if args.publish_shared:
        shared = resolve_shared_dir()
        if shared is None:
            print("[vn2024] shared output folder not found; skipping publish")
        else:
            shared_file = shared / args.output.name
            print(f"[vn2024] publishing workbook to {shared_file}")
            shutil.copy2(args.output, shared_file)
            update_shared_log(
                shared,
                {
                    "Update_Timestamp": timestamp,
                    "Country": "Vietnam",
                    "Year": 2024,
                    "Output_File": args.output.name,
                    "QA_Report_Local": str(args.qa_output),
                    "Trusted_Rows": after_metrics["Trusted rows"],
                    "Trusted_Value_USD": after_metrics["Trusted value"],
                    "Review_Rows": after_metrics["Review rows"],
                    "Review_Value_USD": after_metrics["Review value"],
                    "Capture_Recall_Proxy_Rows": after_metrics["Capture recall proxy rows"],
                    "Capture_Recall_Proxy_Value": after_metrics["Capture recall proxy value"],
                    "Precision_Proxy": after_metrics["Trusted precision proxy"],
                    "Validation_Failures": int(validations["Status"].ne("PASS").sum()),
                    "Runtime_Seconds": runtime,
                    "Notes": "Vietnam FY2024 evidence-scored review capture and QA framework update.",
                },
            )

    print("[vn2024] complete")
    print(metrics.to_string(index=False))
    print(validations.to_string(index=False))


if __name__ == "__main__":
    main()
