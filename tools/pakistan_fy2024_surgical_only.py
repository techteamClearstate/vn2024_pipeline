"""Build a stricter Pakistan FY2024 surgical-only mapping workbook.

This script starts from the reference-compliant Pakistan FY2024 workbook and
adds the additional dashboard inclusion gates requested for surgical-only
reporting:

* latest-master exact family tuple validation
* strong category evidence for category-level inclusions
* high-risk generic/common token evidence checks
* explicit non-surgical exclusion re-audit
* QA sheets for risks, reference gaps, missed surgical candidates, scope audit,
  and dashboard rebuild
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "outputs" / "Pakistan_FY2024_ML_Map_Mapped_SurgicalOnly.xlsx"
DEFAULT_MASTER = ROOT / "reference" / "brand_model" / "Surg_Brand_model_list_Master_03July26.xlsx"
DEFAULT_OUTPUT = ROOT / "outputs" / "Pakistan_FY2024_ML_Map_Mapped_SurgicalOnly.xlsx"
DEFAULT_QA = ROOT / "outputs" / "Pakistan_FY2024_SurgicalOnly_QA.xlsx"

RAW_SHEET = "RawData"
MASTER_SHEET = "Updated (excl. generic)"
GENERIC_MASTER_SHEET = "Updated"
GENERIC_COL = "Generic Family Name?"

DIM_COLS = ["Segment", "Sub-segment", "Product_V0", "Manufacturer", "Family"]
MASTER_DIM_COLS = ["Segment", "Sub-segment", "Product", "Player", "Model/ Family Name"]
CATEGORY_COLS = ["Segment", "Sub-segment", "Product_V0"]
MASTER_CATEGORY_COLS = ["Segment", "Sub-segment", "Product"]

QA_TRUSTED = "Mapped - reference-valid"
QA_GENERIC_WEAK = "Review - generic token / weak evidence"
QA_CATEGORY_WEAK = "Review - weak category evidence"
QA_REFERENCE_GAP = "Review - latest reference gap"
QA_GENERIC_REFERENCE_ONLY = "Review - generic reference row only"
QA_EXCLUSION_REVIEW = "Review - exclusion term / manual review"
QA_EXTENDED = "Review - surgical product in Extended HS scope"
QA_POTENTIAL_MISSED = "Review - potential missed surgical"
QA_MAPPED_NON_DASHBOARD = "Review - mapped non-dashboard tier"
QA_EXCLUDED = "Excluded/Unmapped - irrelevant or no surgical evidence"

TIER_TRUSTED = "Trusted Dashboard"
TIER_REVIEW = "Review Queue"
TIER_EXCLUDED = "Excluded/Unmapped"

HIGH_RISK_TOKENS = {
    "essential",
    "gateway",
    "march",
    "zenith",
    "cirrus",
    "legion",
    "strata",
    "therapy",
    "light source",
    "alcon",
    "hybrid",
    "elite",
    "reinforced",
    "woven",
    "masters",
    "target",
    "rosa",
    "solar",
    "sprinter",
    "arrive",
    "current",
    "volt",
    "maestro",
    "imager",
    "unity",
    "velocity alpha",
    "celsius",
    "express",
    "hydra",
    "zero",
    "hawk",
    "trilogy",
    "direx",
    "bio 1",
}

# Curated aliases are intentionally empty until a reviewed source validates a
# brand-model-product combination. Manufacturer evidence or strong product
# wording can still clear the high-risk token gate.
CURATED_ALIAS_RULES: set[tuple[str, str, str]] = set()


@dataclass(frozen=True)
class PatternHit:
    group: str
    keyword: str


def norm_text(value: object) -> str:
    """Normalize comparison text without mutating the original shipment fields."""
    if value is None or pd.isna(value):
        return ""
    text = str(value).lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def norm_tuple(values: Iterable[object]) -> tuple[str, ...]:
    return tuple(norm_text(v) for v in values)


def is_blank(value: object) -> bool:
    return norm_text(value) == ""


def value_usd(df: pd.DataFrame) -> pd.Series:
    return pd.to_numeric(df.get("Total_Value_USD", 0), errors="coerce").fillna(0.0)


def compile_named(patterns: list[tuple[str, str]]) -> list[tuple[str, re.Pattern[str]]]:
    return [(name, re.compile(pattern, re.IGNORECASE)) for name, pattern in patterns]


POTENTIAL_MISSED_PATTERNS = compile_named(
    [
        ("endoscopy/laparoscopy", r"\b(?:endo(?:scope|scopy|scopic)|laparo(?:scope|scopy|scopic))\b"),
        ("dialysis/dialyzer/hemodialysis", r"\b(?:dialysis|dialy[sz]er|hemo ?dialysis|haemo ?dialysis)\b"),
        ("prosthetic heart valves/On-X", r"\b(?:prosthetic heart valve|heart valve|on[- ]?x)\b"),
        ("surgical instruments", r"\b(?:surgical instrument|instrument set|forceps|scalpel|retractor|trocar)\b"),
        ("staplers/clips", r"\b(?:stapler|staples|clip applier|ligation clip|surgical clip)\b"),
        (
            "cardiac/vascular catheters",
            r"\b(?:(?:cardiac|vascular|angiographic|angioplasty|coronary|diagnostic) catheter|catheter)\b",
        ),
        ("guidewires/sheaths/introducers", r"\b(?:guide ?wire|sheath|introducer)\b"),
        ("sutures", r"\b(?:suture|sutures)\b"),
        ("mesh", r"\b(?:surgical mesh|hernia mesh|mesh)\b"),
        ("cannula", r"\b(?:cannula|cannulae)\b"),
    ]
)

STRONG_PRODUCT_PATTERNS = compile_named(
    [
        *[(name, pattern.pattern) for name, pattern in POTENTIAL_MISSED_PATTERNS],
        ("electrosurgery", r"\b(?:electrosurgical|electrocautery|vessel sealing|ligasure|harmonic scalpel)\b"),
        ("orthopedic implants", r"\b(?:bone screw|locking plate|orthopedic implant|trauma implant|spinal implant)\b"),
        ("stents/balloons", r"\b(?:stent|balloon catheter|angioplasty balloon)\b"),
        ("endoscopic accessories", r"\b(?:biopsy forceps|snare|endoscopic accessory|endoscope accessory)\b"),
        ("surgical drainage", r"\b(?:drainage catheter|surgical drain|wound drain)\b"),
    ]
)

STRONG_CONFLICT_PATTERNS = compile_named(
    [
        ("linear_accelerator", r"\b(?:linar accelerator|linear accelerator|linac)\b"),
        ("cyclotron", r"\bcyclotron\b"),
        ("tomography_oct", r"\b(?:optical coherence tomography|tomography|oct[- ]?1)\b"),
        ("ultrasound", r"\bultrasound\b"),
        ("scanner_imager", r"\b(?:intraoral scanner|scanner|laser imager)\b"),
        ("angiography_detector", r"\b(?:angiography machine|fru detector)\b"),
        ("defib_ecg", r"\b(?:defibrillator|ecg machine)\b"),
        ("heart_lung_pump", r"\b(?:heart[- ]lung machine|centrifugal pump|rotaflow)\b"),
        ("non_surgical_capital", r"\b(?:scientific refrigerator|refrigerator|body warmer|blood warmer)\b"),
        ("urology_lithotripsy_conflict", r"\b(?:swiss lithoclast|swiss trilogy|lithoclast|lithotripter|lithotripsy)\b"),
        ("cosmetic_hydrafacial", r"\b(?:hydra facial|hydrafacial)\b"),
        ("ophthalmic_viscosurgical", r"\b(?:ophthalmic|opthalmic)\b.*\b(?:viscosurgical|visco[- ]?surgical)\b|\b(?:viscosurgical|visco[- ]?surgical)\b"),
    ]
)

EXTENDED_HS_REVIEW_PATTERNS = compile_named(
    [
        ("hs3006_sutures", r"\bsutures?\b"),
        ("hs3006_mesh", r"\b(?:mesh|hernia mesh|surgical mesh)\b"),
        ("hs3006_hemostats", r"\b(?:hemostat|haemostat|hemostatic|haemostatic)\b"),
        ("hs3006_wound_management", r"\b(?:wound|dressing|bandage|adhesive barrier|sealant)\b"),
    ]
)

PRODUCT_EVIDENCE_RULES: list[tuple[tuple[str, ...], str, re.Pattern[str]]] = [
    (("guidewire", "guide wire"), "product-specific guidewire evidence", re.compile(r"\bguide ?wire\b", re.IGNORECASE)),
    (
        ("balloon", "ptca", "pta"),
        "product-specific balloon evidence",
        re.compile(r"\b(?:balloon|ptca|pta|angioplasty)\b", re.IGNORECASE),
    ),
    (
        ("des", "stent", "stents", "stent graft"),
        "product-specific stent evidence",
        re.compile(r"\b(?:stent|stents|stent graft|graft|des)\b", re.IGNORECASE),
    ),
    (("suture",), "product-specific suture evidence", re.compile(r"\bsutures?\b", re.IGNORECASE)),
    (("mesh",), "product-specific mesh evidence", re.compile(r"\b(?:mesh|hernia mesh|surgical mesh)\b", re.IGNORECASE)),
    (
        ("sheath", "introducer"),
        "product-specific sheath/introducer evidence",
        re.compile(r"\b(?:sheath|introducer)\b", re.IGNORECASE),
    ),
    (
        ("ablation catheter",),
        "product-specific ablation catheter evidence",
        re.compile(r"\b(?:ablation|mapping catheter|electrophysiology|ep catheter)\b", re.IGNORECASE),
    ),
    (
        ("catheter", "microcatheter"),
        "product-specific catheter evidence",
        re.compile(r"\b(?:catheter|microcatheter)\b", re.IGNORECASE),
    ),
    (
        ("cannula", "cannulae"),
        "product-specific cannula evidence",
        re.compile(r"\b(?:cannula|cannulae)\b", re.IGNORECASE),
    ),
    (
        ("stapling", "stapler"),
        "product-specific stapling evidence",
        re.compile(r"\b(?:stapler|staples|stapling)\b", re.IGNORECASE),
    ),
    (
        ("clip",),
        "product-specific clip evidence",
        re.compile(r"\b(?:clip|clip applier|ligation clip)\b", re.IGNORECASE),
    ),
    (
        ("trocar",),
        "product-specific trocar evidence",
        re.compile(r"\btrocars?\b", re.IGNORECASE),
    ),
    (
        ("instrument", "retractor"),
        "product-specific instrument evidence",
        re.compile(r"\b(?:surgical instrument|instrument set|forceps|scalpel|retractor|drill|saw)\b", re.IGNORECASE),
    ),
    (
        ("electrosurgical", "grounding", "vessel sealing", "ablation"),
        "product-specific electrosurgery evidence",
        re.compile(r"\b(?:electrosurgical|electrocautery|diathermy|grounding pad|patient plate|vessel sealing|ablation)\b", re.IGNORECASE),
    ),
    (
        ("endoscope", "endoscopy", "mis platform", "mis platforms", "light source"),
        "product-specific endoscopy evidence",
        re.compile(r"\b(?:endoscope|endoscopy|endoscopic|laparoscope|laparoscopy|bronchoscope|gastroscope)\b", re.IGNORECASE),
    ),
    (
        ("dialyzer", "dialyzers", "dialysis", "chronic consumables", "acute consumables"),
        "product-specific dialysis evidence",
        re.compile(r"\b(?:dialysis|dialy[sz]er|hemo ?dialysis|haemo ?dialysis|bloodline)\b", re.IGNORECASE),
    ),
    (
        ("heart valve", "valve", "tpvr", "tavr", "pulmonary"),
        "product-specific valve evidence",
        re.compile(r"\b(?:heart valve|prosthetic valve|tavr|tpvr|on[- ]?x|valve)\b", re.IGNORECASE),
    ),
    (
        ("airway", "endotracheal", "tracheostomy", "breathing circuit"),
        "product-specific airway evidence",
        re.compile(r"\b(?:airway|endotracheal|tracheostomy|breathing circuit|ett|tube)\b", re.IGNORECASE),
    ),
    (
        ("laryngeal mask",),
        "product-specific laryngeal mask evidence",
        re.compile(r"\b(?:laryngeal mask|lma)\b", re.IGNORECASE),
    ),
    (
        ("oxygenator", "ecmo"),
        "product-specific oxygenator evidence",
        re.compile(r"\b(?:oxygenator|ecmo|cardiopulmonary)\b", re.IGNORECASE),
    ),
    (
        ("plate", "plates", "screws", "orthopedic", "orthopaedic"),
        "product-specific orthopedic evidence",
        re.compile(r"\b(?:plate|screw|orthopedic|orthopaedic|bone)\b", re.IGNORECASE),
    ),
    (
        ("suction", "irrigation"),
        "product-specific suction/irrigation evidence",
        re.compile(r"\b(?:suction|irrigation)\b", re.IGNORECASE),
    ),
    (
        ("inflation",),
        "product-specific inflation evidence",
        re.compile(r"\binflation device\b", re.IGNORECASE),
    ),
    (
        ("retrieval bag",),
        "product-specific retrieval bag evidence",
        re.compile(r"\b(?:retrieval bag|specimen bag)\b", re.IGNORECASE),
    ),
    (
        ("delivery system",),
        "product-specific delivery system evidence",
        re.compile(r"\b(?:delivery system|stent delivery|valve delivery|catheter)\b", re.IGNORECASE),
    ),
    (
        ("shunt", "hydrocephalus", "dura"),
        "product-specific shunt/dura evidence",
        re.compile(r"\b(?:shunt|hydrocephalus|dura|dural)\b", re.IGNORECASE),
    ),
    (
        ("embolic", "embolization", "flow diverter"),
        "product-specific embolic evidence",
        re.compile(r"\b(?:embolic|embolization|flow diverter|coil)\b", re.IGNORECASE),
    ),
]

EXCLUSION_PATTERNS = compile_named(
    [
        ("dental", r"\b(?:dental|orthodontic?|tooth|teeth|denture|endodontic)\b"),
        ("veterinary", r"\b(?:veterinary|animal use|bovine|canine|feline|equine|poultry)\b"),
        ("cosmetic", r"\b(?:cosmetic|aesthetic|beauty|dermal filler|botox|skin booster|facial treatment|hydra facial|hydrafacial)\b"),
        (
            "ivd_lab",
            r"\b(?:ivd|in vitro diagnostic|reagent|assay|calibrator|control material|diagnostic kit|test kit|laborator(?:y|ies)|pcr|elisa)\b",
        ),
        (
            "imaging_only",
            r"\b(?:mri|magnetic resonance|ct scan|\bct\b|x[- ]?ray|radiography|ultrasound|ultrasound probe|imaging system|optical coherence tomography|tomography|oct[- ]?1|scanner|laser imager|angiography machine|fru detector)\b",
        ),
        ("ophthalmic_intraocular", r"\b(?:ophthalmic|opthalmic|intraocular|iol\b|phaco|cataract|contact lens|alcon|viscosurgical|visco[- ]?surgical)\b"),
        ("cochlear_hearing", r"\b(?:cochlear|hearing aid|auditory implant|deafness)\b"),
        ("infusion_syringe_blood_bag", r"\b(?:infusion pump|infusion set|syringe|blood bag|blood transfusion bag|iv set)\b"),
        ("linear_accelerator_cyclotron", r"\b(?:linear accelerator|linac|cyclotron|radiotherapy)\b"),
        (
            "general_medical_supplies",
            r"\b(?:glove|mask|gauze|bandage|cotton roll|dressing|disinfectant|saniti[sz]er|ppe|thermometer|hospital bed|wheelchair|stretcher|diaper|first aid)\b",
        ),
        ("donation_humanitarian", r"\b(?:donation|donated|humanitarian|relief goods|aid consignment|free of cost|\bfoc\b)\b"),
        (
            "non_surgical_capital_equipment",
            r"\b(?:analy[sz]er|centrifuge|microscope|patient monitor|bedside monitor|ventilator|ecg machine|defibrillator|heart[- ]lung machine|centrifugal pump|rotaflow|scientific refrigerator|refrigerator|body warmer|blood warmer|swiss lithoclast|swiss trilogy|lithoclast|lithotripter|lithotripsy|hospital furniture|autoclave|hospital ot light|ot light|operating theatre light|operating theater light|operation theatre light|operation theater light|surgical light)\b",
        ),
    ]
)


def first_pattern_hit(text: str, patterns: list[tuple[str, re.Pattern[str]]]) -> PatternHit | None:
    for group, pattern in patterns:
        match = pattern.search(text)
        if match:
            return PatternHit(group, match.group(0))
    return None


def product_evidence_hit(row: pd.Series) -> PatternHit | None:
    product = norm_text(row.get("Product_V0", ""))
    text = str(row.get("Detailed_Product", ""))
    for product_terms, group, pattern in PRODUCT_EVIDENCE_RULES:
        if any(term in product for term in product_terms):
            match = pattern.search(text)
            if match:
                return PatternHit(group, match.group(0))
            return None
    return first_pattern_hit(text, STRONG_PRODUCT_PATTERNS)


def load_master(
    master_path: Path,
) -> tuple[pd.DataFrame, set[tuple[str, ...]], set[tuple[str, ...]], set[tuple[str, ...]]]:
    master = pd.read_excel(master_path, sheet_name=MASTER_SHEET, dtype=str).fillna("")
    strict = master[master[GENERIC_COL].map(is_blank)].copy()
    strict_full = {norm_tuple(row) for row in strict[MASTER_DIM_COLS].itertuples(index=False, name=None)}
    strict_category = {norm_tuple(row) for row in strict[MASTER_CATEGORY_COLS].drop_duplicates().itertuples(index=False, name=None)}
    generic_master = pd.read_excel(master_path, sheet_name=GENERIC_MASTER_SHEET, dtype=str).fillna("")
    generic_rows = generic_master[generic_master[GENERIC_COL].map(is_blank).eq(False)]
    generic_full = {norm_tuple(row) for row in generic_rows[MASTER_DIM_COLS].itertuples(index=False, name=None)}
    return strict, strict_full, strict_category, generic_full


def high_risk_token(row: pd.Series) -> str:
    haystacks = [
        norm_text(row.get("Family", "")),
        norm_text(row.get("Manufacturer", "")),
    ]
    for token in sorted(HIGH_RISK_TOKENS, key=len, reverse=True):
        token_norm = norm_text(token)
        pattern = re.compile(rf"(?:^| ){re.escape(token_norm)}(?: |$)")
        if any(pattern.search(hay) for hay in haystacks):
            return token
    return ""


def manufacturer_evidence(row: pd.Series) -> bool:
    player = norm_text(row.get("Manufacturer", ""))
    if not player or player in {"unspecified", "unknown", "na", "n a", "none"} or len(player) < 3:
        return False
    hay = norm_text(
        " ".join(
            [
                str(row.get("Detailed_Product", "")),
                str(row.get("Importer", "")),
                str(row.get("Exporter", "")),
            ]
        )
    )
    return player in hay


def curated_alias_evidence(row: pd.Series) -> bool:
    key = norm_tuple([row.get("Manufacturer", ""), row.get("Family", ""), row.get("Product_V0", "")])
    return key in CURATED_ALIAS_RULES


def hs4_value(row: pd.Series) -> str:
    hs4 = re.sub(r"\D", "", str(row.get("HS4", "")))
    if hs4:
        return hs4[:4]
    return re.sub(r"\D", "", str(row.get("HS_Code", "")))[:4]


def extended_hs_review_hit(row: pd.Series) -> PatternHit | None:
    if hs4_value(row) != "3006":
        return None
    text = " ".join([str(row.get("Detailed_Product", "")), str(row.get("Product_V0", ""))])
    return first_pattern_hit(text, EXTENDED_HS_REVIEW_PATTERNS)


def row_surgical_potential(row: pd.Series, strong_hit: PatternHit | None) -> bool:
    if strong_hit:
        return True
    if norm_text(row.get("Match_Status", "")) == "matched" and norm_text(row.get("Match_Scope", "")) == "surgical":
        return True
    return False


def add_decision_columns(
    df: pd.DataFrame,
    strict_full: set[tuple[str, ...]],
    strict_category: set[tuple[str, ...]],
    generic_full: set[tuple[str, ...]],
) -> pd.DataFrame:
    out = df.copy()
    out["Original_Dash_Include"] = out.get("Dash_Include", "").fillna("")
    out["Original_QA_Status"] = out.get("QA_Status", "").fillna("")
    out["Normalized_Detailed_Product"] = out["Detailed_Product"].map(norm_text)
    out["Strong_Product_Evidence"] = ""
    out["Exclusion_Group"] = ""
    out["Exclusion_Keyword"] = ""
    out["High_Risk_Token"] = ""
    out["Evidence_Flag"] = ""
    out["Reference_Key_Status"] = ""
    out["Risk_Flag"] = ""
    out["Output_Tier"] = TIER_EXCLUDED
    out["Dash_Include"] = ""
    out["Ref_Valid"] = ""
    out["Scope_Flag"] = out.get("Scope_Flag", "").fillna("")

    for idx, row in out.iterrows():
        desc_norm = row["Normalized_Detailed_Product"]
        strong_hit = first_pattern_hit(str(row.get("Detailed_Product", "")), STRONG_PRODUCT_PATTERNS)
        product_hit = product_evidence_hit(row)
        missed_hit = first_pattern_hit(str(row.get("Detailed_Product", "")), POTENTIAL_MISSED_PATTERNS)
        exclusion_hit = first_pattern_hit(str(row.get("Detailed_Product", "")), EXCLUSION_PATTERNS)
        conflict_hit = first_pattern_hit(str(row.get("Detailed_Product", "")), STRONG_CONFLICT_PATTERNS)
        blocking_hit = conflict_hit or exclusion_hit
        extended_hit = extended_hs_review_hit(row)
        token = high_risk_token(row)
        mfr_ok = manufacturer_evidence(row)
        alias_ok = curated_alias_evidence(row)
        product_ok = product_hit is not None
        risk_evidence_ok = (not token) or mfr_ok or product_ok or alias_ok

        full_key = norm_tuple([row.get(col, "") for col in DIM_COLS])
        cat_key = norm_tuple([row.get(col, "") for col in CATEGORY_COLS])
        tier = norm_text(row.get("Match_Tier", ""))
        scope = norm_text(row.get("Match_Scope", ""))
        matched = norm_text(row.get("Match_Status", "")) == "matched"
        is_family = matched and tier == "family"
        is_category = matched and tier == "category"
        is_hs_prior = matched and tier == "hs prior"
        full_valid = is_family and full_key in strict_full
        cat_valid = is_category and cat_key in strict_category

        evidence_bits = []
        if mfr_ok:
            evidence_bits.append("manufacturer/player in shipment parties or description")
        if product_ok:
            evidence_bits.append(f"product/category phrase: {product_hit.keyword}")
        if alias_ok:
            evidence_bits.append("curated alias rule")
        if missed_hit and not product_ok:
            evidence_bits.append(f"surgical candidate phrase: {missed_hit.keyword}")

        risks = []
        if conflict_hit:
            out.at[idx, "Exclusion_Group"] = f"strong_conflict:{conflict_hit.group}"
            out.at[idx, "Exclusion_Keyword"] = conflict_hit.keyword
            out.at[idx, "Scope_Flag"] = f"strong_conflict:{conflict_hit.group}"
            risks.append(f"strong_conflict:{conflict_hit.group}")
            if exclusion_hit:
                risks.append(f"exclusion:{exclusion_hit.group}")
        elif exclusion_hit:
            out.at[idx, "Exclusion_Group"] = exclusion_hit.group
            out.at[idx, "Exclusion_Keyword"] = exclusion_hit.keyword
            out.at[idx, "Scope_Flag"] = exclusion_hit.group
            risks.append(f"exclusion:{exclusion_hit.group}")
        if token:
            out.at[idx, "High_Risk_Token"] = token
            if not risk_evidence_ok:
                risks.append(f"generic_token_weak:{token}")
        if product_ok:
            out.at[idx, "Strong_Product_Evidence"] = product_hit.group
        if extended_hit:
            risks.append(f"extended_hs_review:{extended_hit.group}")

        if is_family:
            if full_valid:
                out.at[idx, "Reference_Key_Status"] = "latest master family tuple"
                out.at[idx, "Ref_Valid"] = "Y"
                if blocking_hit:
                    if row_surgical_potential(row, strong_hit):
                        qa = QA_EXCLUSION_REVIEW
                        output_tier = TIER_REVIEW
                    else:
                        qa = f"{QA_EXCLUDED}: {blocking_hit.group}"
                        output_tier = TIER_EXCLUDED
                elif not risk_evidence_ok:
                    qa = QA_GENERIC_WEAK
                    output_tier = TIER_REVIEW
                elif extended_hit:
                    qa = QA_EXTENDED
                    output_tier = TIER_REVIEW
                elif scope != "surgical":
                    qa = QA_EXTENDED
                    output_tier = TIER_REVIEW
                else:
                    qa = QA_TRUSTED
                    output_tier = TIER_TRUSTED
                    out.at[idx, "Dash_Include"] = "Y"
                    out.at[idx, "Scope_Flag"] = ""
            elif full_key in generic_full:
                out.at[idx, "Reference_Key_Status"] = "generic reference family only"
                qa = QA_GENERIC_REFERENCE_ONLY
                output_tier = TIER_REVIEW if row_surgical_potential(row, strong_hit) else TIER_EXCLUDED
                risks.append("generic_reference_only")
            else:
                out.at[idx, "Reference_Key_Status"] = "missing latest master family tuple"
                qa = QA_REFERENCE_GAP
                output_tier = TIER_REVIEW if row_surgical_potential(row, strong_hit) else TIER_EXCLUDED
                risks.append("reference_gap")
        elif is_category:
            if cat_valid:
                out.at[idx, "Reference_Key_Status"] = "latest master category tuple"
                out.at[idx, "Ref_Valid"] = "Y"
                if blocking_hit:
                    if row_surgical_potential(row, strong_hit):
                        qa = QA_EXCLUSION_REVIEW
                        output_tier = TIER_REVIEW
                    else:
                        qa = f"{QA_EXCLUDED}: {blocking_hit.group}"
                        output_tier = TIER_EXCLUDED
                elif not product_ok:
                    qa = QA_CATEGORY_WEAK
                    output_tier = TIER_REVIEW
                    risks.append("weak_category_evidence")
                elif not risk_evidence_ok:
                    qa = QA_GENERIC_WEAK
                    output_tier = TIER_REVIEW
                elif extended_hit:
                    qa = QA_EXTENDED
                    output_tier = TIER_REVIEW
                elif scope != "surgical":
                    qa = QA_EXTENDED
                    output_tier = TIER_REVIEW
                else:
                    qa = QA_TRUSTED
                    output_tier = TIER_TRUSTED
                    out.at[idx, "Dash_Include"] = "Y"
                    out.at[idx, "Scope_Flag"] = ""
            else:
                out.at[idx, "Reference_Key_Status"] = "missing latest master category tuple"
                qa = QA_REFERENCE_GAP
                output_tier = TIER_REVIEW if row_surgical_potential(row, strong_hit) else TIER_EXCLUDED
                risks.append("reference_gap")
        elif is_hs_prior:
            qa = QA_CATEGORY_WEAK if not product_ok else QA_EXTENDED
            output_tier = TIER_REVIEW if product_ok else TIER_EXCLUDED
            out.at[idx, "Reference_Key_Status"] = "hs-prior only"
            risks.append("hs_prior_not_dashboard")
        elif matched:
            if row_surgical_potential(row, strong_hit):
                qa = QA_MAPPED_NON_DASHBOARD
                output_tier = TIER_REVIEW
                risks.append("matched_non_dashboard_tier")
            else:
                qa = QA_EXCLUDED
                output_tier = TIER_EXCLUDED
        else:
            if extended_hit and not conflict_hit:
                qa = QA_EXTENDED
                output_tier = TIER_REVIEW
                out.at[idx, "Strong_Product_Evidence"] = extended_hit.group
                evidence_bits.append(f"extended HS surgical candidate: {extended_hit.keyword}")
            elif missed_hit and not blocking_hit:
                qa = QA_POTENTIAL_MISSED
                output_tier = TIER_REVIEW
                out.at[idx, "Strong_Product_Evidence"] = missed_hit.group
                evidence_bits.append(f"surgical candidate phrase: {missed_hit.keyword}")
            elif blocking_hit:
                qa = f"{QA_EXCLUDED}: {blocking_hit.group}"
                output_tier = TIER_EXCLUDED
            else:
                qa = QA_EXCLUDED
                output_tier = TIER_EXCLUDED

        out.at[idx, "QA_Status"] = qa
        out.at[idx, "Output_Tier"] = output_tier
        out.at[idx, "Evidence_Flag"] = "; ".join(dict.fromkeys(evidence_bits))
        out.at[idx, "Risk_Flag"] = "; ".join(dict.fromkeys(risks))

        # Preserve old explicit scope flags outside the trusted dashboard.
        if output_tier != TIER_TRUSTED and not out.at[idx, "Scope_Flag"]:
            old_scope = str(row.get("Scope_Flag", "") or "").strip()
            if old_scope:
                out.at[idx, "Scope_Flag"] = old_scope

    return out


def reference_gaps(df: pd.DataFrame) -> pd.DataFrame:
    gap_statuses = {
        "missing latest master family tuple",
        "missing latest master category tuple",
        "generic reference family only",
    }
    gaps = df[df["Reference_Key_Status"].isin(gap_statuses)].copy()
    if gaps.empty:
        return pd.DataFrame(
            columns=["Reference_Key_Status", "Match_Tier", *DIM_COLS, "Rows", "Value_USD", "Sample_UniqueID", "Sample_Detailed_Product"]
        )
    grouped = (
        gaps.assign(Value_USD=value_usd(gaps))
        .groupby(["Reference_Key_Status", "Match_Tier", *DIM_COLS], dropna=False)
        .agg(
            Rows=("UniqueID", "count"),
            Value_USD=("Value_USD", "sum"),
            Sample_UniqueID=("UniqueID", "first"),
            Sample_Detailed_Product=("Detailed_Product", "first"),
        )
        .reset_index()
        .sort_values(["Value_USD", "Rows"], ascending=[False, False])
    )
    return grouped


def potential_missed(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for idx, row in df.iterrows():
        if norm_text(row.get("Match_Status", "")) == "matched":
            continue
        if row.get("Exclusion_Group"):
            continue
        hit = first_pattern_hit(str(row.get("Detailed_Product", "")), POTENTIAL_MISSED_PATTERNS)
        if not hit:
            continue
        rows.append(
            {
                "Row_Index": idx + 2,
                "UniqueID": row.get("UniqueID", ""),
                "Keyword_Group": hit.group,
                "Keyword": hit.keyword,
                "HS_Code": row.get("HS_Code", ""),
                "Importer": row.get("Importer", ""),
                "Exporter": row.get("Exporter", ""),
                "Detailed_Product": row.get("Detailed_Product", ""),
                "Total_Value_USD": row.get("Total_Value_USD", ""),
                "QA_Status": row.get("QA_Status", ""),
                "Output_Tier": row.get("Output_Tier", ""),
            }
        )
    return pd.DataFrame(rows)


def dashboard_risks(df: pd.DataFrame) -> pd.DataFrame:
    previous_dashboard = df["Original_Dash_Include"].astype(str).str.upper().eq("Y")
    risk = df["Risk_Flag"].astype(str).ne("")
    removed_from_dashboard = previous_dashboard & ~df["Dash_Include"].astype(str).str.upper().eq("Y")
    cols = [
        "UniqueID",
        "Original_Dash_Include",
        "Dash_Include",
        "Original_QA_Status",
        "QA_Status",
        "Output_Tier",
        "Risk_Flag",
        "Reference_Key_Status",
        "High_Risk_Token",
        "Evidence_Flag",
        "Scope_Flag",
        "Exclusion_Group",
        "Exclusion_Keyword",
        "Match_Tier",
        "Match_Scope",
        "Segment",
        "Sub-segment",
        "Product_V0",
        "Manufacturer",
        "Family",
        "Detailed_Product",
        "Total_Value_USD",
    ]
    return df.loc[risk | removed_from_dashboard, cols].copy()


def scope_flag_audit(df: pd.DataFrame) -> pd.DataFrame:
    mask = (
        df["Scope_Flag"].astype(str).str.strip().ne("")
        | df["Exclusion_Group"].astype(str).str.strip().ne("")
        | df["Original_QA_Status"].astype(str).str.contains("scope|extended", case=False, na=False)
    )
    cols = [
        "UniqueID",
        "Output_Tier",
        "Dash_Include",
        "QA_Status",
        "Original_QA_Status",
        "Scope_Flag",
        "Exclusion_Group",
        "Exclusion_Keyword",
        "Match_Tier",
        "Match_Scope",
        "Segment",
        "Sub-segment",
        "Product_V0",
        "Manufacturer",
        "Family",
        "Detailed_Product",
        "Total_Value_USD",
    ]
    return df.loc[mask, cols].copy()


def partition_reconciliation(df: pd.DataFrame) -> pd.DataFrame:
    trusted = df[df["Output_Tier"].eq(TIER_TRUSTED)].copy()
    review = df[df["Output_Tier"].eq(TIER_REVIEW)].copy()
    excluded = df[df["Output_Tier"].eq(TIER_EXCLUDED)].copy()
    parts = pd.concat([trusted, review, excluded], ignore_index=True)
    raw_ids = df["UniqueID"].astype(str)
    part_ids = parts["UniqueID"].astype(str)
    missing_ids = sorted(set(raw_ids) - set(part_ids))
    extra_ids = sorted(set(part_ids) - set(raw_ids))
    duplicate_part_ids = int(part_ids.duplicated().sum())
    raw_value = float(value_usd(df).sum())
    part_value = float(value_usd(parts).sum())
    value_delta = part_value - raw_value

    checks = [
        ("RawData row count", len(df), "", "PASS", ""),
        ("Tier row count", len(parts), "", "PASS" if len(parts) == len(df) else "FAIL", "Trusted + Review + Excluded"),
        ("Row count delta", len(parts) - len(df), "", "PASS" if len(parts) == len(df) else "FAIL", "Must be 0"),
        ("RawData unique UniqueID count", raw_ids.nunique(), "", "PASS", ""),
        (
            "Tier unique UniqueID count",
            part_ids.nunique(),
            "",
            "PASS" if part_ids.nunique() == raw_ids.nunique() else "FAIL",
            "Trusted + Review + Excluded",
        ),
        ("Tier duplicate UniqueID rows", duplicate_part_ids, "", "PASS" if duplicate_part_ids == 0 else "FAIL", "Must be 0"),
        ("Missing RawData UniqueIDs in tiers", len(missing_ids), "", "PASS" if not missing_ids else "FAIL", "; ".join(missing_ids[:25])),
        ("Extra tier UniqueIDs outside RawData", len(extra_ids), "", "PASS" if not extra_ids else "FAIL", "; ".join(extra_ids[:25])),
        ("RawData Total_Value_USD", "", raw_value, "PASS", ""),
        ("Tier Total_Value_USD", "", part_value, "PASS", ""),
        (
            "Total_Value_USD delta",
            "",
            value_delta,
            "PASS" if abs(value_delta) < 0.01 else "FAIL",
            "Must round to 0.00",
        ),
    ]
    return pd.DataFrame(checks, columns=["Check", "Rows_or_Count", "Total_Value_USD", "Result", "Notes"])


def sample_unique_ids(df: pd.DataFrame, mask: pd.Series, limit: int = 25) -> str:
    ids = df.loc[mask, "UniqueID"].astype(str).head(limit).tolist()
    return "; ".join(ids)


def trusted_reference_validation(
    df: pd.DataFrame,
    strict_full: set[tuple[str, ...]],
    strict_category: set[tuple[str, ...]],
    generic_full: set[tuple[str, ...]],
) -> pd.DataFrame:
    trusted = df[df["Dash_Include"].astype(str).str.upper().eq("Y")].copy()
    family_mask = trusted["Match_Tier"].map(norm_text).eq("family")
    category_mask = trusted["Match_Tier"].map(norm_text).eq("category")

    family_bad = []
    generic_only = []
    for idx, row in trusted[family_mask].iterrows():
        full_key = norm_tuple([row.get(col, "") for col in DIM_COLS])
        if full_key not in strict_full:
            family_bad.append(idx)
        if full_key in generic_full and full_key not in strict_full:
            generic_only.append(idx)

    category_bad = []
    category_weak = []
    for idx, row in trusted[category_mask].iterrows():
        if norm_tuple([row.get(col, "") for col in CATEGORY_COLS]) not in strict_category:
            category_bad.append(idx)
        if not str(row.get("Strong_Product_Evidence", "")).strip():
            category_weak.append(idx)

    direct_conflict = trusted["Detailed_Product"].astype(str).map(lambda text: first_pattern_hit(text, STRONG_CONFLICT_PATTERNS) is not None)
    high_risk_weak = trusted["High_Risk_Token"].astype(str).str.strip().ne("") & trusted["Evidence_Flag"].astype(str).str.strip().eq("")
    extended_trusted = trusted.apply(lambda row: extended_hs_review_hit(row) is not None or norm_text(row.get("Match_Scope", "")) != "surgical", axis=1)
    exclusion_trusted = trusted["Exclusion_Group"].astype(str).str.strip().ne("") | trusted["Scope_Flag"].astype(str).str.strip().ne("")

    rows = [
        ("Trusted Dashboard rows", len(trusted), float(value_usd(trusted).sum()), "PASS", ""),
        ("Trusted family-tier rows", int(family_mask.sum()), "", "PASS", ""),
        ("Trusted category-tier rows", int(category_mask.sum()), "", "PASS", ""),
    ]
    check_masks: list[tuple[str, pd.Series | list[int], str]] = [
        ("Family rows outside latest master full key", family_bad, "Must be 0"),
        ("Category rows outside latest master category key", category_bad, "Must be 0"),
        ("Family rows relying only on generic reference rows", generic_only, "Must be 0"),
        ("Category trusted rows without strong product evidence", category_weak, "Must be 0"),
        ("Trusted rows with strong conflict terms", direct_conflict, "Must be 0"),
        ("Trusted rows with explicit scope/exclusion flags", exclusion_trusted, "Must be 0"),
        ("Trusted high-risk-token rows with weak evidence", high_risk_weak, "Must be 0"),
        ("Trusted extended-HS or non-surgical-scope rows", extended_trusted, "Must be 0"),
    ]
    for check, mask_or_ids, notes in check_masks:
        if isinstance(mask_or_ids, list):
            count = len(mask_or_ids)
            samples = "; ".join(trusted.loc[mask_or_ids, "UniqueID"].astype(str).head(25).tolist()) if count else ""
            amount = float(value_usd(trusted.loc[mask_or_ids]).sum()) if count else 0.0
        else:
            count = int(mask_or_ids.sum())
            samples = sample_unique_ids(trusted, mask_or_ids)
            amount = float(value_usd(trusted.loc[mask_or_ids]).sum()) if count else 0.0
        rows.append((check, count, amount, "PASS" if count == 0 else "FAIL", f"{notes}; Samples: {samples}" if samples else notes))
    return pd.DataFrame(rows, columns=["Check", "Rows_or_Count", "Total_Value_USD", "Result", "Notes"])


def dashboard_rebuild(df: pd.DataFrame) -> pd.DataFrame:
    trusted = df[df["Dash_Include"].astype(str).str.upper().eq("Y")].copy()
    if trusted.empty:
        return pd.DataFrame(columns=CATEGORY_COLS + ["Manufacturer", "Family", "Match_Tier", "Rows", "Value_USD", "Quantity", "First_UniqueID"])
    trusted["Value_USD"] = value_usd(trusted)
    trusted["Quantity_Numeric"] = pd.to_numeric(trusted.get("Quantity", 0), errors="coerce").fillna(0.0)
    group_cols = ["Segment", "Sub-segment", "Product_V0", "Manufacturer", "Family", "Match_Tier"]
    return (
        trusted.groupby(group_cols, dropna=False)
        .agg(
            Rows=("UniqueID", "count"),
            Value_USD=("Value_USD", "sum"),
            Quantity=("Quantity_Numeric", "sum"),
            First_UniqueID=("UniqueID", "first"),
        )
        .reset_index()
        .sort_values(["Value_USD", "Rows"], ascending=[False, False])
    )


def dashboard_aggregation_validation(df: pd.DataFrame, dashboard: pd.DataFrame) -> pd.DataFrame:
    trusted = df[df["Dash_Include"].astype(str).str.upper().eq("Y")].copy()
    quantity_raw = trusted.get("Quantity", pd.Series(index=trusted.index, dtype=object))
    quantity_numeric = pd.to_numeric(quantity_raw, errors="coerce")
    quantity_fail = quantity_raw.astype(str).str.strip().ne("") & quantity_numeric.isna()
    trusted["Value_USD"] = value_usd(trusted)
    trusted["Quantity_Numeric"] = quantity_numeric.fillna(0.0)
    group_cols = ["Segment", "Sub-segment", "Product_V0", "Manufacturer", "Family", "Match_Tier"]
    recomputed = (
        trusted.groupby(group_cols, dropna=False)
        .agg(
            Rows=("UniqueID", "count"),
            Value_USD=("Value_USD", "sum"),
            Quantity=("Quantity_Numeric", "sum"),
            First_UniqueID=("UniqueID", "first"),
        )
        .reset_index()
    )
    comparison = recomputed.merge(dashboard, on=group_cols, how="outer", suffixes=("_recomputed", "_dashboard"), indicator=True)
    for col in ["Rows_recomputed", "Rows_dashboard", "Value_USD_recomputed", "Value_USD_dashboard", "Quantity_recomputed", "Quantity_dashboard"]:
        if col in comparison.columns:
            comparison[col] = pd.to_numeric(comparison[col], errors="coerce").fillna(0.0)
    for col in ["Rows_recomputed", "Rows_dashboard", "Value_USD_recomputed", "Value_USD_dashboard", "Quantity_recomputed", "Quantity_dashboard"]:
        if col not in comparison.columns:
            comparison[col] = 0.0
    key_mismatches = int(comparison["_merge"].ne("both").sum()) if not comparison.empty else 0
    row_delta = float((comparison["Rows_recomputed"] - comparison["Rows_dashboard"]).abs().sum()) if not comparison.empty else 0.0
    value_delta = (
        float((comparison["Value_USD_recomputed"] - comparison["Value_USD_dashboard"]).abs().sum())
        if not comparison.empty
        else 0.0
    )
    quantity_delta = (
        float((comparison["Quantity_recomputed"] - comparison["Quantity_dashboard"]).abs().sum())
        if not comparison.empty
        else 0.0
    )
    checks = [
        ("Trusted rows aggregated", len(trusted), "", "PASS", ""),
        ("Dashboard_Rebuild rows", len(dashboard), "", "PASS", ""),
        ("Recomputed group rows", len(recomputed), "", "PASS", ""),
        ("Quantity conversion failures in trusted rows", int(quantity_fail.sum()), "", "PASS" if not quantity_fail.any() else "FAIL", "Must be 0"),
        ("Dashboard group key mismatches", key_mismatches, "", "PASS" if key_mismatches == 0 else "FAIL", "Must be 0"),
        ("Dashboard row-count absolute delta", row_delta, "", "PASS" if row_delta == 0 else "FAIL", "Must be 0"),
        ("Dashboard value absolute delta", "", value_delta, "PASS" if value_delta < 0.01 else "FAIL", "Must round to 0.00"),
        ("Dashboard quantity absolute delta", quantity_delta, "", "PASS" if quantity_delta < 0.000001 else "FAIL", "Must be 0"),
    ]
    return pd.DataFrame(checks, columns=["Check", "Rows_or_Count", "Total_Value_USD", "Result", "Notes"])


def trusted_anomaly_list(df: pd.DataFrame) -> pd.DataFrame:
    trusted = df[df["Output_Tier"].eq(TIER_TRUSTED)].copy()
    rows = []
    for idx, row in trusted.iterrows():
        reasons = []
        conflict = first_pattern_hit(str(row.get("Detailed_Product", "")), STRONG_CONFLICT_PATTERNS)
        if conflict:
            reasons.append(f"strong conflict term: {conflict.group} / {conflict.keyword}")
        if str(row.get("Scope_Flag", "")).strip():
            reasons.append(f"scope flag: {row.get('Scope_Flag', '')}")
        if str(row.get("Exclusion_Group", "")).strip():
            reasons.append(f"exclusion: {row.get('Exclusion_Group', '')}")
        if str(row.get("High_Risk_Token", "")).strip() and not str(row.get("Evidence_Flag", "")).strip():
            reasons.append(f"high-risk token without evidence: {row.get('High_Risk_Token', '')}")
        if norm_text(row.get("Match_Tier", "")) == "category" and not str(row.get("Strong_Product_Evidence", "")).strip():
            reasons.append("category tier without strong product evidence")
        if norm_text(row.get("Match_Scope", "")) != "surgical":
            reasons.append(f"non-surgical/extended match scope: {row.get('Match_Scope', '')}")
        extended_hit = extended_hs_review_hit(row)
        if extended_hit:
            reasons.append(f"extended HS review term: {extended_hit.group} / {extended_hit.keyword}")
        if row.get("Reference_Key_Status") not in {"latest master family tuple", "latest master category tuple"}:
            reasons.append(f"reference status: {row.get('Reference_Key_Status', '')}")
        if not reasons:
            continue
        rows.append(
            {
                "Row_Index": idx + 2,
                "UniqueID": row.get("UniqueID", ""),
                "Anomaly_Reason": "; ".join(reasons),
                "QA_Status": row.get("QA_Status", ""),
                "Match_Tier": row.get("Match_Tier", ""),
                "Match_Scope": row.get("Match_Scope", ""),
                "Segment": row.get("Segment", ""),
                "Sub-segment": row.get("Sub-segment", ""),
                "Product_V0": row.get("Product_V0", ""),
                "Manufacturer": row.get("Manufacturer", ""),
                "Family": row.get("Family", ""),
                "Detailed_Product": row.get("Detailed_Product", ""),
                "Total_Value_USD": row.get("Total_Value_USD", ""),
            }
        )
    return pd.DataFrame(rows)


def extended_surgical_review(df: pd.DataFrame) -> pd.DataFrame:
    review = df[df["Output_Tier"].eq(TIER_REVIEW)].copy()
    if review.empty:
        return pd.DataFrame()
    extended_hit = review.apply(lambda row: extended_hs_review_hit(row) is not None, axis=1)
    non_surgical_scope = review["Match_Scope"].map(norm_text).ne("surgical") & (
        review["Strong_Product_Evidence"].astype(str).str.strip().ne("")
        | review["QA_Status"].isin({QA_EXTENDED, QA_POTENTIAL_MISSED})
    )
    qa_extended = review["QA_Status"].eq(QA_EXTENDED)
    mask = extended_hit | non_surgical_scope | qa_extended
    cols = [
        "UniqueID",
        "QA_Status",
        "Risk_Flag",
        "Match_Tier",
        "Match_Scope",
        "HS_Code",
        "HS4",
        "Strong_Product_Evidence",
        "Segment",
        "Sub-segment",
        "Product_V0",
        "Manufacturer",
        "Family",
        "Detailed_Product",
        "Total_Value_USD",
    ]
    return review.loc[mask, cols].copy()


def extended_surgical_family_bucket(row: pd.Series) -> str:
    text = norm_text(" ".join([str(row.get("Detailed_Product", "")), str(row.get("Product_V0", "")), str(row.get("Family", ""))]))
    buckets = [
        ("Sutures", r"\b(?:suture|vicryl|prolene|polysorb|surgicryl|surgipro|demesorb)\b"),
        ("Mesh", r"\b(?:mesh|hernia mesh|surgical mesh)\b"),
        ("Hemostats", r"\b(?:hemostat|haemostat|hemostatic|haemostatic|surgicel|floseal)\b"),
        ("Wound management", r"\b(?:wound|dressing|bandage|adhesive barrier|sealant)\b"),
        ("Cannula/catheter adjacent", r"\b(?:cannula|catheter|sheath|introducer)\b"),
    ]
    for bucket, pattern in buckets:
        if re.search(pattern, text, re.IGNORECASE):
            return bucket
    return "Other extended surgical candidate"


def extended_surgical_decision(df: pd.DataFrame) -> pd.DataFrame:
    review = extended_surgical_review(df)
    if review.empty:
        return pd.DataFrame(
            columns=[
                "Decision_Bucket",
                "Decision_Recommendation",
                "HS4",
                "HS_Code",
                "Product_Family_Bucket",
                "Segment",
                "Sub-segment",
                "Product_V0",
                "Manufacturer",
                "Family",
                "Rows",
                "Value_USD",
                "First_UniqueID",
                "Sample_Detailed_Product",
                "Business_Rule_Needed",
                "Reference_Action",
            ]
        )
    review = review.copy()
    review["Value_USD"] = value_usd(review)
    review["HS4"] = review.apply(hs4_value, axis=1)
    review["Product_Family_Bucket"] = review.apply(extended_surgical_family_bucket, axis=1)
    review["Decision_Bucket"] = "Extended HS surgical product"
    review["Decision_Recommendation"] = "Keep in Review_Queue until Extended HS dashboard-scope rule is approved"
    review["Business_Rule_Needed"] = (
        "Decide whether surgical products outside core HS scope, especially HS 3006 sutures/mesh/hemostats/wound items, can enter dashboard"
    )
    review["Reference_Action"] = "If approved, promote only rows with valid latest-master category/family key and no conflict/exclusion flag"
    group_cols = [
        "Decision_Bucket",
        "Decision_Recommendation",
        "HS4",
        "HS_Code",
        "Product_Family_Bucket",
        "Segment",
        "Sub-segment",
        "Product_V0",
        "Manufacturer",
        "Family",
        "Business_Rule_Needed",
        "Reference_Action",
    ]
    return (
        review.groupby(group_cols, dropna=False)
        .agg(
            Rows=("UniqueID", "count"),
            Value_USD=("Value_USD", "sum"),
            First_UniqueID=("UniqueID", "first"),
            Sample_Detailed_Product=("Detailed_Product", "first"),
        )
        .reset_index()
        .sort_values(["Value_USD", "Rows"], ascending=[False, False])
    )


def append_validation_status(summary: pd.DataFrame, *validation_tables: pd.DataFrame) -> pd.DataFrame:
    fail_count = 0
    for table in validation_tables:
        if "Result" in table.columns:
            fail_count += int(table["Result"].astype(str).str.upper().eq("FAIL").sum())
    status_row = pd.DataFrame(
        [
            {
                "Metric": "Acceptance validation failures",
                "Value": fail_count,
                "Total_Value_USD": "",
                "Notes": "Must be 0",
            }
        ]
    )
    return pd.concat([summary, status_row], ignore_index=True)


def acceptance_summary(
    df: pd.DataFrame,
    strict_full: set[tuple[str, ...]],
    strict_category: set[tuple[str, ...]],
    generic_full: set[tuple[str, ...]],
    master_rows: int,
) -> pd.DataFrame:
    trusted = df[df["Dash_Include"].astype(str).str.upper().eq("Y")].copy()
    trusted_value = value_usd(trusted).sum()
    previous_trusted = df[df["Original_Dash_Include"].astype(str).str.upper().eq("Y")].copy()

    trusted_scope_flags = int(trusted["Scope_Flag"].astype(str).str.strip().ne("").sum())
    trusted_exclusions = int(trusted["Exclusion_Group"].astype(str).str.strip().ne("").sum())
    trusted_conflicts = int(
        trusted["Detailed_Product"].astype(str).map(lambda text: first_pattern_hit(text, STRONG_CONFLICT_PATTERNS) is not None).sum()
    )
    trusted_extended = int(trusted.apply(lambda row: extended_hs_review_hit(row) is not None, axis=1).sum())
    family_bad = 0
    generic_only = 0
    for _, row in trusted[trusted["Match_Tier"].map(norm_text).eq("family")].iterrows():
        full_key = norm_tuple([row.get(col, "") for col in DIM_COLS])
        if full_key not in strict_full:
            family_bad += 1
        if full_key in generic_full and full_key not in strict_full:
            generic_only += 1
    category_bad = 0
    category_weak = 0
    for _, row in trusted[trusted["Match_Tier"].map(norm_text).eq("category")].iterrows():
        if norm_tuple([row.get(col, "") for col in CATEGORY_COLS]) not in strict_category:
            category_bad += 1
        if not row.get("Strong_Product_Evidence"):
            category_weak += 1

    metrics = [
        ("Input rows", len(df), value_usd(df).sum(), ""),
        ("Latest master strict rows", master_rows, "", "Updated sheet excluding generic family rows"),
        ("Allowed category tuples", len(strict_category), "", "Derived from the same strict master rows"),
        ("Previous dashboard rows", len(previous_trusted), value_usd(previous_trusted).sum(), "From input Dash_Include"),
        ("Trusted Dashboard rows", len(trusted), trusted_value, "Final Dash_Include=Y"),
        ("Review Queue rows", int(df["Output_Tier"].eq(TIER_REVIEW).sum()), value_usd(df[df["Output_Tier"].eq(TIER_REVIEW)]).sum(), ""),
        ("Excluded/Unmapped rows", int(df["Output_Tier"].eq(TIER_EXCLUDED).sum()), value_usd(df[df["Output_Tier"].eq(TIER_EXCLUDED)]).sum(), ""),
        ("High-risk weak rows", int(df["QA_Status"].eq(QA_GENERIC_WEAK).sum()), value_usd(df[df["QA_Status"].eq(QA_GENERIC_WEAK)]).sum(), ""),
        (
            "Latest reference gap rows",
            int(df["Reference_Key_Status"].isin({"missing latest master family tuple", "missing latest master category tuple"}).sum()),
            value_usd(df[df["Reference_Key_Status"].isin({"missing latest master family tuple", "missing latest master category tuple"})]).sum(),
            "",
        ),
        ("Generic-reference-only rows", int(df["Reference_Key_Status"].eq("generic reference family only").sum()), value_usd(df[df["Reference_Key_Status"].eq("generic reference family only")]).sum(), ""),
        ("Potential missed surgical rows", int(df["QA_Status"].eq(QA_POTENTIAL_MISSED).sum()), value_usd(df[df["QA_Status"].eq(QA_POTENTIAL_MISSED)]).sum(), ""),
        ("Acceptance: dashboard rows with explicit scope flag", trusted_scope_flags, "", "Must be 0"),
        ("Acceptance: dashboard rows with exclusion pattern", trusted_exclusions, "", "Must be 0"),
        ("Acceptance: dashboard rows with strong conflict terms", trusted_conflicts, "", "Must be 0"),
        ("Acceptance: dashboard rows in Extended HS review scope", trusted_extended, "", "Must be 0"),
        ("Acceptance: family dashboard rows outside latest master", family_bad, "", "Must be 0"),
        ("Acceptance: family dashboard rows relying only on generic reference", generic_only, "", "Must be 0"),
        ("Acceptance: category dashboard rows outside latest master", category_bad, "", "Must be 0"),
        ("Acceptance: category dashboard rows without strong evidence", category_weak, "", "Must be 0"),
    ]
    return pd.DataFrame(metrics, columns=["Metric", "Value", "Total_Value_USD", "Notes"])


def assert_acceptance(
    df: pd.DataFrame,
    strict_full: set[tuple[str, ...]],
    strict_category: set[tuple[str, ...]],
    generic_full: set[tuple[str, ...]],
) -> None:
    allowed_tiers = {TIER_TRUSTED, TIER_REVIEW, TIER_EXCLUDED}
    invalid_tiers = df[~df["Output_Tier"].isin(allowed_tiers)]
    if not invalid_tiers.empty:
        raise AssertionError(f"{len(invalid_tiers)} rows have an invalid Output_Tier")

    trusted = df[df["Output_Tier"].eq(TIER_TRUSTED)].copy()
    review = df[df["Output_Tier"].eq(TIER_REVIEW)].copy()
    excluded = df[df["Output_Tier"].eq(TIER_EXCLUDED)].copy()
    if len(trusted) + len(review) + len(excluded) != len(df):
        raise AssertionError("Trusted + Review + Excluded row counts do not reconcile to RawData")
    if df["UniqueID"].astype(str).duplicated().any():
        raise AssertionError("RawData contains duplicate UniqueID values")
    raw_value = float(value_usd(df).sum())
    tier_value = float(value_usd(pd.concat([trusted, review, excluded], ignore_index=True)).sum())
    if abs(tier_value - raw_value) >= 0.01:
        raise AssertionError(f"Trusted + Review + Excluded value does not reconcile to RawData: {tier_value - raw_value:.4f}")

    trusted = df[df["Dash_Include"].astype(str).str.upper().eq("Y")].copy()
    tier_mismatch = trusted[~trusted["Output_Tier"].eq(TIER_TRUSTED)]
    if not tier_mismatch.empty:
        raise AssertionError(f"{len(tier_mismatch)} Dash_Include=Y rows are not in Trusted Dashboard")
    scope_bad = trusted[trusted["Scope_Flag"].astype(str).str.strip().ne("")]
    if not scope_bad.empty:
        raise AssertionError(f"{len(scope_bad)} trusted rows have Scope_Flag")
    exclusion_bad = trusted[trusted["Exclusion_Group"].astype(str).str.strip().ne("")]
    if not exclusion_bad.empty:
        raise AssertionError(f"{len(exclusion_bad)} trusted rows have exclusion patterns")
    conflict_bad = trusted[trusted["Detailed_Product"].astype(str).map(lambda text: first_pattern_hit(text, STRONG_CONFLICT_PATTERNS) is not None)]
    if not conflict_bad.empty:
        raise AssertionError(f"{len(conflict_bad)} trusted rows have strong conflict terms")
    scope_extended = trusted[trusted["Match_Scope"].map(norm_text).ne("surgical")]
    if not scope_extended.empty:
        raise AssertionError(f"{len(scope_extended)} trusted rows are outside surgical Match_Scope")
    extended_bad = trusted[trusted.apply(lambda row: extended_hs_review_hit(row) is not None, axis=1)]
    if not extended_bad.empty:
        raise AssertionError(f"{len(extended_bad)} trusted rows are Extended HS review candidates")
    family_bad = []
    generic_only = []
    for idx, row in trusted[trusted["Match_Tier"].map(norm_text).eq("family")].iterrows():
        full_key = norm_tuple([row.get(col, "") for col in DIM_COLS])
        if full_key not in strict_full:
            family_bad.append(idx)
        if full_key in generic_full and full_key not in strict_full:
            generic_only.append(idx)
    if family_bad:
        raise AssertionError(f"{len(family_bad)} trusted family rows are outside latest master")
    if generic_only:
        raise AssertionError(f"{len(generic_only)} trusted family rows rely only on generic reference rows")
    category_bad = []
    category_weak = []
    for idx, row in trusted[trusted["Match_Tier"].map(norm_text).eq("category")].iterrows():
        if norm_tuple([row.get(col, "") for col in CATEGORY_COLS]) not in strict_category:
            category_bad.append(idx)
        if not row.get("Strong_Product_Evidence"):
            category_weak.append(idx)
    if category_bad:
        raise AssertionError(f"{len(category_bad)} trusted category rows are outside latest master")
    if category_weak:
        raise AssertionError(f"{len(category_weak)} trusted category rows lack strong product evidence")
    high_risk_weak = trusted[
        trusted["High_Risk_Token"].astype(str).str.strip().ne("") & trusted["Evidence_Flag"].astype(str).str.strip().eq("")
    ]
    if not high_risk_weak.empty:
        raise AssertionError(f"{len(high_risk_weak)} trusted rows rely on generic/high-risk tokens without evidence")


def empty_sheet(message: str) -> pd.DataFrame:
    return pd.DataFrame({"Message": [message]})


def write_workbooks(df: pd.DataFrame, qa_tables: dict[str, pd.DataFrame], output_path: Path, qa_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    qa_path.parent.mkdir(parents=True, exist_ok=True)

    trusted = df[df["Output_Tier"].eq(TIER_TRUSTED)].copy()
    review = df[df["Output_Tier"].eq(TIER_REVIEW)].copy()
    excluded = df[df["Output_Tier"].eq(TIER_EXCLUDED)].copy()

    writer_kwargs = {"engine": "xlsxwriter", "engine_kwargs": {"options": {"strings_to_urls": False}}}
    with pd.ExcelWriter(output_path, **writer_kwargs) as writer:
        df.to_excel(writer, sheet_name=RAW_SHEET, index=False)
        trusted.to_excel(writer, sheet_name="Trusted_Dashboard", index=False)
        review.to_excel(writer, sheet_name="Review_Queue", index=False)
        excluded.to_excel(writer, sheet_name="Excluded_Unmapped", index=False)
        qa_tables["Dashboard_Rebuild"].to_excel(writer, sheet_name="Dashboard_Rebuild", index=False)

    with pd.ExcelWriter(qa_path, **writer_kwargs) as writer:
        for sheet_name, table in qa_tables.items():
            safe_table = table if not table.empty else empty_sheet(f"No rows for {sheet_name}")
            safe_table.to_excel(writer, sheet_name=sheet_name, index=False)


def run(input_path: Path, master_path: Path, output_path: Path, qa_path: Path) -> None:
    strict_master, strict_full, strict_category, generic_full = load_master(master_path)
    df = pd.read_excel(input_path, sheet_name=RAW_SHEET, dtype=str).fillna("")
    improved = add_decision_columns(df, strict_full, strict_category, generic_full)
    dashboard = dashboard_rebuild(improved)
    partition_validation = partition_reconciliation(improved)
    trusted_ref_validation = trusted_reference_validation(improved, strict_full, strict_category, generic_full)
    dashboard_validation = dashboard_aggregation_validation(improved, dashboard)
    assert_acceptance(improved, strict_full, strict_category, generic_full)

    summary = acceptance_summary(improved, strict_full, strict_category, generic_full, len(strict_master))
    summary = append_validation_status(summary, partition_validation, trusted_ref_validation, dashboard_validation)

    qa_tables = {
        "Summary": summary,
        "Partition_Reconciliation": partition_validation,
        "Trusted_Reference_Validation": trusted_ref_validation,
        "Dashboard_Aggregation_QA": dashboard_validation,
        "Trusted_Anomaly_List": trusted_anomaly_list(improved),
        "Extended_Surgical_Review": extended_surgical_review(improved),
        "Extended_Surgical_Decision": extended_surgical_decision(improved),
        "Latest_Reference_Gaps": reference_gaps(improved),
        "Dashboard_Risks": dashboard_risks(improved),
        "Reference_Gaps": reference_gaps(improved),
        "Potential_Missed_Surgical": potential_missed(improved),
        "Scope_Flag_Audit": scope_flag_audit(improved),
        "Dashboard_Rebuild": dashboard,
    }
    write_workbooks(improved, qa_tables, output_path, qa_path)

    print(f"[surgical-only] wrote {output_path}")
    print(f"[surgical-only] wrote {qa_path}")
    print(summary.to_string(index=False))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--master", type=Path, default=DEFAULT_MASTER)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--qa", type=Path, default=DEFAULT_QA)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(args.input, args.master, args.output, args.qa)
