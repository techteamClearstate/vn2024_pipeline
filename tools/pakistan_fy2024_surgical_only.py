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
DEFAULT_INPUT = ROOT / "outputs" / "Pakistan_FY2024_ML_Map_Mapped.xlsx"
DEFAULT_MASTER = ROOT / "reference" / "brand_model" / "Surg_Brand_model_list_Master_03July26.xlsx"
DEFAULT_OUTPUT = ROOT / "outputs" / "Pakistan_FY2024_ML_Map_Mapped_SurgicalOnly.xlsx"
DEFAULT_QA = ROOT / "outputs" / "Pakistan_FY2024_SurgicalOnly_QA.xlsx"

RAW_SHEET = "RawData"
MASTER_SHEET = "Updated"
GENERIC_COL = "Generic Family Name?"

DIM_COLS = ["Segment", "Sub-segment", "Product_V0", "Manufacturer", "Family"]
MASTER_DIM_COLS = ["Segment", "Sub-segment", "Product", "Player", "Model/ Family Name"]
CATEGORY_COLS = ["Segment", "Sub-segment", "Product_V0"]
MASTER_CATEGORY_COLS = ["Segment", "Sub-segment", "Product"]

QA_TRUSTED = "Mapped - reference-valid"
QA_GENERIC_WEAK = "Review - generic token / weak evidence"
QA_CATEGORY_WEAK = "Review - weak category evidence"
QA_REFERENCE_GAP = "Review - latest reference gap"
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
        ("cosmetic", r"\b(?:cosmetic|aesthetic|beauty|dermal filler|botox|skin booster|facial treatment)\b"),
        (
            "ivd_lab",
            r"\b(?:ivd|in vitro diagnostic|reagent|assay|calibrator|control material|diagnostic kit|test kit|laborator(?:y|ies)|pcr|elisa)\b",
        ),
        ("imaging_only", r"\b(?:mri|magnetic resonance|ct scan|\bct\b|x[- ]?ray|radiography|ultrasound probe|imaging system)\b"),
        ("ophthalmic_intraocular", r"\b(?:ophthalmic|intraocular|iol\b|phaco|cataract|contact lens|alcon)\b"),
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
            r"\b(?:analy[sz]er|centrifuge|microscope|patient monitor|bedside monitor|ventilator|ecg machine|defibrillator|hospital furniture|autoclave|hospital ot light|ot light|operating theatre light|operating theater light|operation theatre light|operation theater light|surgical light)\b",
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


def load_master(master_path: Path) -> tuple[pd.DataFrame, set[tuple[str, ...]], set[tuple[str, ...]]]:
    master = pd.read_excel(master_path, sheet_name=MASTER_SHEET, dtype=str).fillna("")
    strict = master[master[GENERIC_COL].map(is_blank)].copy()
    strict_full = {norm_tuple(row) for row in strict[MASTER_DIM_COLS].itertuples(index=False, name=None)}
    strict_category = {norm_tuple(row) for row in strict[MASTER_CATEGORY_COLS].drop_duplicates().itertuples(index=False, name=None)}
    return strict, strict_full, strict_category


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
        if exclusion_hit:
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

        if is_family:
            if full_valid:
                out.at[idx, "Reference_Key_Status"] = "latest master family tuple"
                out.at[idx, "Ref_Valid"] = "Y"
                if exclusion_hit:
                    if row_surgical_potential(row, strong_hit):
                        qa = QA_EXCLUSION_REVIEW
                        output_tier = TIER_REVIEW
                    else:
                        qa = f"{QA_EXCLUDED}: {exclusion_hit.group}"
                        output_tier = TIER_EXCLUDED
                elif not risk_evidence_ok:
                    qa = QA_GENERIC_WEAK
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
                out.at[idx, "Reference_Key_Status"] = "missing latest master family tuple"
                qa = QA_REFERENCE_GAP
                output_tier = TIER_REVIEW if row_surgical_potential(row, strong_hit) else TIER_EXCLUDED
                risks.append("reference_gap")
        elif is_category:
            if cat_valid:
                out.at[idx, "Reference_Key_Status"] = "latest master category tuple"
                out.at[idx, "Ref_Valid"] = "Y"
                if exclusion_hit:
                    if row_surgical_potential(row, strong_hit):
                        qa = QA_EXCLUSION_REVIEW
                        output_tier = TIER_REVIEW
                    else:
                        qa = f"{QA_EXCLUDED}: {exclusion_hit.group}"
                        output_tier = TIER_EXCLUDED
                elif not product_ok:
                    qa = QA_CATEGORY_WEAK
                    output_tier = TIER_REVIEW
                    risks.append("weak_category_evidence")
                elif not risk_evidence_ok:
                    qa = QA_GENERIC_WEAK
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
            if missed_hit and not exclusion_hit:
                qa = QA_POTENTIAL_MISSED
                output_tier = TIER_REVIEW
                out.at[idx, "Strong_Product_Evidence"] = missed_hit.group
                evidence_bits.append(f"surgical candidate phrase: {missed_hit.keyword}")
            elif exclusion_hit:
                qa = f"{QA_EXCLUDED}: {exclusion_hit.group}"
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
    gaps = df[df["Reference_Key_Status"].eq("missing latest master family tuple")].copy()
    if gaps.empty:
        return pd.DataFrame(columns=DIM_COLS + ["Rows", "Value_USD", "Sample_UniqueID", "Sample_Detailed_Product"])
    grouped = (
        gaps.assign(Value_USD=value_usd(gaps))
        .groupby(DIM_COLS, dropna=False)
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


def dashboard_rebuild(df: pd.DataFrame) -> pd.DataFrame:
    trusted = df[df["Dash_Include"].astype(str).str.upper().eq("Y")].copy()
    if trusted.empty:
        return pd.DataFrame(columns=CATEGORY_COLS + ["Manufacturer", "Family", "Rows", "Value_USD"])
    trusted["Value_USD"] = value_usd(trusted)
    group_cols = ["Segment", "Sub-segment", "Product_V0", "Manufacturer", "Family", "Match_Tier"]
    return (
        trusted.groupby(group_cols, dropna=False)
        .agg(
            Rows=("UniqueID", "count"),
            Value_USD=("Value_USD", "sum"),
            Quantity=("Quantity", "sum"),
            First_UniqueID=("UniqueID", "first"),
        )
        .reset_index()
        .sort_values(["Value_USD", "Rows"], ascending=[False, False])
    )


def acceptance_summary(
    df: pd.DataFrame,
    strict_full: set[tuple[str, ...]],
    strict_category: set[tuple[str, ...]],
    master_rows: int,
) -> pd.DataFrame:
    trusted = df[df["Dash_Include"].astype(str).str.upper().eq("Y")].copy()
    trusted_value = value_usd(trusted).sum()
    previous_trusted = df[df["Original_Dash_Include"].astype(str).str.upper().eq("Y")].copy()

    trusted_scope_flags = int(trusted["Scope_Flag"].astype(str).str.strip().ne("").sum())
    trusted_exclusions = int(trusted["Exclusion_Group"].astype(str).str.strip().ne("").sum())
    family_bad = 0
    for _, row in trusted[trusted["Match_Tier"].map(norm_text).eq("family")].iterrows():
        if norm_tuple([row.get(col, "") for col in DIM_COLS]) not in strict_full:
            family_bad += 1
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
        ("Reference gap rows", int(df["Reference_Key_Status"].eq("missing latest master family tuple").sum()), value_usd(df[df["Reference_Key_Status"].eq("missing latest master family tuple")]).sum(), ""),
        ("Potential missed surgical rows", int(df["QA_Status"].eq(QA_POTENTIAL_MISSED).sum()), value_usd(df[df["QA_Status"].eq(QA_POTENTIAL_MISSED)]).sum(), ""),
        ("Acceptance: dashboard rows with explicit scope flag", trusted_scope_flags, "", "Must be 0"),
        ("Acceptance: dashboard rows with exclusion pattern", trusted_exclusions, "", "Must be 0"),
        ("Acceptance: family dashboard rows outside latest master", family_bad, "", "Must be 0"),
        ("Acceptance: category dashboard rows outside latest master", category_bad, "", "Must be 0"),
        ("Acceptance: category dashboard rows without strong evidence", category_weak, "", "Must be 0"),
    ]
    return pd.DataFrame(metrics, columns=["Metric", "Value", "Total_Value_USD", "Notes"])


def assert_acceptance(
    df: pd.DataFrame,
    strict_full: set[tuple[str, ...]],
    strict_category: set[tuple[str, ...]],
) -> None:
    trusted = df[df["Dash_Include"].astype(str).str.upper().eq("Y")].copy()
    scope_bad = trusted[trusted["Scope_Flag"].astype(str).str.strip().ne("")]
    if not scope_bad.empty:
        raise AssertionError(f"{len(scope_bad)} trusted rows have Scope_Flag")
    exclusion_bad = trusted[trusted["Exclusion_Group"].astype(str).str.strip().ne("")]
    if not exclusion_bad.empty:
        raise AssertionError(f"{len(exclusion_bad)} trusted rows have exclusion patterns")
    family_bad = []
    for idx, row in trusted[trusted["Match_Tier"].map(norm_text).eq("family")].iterrows():
        if norm_tuple([row.get(col, "") for col in DIM_COLS]) not in strict_full:
            family_bad.append(idx)
    if family_bad:
        raise AssertionError(f"{len(family_bad)} trusted family rows are outside latest master")
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
    strict_master, strict_full, strict_category = load_master(master_path)
    df = pd.read_excel(input_path, sheet_name=RAW_SHEET, dtype=str).fillna("")
    improved = add_decision_columns(df, strict_full, strict_category)
    assert_acceptance(improved, strict_full, strict_category)

    qa_tables = {
        "Summary": acceptance_summary(improved, strict_full, strict_category, len(strict_master)),
        "Dashboard_Risks": dashboard_risks(improved),
        "Reference_Gaps": reference_gaps(improved),
        "Potential_Missed_Surgical": potential_missed(improved),
        "Scope_Flag_Audit": scope_flag_audit(improved),
        "Dashboard_Rebuild": dashboard_rebuild(improved),
    }
    write_workbooks(improved, qa_tables, output_path, qa_path)

    summary = qa_tables["Summary"]
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
