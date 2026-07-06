"""Text normalization and feature extraction for retrieval experiments.

The functions in this module are intentionally conservative. They preserve the
raw shipment text in audit outputs while creating normalized fields used by the
experimental retrievers.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable


TEXT_COLUMNS = (
    "Detailed_Product",
    "Product",
    "Product_V0",
    "Manufacturer",
    "Family",
    "Model",
    "Importer",
    "Exporter",
    "Country_of_Exporters",
    "HS_Code",
    "HS4",
    "Segment",
    "Sub-segment",
)

SURGICAL_TERMS = {
    "stent",
    "stents",
    "catheter",
    "catheters",
    "guidewire",
    "guidewires",
    "sheath",
    "sheaths",
    "introducer",
    "introducers",
    "balloon",
    "balloons",
    "cannula",
    "cannulae",
    "canula",
    "trocar",
    "trocars",
    "suture",
    "sutures",
    "vicryl",
    "prolene",
    "polysorb",
    "surgicryl",
    "pdo",
    "polydioxanone",
    "mesh",
    "hemostat",
    "hemostats",
    "clip",
    "clips",
    "stapler",
    "staplers",
    "reload",
    "cartridge",
    "endoscope",
    "endoscopy",
    "laparoscopy",
    "laparoscopic",
    "arthroscopy",
    "dialyzer",
    "dialysis",
    "hemodialysis",
    "valve",
    "valves",
    "prosthetic",
    "on-x",
    "implant",
    "implants",
    "orthopedic",
    "orthopaedic",
    "spinal",
    "cervical",
    "disc",
    "autotransfusion",
    "cell saver",
    "blood recovery",
    "ptca",
    "des",
    "bms",
    "crt-d",
    "icd",
    "tavi",
    "tavr",
}

GENERIC_TOKENS = {
    "surgical",
    "medical",
    "device",
    "devices",
    "kit",
    "kits",
    "system",
    "systems",
    "instrument",
    "instruments",
    "accessory",
    "accessories",
    "premium",
    "standard",
    "advanced",
    "light",
    "disposable",
    "hospital",
    "product",
    "products",
    "essential",
    "gateway",
    "march",
    "zenith",
    "cirrus",
    "legion",
    "strata",
    "therapy",
    "target",
    "solar",
    "sprinter",
    "arrive",
    "current",
    "volt",
    "maestro",
    "imager",
    "hybrid",
    "elite",
    "unity",
    "celsius",
    "express",
    "hydra",
    "zero",
    "xtra",
    "masters",
    "image processor",
    "velocity alpha",
}

EXCLUSION_TERMS_BY_CATEGORY = {
    "dental": {
        "dental",
        "orthodontic",
        "endodontic",
        "abutment",
        "tooth",
        "teeth",
        "intraoral",
        "dentistry",
    },
    "veterinary": {
        "veterinary",
        "vet use",
        "animal",
        "pet",
        "equine",
        "canine",
        "feline",
        "bovine",
    },
    "cosmetic_aesthetic": {
        "cosmetic",
        "aesthetic",
        "dermal",
        "filler",
        "beauty",
        "mesotherapy",
        "hydra facial",
        "hydrafacial",
    },
    "ivd_lab": {
        "ivd",
        "reagent",
        "assay",
        "calibrator",
        "control",
        "diagnostic kit",
        "laboratory",
        "lab ",
        "analyzer",
        "coagulation meter",
        "hemochron",
    },
    "imaging_radiotherapy": {
        "linear accelerator",
        "linar accelerator",
        "cyclotron",
        "radiotherapy",
        "tomography",
        "oct",
        "ct scanner",
        "mri",
        "ultrasound machine",
        "angiography machine",
        "laser imager",
        "dry imager",
        "scanner",
        "fru detector",
    },
    "pharma_drug": {
        "tablet",
        "capsule",
        "vaccine",
        "pharmaceutical",
        "drug",
        "medicine",
        "syrup",
        "injection vial",
    },
    "ppe_general_supply": {
        "mask",
        "glove",
        "gown",
        "ppe",
        "sanitizer",
        "syringe only",
        "blood bag",
        "infusion set",
        "general medical supply",
    },
    "furniture_capital": {
        "hospital bed",
        "wheelchair",
        "refrigerator",
        "freezer",
        "body warmer",
        "ecg machine",
        "defibrillator",
        "heart lung machine",
        "centrifugal pump",
        "rotaflow",
    },
    "ophthalmic": {
        "ophthalmic",
        "intraocular",
        "visco-surgical",
        "viscosurgical",
        "iol",
        "contact lens",
    },
    "donation": {
        "donation",
        "humanitarian",
        "aid supplies",
        "relief goods",
    },
}


_PUNCT_RE = re.compile(r"[^a-z0-9./+\- ]+")
_SPACE_RE = re.compile(r"\s+")
_MODEL_RE = re.compile(r"\b[a-z]{0,4}\d{2,}[a-z0-9./+\-]*\b|\b\d+[a-z]{1,4}\b")


@dataclass
class RowFeatures:
    source_text: str
    normalized_text: str
    tokens: list[str] = field(default_factory=list)
    extracted_manufacturer_terms: list[str] = field(default_factory=list)
    extracted_product_terms: list[str] = field(default_factory=list)
    extracted_model_terms: list[str] = field(default_factory=list)
    detected_exclusion_terms: list[str] = field(default_factory=list)
    detected_exclusion_categories: list[str] = field(default_factory=list)
    detected_generic_terms: list[str] = field(default_factory=list)
    detected_surgical_terms: list[str] = field(default_factory=list)
    hs_code: str = ""
    feature_json: str = "{}"


def normalize_text(value: object) -> str:
    """Return lowercase ASCII-ish normalized text for matching."""

    if value is None:
        return ""
    text = str(value)
    if text.lower() == "nan":
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = text.replace("&", " and ")
    text = text.replace("_", " ")
    text = text.replace(",", " ")
    text = text.replace(";", " ")
    text = _PUNCT_RE.sub(" ", text)
    text = _SPACE_RE.sub(" ", text).strip()
    return text


def tokenize(text: str) -> list[str]:
    return [tok for tok in text.split() if tok]


def char_ngrams(text: str, n: int = 4) -> set[str]:
    compact = re.sub(r"\s+", " ", text.strip())
    if len(compact) <= n:
        return {compact} if compact else set()
    return {compact[i : i + n] for i in range(0, len(compact) - n + 1)}


def phrase_hits(text: str, terms: Iterable[str]) -> list[str]:
    hits: list[str] = []
    padded = f" {text} "
    for term in terms:
        norm = normalize_text(term)
        if not norm:
            continue
        if " " in norm:
            if norm in text:
                hits.append(term)
        elif f" {norm} " in padded:
            hits.append(term)
    return sorted(set(hits), key=lambda x: (len(str(x)), str(x)))


def build_source_search_text(row: dict) -> str:
    parts: list[str] = []
    for col in TEXT_COLUMNS:
        value = row.get(col, "")
        if value is None:
            continue
        text = str(value).strip()
        if text and text.lower() != "nan":
            parts.append(text)
    return " | ".join(parts)


def extract_features(row: dict) -> RowFeatures:
    source_text = build_source_search_text(row)
    normalized = normalize_text(source_text)
    tokens = tokenize(normalized)
    surgical_hits = phrase_hits(normalized, SURGICAL_TERMS)
    generic_hits = phrase_hits(normalized, GENERIC_TOKENS)

    exclusion_terms: list[str] = []
    exclusion_categories: list[str] = []
    for category, terms in EXCLUSION_TERMS_BY_CATEGORY.items():
        hits = phrase_hits(normalized, terms)
        if hits:
            exclusion_categories.append(category)
            exclusion_terms.extend(hits)

    model_terms = sorted(set(_MODEL_RE.findall(normalized)))
    product_terms = sorted(set(surgical_hits))
    manufacturer_terms = []
    for col in ("Manufacturer", "Exporter", "Importer"):
        value = row.get(col, "")
        norm = normalize_text(value)
        if norm:
            manufacturer_terms.append(norm[:120])

    hs_code = str(row.get("HS_Code", row.get("HS4", ""))).strip()
    payload = {
        "surgical_terms": surgical_hits,
        "generic_terms": generic_hits,
        "exclusion_terms": sorted(set(exclusion_terms)),
        "exclusion_categories": sorted(set(exclusion_categories)),
        "model_terms": model_terms,
        "hs_code": hs_code,
    }
    return RowFeatures(
        source_text=source_text,
        normalized_text=normalized,
        tokens=tokens,
        extracted_manufacturer_terms=sorted(set(manufacturer_terms)),
        extracted_product_terms=product_terms,
        extracted_model_terms=model_terms,
        detected_exclusion_terms=sorted(set(exclusion_terms)),
        detected_exclusion_categories=sorted(set(exclusion_categories)),
        detected_generic_terms=generic_hits,
        detected_surgical_terms=surgical_hits,
        hs_code=hs_code,
        feature_json=json.dumps(payload, ensure_ascii=True, sort_keys=True),
    )
