"""Build retrieval objects from the surgical master and governance seed rules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .normalize import EXCLUSION_TERMS_BY_CATEGORY, normalize_text


MASTER_SHEET = "Updated"

OBJECT_COLUMNS = [
    "object_id",
    "object_type",
    "canonical_target_id",
    "canonical_manufacturer",
    "manufacturer_aliases",
    "brand",
    "product_family",
    "model",
    "segment_path",
    "in_scope_flag",
    "common_import_terms",
    "exclusion_terms",
    "source_reference",
    "reference_version",
    "review_status",
    "retrieval_text",
    "metadata_json",
    "exclusion_category",
    "term",
    "decision_default",
    "strength",
    "alias_text",
    "valid_product_categories",
    "source_text",
    "normalized_source_text",
    "country",
    "year",
    "source_file",
    "reason",
    "default_decision",
]


MANUFACTURER_ALIASES = {
    "Medtronic": ["Covidien", "Tyco Healthcare", "US Surgical", "Valleylab"],
    "J&J": ["Johnson and Johnson", "Ethicon", "Depuy", "Cordis", "Biosense Webster"],
    "B. Braun": ["B Braun", "Aesculap", "B Braun Melsungen"],
    "Boston Scientific": ["BSC", "Boston Scientific Corporation"],
    "Abbott": ["Abbott Vascular", "St Jude Medical", "St. Jude Medical"],
    "Zimmer Biomet": ["Zimmer", "Biomet", "Zimmer Dental"],
    "Olympus": ["Olympus Medical", "Olympus Corporation"],
    "Terumo": ["Terumo Medical", "Terumo Corporation"],
    "Nipro": ["Nipro Medical"],
    "Nikkiso": ["Nikkiso Co"],
}

PRODUCT_ALIAS_SEEDS = [
    ("DES", "drug eluting stent", "Cardiovascular > Coronary Intervention > DES"),
    ("BMS", "bare metal stent", "Cardiovascular > Coronary Intervention > BMS"),
    ("PTCA", "percutaneous transluminal coronary angioplasty balloon", "Cardiovascular > Coronary Intervention > PTCA Balloons"),
    ("CRT-D", "cardiac resynchronization therapy defibrillator", "Cardiac Rhythm Management"),
    ("ICD", "implantable cardioverter defibrillator", "Cardiac Rhythm Management"),
    ("TAVI", "transcatheter aortic valve implantation", "Structural Heart"),
    ("TAVR", "transcatheter aortic valve replacement", "Structural Heart"),
    ("ON-X", "prosthetic mechanical heart valve", "Cardiovascular > Heart Valves"),
    ("Vicryl", "absorbable suture", "Wound Closure > Sutures"),
    ("Prolene", "non absorbable suture", "Wound Closure > Sutures"),
    ("Polysorb", "absorbable suture", "Wound Closure > Sutures"),
    ("Surgicryl", "absorbable suture", "Wound Closure > Sutures"),
    ("PDO", "polydioxanone suture", "Wound Closure > Sutures"),
    ("Polydioxanone", "pds pdo absorbable suture", "Wound Closure > Sutures"),
    ("Cannula", "cannula cannulae canula", "Vascular Access / Surgical Consumables"),
    ("Catheter", "catheter cath catheterization", "Vascular Access / Cardiovascular"),
    ("Stent system", "coronary stent system vascular stent implantable stent", "Cardiovascular > Stents"),
    ("Endoscope", "endoscopy system video endoscopy laparoscopy endosurgery", "MIS / Endoscopy"),
    ("Autotransfusion", "cell saver blood recovery autotransfusion", "Cardiopulmonary / Blood Management"),
    ("Artificial disc", "cervical disc spinal disc artificial disc implant", "Orthopedics > Spine"),
    ("Guiding catheter", "guide catheter guiding catheter introducer sheath", "Cardiovascular > Access"),
]

AMBIGUOUS_SCOPE_EXAMPLES = [
    ("surgical implant kit dental", "implant kit", "dental implant", "Dental wording conflicts with implant wording."),
    ("aesthetic cannula for filler injection", "cannula", "cosmetic aesthetic", "Cannula is surgical-looking but filler use is out of scope."),
    ("pathology surgical blade laboratory", "surgical blade", "laboratory", "Surgical term appears in a lab context."),
    ("lab surgical forceps specimen handling", "forceps", "laboratory", "Instrument term appears in lab context."),
    ("ophthalmic surgical injector intraocular lens", "injector", "ophthalmic intraocular", "Ophthalmic scope requires explicit business decision."),
]

NEGATIVE_EXAMPLE_TEXT = {
    "dental": [
        "dental implant surgical kit titanium abutment orthodontic endodontic",
        "intraoral scanner for dental clinic orthodontic treatment",
    ],
    "veterinary": [
        "veterinary suture pack for animal surgery equine canine bovine use",
        "animal surgical instruments for veterinary hospital",
    ],
    "cosmetic_aesthetic": [
        "cosmetic filler cannula aesthetic injection needle dermal filler",
        "hydra facial beauty device aesthetic skin treatment",
    ],
    "ivd_lab": [
        "diagnostic kit reagent assay calibrator laboratory analyzer ivd",
        "coagulation meter hemochron signature elite diagnostic testing",
    ],
    "imaging_radiotherapy": [
        "ct scanner tomography ultrasound machine imaging equipment",
        "linear accelerator cyclotron radiotherapy machine",
    ],
    "pharma_drug": [
        "pharmaceutical tablet capsule vaccine drug injection vial",
        "medicine syrup pharmaceutical finished dosage form",
    ],
    "ppe_general_supply": [
        "medical gloves mask gown ppe disposable hospital supply",
        "blood bag syringe only infusion set general medical consumables",
    ],
    "furniture_capital": [
        "hospital bed refrigerator body warmer ecg machine defibrillator",
        "heart lung machine centrifugal pump rotaflow capital equipment",
    ],
    "ophthalmic": [
        "intraocular lens ophthalmic visco surgical device iol",
        "ophthalmic lens contact lens optical product",
    ],
}


def _clean(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() == "nan":
        return ""
    return text


def _object(**kwargs: Any) -> dict[str, Any]:
    row = {col: "" for col in OBJECT_COLUMNS}
    row.update(kwargs)
    return row


def _canonical_target_id(segment: str, subsegment: str, product: str, player: str, family: str) -> str:
    parts = [segment, subsegment, product, player, family]
    return "|".join(normalize_text(part) for part in parts)


def load_master(reference_path: str | Path, sheet_name: str = MASTER_SHEET) -> pd.DataFrame:
    reference_path = Path(reference_path)
    return pd.read_excel(reference_path, sheet_name=sheet_name, engine="openpyxl")


def build_retrieval_objects(
    reference_path: str | Path,
    output_path: str | Path | None = None,
    reference_version: str = "03July26",
) -> pd.DataFrame:
    """Create auditable retrieval objects from master, aliases, and exclusions."""

    reference_path = Path(reference_path)
    master = load_master(reference_path)
    rows: list[dict[str, Any]] = []

    for idx, record in master.fillna("").iterrows():
        segment = _clean(record.get("Segment"))
        subsegment = _clean(record.get("Sub-segment"))
        product = _clean(record.get("Product"))
        player = _clean(record.get("Player"))
        family = _clean(record.get("Model/ Family Name"))
        if not (segment and subsegment and product):
            continue
        target_id = _canonical_target_id(segment, subsegment, product, player, family)
        segment_path = " > ".join(part for part in (segment, subsegment, product) if part)
        aliases = MANUFACTURER_ALIASES.get(player, [])
        import_terms = " ".join(part for part in (product, family, player, " ".join(aliases)) if part)
        retrieval_text = (
            "Object type: canonical_tuple\n"
            f"Canonical manufacturer: {player}\n"
            f"Manufacturer aliases: {', '.join(aliases)}\n"
            f"Brand/product family: {family}\n"
            f"Product category: {product}\n"
            f"Segment path: {segment_path}\n"
            "In scope: yes\n"
            f"Common import terms: {import_terms}\n"
            "Reference version: latest approved master"
        )
        rows.append(
            _object(
                object_id=f"canonical_tuple:{idx}",
                object_type="canonical_tuple",
                canonical_target_id=target_id,
                canonical_manufacturer=player,
                manufacturer_aliases="; ".join(aliases),
                product_family=family,
                model=family,
                segment_path=segment_path,
                in_scope_flag="yes",
                common_import_terms=import_terms,
                source_reference=str(reference_path),
                reference_version=reference_version,
                review_status="approved_latest_master",
                retrieval_text=retrieval_text,
                metadata_json=json.dumps(
                    {
                        "Segment": segment,
                        "Sub-segment": subsegment,
                        "Product": product,
                        "Player": player,
                        "Model/ Family Name": family,
                        "row_number": int(idx) + 2,
                    },
                    ensure_ascii=True,
                    sort_keys=True,
                ),
            )
        )

    for player, aliases in MANUFACTURER_ALIASES.items():
        for alias in aliases:
            retrieval_text = (
                "Object type: manufacturer_alias\n"
                f"Alias: {alias}\n"
                f"Canonical manufacturer: {player}\n"
                "Review status: approved seed alias"
            )
            rows.append(
                _object(
                    object_id=f"manufacturer_alias:{normalize_text(player)}:{normalize_text(alias)}",
                    object_type="manufacturer_alias",
                    alias_text=alias,
                    canonical_manufacturer=player,
                    source_reference="seed_alias_rules",
                    reference_version=reference_version,
                    review_status="approved_seed",
                    retrieval_text=retrieval_text,
                )
            )

    for alias, canonical, segment_path in PRODUCT_ALIAS_SEEDS:
        retrieval_text = (
            "Object type: product_family_alias\n"
            f"Alias terms: {alias}; {canonical}\n"
            f"Canonical product family: {canonical}\n"
            f"Segment path: {segment_path}\n"
            "Review status: approved seed alias"
        )
        rows.append(
            _object(
                object_id=f"product_family_alias:{normalize_text(alias)}",
                object_type="product_family_alias",
                alias_text=alias,
                product_family=canonical,
                segment_path=segment_path,
                source_reference="seed_alias_rules",
                reference_version=reference_version,
                review_status="approved_seed",
                retrieval_text=retrieval_text,
            )
        )

    for category, terms in EXCLUSION_TERMS_BY_CATEGORY.items():
        for term in sorted(terms):
            rows.append(
                _object(
                    object_id=f"hard_exclusion_term:{category}:{normalize_text(term)}",
                    object_type="hard_exclusion_term",
                    exclusion_category=category,
                    term=term,
                    decision_default="exclude_or_review",
                    strength="hard",
                    source_reference="seed_exclusion_rules",
                    reference_version=reference_version,
                    review_status="approved_seed",
                    retrieval_text=f"Object type: hard_exclusion_term\nCategory: {category}\nTerm: {term}",
                )
            )

    for category, examples in NEGATIVE_EXAMPLE_TEXT.items():
        for i, text in enumerate(examples, start=1):
            rows.append(
                _object(
                    object_id=f"negative_vector_example:{category}:{i}",
                    object_type="negative_vector_example",
                    exclusion_category=category,
                    source_text=text,
                    normalized_source_text=normalize_text(text),
                    reason=f"{category} products are outside the default surgical dashboard scope.",
                    decision_default="exclude_or_review",
                    source_reference="seed_negative_examples",
                    reference_version=reference_version,
                    review_status="approved_seed",
                    retrieval_text=(
                        "Object type: negative_vector_example\n"
                        f"Source text: {text}\n"
                        f"Exclusion category: {category}\n"
                        "Decision: exclude or review\n"
                        f"Reason: {category} products are outside default scope"
                    ),
                )
            )

    for i, (text, positive, negative, reason) in enumerate(AMBIGUOUS_SCOPE_EXAMPLES, start=1):
        rows.append(
            _object(
                object_id=f"ambiguous_scope_example:{i}",
                object_type="ambiguous_scope_example",
                source_text=text,
                normalized_source_text=normalize_text(text),
                common_import_terms=positive,
                exclusion_terms=negative,
                reason=reason,
                default_decision="review",
                source_reference="seed_ambiguous_scope_examples",
                reference_version=reference_version,
                review_status="approved_seed",
                retrieval_text=(
                    "Object type: ambiguous_scope_example\n"
                    f"Source text: {text}\n"
                    f"Possible positive scope: {positive}\n"
                    f"Possible negative scope: {negative}\n"
                    f"Reason for ambiguity: {reason}\n"
                    "Default decision: review"
                ),
            )
        )

    objects = pd.DataFrame(rows, columns=OBJECT_COLUMNS)
    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        objects.to_csv(output_path, index=False, encoding="utf-8-sig")
    return objects
