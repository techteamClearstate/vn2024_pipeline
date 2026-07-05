"""Create the Pakistan FY2024 surgical workflow improvement review workbook.

The workbook is intentionally operational: it combines live examples from the
current mapping workbook with the proposed design changes, experiments, routing
rules, and acceptance criteria needed to improve recall without weakening the
auditable Trusted_Dashboard gate.
"""

from __future__ import annotations

import argparse
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKBOOK = ROOT / "outputs" / "Pakistan_FY2024_ML_Map_Mapped_SurgicalOnly.xlsx"
DEFAULT_QA = ROOT / "outputs" / "Pakistan_FY2024_SurgicalOnly_QA.xlsx"
DEFAULT_OUTPUT = ROOT / "outputs" / "Pakistan_FY2024_Workflow_Improvement_Review.xlsx"

RAW_SHEET = "RawData"
VALUE_COL = "Total_Value_USD"
TIER_TRUSTED = "Trusted Dashboard"
TIER_REVIEW = "Review Queue"
TIER_EXCLUDED = "Excluded/Unmapped"

SURGICAL_KEYWORD_RE = re.compile(
    r"\b(?:endoscop|laparoscop|dialysis|dialy[sz]er|hemo ?dialysis|haemo ?dialysis|"
    r"prosthetic heart valve|on[- ]?x|surgical instrument|forceps|scalpel|retractor|"
    r"stapler|clip applier|ligation clip|catheter|guide ?wire|sheath|introducer|"
    r"suture|mesh|cannula|cannulae|stent|balloon|trocar|implant|orthop(?:a)?edic|"
    r"bone screw|bone plate|heart valve|shunt|valve)\b",
    re.IGNORECASE,
)

CONFLICT_RE = re.compile(
    r"\b(?:linear accelerator|linar accelerator|cyclotron|radiotherapy|tomography|oct[- ]?1|"
    r"ultrasound|angiography machine|ecg machine|defibrillator|refrigerator|body warmer|"
    r"blood warmer|lithotripter|lithotripsy|lithoclast|laser imager|dry imager|"
    r"intraoral scanner|hydra facial|hydrafacial|ophthalmic|viscosurgical|visco[- ]?surgical|"
    r"veterinary|dental|orthodontic|cosmetic|aesthetic|reagent|assay|calibrator|ivd|laborator(?:y|ies))\b",
    re.IGNORECASE,
)


def norm_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def value_usd(df: pd.DataFrame) -> pd.Series:
    return pd.to_numeric(df.get(VALUE_COL, 0), errors="coerce").fillna(0.0)


def text_blob(row: pd.Series, fields: Iterable[str] = ("Detailed_Product", "Importer", "Exporter")) -> str:
    return " ".join(str(row.get(field, "")) for field in fields)


def mask_contains(df: pd.DataFrame, pattern: str, fields: Iterable[str] = ("Detailed_Product", "Importer", "Exporter")) -> pd.Series:
    regex = re.compile(pattern, re.IGNORECASE)
    return df.apply(lambda row: bool(regex.search(text_blob(row, fields))), axis=1)


def first_present(columns: list[str], candidates: Iterable[str]) -> list[str]:
    return [col for col in candidates if col in columns]


def sample_text(series: pd.Series) -> str:
    for value in series:
        if str(value).strip():
            return str(value)
    return ""


def row_value(row: pd.Series, col: str) -> str:
    value = row.get(col, "")
    return "" if pd.isna(value) else value


def example_group(
    df: pd.DataFrame,
    group_name: str,
    mask: pd.Series,
    why: str,
    recommended_action: str,
    suggested_update: str,
) -> dict[str, object]:
    aligned_mask = pd.Series(mask, index=mask.index).reindex(df.index, fill_value=False).astype(bool)
    rows = df.loc[aligned_mask].copy()
    if rows.empty:
        return {
            "Example_Group": group_name,
            "Rows": 0,
            "Value_USD": 0.0,
            "UniqueID": "",
            "Detailed_Product": "",
            "Importer": "",
            "Exporter": "",
            "HS_Code": "",
            "Current_Status": "No current rows found by this screen",
            "Current_Mapping": "",
            "Why_Missing_or_Risky": why,
            "Recommended_Action": recommended_action,
            "Suggested_Alias_Rule_or_Reference_Update": suggested_update,
        }
    rows["Value_USD"] = value_usd(rows)
    sample = rows.sort_values("Value_USD", ascending=False).iloc[0]
    mapping = " | ".join(
        str(row_value(sample, col))
        for col in ["Segment", "Sub-segment", "Product_V0", "Manufacturer", "Family"]
        if str(row_value(sample, col)).strip()
    )
    return {
        "Example_Group": group_name,
        "Rows": int(len(rows)),
        "Value_USD": float(rows["Value_USD"].sum()),
        "UniqueID": row_value(sample, "UniqueID"),
        "Detailed_Product": row_value(sample, "Detailed_Product"),
        "Importer": row_value(sample, "Importer"),
        "Exporter": row_value(sample, "Exporter"),
        "HS_Code": row_value(sample, "HS_Code"),
        "Current_Status": " / ".join(
            str(row_value(sample, col))
            for col in ["Output_Tier", "QA_Status", "Reference_Key_Status"]
            if str(row_value(sample, col)).strip()
        ),
        "Current_Mapping": mapping,
        "Why_Missing_or_Risky": why,
        "Recommended_Action": recommended_action,
        "Suggested_Alias_Rule_or_Reference_Update": suggested_update,
    }


def tier_summary(raw: pd.DataFrame) -> pd.DataFrame:
    data = raw.copy()
    data["Value_USD"] = value_usd(data)
    summary = (
        data.groupby("Output_Tier", dropna=False)
        .agg(Rows=("UniqueID", "count"), Value_USD=("Value_USD", "sum"))
        .reset_index()
        .sort_values("Rows", ascending=False)
    )
    total_row = pd.DataFrame(
        [{"Output_Tier": "RawData Total", "Rows": int(len(data)), "Value_USD": float(data["Value_USD"].sum())}]
    )
    return pd.concat([summary, total_row], ignore_index=True)


def review_burden(raw: pd.DataFrame) -> pd.DataFrame:
    review = raw[raw["Output_Tier"].eq(TIER_REVIEW)].copy()
    review["Value_USD"] = value_usd(review)
    rows = []
    for threshold in [25_000, 50_000, 100_000, 250_000, 500_000]:
        subset = review[review["Value_USD"].ge(threshold)]
        rows.append(
            {
                "Review_Value_Threshold_USD": threshold,
                "Rows": int(len(subset)),
                "Value_USD": float(subset["Value_USD"].sum()),
                "Workflow_Implication": "Prioritize this bucket for deterministic aliases, clustering, and targeted LLM review",
            }
        )
    return pd.DataFrame(rows)


def qa_status_summary(raw: pd.DataFrame) -> pd.DataFrame:
    data = raw.copy()
    data["Value_USD"] = value_usd(data)
    return (
        data.groupby(["Output_Tier", "QA_Status"], dropna=False)
        .agg(Rows=("UniqueID", "count"), Value_USD=("Value_USD", "sum"))
        .reset_index()
        .sort_values(["Output_Tier", "Value_USD"], ascending=[True, False])
    )


def baseline_assessment(raw: pd.DataFrame, qa_sheets: dict[str, pd.DataFrame]) -> pd.DataFrame:
    trusted = raw[raw["Output_Tier"].eq(TIER_TRUSTED)].copy()
    review = raw[raw["Output_Tier"].eq(TIER_REVIEW)].copy()
    excluded = raw[raw["Output_Tier"].eq(TIER_EXCLUDED)].copy()
    raw_value = float(value_usd(raw).sum())
    trusted_value = float(value_usd(trusted).sum())
    review_value = float(value_usd(review).sum())
    excluded_value = float(value_usd(excluded).sum())
    excluded_screen = excluded[
        excluded.apply(lambda row: bool(SURGICAL_KEYWORD_RE.search(text_blob(row))), axis=1)
        & ~excluded.apply(lambda row: bool(CONFLICT_RE.search(text_blob(row))), axis=1)
    ].copy()
    excluded_screen_value = float(value_usd(excluded_screen).sum())
    capture_rows = len(trusted) + len(review)
    capture_value = trusted_value + review_value
    proxy_rows_denom = capture_rows + len(excluded_screen)
    proxy_value_denom = capture_value + excluded_screen_value

    validation_failures = ""
    summary = qa_sheets.get("Summary")
    if summary is not None and {"Metric", "Value"}.issubset(summary.columns):
        match = summary[summary["Metric"].astype(str).eq("Acceptance validation failures")]
        if not match.empty:
            validation_failures = match.iloc[0]["Value"]

    rows = [
        ("RawData rows", len(raw), raw_value, "Source population"),
        ("Trusted_Dashboard rows", len(trusted), trusted_value, "Auditable reference-valid dashboard rows"),
        ("Review_Queue rows", len(review), review_value, "Surgical-looking or unresolved rows needing routing/resolution"),
        ("Excluded_Unmapped rows", len(excluded), excluded_value, "Rows without sufficient surgical evidence or out of scope"),
        ("Dashboard aggregation validation failures", validation_failures, "", "From QA Summary; target is 0"),
        ("Trusted precision estimate", "98.5% to 99.5% before named anomaly fixes", "", "Proxy estimate; true metric needs Gold_Labels"),
        (
            "Trusted recall diagnosis",
            "Low proxy recall",
            "",
            "Trusted is precise but too much surgical-looking value remains in Review_Queue",
        ),
        (
            "Capture recall proxy, row-based",
            f"{capture_rows / proxy_rows_denom:.1%}" if proxy_rows_denom else "",
            "",
            "Proxy denominator is Trusted + Review + Excluded surgical-keyword candidates without hard conflict",
        ),
        (
            "Capture recall proxy, value-based",
            "",
            f"{capture_value / proxy_value_denom:.1%}" if proxy_value_denom else "",
            "Proxy denominator is Trusted + Review + Excluded surgical-keyword candidates without hard conflict",
        ),
        (
            "Manual review bottleneck",
            len(review),
            review_value,
            "Review_Queue is too large; prioritize by value, repeated pattern, and evidence conflict",
        ),
    ]
    return pd.DataFrame(rows, columns=["Metric", "Rows_or_Value", "Total_Value_USD", "Assessment"])


def latest_reference_gaps(raw: pd.DataFrame) -> pd.DataFrame:
    gap = raw[raw["QA_Status"].astype(str).str.contains("latest reference gap|generic reference", case=False, na=False)].copy()
    known = [
        (
            "Medtronic unspecified stents",
            gap["Manufacturer"].astype(str).str.contains("medtronic", case=False, na=False)
            & mask_contains(gap, r"\bstents?\b|ronyx|onyx|resolute"),
            "Likely surgical coronary stent rows, but full family/category reference does not validate for the parsed tuple.",
            "Keep in Review_Queue now; promote only after latest-master category/full tuple validates.",
            "Add stent system aliases and request master update for Medtronic unspecified/Resolute Onyx variants if business confirms.",
        ),
        (
            "Unspecified cannulas",
            gap["Manufacturer"].astype(str).str.contains("unspecified|unknown|^$", case=False, na=False)
            & mask_contains(gap, r"\bcannulae?\b|canula"),
            "Strong cannula product evidence but weak manufacturer/family support.",
            "Route by product phrase and HS to Review_Queue; Trusted only if a valid master category is available.",
            "Add cannula/cannulae/canula aliases and product phrase classifier; request category tuple if in dashboard scope.",
        ),
        (
            "B. Braun unspecified cannulas",
            mask_contains(gap, r"\bb\.?\s*braun\b|bbraun|introcan|introcan[- ]?w"),
            "B. Braun/Introcan cannula rows are likely true device rows but currently fail master/full evidence.",
            "Keep Review_Queue until master category or family tuple is approved.",
            "Add B. Braun manufacturer aliases and Introcan/cannula family aliases; request reference update if IV cannulas are in scope.",
        ),
        (
            "Unspecified catheters",
            gap["Manufacturer"].astype(str).str.contains("unspecified|unknown|^$", case=False, na=False)
            & mask_contains(gap, r"\bcatheter\b|microcatheter|drainage catheter"),
            "Catheter evidence is real but mixed across vascular, urinary, dialysis, and drainage categories.",
            "Split by product phrase; Review_Queue until category classifier and master key resolve.",
            "Add catheter phrase taxonomy and negative rules for non-surgical catheter-only rows.",
        ),
        (
            "Nipro unspecified cannulas",
            mask_contains(gap, r"\bnipro\b") & mask_contains(gap, r"\bcannulae?\b|canula"),
            "Likely alias/reference gap for Nipro cannula rows.",
            "Keep Review_Queue until the validated Nipro/cannula tuple exists.",
            "Add Nipro alias and cannula spelling variants; request master category/family update if in scope.",
        ),
        (
            "Unspecified balloons",
            gap["Manufacturer"].astype(str).str.contains("unspecified|unknown|^$", case=False, na=False)
            & mask_contains(gap, r"\bballoon\b|ptca|pta|angioplasty"),
            "Balloon rows can be PTCA/vascular or Foley/non-dashboard; weak evidence cannot be trusted blindly.",
            "Split PTCA/angioplasty balloons into Review_Queue; keep Foley/urinary rows outside Trusted unless approved.",
            "Add balloon phrase classifier and master category validation for PTCA/vascular balloons.",
        ),
        (
            "SafeSheath II / CRT-D accessory reference issue",
            mask_contains(gap, r"safesheath|safe sheath|crt[- ]?d"),
            "Likely CRM accessory rows with reference-list or family alias issue.",
            "Review_Queue until CRM accessory scope and latest master tuple are confirmed.",
            "Add CRT-D/ICD/SafeSheath aliases and request master reference update if accepted in surgical scope.",
        ),
    ]
    return pd.DataFrame([example_group(raw, *item) for item in known])


def potential_missed_rows(raw: pd.DataFrame) -> pd.DataFrame:
    candidates = raw[~raw["Output_Tier"].eq(TIER_TRUSTED)].copy()
    known = [
        (
            "Video endoscopy system",
            mask_contains(candidates, r"video endoscop|endoscopy system|endoscopic video"),
            "High-signal endoscopy product/capital row; current logic does not resolve to a trusted master category.",
            "Keep Review_Queue unless surgical capital equipment is approved; if approved, map to latest valid endoscopy/MIS category.",
            "Add video endoscopy/endoscopy system aliases and a capital-equipment scope flag requiring business decision.",
        ),
        (
            "Nikkiso hemodialysis system",
            mask_contains(candidates, r"nikkiso|hemodialysis system|haemodialysis system"),
            "Renal/dialysis capital or system row, probably true medical device but scope-dependent.",
            "Keep Review_Queue until dialysis system/capital-equipment dashboard scope is decided.",
            "Add Nikkiso and hemodialysis system aliases; request dialysis category/reference update if approved.",
        ),
        (
            "Endoscopy / endosurgery equipment",
            mask_contains(candidates, r"endoscopy|endosurgery|endoscope|laparoscopy|laparoscope"),
            "Surgical-looking rows remain unresolved because product/manufacturer/family evidence is incomplete.",
            "Cluster by manufacturer and product phrase; promote only if latest master category validates and capital scope is approved.",
            "Add Olympus/Fujifilm/Karl Storz/Richard Wolf aliases and endoscopy accessory phrase rules.",
        ),
        (
            "Prosthetic heart valves / ON-X",
            mask_contains(candidates, r"prosthetic heart valve|heart valve|on[- ]?x|artivion|cryolife"),
            "Likely true surgical implant rows; known master rows exist but alias/player/family parsing can miss them.",
            "Resolve through alias table and promote to Trusted when full latest master key validates.",
            "Add ON-X, On X, Artivion, and CryoLife alias rules to the validated family tuple.",
        ),
    ]
    return pd.DataFrame([example_group(raw, *item) for item in known])


def extended_hs_rows(raw: pd.DataFrame, qa_sheets: dict[str, pd.DataFrame]) -> pd.DataFrame:
    table = qa_sheets.get("Extended_Surgical_Decision")
    if table is not None and not table.empty:
        return table
    review = raw[raw["QA_Status"].astype(str).eq("Review - surgical product in Extended HS scope")].copy()
    if review.empty:
        return pd.DataFrame({"Message": ["No Extended HS surgical review rows found."]})
    review["Value_USD"] = value_usd(review)
    review["Product_Family_Bucket"] = review.apply(
        lambda row: (
            "Sutures"
            if re.search(r"\b(?:suture|vicryl|prolene|polysorb|surgicryl|surgipro|demesorb)\b", text_blob(row), re.I)
            else "Mesh"
            if re.search(r"\bmesh\b", text_blob(row), re.I)
            else "Hemostats"
            if re.search(r"\bha?emostat", text_blob(row), re.I)
            else "Wound management"
            if re.search(r"\b(?:wound|dressing|bandage)\b", text_blob(row), re.I)
            else "Other extended surgical candidate"
        ),
        axis=1,
    )
    return (
        review.groupby(["Product_Family_Bucket", "HS_Code"], dropna=False)
        .agg(
            Rows=("UniqueID", "count"),
            Value_USD=("Value_USD", "sum"),
            First_UniqueID=("UniqueID", "first"),
            Sample_Detailed_Product=("Detailed_Product", "first"),
        )
        .reset_index()
        .sort_values("Value_USD", ascending=False)
    )


def precision_risk_rows(raw: pd.DataFrame) -> pd.DataFrame:
    patterns = [
        (
            "Scientific refrigerator mapped to Alsa/Excell/HW Basic",
            r"scientific refrigerator|refrigerator",
            "False positive / non-surgical capital or mixed capital row",
            "Move out of Trusted_Dashboard; Review_Queue if mixed with cautery/colposcope, otherwise Excluded_Unmapped.",
            "Add refrigerator conflict and prevent generic family collision with Excell/HW Basic.",
        ),
        (
            "Swiss Lithoclast mapped to Philips/Trilogy/Ventilator Consumables",
            r"swiss lithoclast|lithoclast",
            "Wrong product category; urology lithotripsy collision with generic Trilogy token.",
            "Move to Review_Queue until lithotripsy scope/master category is decided.",
            "Add Swiss Lithoclast/lithotripter conflict and Trilogy generic-token guard.",
        ),
        (
            "Body or blood warmer mapped to Celsius/Hawk surgical products",
            r"body warmer|blood warmer",
            "False positive from generic family token or weak semantic similarity.",
            "Move out of Trusted_Dashboard; usually Excluded_Unmapped unless manually approved as surgical-adjacent.",
            "Add body warmer/blood warmer conflict; guard Celsius and Hawk generic tokens.",
        ),
        (
            "Lithotripter mapped to Zero or Direx surgical categories",
            r"lithotripter|lithotripsy|lithobox",
            "Scope/category ambiguity and wrong reference collision.",
            "Move to Review_Queue; promote only if lithotripsy is approved and master key exists.",
            "Add lithotripsy/lithotripter conflict and Zero/Direx generic-token guard.",
        ),
        (
            "ECG machine mapped to Express/BMS stent",
            r"ecg machine|electrocardiograph",
            "Non-surgical capital false positive.",
            "Exclude or Review_Queue only with explicit manual override.",
            "Keep ECG machine as strong negative and Express as generic-token guard.",
        ),
        (
            "Hydra Facial mapped to SMT/Hydra/Delivery Aortic",
            r"hydra facial|hydrafacial",
            "Cosmetic/aesthetic false positive caused by generic Hydra token.",
            "Exclude unless manually approved outside surgical dashboard.",
            "Add Hydra Facial cosmetic exclusion and Hydra generic-token guard.",
        ),
        (
            "Ophthalmic visco-surgical device mapped to SBM/BIO 1/Spinal Synthetics",
            r"ophthalmic|opthalmic|viscosurgical|visco[- ]?surgical",
            "Out-of-scope ophthalmic/intraocular false positive or wrong product category.",
            "Move out of Trusted_Dashboard; Review_Queue only if ophthalmic scope is later approved.",
            "Add ophthalmic viscosurgical exclusion and BIO 1 generic-token guard.",
        ),
    ]
    rows = []
    for group, pattern, decision, action, update in patterns:
        rows.append(
            example_group(
                raw,
                group,
                mask_contains(raw, pattern),
                decision,
                action,
                update,
            )
        )
    return pd.DataFrame(rows)


def excluded_candidates(raw: pd.DataFrame) -> pd.DataFrame:
    excluded = raw[raw["Output_Tier"].eq(TIER_EXCLUDED)].copy()
    if excluded.empty:
        return pd.DataFrame()
    surgical_mask = excluded.apply(lambda row: bool(SURGICAL_KEYWORD_RE.search(text_blob(row))), axis=1)
    conflict_mask = excluded.apply(lambda row: bool(CONFLICT_RE.search(text_blob(row))), axis=1)
    candidates = excluded[surgical_mask].copy()
    candidates["Value_USD"] = value_usd(candidates)
    candidates["Conflict_Term_Present"] = conflict_mask.loc[candidates.index].map(lambda value: "Y" if value else "")
    candidates["Why_Risky"] = candidates["Conflict_Term_Present"].map(
        lambda value: "Has surgical keyword but also exclusion/conflict term; review only if high value or repeated pattern"
        if value == "Y"
        else "Surgical keyword in Excluded_Unmapped without hard conflict; candidate for recall-hunter review"
    )
    candidates["Recommended_Action"] = candidates["Conflict_Term_Present"].map(
        lambda value: "Keep excluded unless manual override supports surgical scope"
        if value == "Y"
        else "Route repeated/high-value clusters to Review_Queue and create reusable alias/rule if validated"
    )
    cols = first_present(
        candidates.columns.tolist(),
        [
            "UniqueID",
            "Detailed_Product",
            "Importer",
            "Exporter",
            "HS_Code",
            "QA_Status",
            "Scope_Flag",
            "Exclusion_Group",
            "Conflict_Term_Present",
            "Segment",
            "Sub-segment",
            "Product_V0",
            "Manufacturer",
            "Family",
            "Value_USD",
            "Why_Risky",
            "Recommended_Action",
        ],
    )
    return candidates.sort_values("Value_USD", ascending=False).loc[:, cols].head(150)


def executive_summary(raw: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Question": "What is missing?",
                "Answer": (
                    "Candidate_Table, governed alias tables, separated evidence scores, lexical/semantic recall retrieval, "
                    "gold labels, active learning, and a precision/recall dashboard are not yet first-class workflow outputs."
                ),
                "Operational_Implication": "Current routing is defensible but still hides why candidate mappings were accepted, reviewed, or discarded.",
            },
            {
                "Question": "Biggest recall risk",
                "Answer": (
                    "Latest reference gaps and unresolved product/category candidates: stents, cannulas, catheters, balloons, endoscopy, dialysis, "
                    "prosthetic valves, sutures, mesh, hemostats, sheaths, and orthopedic implants."
                ),
                "Operational_Implication": "Do not silently exclude these; route into Review_Queue or master-reference update requests.",
            },
            {
                "Question": "Biggest precision risk",
                "Answer": (
                    "Generic family tokens and broad device words colliding with non-surgical capital, imaging, ophthalmic, cosmetic, and urology equipment."
                ),
                "Operational_Implication": "Keep Trusted_Dashboard reference-valid and force rows with conflict terms to review unless manually approved.",
            },
            {
                "Question": "Biggest efficiency bottleneck",
                "Answer": "Review_Queue is too large and not sufficiently clustered by repeated phrase, alias gap, reference gap, and value.",
                "Operational_Implication": "Prioritize high-value clusters and convert each human correction into reusable alias/rule/reference updates.",
            },
            {
                "Question": "Fix first",
                "Answer": "Implement Candidate_Table + alias tables + evidence scoring before adding LLM review.",
                "Operational_Implication": "These deterministic layers raise recall and reduce LLM/manual review cost while preserving auditability.",
            },
        ]
    )


def missing_capabilities() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("Candidate_Table", "Missing/insufficient", "Expose every candidate considered per UniqueID with rank, method, scores, validation, and routing decision."),
            ("Manufacturer_Alias", "Missing/insufficient", "Add B. Braun, Nipro, Medtronic, Artivion/CryoLife, Olympus/Fujifilm/Karl Storz/Richard Wolf variants."),
            ("Family_Alias", "Missing/insufficient", "Add ON-X, Introcan, SafeSheath, Resolute Onyx, Vicryl, Prolene, Polysorb, Surgicryl, Surgipro, Demesorb."),
            ("Product_Alias", "Missing/insufficient", "Add stent system, coronary stent system, vascular stent, cannula/cannulae/canula, PTCA balloon, endoscopy system."),
            ("Abbreviation_Alias", "Missing/insufficient", "DES, BMS, PTCA, CRT-D, ICD, ON-X."),
            ("Customs_Phrase_Alias", "Missing/insufficient", "Translate messy customs phrases into canonical product evidence without mutating original text."),
            ("Misspelling_Alias", "Missing/insufficient", "Handle canula/cannulae, haemodialysis/hemodialysis, ophthalmic/opthalmic, hyphen variants."),
            ("Negative_Terms", "Partially present", "Strengthen imaging, cosmetic, ophthalmic, lab/IVD, dental, veterinary, donation, and capital equipment conflicts."),
            ("Generic_Tokens", "Partially present", "Guard Light Source, Target, Sprinter, Arrive, Current, Volt, Maestro, Imager, Hybrid, Elite, Celsius, Express, Hydra, Zero."),
            ("HS_Scope_Rules", "Insufficient", "Separate core dashboard HS from Extended HS review and business-decision scope."),
            ("Evidence scoring", "Missing/insufficient", "Replace one Match_Confidence with product, family, manufacturer, fuzzy, TF-IDF, semantic, HS, exclusion, and master scores."),
            ("TF-IDF lexical retrieval", "Missing", "Add word and char n-gram candidate retrieval for messy descriptions, misspellings, and truncated models."),
            ("Semantic retrieval", "Missing", "Use embeddings only for candidate generation/recall hunting, never as a standalone trusted decision."),
            ("LLM resolver", "Missing", "Use only after deterministic top candidates exist; output structured JSON and require master validation."),
            ("LLM recall hunter", "Missing", "Review high-value clusters in Review_Queue/Excluded_Unmapped and suggest reusable aliases/rules."),
            ("LLM conflict/QC agent", "Missing", "Review Trusted_Dashboard precision-risk clusters and generic-token rows."),
            ("Gold_Labels", "Missing", "Create ground-truth table for real precision/recall rather than proxy metrics."),
            ("Active learning loop", "Missing", "Every human correction updates alias/rule/reference tables and is tested in next run."),
            ("Precision/recall dashboard", "Missing", "Track Trusted precision, Trusted recall, capture recall, review burden, high-value unresolved, and repeat corrections."),
        ],
        columns=["Capability", "Current_Status", "Implementation_Detail"],
    )


def experiment_matrix() -> pd.DataFrame:
    rows = [
        ("A0", "Current baseline", "Reference-valid Trusted_Dashboard remains precise", "Known review burden baseline", "None", "Recall still low", "Baseline metrics", "Run current workbook QA", "Reference"),
        ("A1", "Alias dictionary expansion", "Improves recall for known families/manufacturers/products", "Reduces repeated manual review", "Medium", "Bad aliases can create false positives", "Capture recall and review rows", "Add governed aliases, rerun, compare", "Implement immediately"),
        ("A2", "Fuzzy lexical matching", "Finds misspellings and partial manufacturers/families", "Creates better candidate list", "Medium", "False positives for common tokens", "Missed surgical rows", "Use fuzzy score as evidence only", "Test controlled"),
        ("A3", "Character n-gram TF-IDF", "Handles punctuation, truncation, spelling noise", "Batch candidate generation", "Medium", "Overmatches short model names", "Candidate recall", "Compare top-k recall on gold labels", "Test controlled"),
        ("A4", "Word n-gram TF-IDF", "Improves product phrase/category recall", "Clusters similar customs descriptions", "Medium", "Generic medical phrases overmatch", "Capture recall", "Test top-k product retrieval", "Implement after aliases"),
        ("A5", "Semantic retrieval", "Finds surgical-looking rows missed by lexical methods", "Prioritizes recall-hunter work", "Medium-high", "Can over-map capital equipment", "Review capture recall", "Semantic candidates go Review unless evidence supports", "Test further"),
        ("A6", "Evidence scoring", "Improves routing explainability and precision controls", "Reduces reviewer time", "Medium", "Weights need calibration", "Trusted precision and capture recall", "Score all candidates and compare A0", "Implement immediately"),
        ("A7", "LLM resolver agent", "May resolve close candidates and reference gaps", "Targets high-value ambiguous rows", "High", "Cost and non-determinism", "High-value unresolved rows", "JSON outputs on deterministic top candidates", "Test controlled"),
        ("A8", "LLM recall hunter agent", "Finds missed surgical clusters/rule ideas", "Reduces blind manual search", "High", "May hallucinate aliases", "Excluded false negatives", "Cluster input, require evidence terms", "Test controlled"),
        ("A9", "LLM conflict/QC agent", "Reduces false positives from generic tokens/conflicts", "Automates precision risk audit", "High", "May over-review valid rows", "False-positive value", "Run on Trusted risk screens only", "Test controlled"),
        ("A10", "Active learning loop", "Sustained recall gains across reruns", "Review burden declines run over run", "Medium", "Needs governance discipline", "Repeat correction rate", "Apply corrections then rerun A1-A6", "Implement immediately"),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "Experiment_ID",
            "Design_Change",
            "Expected_Accuracy_Benefit",
            "Expected_Efficiency_Benefit",
            "Implementation_Difficulty",
            "Risk",
            "Metric_to_Improve",
            "Test_Method",
            "Recommendation_Priority",
        ],
    )


def accuracy_plan() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("Improve recall", "Promote deterministic candidate generation for reference gaps, potential missed rows, and excluded surgical-keyword candidates.", "Measure capture recall and false-negative value."),
            ("Keep precision >=90%", "Trusted requires surgical scope, latest master validation, product evidence, no conflict terms, and generic-token support.", "Measure trusted precision on Gold_Labels and risk screens."),
            ("Prioritize product areas", "Stents, cannulas, catheters, balloons, endoscopy, dialysis/dialyzers, heart valves/ON-X, sutures, mesh, hemostats, sheaths, orthopedic implants.", "Track value captured and unresolved value by bucket."),
            ("Review bucket priority", "First review >=USD 250K, then >=USD 100K, repeated phrase clusters, and reference gaps with strong product evidence.", "Review rows/value cleared per hour."),
            ("Extended HS", "Create explicit Extended_Surgical_Decision and keep rows in Review until business approves inclusion.", "No silent drops; decision status by product family."),
            ("Latest reference gaps", "Split alias gap vs master-reference gap vs weak evidence vs true exclusion.", "Reference_Update_Request count and resolved value."),
        ],
        columns=["Theme", "Operational_Action", "Acceptance_Criterion"],
    )


def efficiency_plan() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("Reduce Review_Queue volume", "Cluster by normalized phrase/manufacturer/product bucket and apply reusable alias/rule updates.", "Review row count declines without precision failures."),
            ("Prioritize high value", "Route rows >=USD 50K and repeated clusters to top of queue; run LLM only on high-value ambiguity.", "High-value unresolved review rows decline."),
            ("Cluster repeated patterns", "Create Cluster_ID from normalized product phrase, HS4, importer/exporter, and candidate product.", "Reviewer can approve many rows per decision."),
            ("Reduce repeated corrections", "Convert every correction into Alias, Negative_Term, HS_Scope, or Reference_Update row.", "Repeat correction rate declines run over run."),
            ("Reduce LLM/token cost", "Run deterministic retrieval first; LLM receives only top candidates and evidence fields.", "Token cost per resolved USD declines."),
            ("Reproducibility", "Version alias/rule/reference tables, log run timestamp/master checksum/script version, and write candidate/audit outputs.", "Same inputs and rules reproduce same workbook."),
        ],
        columns=["Efficiency_Lever", "Operational_Action", "Success_Metric"],
    )


def evidence_model() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("exact_family_alias", 25, "Exact reviewed family/model alias hit", "Positive; strong only with master validation"),
            ("exact_manufacturer_alias", 15, "Manufacturer/player alias appears in detailed/importer/exporter", "Positive support"),
            ("product_phrase_match", 20, "Strong product phrase in shipment text", "Positive; required for category Trusted"),
            ("category_match", 10, "Segment/Sub-segment/Product candidate fits master category", "Positive support"),
            ("hs_compatibility", 8, "HS4/HS6 compatible with product scope", "Positive or review-only for Extended HS"),
            ("fuzzy_family_score", 0, "Fuzzy family score retained as evidence", "Use as candidate evidence; no standalone Trusted"),
            ("fuzzy_product_score", 0, "Fuzzy product phrase score", "Use as candidate evidence; no standalone Trusted"),
            ("word_tfidf_score", 0, "Word n-gram retrieval score", "Candidate generation/review priority"),
            ("char_tfidf_score", 0, "Character n-gram retrieval score", "Candidate generation for misspellings/truncation"),
            ("semantic_score", 0, "Embedding similarity score", "Recall generation only unless supported by deterministic evidence"),
            ("generic_token_penalty", -20, "Family/model token is generic/common without support", "Route Review unless manufacturer/product/alias evidence exists"),
            ("exclusion_term_penalty", -100, "Strong exclusion or conflict term", "Block Trusted unless manual override"),
            ("master_reference_validation", 100, "Full family key or category key validates in latest master", "Mandatory for Trusted"),
        ],
        columns=["Feature", "Suggested_Weight", "Definition", "Routing_Effect"],
    )


def routing_rules() -> pd.DataFrame:
    return pd.DataFrame(
        [
            (
                "Trusted_Dashboard",
                "surgical_scope=Y AND master_reference_validation=Y AND product_evidence sufficient AND no conflict/exclusion AND no unsupported generic token",
                "Family-tier rows require full latest master key and family/manufacturer or curated alias support. Category-tier rows require latest category key and strong product evidence.",
            ),
            (
                "Review_Queue",
                "surgical-looking but weak evidence OR semantic/fuzzy-only OR generic-token driven OR Extended HS OR high-value uncertain OR reference/alias gap",
                "Review rows must carry evidence terms, candidate tuple, reason code, and suggested alias/rule/reference action.",
            ),
            (
                "Excluded_Unmapped",
                "no surgical evidence OR strong non-surgical evidence with no countervailing surgical evidence",
                "Dental, veterinary, cosmetic, lab/IVD, imaging/radiotherapy-only, ophthalmic-only, donation/humanitarian, and non-surgical capital stay out of Trusted.",
            ),
        ],
        columns=["Output_Tier", "Exact_Routing_Logic", "Notes"],
    )


def llm_agents() -> pd.DataFrame:
    schema = (
        "{UniqueID, decision, proposed_mapping_tuple, confidence, evidence_terms, negative_evidence_terms, "
        "reason_code, master_reference_status, human_review_required, suggested_alias_update, suggested_rule_update}"
    )
    rows = [
        ("Scope Agent", "Classify surgical/non-surgical/ambiguous", "High-value Review and Excluded surgical-keyword rows", "Raw text, HS, importer/exporter, deterministic candidates", schema, "Must cite evidence and cannot set Trusted without master validation", "Over-including capital equipment"),
        ("Resolver Agent", "Choose best mapping among top candidates", "Multiple candidates close or evidence conflict", "Top-k candidates with scores and master status", schema, "Must choose from candidates or request reference update", "Hallucinating tuple not in master"),
        ("Conflict Agent", "Detect exclusion conflicts", "Trusted or candidate rows with conflict keywords", "Row text, proposed mapping, conflict terms", schema, "Any conflict blocks Trusted unless manual override", "Over-blocking valid surgical rows with generic words"),
        ("Recall Hunter Agent", "Find missed surgical clusters and reusable rules", "Clusters from Review and Excluded surgical screens", "Cluster samples, values, existing candidates", schema, "Must suggest alias/rule with evidence examples", "Suggesting non-reusable one-off decisions"),
        ("QC Agent", "Independent Trusted_Dashboard review", "Generic-token rows, high-value Trusted rows, risk screens", "Trusted rows plus evidence and reference status", schema, "Find false positives without weakening master validation", "Excessive manual review escalation"),
    ]
    return pd.DataFrame(
        rows,
        columns=["Agent", "Purpose", "Trigger_Condition", "Input_Fields", "Output_JSON_Schema", "Acceptance_Criteria", "Failure_Modes"],
    )


def gold_label_design() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("100% precision-risk Trusted rows", "All rows with conflict/generic-token risk terms", "Measure false positives and tune negative terms."),
            ("100% Review_Queue rows >= USD 50K", "All high-value review rows", "Resolve value concentration and calibrate capture recall."),
            ("100% Extended HS rows >= USD 25K", "All high-value HS 3006/extended surgical rows", "Support business scope decision."),
            ("Stratified Excluded surgical-keyword sample", "At least 200 rows or all high-value clusters", "Estimate false-negative value and recall gap."),
            ("Stratified clean Trusted rows", "By segment/product/player", "Estimate precision beyond risk screens."),
            ("Random sample from each QA_Status bucket", "Minimum 30 per bucket where possible", "Catch bucket-specific logic errors."),
            ("Metrics", "Trusted precision row/value, Trusted recall row/value, capture recall, false-positive value, false-negative value, segment precision/recall, review burden, repeat correction rate", "Compare every experiment A1-A10 against A0."),
        ],
        columns=["Sampling_Stratum", "Rows_to_Label_First", "Purpose_and_Metric"],
    )


def final_recommendations() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("Implement immediately", "Candidate_Table, alias tables, evidence scoring, Extended_Surgical_Decision, precision-risk negative terms, active learning log."),
            ("Test in controlled experiment", "Fuzzy matching, char/word TF-IDF, semantic retrieval, LLM resolver, LLM recall hunter, LLM conflict/QC."),
            ("Defer", "Automatic promotion of semantic-only or LLM-only candidates to Trusted_Dashboard."),
            ("Avoid", "One-shot LLM raw-row-to-final-mapping and any Trusted row that fails latest master validation."),
        ],
        columns=["Recommendation_Category", "Items"],
    )


def candidate_table_design() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("UniqueID", "RawData row identifier", "Audit join key"),
            ("candidate_rank", "1..N candidate order", "Reviewer sees alternatives"),
            ("candidate_segment/subsegment/product/player/family", "Proposed tuple", "Must validate before Trusted"),
            ("source_method", "exact / alias / fuzzy / TF-IDF / semantic / HS-rule / LLM", "Separates deterministic and probabilistic sources"),
            ("product_score/family_score/manufacturer_score", "Evidence scores", "Explain positive mapping support"),
            ("fuzzy_score/tfidf_score/semantic_score/hs_score", "Retrieval evidence", "Recall and ranking"),
            ("exclusion_score/generic_token_risk", "Risk evidence", "Blocks or routes to Review"),
            ("master_validation_status", "latest full key / latest category / gap / generic-only", "Trusted gate"),
            ("final_candidate_score", "Weighted score", "Routing and priority"),
            ("routing_decision", "Trusted / Review / Exclude", "Human-readable final action"),
        ],
        columns=["Field", "Definition", "Purpose"],
    )


def alias_table_design() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("Manufacturer_Alias", "B. Braun, BBraun, Nipro, Medtronic, Artivion, CryoLife, Olympus, Fujifilm, Karl Storz", "Map messy shipper/importer/manufacturer text to Player"),
            ("Family_Alias", "ON-X, SafeSheath, Introcan, Resolute Onyx, Vicryl, Prolene, Polysorb, Surgicryl, Surgipro", "Map model/family variants to latest master family"),
            ("Product_Alias", "stent system, vascular stent, cannulae, canula, PTCA balloon, endoscopy system, dialyzer", "Map phrase to canonical product/category evidence"),
            ("Abbreviation_Alias", "DES, BMS, PTCA, CRT-D, ICD, ON-X", "Resolve common abbreviations"),
            ("Customs_Phrase_Alias", "video endoscopy system, hollow fiber hemodialyzer, coronary stent system", "Handle customs phrasing"),
            ("Misspelling_Alias", "opthalmic, haemodialysis, canula, hyphen variants", "Improve lexical recall"),
            ("Negative_Terms", "hydrafacial, refrigerator, body warmer, lithotripter, tomography, OCT, ECG machine", "Prevent repeat false positives"),
            ("Generic_Tokens", "Light Source, Target, Sprinter, Current, Volt, Celsius, Express, Hydra, Zero, Trilogy, Bio 1", "Require supporting evidence"),
            ("HS_Scope_Rules", "core HS vs Extended HS 3006 vs out-of-scope HS", "Make business-scope decisions explicit"),
        ],
        columns=["Table", "Examples_to_Add", "Purpose"],
    )


def write_review_workbook(tables: dict[str, pd.DataFrame], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer_kwargs = {"engine": "xlsxwriter", "engine_kwargs": {"options": {"strings_to_urls": False}}}
    with pd.ExcelWriter(output_path, **writer_kwargs) as writer:
        for sheet_name, table in tables.items():
            safe = table.copy()
            if safe.empty:
                safe = pd.DataFrame({"Message": [f"No rows for {sheet_name}"]})
            safe.to_excel(writer, sheet_name=sheet_name[:31], index=False)
            workbook = writer.book
            worksheet = writer.sheets[sheet_name[:31]]
            header_fmt = workbook.add_format({"bold": True, "bg_color": "#D9EAF7", "border": 1})
            money_fmt = workbook.add_format({"num_format": "$#,##0"})
            count_fmt = workbook.add_format({"num_format": "#,##0"})
            for col_idx, col_name in enumerate(safe.columns):
                worksheet.write(0, col_idx, col_name, header_fmt)
                values = [
                    "" if pd.isna(value) else str(value)
                    for value in safe.iloc[:, col_idx].head(200).tolist()
                ]
                width = min(max([len(str(col_name)), *[len(value) for value in values]]) + 2, 70)
                fmt = money_fmt if "Value_USD" in str(col_name) or str(col_name).endswith("_USD") else count_fmt if col_name in {"Rows", "Rows_or_Value"} else None
                worksheet.set_column(col_idx, col_idx, width, fmt)
            worksheet.freeze_panes(1, 0)
            worksheet.autofilter(0, 0, len(safe), len(safe.columns) - 1)


def build_tables(raw: pd.DataFrame, qa_sheets: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    metadata = pd.DataFrame(
        [
            ("Generated_Timestamp", datetime.now().isoformat(timespec="seconds")),
            ("Source_Workbook", str(DEFAULT_WORKBOOK)),
            ("Source_QA_Workbook", str(DEFAULT_QA)),
            ("Master_Reference", "Surg_Brand_model_list_Master 03July26.xlsx"),
            ("Review_Principle", "Recall is priority; Trusted_Dashboard remains master-valid and defensible; uncertainty routes to Review_Queue."),
        ],
        columns=["Field", "Value"],
    )
    return {
        "Executive_Summary": executive_summary(raw),
        "Baseline_Assessment": pd.concat([metadata, baseline_assessment(raw, qa_sheets)], ignore_index=True),
        "Tier_Summary": tier_summary(raw),
        "QA_Status_Summary": qa_status_summary(raw),
        "Review_Burden": review_burden(raw),
        "Latest_Ref_Gaps": latest_reference_gaps(raw),
        "Potential_Missed": potential_missed_rows(raw),
        "Extended_Decision": extended_hs_rows(raw, qa_sheets),
        "Precision_Risks": precision_risk_rows(raw),
        "Excluded_Candidates": excluded_candidates(raw),
        "Missing_Capabilities": missing_capabilities(),
        "Experiment_Matrix": experiment_matrix(),
        "Accuracy_Plan": accuracy_plan(),
        "Efficiency_Plan": efficiency_plan(),
        "Evidence_Model": evidence_model(),
        "Routing_Rules": routing_rules(),
        "LLM_Agents": llm_agents(),
        "Gold_Label_Design": gold_label_design(),
        "Final_Recommendations": final_recommendations(),
        "Candidate_Table_Design": candidate_table_design(),
        "Alias_Table_Design": alias_table_design(),
    }


def run(workbook_path: Path, qa_path: Path, output_path: Path) -> None:
    raw = pd.read_excel(workbook_path, sheet_name=RAW_SHEET, dtype=str).fillna("")
    qa_sheets = pd.read_excel(qa_path, sheet_name=None, dtype=str) if qa_path.exists() else {}
    tables = build_tables(raw, qa_sheets)
    write_review_workbook(tables, output_path)
    print(f"[workflow-review] wrote {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--qa", type=Path, default=DEFAULT_QA)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(args.workbook, args.qa, args.output)
