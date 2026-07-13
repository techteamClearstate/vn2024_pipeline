"""Batch remap surgical import workbooks with auditable recall-focused routing.

This script applies the reference-compliant surgical-only workflow to the six
current country/year mapped workbooks and publishes the current versions to the
shared delivery folder. It keeps high-confidence trusted rows strict while
moving surgical-looking uncertain rows into Review_Queue instead of silently
leaving them excluded.
"""

from __future__ import annotations

import argparse
import gc
import json
import math
import os
import re
import shutil
import sys
import time
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import vietnam_fy2024_workflow_improvement as wf  # noqa: E402
from config import settings as cfg  # noqa: E402
from src.step3_map import apply_reference_gate  # noqa: E402


INPUT_DIR = ROOT / "outputs"
OUT_DIR = ROOT / "outputs" / "remapped_current"
REPORT_DIR = OUT_DIR / "reports"
MASTER_PATH = ROOT / "reference" / "brand_model" / "Surg_Brand_model_list_Master_03July26.xlsx"
XLSX_TMP_DIR = Path(os.environ.get("SURGICAL_XLSX_TMPDIR", r"D:\vn2024_xlsx_tmp"))
ARCHIVE_DIR = ROOT / "90_archive_deprecated" / "shared_publish_cleanup"

EXPECTED_FILES = [
    "Pakistan_FY2024_ML_Map_Mapped.xlsx",
    "Pakistan_FY2025_ML_Map_Mapped.xlsx",
    "India_FY2024_ML_Map_Mapped.xlsx",
    "India_FY2025_ML_Map_Mapped.xlsx",
    "Vietnam_FY2024_ML_Map_Mapped.xlsx",
    "Vietnam_FY2025_ML_Map_Mapped.xlsx",
]

SHARED_DIR_CANDIDATES = [
    Path(
        r"G:\Shared drives\New EIU Gateway\0. Gateway Ops & Databases\Import Data Master\6. Workflow\Surgicals\Claude code\1. Mapped Results"
    ),
    Path(
        r"G:\共享云端硬盘\New EIU Gateway\0. Gateway Ops & Databases\Import Data Master\6. Workflow\Surgicals\Claude code\1. Mapped Results"
    ),
]

EXCEL_MAX_DATA_ROWS = 1_048_575
VALUE_COL = "Total_Value_USD"
QUANTITY_COL = "Quantity"
TIMESTAMP = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

QA_SILENT_SURGICAL = "Review - candidate surgical evidence"
QA_SURGICAL_CONFLICT = "Review - surgical evidence with exclusion conflict"
QA_CATEGORY_WEAK = "Review - category evidence insufficient"
QA_DATE_MONTH = "Review - date-month token risk"
QA_PHARMA = "Review - pharmaceutical/vaccine conflict"
QA_MARCH = "Review - APT March date/token rule"
QA_EXTENDED_FALSE_POSITIVE = "Excluded - false positive extended scope"
QA_OPHTHALMIC_FALSE_POSITIVE = "Excluded - ophthalmic/imaging false positive"

RAW_SIGNAL_COLUMNS = [
    "Detailed_Product",
    "Product_Description",
    "Description",
    "Importer",
    "Exporter",
    "HS_Code",
    "HS4",
    "Manufacturer",
    "Family",
    "Segment",
    "Sub-segment",
    "Product_V0",
    "Brand",
    "Model",
]

# Family aliases are learned/adjudicated against the source product description,
# not against mapping columns that a previous run already populated.  Keeping
# this list deliberately narrow prevents an old Family/Manufacturer value from
# becoming self-confirming evidence in a later remap.
ALIAS_SOURCE_COLUMNS = [
    "Detailed_Product",
    "Product_Description",
    "Description",
]

MAX_CANDIDATE_EXTRA_ROWS_PER_METHOD = 25_000
MAX_CANDIDATE_ROWS = 150_000
SOURCE_TEXT_NORM_ATTR = "_surgical_source_text_norm_cache"
SOURCE_TEXT_NORM_CACHE: dict[int, tuple[pd.Index, pd.Series]] = {}


def log_step(message: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}", flush=True)

DATE_MONTH_TOKENS = [
    "jan",
    "january",
    "feb",
    "february",
    "mar",
    "march",
    "apr",
    "april",
    "may",
    "jun",
    "june",
    "jul",
    "july",
    "aug",
    "august",
    "sep",
    "sept",
    "september",
    "oct",
    "october",
    "nov",
    "november",
    "dec",
    "december",
]

DATE_MONTH_RE = re.compile(r"\b(?:" + "|".join(map(re.escape, DATE_MONTH_TOKENS)) + r")\b", re.I)

CONTROLLED_GENERIC_TOKENS = sorted(
    {
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
        "Signia",
        "Stride",
        "Enterprise",
        "Concerto",
        "Legion",
        "Lens",
        "Exacta",
        *DATE_MONTH_TOKENS,
    },
    key=str.lower,
)


def regex_term(term: str) -> str:
    return re.escape(wf.norm_text(term)).replace(r"\ ", r"\s+")


CONTROLLED_GENERIC_RE = re.compile(
    r"\b(?:" + "|".join(regex_term(term) for term in CONTROLLED_GENERIC_TOKENS) + r")\b",
    re.I,
)

DATE_CONTEXT_RE = re.compile(
    r"\b(?:mfg|manufactur(?:e|ed|ing)|production|prod|expiry|expiration|exp|dated?|date|lot|batch|"
    r"invoice|registration|reg|license|valid|validity|import\s+permit)\b.{0,35}\b(?:"
    + "|".join(map(re.escape, DATE_MONTH_TOKENS))
    + r")\b|\b(?:"
    + "|".join(map(re.escape, DATE_MONTH_TOKENS))
    + r")\b.{0,35}\b(?:mfg|manufactur(?:e|ed|ing)|production|prod|expiry|expiration|exp|dated?|date|lot|batch|"
    r"invoice|registration|reg|license|valid|validity|import\s+permit)\b",
    re.I,
)

DATE_PATTERN_RE = re.compile(
    r"\b(?:\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{4}[-/]\d{1,2}[-/]\d{1,2})\b|"
    r"\b(?:"
    + "|".join(map(re.escape, DATE_MONTH_TOKENS))
    + r")\s+\d{1,2},?\s+\d{4}\b",
    re.I,
)

OPHTHALMIC_IMAGING_RE = re.compile(
    r"\b(?:fundus\s+camera|retinal\s+camera|camera\s+without\s+pupil\s+dilation|nidek|afc[-\s]?330|"
    r"ophthalmic|intraocular|ocular|retina|retinal|phaco|viscoelastic|optical\s+coherence|"
    r"oct[-\s]?\d*|tomograph(?:y|ic)|diagnostic\s+camera|medical\s+imaging\s+camera|imaging\s+system)\b",
    re.I,
)

TRUE_EXTENDED_SURGICAL_RE = re.compile(
    r"\b(?:vicryl|prolene|polysorb|surgicryl|pdo|polydioxanone|sutures?|mesh|bone\s+cement|"
    r"floseal|hemostats?|wound|surgipro|demesorb|surgical\s+needle|skin\s+stapler|ligature|"
    r"hernia\s+mesh)\b",
    re.I,
)

FALSE_NEGATIVE_SURGICAL_RE = re.compile(
    r"\b(?:endoscopy|endoscope|laparoscopy|laparoscopic|hemodialysis|dialyzer|dialysis|"
    r"prosthetic\s+heart\s+valve|on[-\s]?x|surgical\s+instruments?|staplers?|clips?|catheters?|"
    r"guidewires?|sheaths?|introducers?|sutures?|mesh|cannulas?|cannulae|canula|stents?|balloons?|"
    r"trocars?|implants?|shunts?|valves?)\b",
    re.I,
)

HIGH_VALUE_DEVICE_RE = re.compile(
    r"\b(?:video\s+endoscopy|endosurgery|hemodialysis\s+system|nikkiso|on[-\s]?x|"
    r"prosthetic\s+heart\s+valve|autotransfusion|cell\s+saver|artificial\s+disc|guiding\s+catheter)\b",
    re.I,
)

ABBREVIATION_RE = re.compile(r"\b(?:DES|BMS|PTCA|CRT[-\s]?D|ICD|TAVI|TAVR|PDO|IOL|OCT)\b", re.I)

PHARMA_VACCINE_RE = re.compile(
    r"\b(?:vaccines?|vaccination|pharmaceuticals?|medicines?|drug products?|"
    r"tablets?|capsules?|syrups?|ampoules?|vials?|doses?|human medicine|"
    r"antibiotics?|insulin)\b",
    re.I,
)

APT_MARCH_RE = re.compile(r"\b(?:apt\s*medical|aptmed|apt\b)\b", re.I)
MARCH_VASCULAR_RE = re.compile(
    r"\b(?:guiding\s+catheter|guide\s+catheter|catheter|vascular\s+access|introducer|sheath)\b",
    re.I,
)
MARCH_BAD_CONTEXT_RE = re.compile(
    r"\b(?:vaccine|vaccination|pharmaceutical|pharma|medicine|tablet|capsule|"
    r"food|beverage|reagent|assay|diagnostic|laboratory|lab|fundus|ophthalmic|ocular|"
    r"retina|retinal|scanner|camera|imaging|tomography|oct|nidek|afc[-\s]?330)\b",
    re.I,
)


def patch_workflow_rules() -> None:
    """Extend the shared workflow module with stricter recall/precision guards."""

    extra_negative_rules = [
        (
            "pharmaceutical/vaccine expanded",
            r"\b(?:vaccines?|vaccination|pharmaceuticals?|medicines?|drug products?|"
            r"tablets?|capsules?|syrups?|ampoules?|vials?|doses?|human medicine|"
            r"antibiotics?|insulin)\b",
        ),
        (
            "donation/humanitarian",
            r"\b(?:donation|donated|humanitarian|relief goods|free of charge|foc|aid consignment)\b",
        ),
        (
            "ophthalmic/intraocular expanded",
            r"\b(?:ophthalmic|intraocular|ocular|iol|i\.o\.l\.|eye lens|phaco|viscoelastic|"
            r"ophthalmic visco[- ]?surgical device|fundus camera|retinal camera|"
            r"camera without pupil dilation|nidek|afc[- ]?330|optical coherence|oct[- ]?\d*)\b",
        ),
        (
            "ophthalmic/imaging camera conflict",
            r"\b(?:fundus camera|retinal camera|camera without pupil dilation|diagnostic camera|"
            r"medical imaging camera|optical coherence tomography|oct[- ]?\d*|nidek|afc[- ]?330)\b",
        ),
        (
            "cochlear/hearing",
            r"\b(?:cochlear|hearing aids?|hearing devices?|audiology|ear mould|earmold)\b",
        ),
        (
            "blood pressure monitor",
            r"\b(?:blood pressure monitor|bp monitor|sphygmomanometers?)\b",
        ),
        (
            "suction generator",
            r"\b(?:suction generator|aspirator pump|medical suction pump)\b",
        ),
        (
            "food/nutrition",
            r"\b(?:food supplement|nutritional supplement|infant formula|milk powder|protein powder)\b",
        ),
        (
            "general medical supplies",
            r"\b(?:hospital beds?|wheelchairs?|walkers?|walking aids?|gloves?|masks?|ppe|"
            r"infusion sets?|syringes? only|blood bags?)\b",
        ),
    ]
    existing_groups = {group for group, _pattern in wf.NEGATIVE_RULES}
    for group, pattern in extra_negative_rules:
        if group not in existing_groups:
            wf.NEGATIVE_RULES.append((group, pattern))

    for token in CONTROLLED_GENERIC_TOKENS:
        if token not in wf.GENERIC_TOKENS:
            wf.GENERIC_TOKENS.append(token)

    wf.NEGATIVE_COMPILED = [(group, re.compile(pattern, re.I)) for group, pattern in wf.NEGATIVE_RULES]
    generic_terms = sorted({wf.norm_text(t) for t in wf.GENERIC_TOKENS if wf.norm_text(t)}, key=len, reverse=True)
    wf.GENERIC_RE = re.compile(
        r"\b(?:" + "|".join(re.escape(term).replace(r"\ ", r"\s+") for term in generic_terms) + r")\b",
        re.I,
    )


def resolve_shared_dir() -> Path | None:
    for candidate in SHARED_DIR_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def parse_country_year(path: Path) -> tuple[str, str]:
    match = re.match(r"^(?P<country>.+)_FY(?P<year>\d{4})_ML_Map_Mapped\.xlsx$", path.name)
    if not match:
        raise ValueError(f"Cannot parse country/year from {path.name}")
    return match.group("country"), match.group("year")


def value_usd(df: pd.DataFrame) -> float:
    if VALUE_COL not in df.columns or df.empty:
        return 0.0
    return float(pd.to_numeric(df[VALUE_COL], errors="coerce").fillna(0).sum())


def numeric_series(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(0.0, index=df.index)
    return pd.to_numeric(df[column], errors="coerce").fillna(0)


def source_text_norm(df: pd.DataFrame, ev: pd.DataFrame | None = None) -> pd.Series:
    df.attrs.pop(SOURCE_TEXT_NORM_ATTR, None)
    cached = SOURCE_TEXT_NORM_CACHE.get(id(df))
    if cached is not None and cached[0].equals(df.index):
        cached_series = cached[1]
        if cached_series.index.equals(df.index):
            return cached_series
    legacy_cached = df.attrs.get(SOURCE_TEXT_NORM_ATTR)
    if isinstance(legacy_cached, pd.Series) and legacy_cached.index.equals(df.index):
        return legacy_cached
    parts: list[pd.Series] = []
    if ev is not None and "row_text_norm" in ev.columns:
        parts.append(ev["row_text_norm"].reindex(df.index).fillna("").astype(str))
    for column in RAW_SIGNAL_COLUMNS:
        if column in df.columns:
            parts.append(df[column].reindex(df.index).fillna("").astype(str))
    if not parts:
        return pd.Series("", index=df.index)
    text = parts[0]
    for part in parts[1:]:
        text = text.str.cat(part, sep=" ")
    normalized = text.map(wf.norm_text)
    SOURCE_TEXT_NORM_CACHE[id(df)] = (df.index.copy(), normalized)
    return normalized


def regex_contains(series: pd.Series, pattern: re.Pattern | str) -> pd.Series:
    """Vectorized regex contains that preserves flags from compiled patterns."""
    if hasattr(pattern, "pattern"):
        return series.astype("string").str.contains(
            pattern.pattern,
            flags=pattern.flags,
            regex=True,
            na=False,
        )
    return series.astype("string").str.contains(str(pattern), regex=True, na=False)


def configured_complete_source(path: Path) -> tuple[Path, int | None] | None:
    """Return the governed complete RAW source for an Excel-capped market.

    The audit-source registry is the authority for exceptional ingestion.  In
    particular, India FY2025 has more rows than one Excel worksheet can hold,
    so reading the legacy workbook's ``RawData`` sheet would silently discard
    more than 600k rows.

    Uses the registry's ``complete_source_path`` — the immutable governed raw
    upload under ``data/uploads/`` — and NEVER ``path``, which points at
    ``data/intermediate/vn_v0_mapped.csv``: a single mutable cache shared by
    every market/year run through ``run_pipeline.py`` and already fully MAPPED
    by whichever market ran last. Reading that file here would either raise
    ``FileNotFoundError`` on a clean checkout or, worse, silently remap this
    market/year from a different market's cached mapping.
    """
    config_path = ROOT / "config" / "audit_sources.json"
    if not config_path.exists():
        return None
    country, year = parse_country_year(path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    for source in config.get("outputs", []):
        if (
            source.get("country") == country
            and str(source.get("fiscal_year")) == str(year)
            and source.get("ingestion_mode") == "complete_csv_current_remap"
        ):
            complete_source_path = source.get("complete_source_path")
            if not complete_source_path:
                raise ValueError(
                    f"Governed source registry is missing complete_source_path for {country} FY{year}"
                )
            candidate = ROOT / str(complete_source_path)
            if not candidate.is_file():
                raise FileNotFoundError(
                    f"Governed complete source is missing for {country} FY{year}: {candidate}"
                )
            expected_rows = source.get("expected_rows")
            return candidate, (int(expected_rows) if expected_rows is not None else None)
    return None


def read_raw(path: Path) -> pd.DataFrame:
    complete_source = configured_complete_source(path)
    if complete_source is not None:
        candidate, expected_rows = complete_source
        log_step(f"{path.name}: using complete source {candidate.relative_to(ROOT)}")
        raw = pd.read_csv(candidate, dtype=str, low_memory=False)
        if expected_rows is not None and len(raw) != expected_rows:
            raise ValueError(
                f"Governed complete source row count mismatch for "
                f"{candidate.relative_to(ROOT)}: expected {expected_rows:,} rows, "
                f"found {len(raw):,}. Refusing to remap with an unverified source."
            )
    else:
        raw = pd.read_excel(path, sheet_name="RawData", dtype=str)
    raw = raw.fillna("")
    for column in [VALUE_COL, QUANTITY_COL, "ASP_USD"]:
        if column in raw.columns:
            raw[column] = pd.to_numeric(raw[column], errors="coerce").fillna(0)
    if "UniqueID" not in raw.columns:
        raw.insert(0, "UniqueID", [f"{path.stem}_{i + 1}" for i in range(len(raw))])
    return raw


def ensure_base_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    defaults = {
        "Dash_Include": "",
        "QA_Status": wf.QA_UNMAPPED,
        "Ref_Valid": "",
        "Scope_Flag": "",
        "Match_Scope": "",
        "Match_Tier": "",
        "Manufacturer": "",
        "Family": "",
        "Segment": "",
        "Sub-segment": "",
        "Product_V0": "",
        "Match_Status": "",
        "Match_Confidence": "",
    }
    for column, default in defaults.items():
        if column not in out.columns:
            out[column] = default

    if "Original_Dash_Include" not in out.columns:
        out["Original_Dash_Include"] = out["Dash_Include"].astype(str)
    if "Original_QA_Status" not in out.columns:
        out["Original_QA_Status"] = out["QA_Status"].astype(str)
    if "Original_Detailed_Product" not in out.columns and "Detailed_Product" in out.columns:
        out["Original_Detailed_Product"] = out["Detailed_Product"].astype(str)
    return out


def apply_governed_family_aliases(
    baseline: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply adjudicated family aliases to non-Trusted rows before rerouting.

    The normal end-to-end mapper merges ``cfg.FAMILY_ALIASES`` into its Tier-1
    lookup.  This batch workflow starts from governed, already-mapped workbooks,
    so it must reproduce that narrowly-scoped step or approved aliases would not
    affect the rerun.  Every hit is still sent through the standard reference and
    scope gate; this function never grants Trusted status directly.
    """
    aliases = getattr(cfg, "FAMILY_ALIASES", {})
    if not aliases:
        return baseline, pd.DataFrame(
            columns=["Change_Type", "Rows", "Value_USD", "Rule"]
        )

    parsed: dict[str, tuple[str, str, str, str, str]] = {}
    for term, key5 in aliases.items():
        parts = tuple(part.strip() for part in str(key5).split("|"))
        if len(parts) != 5:
            raise ValueError(
                f"Governed family alias {term!r} has malformed five-key value {key5!r}"
            )
        parsed[str(term).strip().lower()] = parts  # type: ignore[assignment]

    source_columns = [column for column in ALIAS_SOURCE_COLUMNS if column in baseline.columns]
    if not source_columns:
        return baseline, pd.DataFrame(
            columns=["Change_Type", "Rows", "Value_USD", "Rule"]
        )

    description = baseline[source_columns[0]].fillna("").astype(str)
    for column in source_columns[1:]:
        description = description.str.cat(
            baseline[column].fillna("").astype(str), sep=" "
        )

    # Match the same whole-word semantics as the Tier-1 pipeline matcher.  Terms
    # are longest-first so a specific model wins over a shorter nested family.
    ordered_terms = sorted(parsed, key=len, reverse=True)
    alternation = "|".join(re.escape(term) for term in ordered_terms)
    extracted = description.str.extract(
        rf"(?i)(?<![a-z0-9])({alternation})(?![a-z0-9])", expand=False
    ).fillna("").str.lower()

    eligible = extracted.ne("") & ~wf.output_tier(baseline).eq("Trusted_Dashboard")
    if "HS4" in baseline.columns:
        hs4 = pd.to_numeric(baseline["HS4"], errors="coerce")
        excluded_hs4 = set(getattr(cfg, "SCOPE_EXCLUDE_HS4", set()))
        if excluded_hs4:
            eligible &= ~hs4.isin(excluded_hs4)
    dental_cues = tuple(getattr(cfg, "DENTAL_NEGATIVE_CUES", ()))
    if dental_cues:
        description_lower = description.str.lower()
        dental = pd.Series(False, index=baseline.index)
        for cue in dental_cues:
            dental |= description_lower.str.contains(str(cue).lower(), regex=False, na=False)
        eligible &= ~dental

    if not bool(eligible.any()):
        return baseline, pd.DataFrame(
            columns=["Change_Type", "Rows", "Value_USD", "Rule"]
        )

    out = baseline.copy()
    for column in ["Segment", "Sub-segment", "Product_V0", "Manufacturer", "Family"]:
        audit_column = f"Pre_Adjudication_{column.replace('-', '_')}"
        if audit_column not in out.columns:
            out[audit_column] = out[column].fillna("").astype(str)

    matched_terms = extracted.loc[eligible]
    for term, index in matched_terms.groupby(matched_terms).groups.items():
        segment, subsegment, product, player, family = parsed[term]
        out.loc[index, ["Segment", "Sub-segment", "Product_V0", "Manufacturer", "Family"]] = [
            segment,
            subsegment,
            product,
            player,
            family,
        ]
        out.loc[index, "Match_Status"] = "Matched"
        out.loc[index, "Match_Tier"] = "family"
        out.loc[index, "Match_Confidence"] = "high"
        if "HS4" in out.columns:
            surgical = pd.to_numeric(out.loc[index, "HS4"], errors="coerce").isin(
                cfg.SURGICAL_HS4
            )
            out.loc[index, "Match_Scope"] = surgical.map(
                {True: cfg.SCOPE_SURGICAL_LABEL, False: cfg.SCOPE_EXTENDED_LABEL}
            )
        out.loc[index, "Adjudicated_Family_Alias"] = term
        out.loc[index, "Adjudicated_Alias_Applied"] = "Y"

    # Re-run the production reference/scope decision tree only for changed rows.
    # This recomputes Ref_Valid, Scope_Flag, QA_Status and Dash_Include and makes
    # approval necessary but never sufficient for a row to become Trusted.
    gated = apply_reference_gate(out.loc[eligible].copy())
    for column in gated.columns:
        if column not in out.columns:
            out[column] = ""
    out.loc[eligible, gated.columns] = gated

    change_rows = []
    for term, index in matched_terms.groupby(matched_terms).groups.items():
        change_rows.append(
            {
                "Change_Type": f"Governed LLM-adjudicated family alias: {term}",
                "Rows": int(len(index)),
                "Value_USD": value_usd(out.loc[index]),
                "Rule": "Approved alias; then standard reference/scope gate",
            }
        )
    return out, pd.DataFrame(change_rows)


def strong_product_support(df: pd.DataFrame, ev: pd.DataFrame) -> pd.Series:
    product_score = ev.get("product_score", pd.Series(0, index=df.index)).astype(float)
    support = product_score > 0

    product = df.get("Product_V0", pd.Series("", index=df.index)).astype(str).map(wf.norm_text)
    row_text = source_text_norm(df, ev)
    product_direct = pd.Series(False, index=df.index)
    eligible = product.str.len().ge(4) & ~product.isin(wf.UNSPECIFIED)
    if bool(eligible.any()):
        product_direct.loc[eligible] = [
            p in text for p, text in zip(product.loc[eligible], row_text.loc[eligible], strict=False)
        ]
    return support | product_direct


def detect_date_month_false_positive(df: pd.DataFrame, ev: pd.DataFrame) -> pd.Series:
    family = df.get("Family", pd.Series("", index=df.index)).astype(str)
    text = source_text_norm(df, ev)
    manufacturer_score = ev.get("manufacturer_score", pd.Series(0, index=df.index)).astype(float)
    product_score = ev.get("product_score", pd.Series(0, index=df.index)).astype(float)
    negative_group = ev.get("negative_conflict_group", pd.Series("", index=df.index)).astype(str)

    month_terms = {wf.norm_text(term) for term in DATE_MONTH_TOKENS}
    family_norm = family.map(wf.norm_text)
    family_is_month = family_norm.isin(month_terms) | family_norm.astype("string").str.fullmatch(
        DATE_MONTH_RE.pattern,
        flags=DATE_MONTH_RE.flags,
        na=False,
    )
    text_has_month = regex_contains(text, DATE_MONTH_RE)
    date_context = regex_contains(text, DATE_CONTEXT_RE) | regex_contains(text, DATE_PATTERN_RE)
    bad_context = (
        regex_contains(text, MARCH_BAD_CONTEXT_RE)
        | regex_contains(text, OPHTHALMIC_IMAGING_RE)
        | regex_contains(text, PHARMA_VACCINE_RE)
    ) | negative_group.str.contains(
        r"pharmaceutical|vaccine|diagnostic|lab|food|imaging|ophthalmic|camera", case=False, na=False
    )
    strong_support = (manufacturer_score >= 20) & (product_score > 0) & ~date_context & ~bad_context
    return family_is_month & text_has_month & (~strong_support | date_context | bad_context)


def detect_march_rule_violation(df: pd.DataFrame, ev: pd.DataFrame) -> pd.Series:
    """Only trust APT Medical / March with APT evidence and catheter/vascular context."""
    family = df.get("Family", pd.Series("", index=df.index)).astype(str).map(wf.norm_text)
    player = df.get("Manufacturer", pd.Series("", index=df.index)).astype(str)
    text = source_text_norm(df, ev)
    product_group = ev.get("product_evidence_group", pd.Series("", index=df.index)).astype(str)
    negative_group = ev.get("negative_conflict_group", pd.Series("", index=df.index)).astype(str)

    march_family = family.eq("march")
    apt_context = regex_contains(text, APT_MARCH_RE) | regex_contains(player, APT_MARCH_RE)
    vascular_context = regex_contains(text, MARCH_VASCULAR_RE) | product_group.str.contains(
        r"guiding catheter|catheter|vascular", case=False, na=False
    )
    bad_context = regex_contains(text, MARCH_BAD_CONTEXT_RE) | negative_group.str.contains(
        r"pharmaceutical|vaccine|diagnostic|lab|food|imaging|ophthalmic|camera|dental|veterinary|cosmetic",
        case=False,
        na=False,
    )
    return march_family & ~(apt_context & vascular_context & ~bad_context)


def detect_ophthalmic_imaging_conflict(df: pd.DataFrame, ev: pd.DataFrame) -> pd.Series:
    text = source_text_norm(df, ev)
    negative_group = ev.get("negative_conflict_group", pd.Series("", index=df.index)).astype(str)
    conflict = regex_contains(text, OPHTHALMIC_IMAGING_RE) | negative_group.str.contains(
        r"ophthalmic|imaging|camera|tomography|diagnostic", case=False, na=False
    )
    # Approved exceptions live in the governed reference list.  Suppress the
    # final guard only when the source description itself contains an approved
    # surgical context; mapped Family/Manufacturer fields are never sufficient.
    whitelist = pd.Series(False, index=df.index)
    for pattern in wf.rc.SURGICAL_CONTEXT_WHITELIST:
        whitelist |= regex_contains(text, pattern)
    return conflict & ~whitelist


def detect_independent_surgical_signal(df: pd.DataFrame, ev: pd.DataFrame) -> pd.Series:
    text = source_text_norm(df, ev)
    value = numeric_series(df, VALUE_COL)
    high_value_device = value.ge(50_000) & regex_contains(text, HIGH_VALUE_DEVICE_RE)
    product_signal = regex_contains(text, FALSE_NEGATIVE_SURGICAL_RE)
    return product_signal | high_value_device


def detect_extended_false_positive(
    df: pd.DataFrame, ev: pd.DataFrame, month_risk: pd.Series | None = None
) -> pd.Series:
    tier = wf.output_tier(df)
    qa = df.get("QA_Status", pd.Series("", index=df.index)).astype(str)
    extended = qa.str.contains("Extended HS", case=False, na=False) | (
        tier.eq("Review_Queue") & qa.str.contains("surgical product in Extended", case=False, na=False)
    )
    text = source_text_norm(df, ev)
    negative_group = ev.get("negative_conflict_group", pd.Series("", index=df.index)).astype(str)
    product_score = ev.get("product_score", pd.Series(0, index=df.index)).astype(float)
    generic_risk = ev.get("generic_token_risk", pd.Series(False, index=df.index)).astype(bool)
    family_norm = df.get("Family", pd.Series("", index=df.index)).astype(str).map(wf.norm_text)
    controlled_generic = family_norm.isin({wf.norm_text(term) for term in CONTROLLED_GENERIC_TOKENS})

    bad_context = (
        regex_contains(text, PHARMA_VACCINE_RE)
        | regex_contains(text, MARCH_BAD_CONTEXT_RE)
        | regex_contains(text, OPHTHALMIC_IMAGING_RE)
    ) | negative_group.str.contains(
        r"pharmaceutical|vaccine|diagnostic|lab|food|imaging|ophthalmic|camera|dental|veterinary|cosmetic",
        case=False,
        na=False,
    )
    true_extended = regex_contains(text, TRUE_EXTENDED_SURGICAL_RE) | (
        product_score.gt(0) & regex_contains(text, FALSE_NEGATIVE_SURGICAL_RE)
    )
    apt_march_valid = (
        family_norm.eq("march")
        & regex_contains(text, APT_MARCH_RE)
        & regex_contains(text, MARCH_VASCULAR_RE)
        & ~bad_context
    )
    if month_risk is None:
        month_risk = detect_date_month_false_positive(df, ev)
    else:
        month_risk = month_risk.reindex(df.index).fillna(False).astype(bool)
    generic_without_support = (controlled_generic | generic_risk | month_risk) & ~true_extended & ~apt_march_valid
    return extended & (((bad_context) & ~true_extended) | generic_without_support)


def apply_recall_precision_guards(
    baseline: pd.DataFrame, routed: pd.DataFrame, ev: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    out = routed.copy()
    out["Dash_Include"] = out.get("Dash_Include", "").astype(str).replace({"nan": ""})
    out["QA_Status"] = out.get("QA_Status", "").astype(str)
    out["Scope_Flag"] = out.get("Scope_Flag", "").astype(str).replace({"nan": ""})

    product_support = strong_product_support(out, ev)
    negative_group = ev.get("negative_conflict_group", pd.Series("", index=out.index)).astype(str)
    generic_risk = ev.get("generic_token_risk", pd.Series(False, index=out.index)).astype(bool)
    family_score = ev.get("family_score", pd.Series(0, index=out.index)).astype(float)
    manufacturer_score = ev.get("manufacturer_score", pd.Series(0, index=out.index)).astype(float)
    row_text = source_text_norm(out, ev)
    date_month_signal = detect_date_month_false_positive(out, ev)
    march_rule_signal = detect_march_rule_violation(out, ev)
    independent_surgical_signal = detect_independent_surgical_signal(out, ev)
    ophthalmic_conflict = detect_ophthalmic_imaging_conflict(out, ev)
    extended_false_positive = detect_extended_false_positive(out, ev, date_month_signal)
    pharma_false = regex_contains(row_text, PHARMA_VACCINE_RE)

    tier = wf.output_tier(out)
    trusted_before = out["Dash_Include"].astype(str).str.upper().eq("Y")

    surgical_signal = product_support | independent_surgical_signal
    surgical_excluded = (
        tier.eq("Excluded_Unmapped")
        & surgical_signal
        & negative_group.eq("")
        & ~ophthalmic_conflict
        & ~extended_false_positive
        & ~pharma_false
    )
    surgical_conflict = (
        tier.eq("Excluded_Unmapped")
        & surgical_signal
        & negative_group.ne("")
        & ~ophthalmic_conflict
        & ~extended_false_positive
        & ~pharma_false
    )
    ophthalmic_false_positive = (
        (trusted_before | tier.eq("Review_Queue") | tier.eq("Excluded_Unmapped")) & ophthalmic_conflict
    )
    trusted_conflict = trusted_before & negative_group.ne("") & ~ophthalmic_conflict
    category_weak = trusted_before & out.get("Match_Tier", "").astype(str).str.contains("category", case=False, na=False) & ~product_support
    generic_weak = trusted_before & generic_risk & ~product_support & ((family_score <= 0) | (manufacturer_score < 20))
    date_month_risk = trusted_before & date_month_signal
    march_rule_risk = trusted_before & march_rule_signal
    pharma_risk = trusted_before & (
        negative_group.str.contains("pharmaceutical/vaccine", case=False, na=False)
        | pharma_false
    )

    changes = []

    def apply_mask(mask: pd.Series, status: str, scope_flag_prefix: str, change_name: str, change_type: str) -> None:
        count = int(mask.sum())
        if not count:
            return
        out.loc[mask, "QA_Status"] = status
        out.loc[mask, "Dash_Include"] = ""
        existing = out.loc[mask, "Scope_Flag"].astype(str).replace({"nan": ""})
        suffix = negative_group.loc[mask].where(negative_group.loc[mask].ne(""), scope_flag_prefix)
        out.loc[mask, "Scope_Flag"] = [
            cur if cur else f"{scope_flag_prefix}:{group}" for cur, group in zip(existing, suffix, strict=False)
        ]
        changes.append(
            {
                "Change": change_name,
                "Rows": count,
                "Value_USD": round(value_usd(out.loc[mask]), 2),
                "Purpose": "Improve recall/routing auditability or remove precision risk from Trusted_Dashboard",
                "Change_Type": change_type,
            }
        )

    apply_mask(
        extended_false_positive,
        QA_EXTENDED_FALSE_POSITIVE,
        "excluded_false_positive",
        "Moved false-positive Extended HS rows to Excluded_Unmapped",
        "False-positive Extended HS moved to Excluded",
    )
    apply_mask(
        ophthalmic_false_positive,
        QA_OPHTHALMIC_FALSE_POSITIVE,
        "excluded_ophthalmic_imaging",
        "Moved ophthalmic/imaging false positives out of dashboard/review scope",
        "Ophthalmic/imaging false positive excluded",
    )
    apply_mask(
        surgical_excluded,
        QA_SILENT_SURGICAL,
        "review",
        "Moved excluded surgical-evidence rows to Review_Queue",
        "Recall capture moved to Review",
    )
    apply_mask(
        surgical_conflict,
        QA_SURGICAL_CONFLICT,
        "review_conflict",
        "Moved excluded surgical-evidence rows with exclusion conflicts to Review_Queue",
        "Conflict capture moved to Review",
    )
    apply_mask(
        trusted_conflict,
        wf.QA_PRECISION_RISK,
        "precision_risk",
        "Moved trusted exclusion-conflict rows to Review_Queue",
        "Trusted precision-risk moved to Review",
    )
    apply_mask(
        category_weak,
        QA_CATEGORY_WEAK,
        "review",
        "Moved weak category-only trusted rows to Review_Queue",
        "Weak category trusted moved to Review",
    )
    apply_mask(
        generic_weak,
        wf.QA_PRECISION_RISK,
        "precision_risk",
        "Moved weak generic-token trusted rows to Review_Queue",
        "Generic-token trusted moved to Review",
    )
    apply_mask(
        date_month_risk,
        QA_DATE_MONTH,
        "precision_risk",
        "Moved date/month token trusted rows to Review_Queue",
        "Date/month trusted moved to Review",
    )
    apply_mask(
        march_rule_risk,
        QA_MARCH,
        "precision_risk",
        "Moved APT/March rows without required context to Review_Queue",
        "APT/March trusted moved to Review",
    )
    apply_mask(
        pharma_risk,
        QA_PHARMA,
        "precision_risk",
        "Moved pharmaceutical/vaccine trusted rows to Review_Queue",
        "Pharma/vaccine trusted moved to Review",
    )

    # Re-apply the trusted gate after all exclusions and evidence checks.
    negative_group = ev.get("negative_conflict_group", pd.Series("", index=out.index)).astype(str)
    generic_risk = ev.get("generic_token_risk", pd.Series(False, index=out.index)).astype(bool)
    family_score = ev.get("family_score", pd.Series(0, index=out.index)).astype(float)
    manufacturer_score = ev.get("manufacturer_score", pd.Series(0, index=out.index)).astype(float)
    extended_false_positive_after = extended_false_positive
    category_weak_after = (
        out.get("Match_Tier", "").astype(str).str.contains("category", case=False, na=False) & ~product_support
    )
    generic_weak_after = generic_risk & ~product_support & ((family_score <= 0) | (manufacturer_score < 20))
    trusted_gate = (
        out["QA_Status"].eq(wf.QA_MAPPED)
        & out.get("Ref_Valid", "").astype(str).str.upper().eq("Y")
        & out.get("Match_Scope", "").astype(str).str.lower().eq("surgical")
        & out["Scope_Flag"].astype(str).replace({"nan": ""}).eq("")
        & negative_group.eq("")
        & ~category_weak_after
        & ~generic_weak_after
        & ~date_month_signal
        & ~march_rule_signal
        & ~ophthalmic_conflict
        & ~extended_false_positive_after
        & ~pharma_false
    )
    out["Dash_Include"] = ""
    out.loc[trusted_gate, "Dash_Include"] = "Y"

    out = annotate_audit_fields(
        out,
        ev,
        {
            "strong_product_support": product_support,
            "date_month_token_risk": date_month_signal,
            "apt_march_rule_risk": march_rule_signal,
            "independent_surgical_signal": independent_surgical_signal,
            "ophthalmic_imaging_conflict": ophthalmic_conflict,
            "extended_false_positive": extended_false_positive_after,
        },
    )

    if changes:
        changes_df = pd.DataFrame(changes)
    else:
        changes_df = pd.DataFrame(columns=["Change", "Rows", "Value_USD", "Purpose", "Change_Type"])

    baseline_tier = wf.output_tier(baseline)
    new_tier = wf.output_tier(out)
    moved_to_review = baseline_tier.ne("Review_Queue") & new_tier.eq("Review_Queue")
    moved_to_trusted = baseline_tier.ne("Trusted_Dashboard") & new_tier.eq("Trusted_Dashboard")
    moved_from_trusted = baseline_tier.eq("Trusted_Dashboard") & ~new_tier.eq("Trusted_Dashboard")
    aggregate_changes = pd.DataFrame(
        [
            {
                "Change": "Net rows newly routed to Review_Queue",
                "Rows": int(moved_to_review.sum()),
                "Value_USD": round(value_usd(out.loc[moved_to_review]), 2),
                "Purpose": "Capture recall by surfacing surgical-looking uncertain rows",
                "Change_Type": "Net routing movement",
            },
            {
                "Change": "Net rows newly routed to Trusted_Dashboard",
                "Rows": int(moved_to_trusted.sum()),
                "Value_USD": round(value_usd(out.loc[moved_to_trusted]), 2),
                "Purpose": "Reference-valid trusted expansion after evidence gates",
                "Change_Type": "Net routing movement",
            },
            {
                "Change": "Net rows removed from Trusted_Dashboard",
                "Rows": int(moved_from_trusted.sum()),
                "Value_USD": round(value_usd(out.loc[moved_from_trusted]), 2),
                "Purpose": "Precision guardrail removals",
                "Change_Type": "Net routing movement",
            },
        ]
    )
    return out, pd.concat([aggregate_changes, changes_df], ignore_index=True)


def annotate_audit_fields(
    df: pd.DataFrame, ev: pd.DataFrame, flags: dict[str, pd.Series] | None = None
) -> pd.DataFrame:
    out = df.copy()

    def flag(name: str, fallback) -> pd.Series:
        if flags and name in flags:
            return flags[name].reindex(out.index).fillna(False).astype(bool)
        return fallback().reindex(out.index).fillna(False).astype(bool)

    normalized_source_text = source_text_norm(out, ev)
    strong_product = flag("strong_product_support", lambda: strong_product_support(out, ev))
    date_month = flag("date_month_token_risk", lambda: detect_date_month_false_positive(out, ev))
    apt_march = flag("apt_march_rule_risk", lambda: detect_march_rule_violation(out, ev))
    independent_signal = flag("independent_surgical_signal", lambda: detect_independent_surgical_signal(out, ev))
    ophthalmic_conflict = flag("ophthalmic_imaging_conflict", lambda: detect_ophthalmic_imaging_conflict(out, ev))
    extended_false_positive = flag("extended_false_positive", lambda: detect_extended_false_positive(out, ev))

    if "Detailed_Product" in out.columns:
        out["Normalized_Detailed_Product"] = out["Detailed_Product"].astype(str).map(wf.norm_text)
    out["Normalized_Source_Text"] = normalized_source_text
    out["Product_Evidence_Group"] = ev.get("product_rule", pd.Series("", index=out.index)).astype(str)
    out["Strong_Product_Evidence"] = strong_product.map({True: "Y", False: ""})
    out["Negative_Conflict_Group"] = ev.get("negative_conflict_group", pd.Series("", index=out.index)).astype(str)
    out["Exclusion_Group"] = out["Negative_Conflict_Group"]
    out["Generic_Token_Risk"] = ev.get("generic_token_risk", pd.Series(False, index=out.index)).map({True: "Y", False: ""})
    out["High_Risk_Token"] = out["Generic_Token_Risk"]
    out["Date_Month_Token_Risk"] = date_month.map({True: "Y", False: ""})
    out["APT_March_Rule_Risk"] = apt_march.map({True: "Y", False: ""})
    out["Independent_Surgical_Signal"] = independent_signal.map({True: "Y", False: ""})
    out["Ophthalmic_Imaging_Conflict_Risk"] = ophthalmic_conflict.map({True: "Y", False: ""})
    out["Extended_False_Positive_Risk"] = extended_false_positive.map({True: "Y", False: ""})
    out["Vector_Auto_Mapping_Status"] = "archived_disabled"
    out["Master_Validation_Status"] = ev.get("master_validation_status", pd.Series("", index=out.index)).astype(str)
    out["Reference_Key_Status"] = out["Master_Validation_Status"]
    out["Final_Candidate_Score"] = ev.get("final_candidate_score", pd.Series(0, index=out.index)).astype(float)
    out["Evidence_Flag"] = out["Product_Evidence_Group"].where(out["Product_Evidence_Group"].ne(""), out["Master_Validation_Status"])
    out["Risk_Flag"] = ""
    out.loc[out["Negative_Conflict_Group"].ne(""), "Risk_Flag"] = "exclusion_conflict"
    out.loc[out["Generic_Token_Risk"].eq("Y") & out["Risk_Flag"].eq(""), "Risk_Flag"] = "generic_token_risk"
    out.loc[date_month & out["Risk_Flag"].eq(""), "Risk_Flag"] = "date_month_token_risk"
    out.loc[apt_march & out["Risk_Flag"].eq(""), "Risk_Flag"] = "apt_march_rule_risk"
    out.loc[
        ophthalmic_conflict & out["Risk_Flag"].eq(""),
        "Risk_Flag",
    ] = "ophthalmic_imaging_conflict"
    out.loc[
        extended_false_positive & out["Risk_Flag"].eq(""),
        "Risk_Flag",
    ] = "extended_false_positive"
    out["Output_Tier"] = wf.output_tier(out)
    return out


def dashboard_rebuild(df: pd.DataFrame, country: str) -> pd.DataFrame:
    trusted = df.loc[df.get("Dash_Include", "").astype(str).str.upper().eq("Y")].copy()
    if trusted.empty:
        return pd.DataFrame(
            columns=[
                "Country",
                "Segment",
                "Sub-segment",
                "Product_V0",
                "Manufacturer",
                "Family",
                "Rows",
                "Quantity",
                "Total_Value_USD",
                "ASP_USD",
            ]
        )
    trusted[QUANTITY_COL] = numeric_series(trusted, QUANTITY_COL)
    trusted[VALUE_COL] = numeric_series(trusted, VALUE_COL)
    group_cols = ["Segment", "Sub-segment", "Product_V0", "Manufacturer", "Family"]
    for column in group_cols:
        if column not in trusted.columns:
            trusted[column] = ""
    dash = (
        trusted.groupby(group_cols, dropna=False, as_index=False)
        .agg(Rows=("UniqueID", "count"), Quantity=(QUANTITY_COL, "sum"), Total_Value_USD=(VALUE_COL, "sum"))
        .sort_values(["Total_Value_USD", "Rows"], ascending=[False, False])
    )
    dash.insert(0, "Country", country)
    dash["ASP_USD"] = dash.apply(
        lambda row: row["Total_Value_USD"] / row["Quantity"] if row["Quantity"] else math.nan,
        axis=1,
    )
    return dash


def route_file(
    raw: pd.DataFrame,
    master_keys: wf.MasterKeys,
    baseline: pd.DataFrame | None = None,
    ev: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    baseline = ensure_base_columns(raw) if baseline is None else baseline
    ev = wf.build_evidence(baseline, master_keys) if ev is None else ev
    routed, route_changes = wf.route_rows(baseline, ev)
    improved, guard_changes = apply_recall_precision_guards(baseline, routed, ev)
    return improved, ev, pd.concat([route_changes, guard_changes], ignore_index=True)


def reconciliation_validation(df: pd.DataFrame) -> pd.DataFrame:
    tier = wf.output_tier(df)
    frames = {
        "Trusted_Dashboard": df.loc[tier.eq("Trusted_Dashboard")],
        "Review_Queue": df.loc[tier.eq("Review_Queue")],
        "Excluded_Unmapped": df.loc[tier.eq("Excluded_Unmapped")],
    }
    partition_rows = sum(len(frame) for frame in frames.values())
    partition_value = sum(value_usd(frame) for frame in frames.values())
    raw_value = value_usd(df)
    uid_ok = True
    duplicate_raw = int(df["UniqueID"].astype(str).duplicated().sum()) if "UniqueID" in df.columns else 0
    if "UniqueID" in df.columns:
        combined = pd.concat([frame["UniqueID"].astype(str) for frame in frames.values()], ignore_index=True)
        uid_ok = sorted(combined.tolist()) == sorted(df["UniqueID"].astype(str).tolist())
    return pd.DataFrame(
        [
            {
                "Validation": "Tier row reconciliation",
                "Observed": partition_rows - len(df),
                "Target": "0",
                "Status": "PASS" if partition_rows == len(df) else "FAIL",
            },
            {
                "Validation": "Tier value reconciliation",
                "Observed": round(partition_value - raw_value, 6),
                "Target": "0",
                "Status": "PASS" if abs(partition_value - raw_value) < 0.01 else "FAIL",
            },
            {
                "Validation": "Tier UniqueID reconciliation",
                "Observed": "match" if uid_ok else "mismatch",
                "Target": "match",
                "Status": "PASS" if uid_ok else "FAIL",
            },
            {
                "Validation": "RawData duplicate UniqueID count",
                "Observed": duplicate_raw,
                "Target": "0",
                "Status": "PASS" if duplicate_raw == 0 else "WARN",
            },
        ]
    )


def extra_validations(
    df: pd.DataFrame, ev: pd.DataFrame, master_keys: wf.MasterKeys, country: str
) -> pd.DataFrame:
    base = wf.validate(df, master_keys).copy()
    trusted = df.get("Dash_Include", "").astype(str).str.upper().eq("Y")
    product_support = strong_product_support(df, ev)
    source_text = source_text_norm(df, ev)
    negative_group = ev.get("negative_conflict_group", pd.Series("", index=df.index)).astype(str)
    generic_risk = ev.get("generic_token_risk", pd.Series(False, index=df.index)).astype(bool)
    family_score = ev.get("family_score", pd.Series(0, index=df.index)).astype(float)
    manufacturer_score = ev.get("manufacturer_score", pd.Series(0, index=df.index)).astype(float)
    tier = wf.output_tier(df)
    date_month_signal = detect_date_month_false_positive(df, ev)
    march_rule_signal = detect_march_rule_violation(df, ev)
    independent_surgical_signal = detect_independent_surgical_signal(df, ev)
    ophthalmic_conflict = detect_ophthalmic_imaging_conflict(df, ev)
    extended_false_positive = detect_extended_false_positive(df, ev, date_month_signal)
    pharma_false = regex_contains(source_text, PHARMA_VACCINE_RE)
    surgicalish_excluded = (
        tier.eq("Excluded_Unmapped")
        & (product_support | independent_surgical_signal)
        & negative_group.eq("")
        & ~ophthalmic_conflict
        & ~extended_false_positive
        & ~pharma_false
    )
    capture_denominator = trusted | tier.eq("Review_Queue") | surgicalish_excluded
    capture_recall = (
        float((trusted | tier.eq("Review_Queue")).sum()) / float(capture_denominator.sum())
        if int(capture_denominator.sum())
        else 1.0
    )
    capture_denominator_value = value_usd(df.loc[capture_denominator])
    capture_recall_value = (
        value_usd(df.loc[trusted | tier.eq("Review_Queue")]) / capture_denominator_value if capture_denominator_value else 1.0
    )
    trusted_precision_proxy = 1.0
    if int(trusted.sum()):
        precision_risk = trusted & (
            negative_group.ne("")
            | df.get("Scope_Flag", "").astype(str).replace({"nan": ""}).ne("")
            | date_month_signal
            | march_rule_signal
            | ophthalmic_conflict
            | extended_false_positive
            | pharma_false
        )
        trusted_precision_proxy = 1.0 - (float(precision_risk.sum()) / float(trusted.sum()))

    category_weak = trusted & df.get("Match_Tier", "").astype(str).str.contains("category", case=False, na=False) & ~product_support
    generic_only = trusted & generic_risk & ~product_support & ((family_score <= 0) | (manufacturer_score < 20))
    march_violation = trusted & march_rule_signal
    pharma = trusted & (
        negative_group.str.contains("pharmaceutical/vaccine", case=False, na=False)
        | pharma_false
    )
    trusted_ophthalmic = trusted & ophthalmic_conflict
    trusted_extended_fp = trusted & extended_false_positive
    trusted_date_month = trusted & date_month_signal
    independent_excluded_rows = int(surgicalish_excluded.sum())
    independent_excluded_value = value_usd(df.loc[surgicalish_excluded])

    added = pd.DataFrame(
        [
            {
                "Validation": "Trusted high-confidence exclusion conflicts",
                "Observed": int((trusted & negative_group.ne("")).sum()),
                "Target": "0",
                "Status": "PASS" if int((trusted & negative_group.ne("")).sum()) == 0 else "FAIL",
            },
            {
                "Validation": "Trusted pharmaceutical/vaccine conflicts",
                "Observed": int(pharma.sum()),
                "Target": "0",
                "Status": "PASS" if int(pharma.sum()) == 0 else "FAIL",
            },
            {
                "Validation": "Trusted ophthalmic/imaging false positives",
                "Observed": int(trusted_ophthalmic.sum()),
                "Target": "0",
                "Status": "PASS" if int(trusted_ophthalmic.sum()) == 0 else "FAIL",
            },
            {
                "Validation": "Trusted false-positive Extended HS conflicts",
                "Observed": int(trusted_extended_fp.sum()),
                "Target": "0",
                "Status": "PASS" if int(trusted_extended_fp.sum()) == 0 else "FAIL",
            },
            {
                "Validation": "Trusted date-month token false positives",
                "Observed": int(trusted_date_month.sum()),
                "Target": "0",
                "Status": "PASS" if int(trusted_date_month.sum()) == 0 else "FAIL",
            },
            {
                "Validation": "Trusted APT March rule violations",
                "Observed": int(march_violation.sum()),
                "Target": "0",
                "Status": "PASS" if int(march_violation.sum()) == 0 else "FAIL",
            },
            {
                "Validation": "Trusted generic-token-only mappings",
                "Observed": int(generic_only.sum()),
                "Target": "0",
                "Status": "PASS" if int(generic_only.sum()) == 0 else "FAIL",
            },
            {
                "Validation": "Trusted category-tier rows with weak product evidence",
                "Observed": int(category_weak.sum()),
                "Target": "0",
                "Status": "PASS" if int(category_weak.sum()) == 0 else "FAIL",
            },
            {
                "Validation": "Capture recall proxy rows",
                "Observed": round(capture_recall, 4),
                "Target": ">=0.95",
                "Status": "PASS" if capture_recall >= 0.95 else "FAIL",
            },
            {
                "Validation": "Capture recall proxy value",
                "Observed": round(capture_recall_value, 4),
                "Target": ">=0.95",
                "Status": "PASS" if capture_recall_value >= 0.95 else "FAIL",
            },
            {
                "Validation": "Trusted precision proxy",
                "Observed": round(trusted_precision_proxy, 4),
                "Target": ">=0.90",
                "Status": "PASS" if trusted_precision_proxy >= 0.90 else "FAIL",
            },
            {
                "Validation": "Independent Excluded_Unmapped surgical screen rows",
                "Observed": independent_excluded_rows,
                "Target": "0 after review routing",
                "Status": "PASS" if independent_excluded_rows == 0 else "WARN",
            },
            {
                "Validation": "Independent Excluded_Unmapped surgical screen value",
                "Observed": round(independent_excluded_value, 2),
                "Target": "0 after review routing",
                "Status": "PASS" if independent_excluded_value == 0 else "WARN",
            },
            {
                "Validation": "Vector auto-mapping status",
                "Observed": "archived_disabled",
                "Target": "archived_disabled",
                "Status": "PASS",
            },
            {
                "Validation": "Country processed",
                "Observed": country,
                "Target": country,
                "Status": "PASS",
            },
        ]
    )
    return pd.concat([reconciliation_validation(df), base, added], ignore_index=True)


def metrics_snapshot(
    country: str,
    year: str,
    label: str,
    df: pd.DataFrame,
    ev: pd.DataFrame,
    runtime: float,
    full_recall_screen: bool = True,
) -> dict[str, Any]:
    metrics = wf.metrics_snapshot(label, df, ev, runtime_seconds=runtime)
    if not full_recall_screen:
        metrics["Independent excluded surgical screen rows"] = metrics.get("Surgicalish excluded rows", 0)
        metrics["Independent excluded surgical screen value"] = metrics.get("Surgicalish excluded value", 0.0)
        metrics["Vector auto-mapping status"] = "archived_disabled"
        row: OrderedDict[str, Any] = OrderedDict([("Country", country), ("Year", year)])
        row.update(metrics)
        return dict(row)

    tier = wf.output_tier(df)
    trusted = tier.eq("Trusted_Dashboard")
    review = tier.eq("Review_Queue")
    source_text = source_text_norm(df, ev)
    negative_group = _evidence_series(ev, "negative_conflict_group", "").astype(str)
    product_support = strong_product_support(df, ev)
    date_month_signal = detect_date_month_false_positive(df, ev)
    independent_signal = detect_independent_surgical_signal(df, ev)
    ophthalmic_conflict = detect_ophthalmic_imaging_conflict(df, ev)
    extended_false_positive = detect_extended_false_positive(df, ev, date_month_signal)
    pharma_false = regex_contains(source_text, PHARMA_VACCINE_RE)
    surgicalish_excluded = (
        tier.eq("Excluded_Unmapped")
        & (product_support | independent_signal)
        & negative_group.eq("")
        & ~ophthalmic_conflict
        & ~extended_false_positive
        & ~pharma_false
    )
    values = wf.value_usd(df)
    capture = trusted | review
    denominator = capture | surgicalish_excluded
    denominator_rows = int(denominator.sum())
    denominator_value = float(values.loc[denominator].sum()) if denominator_rows else 0.0
    metrics["Surgicalish excluded rows"] = int(surgicalish_excluded.sum())
    metrics["Surgicalish excluded value"] = round(float(values.loc[surgicalish_excluded].sum()), 2)
    metrics["Independent excluded surgical screen rows"] = int(surgicalish_excluded.sum())
    metrics["Independent excluded surgical screen value"] = round(float(values.loc[surgicalish_excluded].sum()), 2)
    metrics["Capture recall proxy rows"] = float(capture.sum()) / denominator_rows if denominator_rows else 1.0
    metrics["Capture recall proxy value"] = float(values.loc[capture].sum()) / denominator_value if denominator_value else 1.0
    metrics["Vector auto-mapping status"] = "archived_disabled"
    row: OrderedDict[str, Any] = OrderedDict([("Country", country), ("Year", year)])
    row.update(metrics)
    return dict(row)


def executive_summary(
    country: str,
    year: str,
    before: dict[str, Any],
    after: dict[str, Any],
    validation: pd.DataFrame,
    changes: pd.DataFrame,
) -> pd.DataFrame:
    failed = int(validation["Status"].astype(str).eq("FAIL").sum()) if not validation.empty else 0
    rows_to_review = int(after.get("Review rows", 0))
    high_value = int(after.get("High-value review rows >=50K", 0))
    summary = [
        {
            "Section": "What changed",
            "Detail": (
                "Applied alias/product evidence expansion, negative gates, generic/date-month controls, "
                "strict reference validation, and recall-first review routing."
            ),
        },
        {
            "Section": "Precision",
            "Detail": f"Trusted precision proxy is {after.get('Trusted precision proxy', 0):.1%}; target is >=90%.",
        },
        {
            "Section": "Recall",
            "Detail": f"Capture recall proxy is {after.get('Capture recall proxy rows', 0):.1%} rows and {after.get('Capture recall proxy value', 0):.1%} value.",
        },
        {
            "Section": "Manual review",
            "Detail": f"Review_Queue has {rows_to_review:,} rows; {high_value:,} rows are >= USD 50K and should be prioritized.",
        },
        {
            "Section": "Unresolved issues",
            "Detail": (
                f"{failed} acceptance validation(s) failed. Extended HS and reference gaps remain isolated "
                "for business/reference-owner decisions."
            ),
        },
        {
            "Section": "Largest iteration changes",
            "Detail": "; ".join(
                f"{row.Change}: {int(row.Rows):,} rows"
                for row in changes.head(5).itertuples(index=False)
                if hasattr(row, "Change")
            ),
        },
        {"Section": "Country/year", "Detail": f"{country} FY{year}"},
    ]
    return pd.DataFrame(summary)


def workflow_recommendations() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Category": "Implement immediately",
                "Recommendation": "Keep strict master-reference gates for Trusted_Dashboard and route weak/generic/semantic-only evidence to Review_Queue.",
            },
            {
                "Category": "Implement immediately",
                "Recommendation": "Review high-value clusters first using Review_Queue_Cluster_Summary instead of row-by-row review.",
            },
            {
                "Category": "Implement immediately",
                "Recommendation": "Convert accepted reviewer corrections into Alias_Update_Request, Reference_Update_Request, and HS_Scope_Rules before each rerun.",
            },
            {
                "Category": "Controlled experiment",
                "Recommendation": "Test word and character TF-IDF thresholds against Gold_Labels before allowing any additional Trusted routing.",
            },
            {
                "Category": "Controlled experiment",
                "Recommendation": "Use LLM resolver only on high-value ambiguous candidate sets and require JSON output plus master validation.",
            },
            {
                "Category": "Defer",
                "Recommendation": "Do not move Extended HS surgical products into Trusted_Dashboard until the dashboard-scope business rule is approved.",
            },
            {
                "Category": "Avoid",
                "Recommendation": "Avoid one-shot raw-row-to-final LLM mapping and avoid generic token matches without product/manufacturer support.",
            },
            {
                "Category": "Avoid",
                "Recommendation": "Keep vector/semantic retrieval out of auto-mapping; use it only for review/discovery until a separate controlled experiment passes precision and recall gates.",
            },
        ]
    )


def build_mapping_decision_log(df: pd.DataFrame, ev: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "UniqueID",
        "Output_Tier",
        "QA_Status",
        "Dash_Include",
        "Ref_Valid",
        "Segment",
        "Sub-segment",
        "Product_V0",
        "Manufacturer",
        "Family",
        "Product_Evidence_Group",
        "Negative_Conflict_Group",
        "Generic_Token_Risk",
        "Master_Validation_Status",
        "Final_Candidate_Score",
        "Scope_Flag",
    ]
    present = [column for column in columns if column in df.columns]
    decision = df[present].copy()
    decision["Decision_Reason"] = ""
    decision.loc[decision["Output_Tier"].eq("Trusted_Dashboard"), "Decision_Reason"] = (
        "Reference-valid surgical mapping with sufficient evidence and no exclusion conflict"
    )
    decision.loc[decision["Output_Tier"].eq("Review_Queue"), "Decision_Reason"] = (
        "Potential surgical row or mapping risk requiring human/business/reference review"
    )
    decision.loc[decision["Output_Tier"].eq("Excluded_Unmapped"), "Decision_Reason"] = (
        "No sufficient surgical evidence or strong non-surgical scope"
    )
    return decision


def _series(df: pd.DataFrame, column: str, default: Any = "") -> pd.Series:
    if column in df.columns:
        return df[column]
    return pd.Series(default, index=df.index)


def _add_country_year(frame: pd.DataFrame, country: str, year: str) -> pd.DataFrame:
    if frame is None or frame.empty:
        return frame
    out = frame.copy()
    if "Country" in out.columns:
        out["Country"] = country
    else:
        out.insert(0, "Country", country)
    if "Year" in out.columns:
        out["Year"] = year
    else:
        out.insert(1, "Year", year)
    return out


def _evidence_series(ev: pd.DataFrame, column: str, default: Any = "") -> pd.Series:
    if column in ev.columns:
        return ev[column]
    return pd.Series(default, index=ev.index)


def build_topn_candidate_table(
    country: str,
    year: str,
    source_file: str,
    df: pd.DataFrame,
    ev: pd.DataFrame,
) -> pd.DataFrame:
    """Expose deterministic top-N candidates without re-enabling vector auto mapping."""

    base = wf.build_candidate_table(df, ev)
    base = base.copy()
    tier = wf.output_tier(df)
    uid = _series(df, "UniqueID").astype(str)
    row_value = wf.value_usd(df)
    source_text = source_text_norm(df, ev)

    def num_ev(column: str, default: float = 0.0) -> pd.Series:
        return pd.to_numeric(_evidence_series(ev, column, default), errors="coerce").fillna(default).astype(float)

    product_score = num_ev("product_score")
    family_score = num_ev("family_score")
    manufacturer_score = num_ev("manufacturer_score")
    fuzzy_score = num_ev("fuzzy_score")
    word_tfidf_score = num_ev("word_tfidf_score")
    char_tfidf_score = num_ev("char_tfidf_score")
    semantic_score = num_ev("semantic_score")
    hs_score = num_ev("hs_score")
    exclusion_score = num_ev("exclusion_score")
    final_score = num_ev("final_candidate_score")
    generic_risk = _evidence_series(ev, "generic_token_risk", False).fillna(False).astype(bool)
    ref_valid = _series(df, "Ref_Valid", "").fillna("").astype(str)
    master_status = _evidence_series(ev, "master_validation_status", "").fillna("").astype(str)
    qa_status = _series(df, "QA_Status", "").fillna("").astype(str)
    candidate_segment = _evidence_series(ev, "candidate_segment", "").fillna("").astype(str)
    candidate_subsegment = _evidence_series(ev, "candidate_subsegment", "").fillna("").astype(str)
    candidate_product = _evidence_series(ev, "candidate_product", "").fillna("").astype(str)
    date_risk = detect_date_month_false_positive(df, ev).astype(bool)
    ophthalmic_risk = detect_ophthalmic_imaging_conflict(df, ev).astype(bool)
    extended_fp_risk = detect_extended_false_positive(df, ev).astype(bool)
    independent_surgical = detect_independent_surgical_signal(df, ev).astype(bool)

    def choose_candidate(current: pd.Series, proposed: pd.Series) -> pd.Series:
        current = current.fillna("").astype(str)
        proposed = proposed.fillna("").astype(str)
        return current.where(current.map(wf.norm_text).ne(""), proposed)

    uid_to_date = dict(zip(uid, date_risk, strict=False))
    uid_to_ophthalmic = dict(zip(uid, ophthalmic_risk, strict=False))
    uid_to_extended_fp = dict(zip(uid, extended_fp_risk, strict=False))
    uid_to_value = dict(zip(uid, row_value, strict=False))

    if not base.empty:
        for offset, value in [(0, country), (1, year), (2, source_file)]:
            column = ["Country", "Year", "Source_File"][offset]
            if column in base.columns:
                base[column] = value
            else:
                base.insert(offset, column, value)
        if "candidate_source_method" not in base.columns:
            base["candidate_source_method"] = "existing_mapping"
        else:
            base["candidate_source_method"] = base["candidate_source_method"].replace("", "existing_mapping")
        if "UniqueID" in base.columns:
            base_uid = base["UniqueID"].astype(str)
            base["date_month_token_risk"] = base_uid.map(uid_to_date).fillna(False).astype(bool)
            base["ophthalmic_imaging_conflict"] = base_uid.map(uid_to_ophthalmic).fillna(False).astype(bool)
            base["extended_false_positive_risk"] = base_uid.map(uid_to_extended_fp).fillna(False).astype(bool)
            base["Value_USD_num"] = base_uid.map(uid_to_value).fillna(0).astype(float)
        else:
            base["date_month_token_risk"] = False
            base["ophthalmic_imaging_conflict"] = False
            base["extended_false_positive_risk"] = False
            base["Value_USD_num"] = 0.0
        base["vector_auto_mapping_status"] = "archived_disabled"
        if "semantic_score" not in base.columns:
            base["semantic_score"] = 0.0

    def method_frame(
        method: str,
        mask: pd.Series,
        rank: int,
        reason: str,
        *,
        semantic_override: pd.Series | None = None,
        hs_override: pd.Series | None = None,
        final_override: pd.Series | None = None,
    ) -> pd.DataFrame:
        mask = mask.reindex(df.index).fillna(False).astype(bool)
        if not mask.any():
            return pd.DataFrame()
        selected_values = row_value.loc[mask]
        if len(selected_values) > MAX_CANDIDATE_EXTRA_ROWS_PER_METHOD:
            selected = selected_values.sort_values(ascending=False).head(MAX_CANDIDATE_EXTRA_ROWS_PER_METHOD).index
        else:
            selected = selected_values.index
        source = df.loc[selected].copy()
        cand_segment = choose_candidate(
            source.get("Segment", pd.Series("", index=selected)),
            candidate_segment.loc[selected],
        )
        cand_subsegment = choose_candidate(
            source.get("Sub-segment", pd.Series("", index=selected)),
            candidate_subsegment.loc[selected],
        )
        cand_product = choose_candidate(
            source.get("Product_V0", pd.Series("", index=selected)),
            candidate_product.loc[selected],
        )
        local_semantic = semantic_score.loc[selected]
        local_hs = hs_score.loc[selected]
        local_final = final_score.loc[selected]
        if semantic_override is not None:
            local_semantic = semantic_override.reindex(selected).fillna(local_semantic)
        if hs_override is not None:
            local_hs = hs_override.reindex(selected).fillna(local_hs)
        if final_override is not None:
            local_final = final_override.reindex(selected).fillna(local_final)
        out = pd.DataFrame(
            {
                "Country": country,
                "Year": year,
                "Source_File": source_file,
                "UniqueID": uid.loc[selected].values,
                "candidate_rank": rank,
                "candidate_segment": cand_segment.values,
                "candidate_subsegment": cand_subsegment.values,
                "candidate_product": cand_product.values,
                "candidate_player": source.get("Manufacturer", pd.Series("", index=selected)).fillna("").astype(str).values,
                "candidate_family": source.get("Family", pd.Series("", index=selected)).fillna("").astype(str).values,
                "candidate_source_method": method,
                "product_score": product_score.loc[selected].values,
                "family_score": family_score.loc[selected].values,
                "manufacturer_score": manufacturer_score.loc[selected].values,
                "fuzzy_score": fuzzy_score.loc[selected].values,
                "word_tfidf_score": word_tfidf_score.loc[selected].values,
                "char_tfidf_score": char_tfidf_score.loc[selected].values,
                "semantic_score": local_semantic.values,
                "hs_score": local_hs.values,
                "exclusion_score": exclusion_score.loc[selected].values,
                "generic_token_risk": generic_risk.loc[selected].values,
                "date_month_token_risk": date_risk.loc[selected].values,
                "ophthalmic_imaging_conflict": ophthalmic_risk.loc[selected].values,
                "extended_false_positive_risk": extended_fp_risk.loc[selected].values,
                "vector_auto_mapping_status": "archived_disabled",
                "master_validation_status": master_status.loc[selected].values,
                "final_candidate_score": local_final.values,
                "routing_decision": tier.loc[selected].values,
                "decision_reason": reason,
                "Value_USD_num": row_value.loc[selected].values,
            }
        )
        return out

    mapped_product = _series(df, "Product_V0", "").fillna("").astype(str)
    has_alt_category = (
        product_score.gt(0)
        & candidate_product.ne("")
        & candidate_product.map(wf.norm_text).ne(mapped_product.map(wf.norm_text))
    )
    uncertain = tier.eq("Review_Queue") | tier.eq("Excluded_Unmapped")
    abbreviation_mask = source_text.str.contains(
        r"\b(?:des|bms|ptca|crt[\s-]?d|icd|tavi|tavr|pdo|on[\s-]?x)\b",
        regex=True,
        na=False,
    )
    llm_review_mask = (
        tier.eq("Review_Queue")
        & row_value.ge(50_000)
        & (exclusion_score.gt(0) | generic_risk | final_score.between(25, 70))
    )
    semantic_discovery_score = pd.Series(0.0, index=df.index)
    semantic_discovery_score.loc[independent_surgical] = 10.0

    frames = []
    if not base.empty:
        frames.append(base)
    method_specs = [
        (
            "exact",
            tier.eq("Trusted_Dashboard") & ref_valid.eq("Y"),
            1,
            "Existing trusted row retained because the final tuple passes latest master validation",
            {},
        ),
        (
            "existing_mapping",
            uncertain & final_score.ge(45),
            2,
            "Existing deterministic mapping retained for review; not promoted unless master/evidence gates pass",
            {},
        ),
        (
            "manufacturer_alias",
            uncertain & manufacturer_score.gt(0),
            3,
            "Manufacturer alias evidence found; product/family support still required before Trusted_Dashboard",
            {},
        ),
        (
            "family_alias",
            uncertain & family_score.gt(0),
            4,
            "Family/model alias evidence found; generic-token and manufacturer/product support gates still apply",
            {},
        ),
        (
            "product_alias",
            uncertain & (product_score.gt(0) | has_alt_category),
            5,
            "Product/category phrase evidence retained for review and recall measurement",
            {},
        ),
        (
            "abbreviation",
            uncertain & abbreviation_mask,
            6,
            "Clinical/product abbreviation evidence retained for review; abbreviations cannot auto-map by themselves",
            {},
        ),
        (
            "fuzzy",
            uncertain & fuzzy_score.gt(0),
            7,
            "Fuzzy lexical evidence retained as a candidate only; fuzzy-only rows remain review",
            {},
        ),
        (
            "word_tfidf",
            uncertain & word_tfidf_score.gt(0),
            8,
            "Word n-gram TF-IDF product evidence retained for review and threshold tuning",
            {},
        ),
        (
            "char_tfidf",
            uncertain & char_tfidf_score.gt(0),
            9,
            "Character n-gram evidence retained for spelling/truncation discovery",
            {},
        ),
        (
            "semantic",
            uncertain & independent_surgical,
            10,
            "Semantic/discovery placeholder from deterministic surgical concept screen; vector auto-mapping remains disabled",
            {"semantic_override": semantic_discovery_score},
        ),
        (
            "hs_rule",
            tier.eq("Review_Queue") & qa_status.str.contains("Extended HS", case=False, regex=False),
            11,
            "Extended HS surgical product retained for explicit business-scope decision, not auto-trusted",
            {"hs_override": hs_score.clip(lower=10)},
        ),
        (
            "llm_review",
            llm_review_mask,
            12,
            "High-value ambiguous row queued for optional resolver/QC review after deterministic candidate generation",
            {},
        ),
    ]
    for method, mask, rank, reason, overrides in method_specs:
        frame = method_frame(method, mask, rank, reason, **overrides)
        if not frame.empty:
            frames.append(frame)

    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    dedupe_cols = [
        "UniqueID",
        "candidate_source_method",
        "candidate_segment",
        "candidate_subsegment",
        "candidate_product",
        "candidate_player",
        "candidate_family",
    ]
    for column in dedupe_cols:
        if column not in out.columns:
            out[column] = ""
    out = out.drop_duplicates(subset=dedupe_cols)
    out = out.sort_values(
        ["Value_USD_num", "candidate_rank", "final_candidate_score", "UniqueID"],
        ascending=[False, True, False, True],
    )
    out = out.groupby("UniqueID", group_keys=False).head(10)
    if len(out) > MAX_CANDIDATE_ROWS:
        out = out.head(MAX_CANDIDATE_ROWS)
    out = out.sort_values(
        ["Country", "Year", "UniqueID", "candidate_rank", "final_candidate_score", "Value_USD_num"],
        ascending=[True, True, True, True, False, False],
    )
    return out.reset_index(drop=True)


def build_rule_tables() -> dict[str, pd.DataFrame]:
    manufacturer_alias = pd.DataFrame(
        [
            {
                "Alias_Group": canonical,
                "Canonical_Manufacturer": canonical,
                "Regex_Pattern": pattern,
                "Alias_Text": aliases,
                "Review_Status": "approved deterministic rule",
            }
            for canonical, pattern, aliases in wf.MANUFACTURER_ALIAS_RULES
        ]
    )
    product_alias = pd.DataFrame(
        [
            {
                "Evidence_Group": rule.get("group", ""),
                "Regex_Pattern": rule.get("pattern", ""),
                "Segment": rule.get("segment", ""),
                "Sub-segment": rule.get("subsegment", ""),
                "Product": rule.get("product", ""),
                "Alias_Text": rule.get("aliases", ""),
                "Score": rule.get("score", ""),
                "Review_Status": "approved deterministic product evidence",
            }
            for rule in wf.PRODUCT_RULES
        ]
    )
    abbreviations = pd.DataFrame(
        [
            ("DES", "drug eluting stent", "stents / DES / BMS"),
            ("BMS", "bare metal stent", "stents / DES / BMS"),
            ("PTCA", "percutaneous transluminal coronary angioplasty", "balloons / PTCA"),
            ("CRT-D", "cardiac resynchronization therapy defibrillator", "cardiac rhythm accessory review"),
            ("ICD", "implantable cardioverter defibrillator", "cardiac rhythm accessory review"),
            ("TAVI", "transcatheter aortic valve implantation", "heart valve"),
            ("TAVR", "transcatheter aortic valve replacement", "heart valve"),
            ("PDO", "polydioxanone", "suture-related extended scope"),
        ],
        columns=["Abbreviation", "Expansion", "Mapping_Use"],
    )
    customs_phrase = pd.DataFrame(
        [
            ("stent system", "stents / DES / BMS", "candidate product evidence"),
            ("coronary stent system", "stents / DES / BMS", "candidate product evidence"),
            ("vascular stent", "stents / DES / BMS", "candidate product evidence"),
            ("implantable stent", "stents / DES / BMS", "candidate product evidence"),
            ("guiding catheter", "catheters / guiding catheters", "candidate product evidence"),
            ("guide catheter", "catheters / guiding catheters", "candidate product evidence"),
            ("introducer sheath", "guidewires / sheaths / introducers", "candidate product evidence"),
            ("video endoscopy", "endoscopy / laparoscopy", "review candidate evidence"),
            ("cell saver", "autotransfusion", "reference update candidate"),
            ("blood recovery", "autotransfusion", "reference update candidate"),
            ("artificial disc", "spine implant", "reference update candidate"),
        ],
        columns=["Customs_Phrase", "Evidence_Group", "Mapping_Use"],
    )
    misspellings = pd.DataFrame(
        [
            ("cannulae", "cannula", "cannula product evidence"),
            ("canula", "cannula", "cannula product evidence"),
            ("catheder", "catheter", "catheter product evidence"),
            ("cathetar", "catheter", "catheter product evidence"),
            ("endoscpy", "endoscopy", "endoscopy review evidence"),
            ("laproscopy", "laparoscopy", "laparoscopy review evidence"),
        ],
        columns=["Observed_Text", "Canonical_Text", "Mapping_Use"],
    )
    family_alias = pd.DataFrame(
        [
            ("ON-X", "prosthetic heart valve family", "heart valve", "reference/update review"),
            ("Vicryl", "suture family", "extended surgical product", "business scope pending"),
            ("Prolene", "suture family", "extended surgical product", "business scope pending"),
            ("Polysorb", "suture family", "extended surgical product", "business scope pending"),
            ("Surgicryl", "suture family", "extended surgical product", "business scope pending"),
            ("Polydioxanone", "suture family", "extended surgical product", "business scope pending"),
            ("March", "APT Medical guiding catheter family", "guiding catheter", "requires APT Medical + vascular product context"),
        ],
        columns=["Family_Alias", "Canonical_Family_Or_Use", "Product_Context", "Guardrail"],
    )
    negative_terms = pd.DataFrame(
        [
            {
                "Exclusion_Category": name,
                "Regex_Pattern": pattern,
                "Decision_Default": "review_or_exclude_before_trusted",
                "Strength": "strong",
            }
            for name, pattern in wf.NEGATIVE_RULES
        ]
        + [
            {
                "Exclusion_Category": "pharma/vaccine",
                "Regex_Pattern": PHARMA_VACCINE_RE.pattern,
                "Decision_Default": "review_or_exclude_before_trusted",
                "Strength": "strong",
            },
            {
                "Exclusion_Category": "date/month token",
                "Regex_Pattern": DATE_MONTH_RE.pattern,
                "Decision_Default": "review unless validated as product family",
                "Strength": "contextual",
            },
        ]
    )
    generic_tokens = pd.DataFrame(
        sorted(set(wf.GENERIC_TOKENS + ["March", "Xtra", "Masters", "Image Processor"])),
        columns=["Generic_Token"],
    )
    generic_tokens["Rule"] = "Cannot drive Trusted_Dashboard by itself; requires product, manufacturer/family, and master validation"
    date_month_tokens = pd.DataFrame(DATE_MONTH_TOKENS, columns=["Date_Month_Token"])
    date_month_tokens["Rule"] = "Treat as date/month risk unless validated as a specific approved product family with context"
    hs_scope = pd.DataFrame(
        [
            ("core surgical HS", "Trusted eligible only after product evidence and master validation", "active"),
            ("extended HS", "Review_Queue until business approves inclusion", "business_scope_pending"),
            ("HS 3006 sutures/mesh/hemostats/wound items", "Extended_Surgical_Decision", "business_scope_pending"),
        ],
        columns=["HS_Scope_Group", "Rule", "Decision_Status"],
    )
    disambig = pd.DataFrame(
        [
            {
                "Rule_Name": "APT Medical March",
                "Positive_Context_Required": "APT Medical/APT alias plus guiding catheter/catheter/vascular access/introducer/sheath",
                "Negative_Context": "vaccine/pharma/food/lab/diagnostic or month-only text",
                "Default_Route": "Review_Queue",
            },
            {
                "Rule_Name": "Generic token family",
                "Positive_Context_Required": "non-generic product phrase plus manufacturer/family evidence and latest master validation",
                "Negative_Context": "generic token alone or raw description conflicts with mapped product",
                "Default_Route": "Review_Queue",
            },
        ]
    )
    return {
        "Manufacturer_Alias": manufacturer_alias,
        "Family_Alias": family_alias,
        "Product_Alias": product_alias,
        "Abbreviation_Alias": abbreviations,
        "Customs_Phrase_Alias": customs_phrase,
        "Misspelling_Alias": misspellings,
        "Negative_Terms": negative_terms,
        "Generic_Tokens": generic_tokens,
        "Date_Month_Tokens": date_month_tokens,
        "HS_Scope_Rules": hs_scope,
        "Product_Disambig_Rules": disambig,
    }


def classify_extended_decision(extended: pd.DataFrame) -> pd.DataFrame:
    if extended is None or extended.empty:
        return extended
    out = extended.copy()
    text_cols = [
        col
        for col in [
            "Sample_Detailed_Product",
            "Sample_Importer",
            "Sample_Exporter",
            "Segment",
            "Sub-segment",
            "Product",
            "Manufacturer",
            "Family",
            "Evidence_Group",
        ]
        if col in out.columns
    ]
    text = out[text_cols].fillna("").astype(str).agg(" ".join, axis=1).str.lower() if text_cols else pd.Series("", index=out.index)
    category = pd.Series("business_scope_pending", index=out.index, dtype="object")
    category.loc[text.str.contains(r"\b(?:vaccine|vaccination|pharmaceutical|pharma|medicine|tablet|capsule|food|beverage|reagent|assay|diagnostic|laborator(?:y|ies)|ivd)\b", regex=True, na=False)] = "false_positive_pharma_vaccine_food_lab"
    category.loc[text.str.contains(r"\b(?:tomography|oct\b|ct scanner|mri|ultrasound|angiography|laser imager|dry imager|scanner)\b", regex=True, na=False)] = "false_positive_imaging_or_diagnostic"
    category.loc[text.str.contains(r"\b(?:dental|orthodontic|veterinary|equine|canine|bovine|feline|cosmetic|aesthetic|dermal filler|hydra facial)\b", regex=True, na=False)] = "false_positive_dental_cosmetic_veterinary"
    category.loc[text.str.contains(r"\b(?:march|jan|january|feb|february|apr|april|may|jun|june|jul|july|aug|august|sep|september|oct|october|nov|november|dec|december|light source|target|sprinter|arrive|current|volt|maestro|imager|hybrid|elite|essential|unity|therapy|velocity alpha|celsius|express|hydra|zero|xtra|masters)\b", regex=True, na=False)] = "false_positive_month_or_generic_token"
    true_extended = text.str.contains(
        r"\b(?:vicryl|prolene|polysorb|surgicryl|pdo|polydioxanone|sutures?|mesh|bone cement|floseal|hemostat|wound|surgipro|demesorb)\b",
        regex=True,
        na=False,
    )
    category.loc[true_extended & category.eq("business_scope_pending")] = "true_extended_surgical_candidate"
    out.insert(0, "Extended_Decision_Category", category)
    out.insert(1, "Human_Decision_Status", "pending")
    out["Recommended_Current_Routing"] = out.get(
        "Recommended_Current_Routing",
        pd.Series("Review_Queue - Extended HS business decision required", index=out.index),
    )
    out["Recommended_Current_Routing"] = out["Extended_Decision_Category"].map(
        {
            "true_extended_surgical_candidate": "Review_Queue until business decides extended surgical scope",
            "business_scope_pending": "Review_Queue - business scope pending",
            "false_positive_month_or_generic_token": "Keep out of Trusted; generic/date token needs human validation",
            "false_positive_pharma_vaccine_food_lab": "Keep out of Trusted; likely pharma/vaccine/food/lab conflict",
            "false_positive_imaging_or_diagnostic": "Keep out of Trusted; imaging/diagnostic conflict",
            "false_positive_dental_cosmetic_veterinary": "Keep out of Trusted; dental/cosmetic/veterinary conflict",
        }
    ).fillna(out["Recommended_Current_Routing"])
    return out


def split_reference_requests(reference_request: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if reference_request is None or reference_request.empty:
        empty = pd.DataFrame()
        return empty, empty, empty
    out = reference_request.copy()
    text_cols = [
        col
        for col in [
            "Segment",
            "Sub-segment",
            "Product_V0",
            "Product",
            "Manufacturer",
            "Family",
            "Sample_Detailed_Product",
            "Sample_Importer",
            "Sample_Exporter",
            "Evidence_Group",
            "Negative_Conflict_Group",
        ]
        if col in out.columns
    ]
    text = out[text_cols].fillna("").astype(str).agg(" ".join, axis=1).str.lower() if text_cols else pd.Series("", index=out.index)
    negative = out.get("Negative_Conflict_Group", pd.Series("", index=out.index)).fillna("").astype(str).str.strip().ne("")
    generic = text.str.contains(
        r"\b(?:light source|target|sprinter|arrive|current|volt|maestro|imager|hybrid|elite|essential|unity|therapy|velocity alpha|celsius|express|hydra|zero|march|xtra|masters|image processor)\b",
        regex=True,
        na=False,
    )
    date_month = regex_contains(text, DATE_MONTH_RE)
    needs_review = negative | text.str.contains(
        r"\b(?:mentor|breast implant|microcatheter|autotransfusion|cell saver|artificial disc|image processor|crt[- ]?d|icd)\b",
        regex=True,
        na=False,
    )
    rejected_mask = generic | date_month
    clean_mask = ~rejected_mask & ~needs_review

    def label(frame: pd.DataFrame, decision: str) -> pd.DataFrame:
        if frame.empty:
            return frame
        data = frame.copy()
        data.insert(0, "Reference_Request_Decision", decision)
        data.insert(1, "Human_Decision_Status", "pending")
        return data

    clean = label(out.loc[clean_mask].copy(), "Reference_Update_Request_Clean")
    rejected = label(out.loc[rejected_mask].copy(), "Reference_Update_Rejected_GenericToken")
    review = label(out.loc[~rejected_mask & needs_review].copy(), "Reference_Update_Needs_Human_Review")
    return clean, rejected, review


def build_trusted_generic_token_qc(df: pd.DataFrame, ev: pd.DataFrame) -> pd.DataFrame:
    tier = wf.output_tier(df)
    generic = _evidence_series(ev, "generic_token_risk", False).astype(bool)
    date_risk = detect_date_month_false_positive(df, ev)
    march_risk = detect_march_rule_violation(df, ev)
    family = _series(df, "Family", "").fillna("").astype(str).str.lower()
    generic_family = family.isin({token.lower() for token in wf.GENERIC_TOKENS + ["march", "xtra", "masters", "image processor"]})
    mask = tier.eq("Trusted_Dashboard") & (generic | date_risk | march_risk | generic_family)
    if not mask.any():
        return pd.DataFrame()
    out = wf.row_sample_columns(df, ev, mask).copy()
    out["Date_Month_Token_Risk"] = date_risk.loc[mask].values
    out["APT_March_Rule_Risk"] = march_risk.loc[mask].values
    out["Generic_Token_Risk"] = generic.loc[mask].values
    out["QC_Recommendation"] = "Review before release; trusted generic/date-token rows require explicit supporting product and manufacturer evidence"
    return out.sort_values("Value_USD_num", ascending=False)


def build_independent_false_negative_screen(df: pd.DataFrame, ev: pd.DataFrame) -> pd.DataFrame:
    """Full-text surgical signal screen over Excluded/Unmapped rows."""
    tier = wf.output_tier(df)
    source_text = source_text_norm(df, ev)
    negative = _evidence_series(ev, "negative_conflict_group", "").fillna("").astype(str)
    product_support = strong_product_support(df, ev)
    independent = detect_independent_surgical_signal(df, ev)
    ophthalmic = detect_ophthalmic_imaging_conflict(df, ev)
    extended_false_positive = detect_extended_false_positive(df, ev)
    pharma_false_positive = regex_contains(source_text, PHARMA_VACCINE_RE)
    mask = (
        tier.eq("Excluded_Unmapped")
        & (product_support | independent)
        & negative.eq("")
        & ~ophthalmic
        & ~extended_false_positive
        & ~pharma_false_positive
    )
    if not mask.any():
        return pd.DataFrame()
    out = wf.row_sample_columns(df, ev, mask, limit=None).copy()
    out["Independent_Screen_Reason"] = (
        "Full-text surgical keyword/alias/product screen found possible surgical evidence in Excluded_Unmapped"
    )
    out["Recommended_Action"] = "Move to Review_Queue or add deterministic exclusion after human check"
    out["Normalized_Source_Text"] = source_text.loc[mask].values
    return out.sort_values("Value_USD_num", ascending=False).reset_index(drop=True)


def build_output_tables(
    country: str,
    year: str,
    input_path: Path,
    output_path: Path,
    report_path: Path,
    baseline: pd.DataFrame,
    improved: pd.DataFrame,
    ev: pd.DataFrame,
    before_metrics: dict[str, Any],
    after_metrics: dict[str, Any],
    validation: pd.DataFrame,
    changes: pd.DataFrame,
    runtime: float,
) -> tuple[OrderedDict[str, pd.DataFrame], OrderedDict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    tier = wf.output_tier(improved)
    trusted = improved.loc[tier.eq("Trusted_Dashboard")].copy()
    review = improved.loc[tier.eq("Review_Queue")].copy()
    excluded = improved.loc[tier.eq("Excluded_Unmapped")].copy()

    log_step(f"{input_path.name}: building dashboard rebuild")
    dash = dashboard_rebuild(improved, country)
    log_step(f"{input_path.name}: building bounded top-N candidate table")
    candidate = build_topn_candidate_table(country, year, input_path.name, improved, ev)
    log_step(f"{input_path.name}: building review and reference request tables")
    extended = classify_extended_decision(wf.build_extended_decision(improved, ev))
    alias_request = wf.build_alias_update_request(improved, ev)
    reference_request = wf.build_reference_update_request(improved, ev)
    reference_request_clean, reference_request_rejected_generic, reference_request_needs_review = split_reference_requests(reference_request)
    precision_risk = wf.build_precision_risk_rows(baseline, improved, ev)
    false_positive_screen = precision_risk.copy()
    if not false_positive_screen.empty:
        false_positive_screen.insert(0, "Screen_Type", "Trusted precision risk")
    trusted_generic_qc = build_trusted_generic_token_qc(improved, ev)
    log_step(f"{input_path.name}: building recall-hunt QA screens")
    potential_missed = wf.build_potential_missed(improved, ev, baseline)
    cluster_summary = wf.build_cluster_summary(improved, ev)
    excluded_screen = wf.build_excluded_surgicalish(improved, ev)
    independent_false_negative = build_independent_false_negative_screen(improved, ev)
    gold_template = wf.build_gold_label_template(improved, ev, baseline)
    experiment = wf.build_experiment_matrix(before_metrics, after_metrics, changes, runtime)
    active_learning = wf.build_active_learning_updates(alias_request, reference_request)
    specific_examples, unresolved_examples = wf.build_specific_examples(improved, ev, baseline)
    metrics = pd.DataFrame([before_metrics, after_metrics])

    change_log = changes.copy()
    change_log.insert(0, "Update_Timestamp", TIMESTAMP)
    change_log.insert(1, "Country", country)
    change_log.insert(2, "Year", year)
    change_log["Input_File"] = str(input_path)
    change_log["Output_File"] = str(output_path)
    change_log["QA_Report_File"] = str(report_path)
    change_log["Runtime_Seconds"] = round(runtime, 2)
    change_log["Raw_Rows"] = len(improved)
    change_log["Raw_Value_USD"] = round(value_usd(improved), 2)

    summary = executive_summary(country, year, before_metrics, after_metrics, validation, changes)
    recommendations = workflow_recommendations()
    log_step(f"{input_path.name}: building decision log and rule tables")
    decision_log = build_mapping_decision_log(improved, ev)
    rule_tables = build_rule_tables()

    workbook_tables: OrderedDict[str, pd.DataFrame] = OrderedDict(
        [
            ("RawData", improved),
            ("Trusted_Dashboard", trusted),
            ("Review_Queue", review),
            ("Excluded_Unmapped", excluded),
            ("Dashboard_Rebuild", dash),
            ("Candidate_Table", candidate),
            ("Extended_Surgical_Decision", extended),
            ("Alias_Update_Request", alias_request),
            ("Reference_Update_Request", reference_request),
            ("Reference_Update_Request_Clean", reference_request_clean),
            ("Ref_Rejected_GenericToken", reference_request_rejected_generic),
            ("Ref_Needs_Human_Review", reference_request_needs_review),
            ("Precision_Risk_Rows", precision_risk),
            ("False_Positive_Screen", false_positive_screen),
            ("Trusted_Generic_Token_QC", trusted_generic_qc),
            ("Potential_Missed_Surgical_Rows", potential_missed),
            ("Specific_Examples", specific_examples),
            ("Unresolved_Examples", unresolved_examples),
            ("Review_Queue_Cluster_Summary", cluster_summary),
            ("Excluded_Surgicalish_Screen", excluded_screen),
            ("Independent_FN_Screen", independent_false_negative),
            ("Gold_Label_Template", gold_template),
            ("Metrics_Summary", metrics),
            ("Change_Log", change_log),
            ("Validation", validation),
            ("Mapping_Decision_Log", decision_log),
            ("Experiment_Matrix", experiment),
            ("Evidence_Scoring_Model", wf.build_evidence_model()),
            ("Routing_Rules", wf.build_routing_rules()),
            *rule_tables.items(),
            ("Active_Learning_Updates", active_learning),
            ("Workflow_Recommendations", recommendations),
        ]
    )

    qa_tables: OrderedDict[str, pd.DataFrame] = OrderedDict(
        [
            ("Executive_Summary", summary),
            ("Baseline_vs_Improved", metrics),
            ("Validation", validation),
            ("Changes_Applied", change_log),
            ("Dashboard_Rebuild", dash),
            ("Candidate_Table", candidate),
            ("Specific_Examples", specific_examples),
            ("Remaining_Unresolved", unresolved_examples),
            ("Extended_Surgical_Decision", extended),
            ("Alias_Update_Request", alias_request),
            ("Reference_Update_Request", reference_request),
            ("Reference_Update_Request_Clean", reference_request_clean),
            ("Ref_Rejected_GenericToken", reference_request_rejected_generic),
            ("Ref_Needs_Human_Review", reference_request_needs_review),
            ("Precision_Risk_Rows", precision_risk),
            ("False_Positive_Screen", false_positive_screen),
            ("Trusted_Generic_Token_QC", trusted_generic_qc),
            ("Potential_Missed_Surgical_Rows", potential_missed),
            ("Review_Queue_Cluster_Summary", cluster_summary),
            ("Excluded_Surgicalish_Screen", excluded_screen),
            ("Independent_FN_Screen", independent_false_negative),
            ("Gold_Label_Template", gold_template),
            ("Experiment_Matrix", experiment),
            ("Evidence_Scoring_Model", wf.build_evidence_model()),
            ("Routing_Rules", wf.build_routing_rules()),
            *rule_tables.items(),
            ("LLM_Agent_Evaluation", wf.build_llm_agent_eval()),
            ("Active_Learning_Updates", active_learning),
            ("Workflow_Recommendations", recommendations),
        ]
    )

    consolidated = {
        "metrics": metrics,
        "validation": validation.assign(Country=country, Year=year),
        "change_log": change_log,
        "alias": _add_country_year(alias_request, country, year),
        "reference": _add_country_year(reference_request, country, year),
        "reference_clean": _add_country_year(reference_request_clean, country, year),
        "reference_rejected_generic": _add_country_year(reference_request_rejected_generic, country, year),
        "reference_needs_review": _add_country_year(reference_request_needs_review, country, year),
        "extended": _add_country_year(extended, country, year),
        "precision": _add_country_year(precision_risk, country, year),
        "false_positive": _add_country_year(false_positive_screen, country, year),
        "trusted_generic_qc": _add_country_year(trusted_generic_qc, country, year),
        "missed": _add_country_year(potential_missed, country, year),
        "clusters": _add_country_year(cluster_summary, country, year),
        "excluded": _add_country_year(excluded_screen, country, year),
        "independent_fn": _add_country_year(independent_false_negative, country, year),
    }
    return workbook_tables, qa_tables, consolidated


def clean_sheet_name(name: str) -> str:
    cleaned = re.sub(r"[\[\]:*?/\\]", "_", name)[:31]
    return cleaned or "Sheet"


def write_cell(worksheet: Any, row: int, col: int, value: Any, text_format: Any = None) -> None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        worksheet.write_blank(row, col, None)
        return
    if isinstance(value, (pd.Timestamp, datetime)):
        worksheet.write_string(row, col, value.strftime("%Y-%m-%d %H:%M:%S"), text_format)
        return
    if isinstance(value, bool):
        worksheet.write_boolean(row, col, value)
        return
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if math.isfinite(float(value)):
            worksheet.write_number(row, col, float(value))
        else:
            worksheet.write_string(row, col, str(value), text_format)
        return
    text = str(value)
    if len(text) > 30000:
        text = text[:30000]
    worksheet.write_string(row, col, text, text_format)


def _write_df_part(workbook: Any, sheet_name: str, frame: pd.DataFrame) -> None:
    worksheet = workbook.add_worksheet(clean_sheet_name(sheet_name))
    header_format = workbook.add_format({"bold": True, "bg_color": "#D9EAF7", "border": 1})
    text_format = workbook.add_format({"text_wrap": False})
    if frame.empty:
        worksheet.write_row(0, 0, ["Note"], header_format)
        worksheet.write_string(1, 0, "No rows")
        worksheet.freeze_panes(1, 0)
        worksheet.set_column(0, 0, 22)
        return

    columns = [str(column) for column in frame.columns]
    worksheet.write_row(0, 0, columns, header_format)
    write_rows = len(frame)
    for excel_row, values in enumerate(frame.itertuples(index=False, name=None), start=1):
        for col_idx, value in enumerate(values):
            write_cell(worksheet, excel_row, col_idx, value, text_format)
    worksheet.freeze_panes(1, 0)
    worksheet.autofilter(0, 0, min(write_rows, EXCEL_MAX_DATA_ROWS), max(0, len(columns) - 1))
    for col_idx, column in enumerate(columns[:60]):
        sample = frame.iloc[:100, col_idx].map(lambda value: "" if pd.isna(value) else str(value))
        width = min(max([len(column), *(sample.map(len).tolist() or [0])]) + 2, 42)
        worksheet.set_column(col_idx, col_idx, width)


def write_df(workbook: Any, sheet_name: str, df: pd.DataFrame, max_rows: int = EXCEL_MAX_DATA_ROWS) -> None:
    """Write every row, splitting oversized tables across numbered sheets."""
    if df is None:
        df = pd.DataFrame()
    frame = df.reset_index(drop=True)
    if len(frame) <= max_rows:
        _write_df_part(workbook, sheet_name, frame)
        return
    for start in range(0, len(frame), max_rows):
        part_number = start // max_rows + 1
        part_name = sheet_name if part_number == 1 else f"{sheet_name}_Part_{part_number}"
        _write_df_part(workbook, part_name, frame.iloc[start : start + max_rows].reset_index(drop=True))


def write_workbook(path: Path, tables: OrderedDict[str, pd.DataFrame]) -> None:
    import xlsxwriter

    path.parent.mkdir(parents=True, exist_ok=True)
    XLSX_TMP_DIR.mkdir(parents=True, exist_ok=True)
    with xlsxwriter.Workbook(
        str(path),
        {
            "constant_memory": True,
            "nan_inf_to_errors": True,
            "strings_to_urls": False,
            "tmpdir": str(XLSX_TMP_DIR),
        },
    ) as workbook:
        workbook.use_zip64()
        for sheet_name, frame in tables.items():
            write_df(workbook, sheet_name, frame)


def combine_tables(frames: list[pd.DataFrame]) -> pd.DataFrame:
    non_empty = [frame for frame in frames if frame is not None and not frame.empty]
    if not non_empty:
        return pd.DataFrame()
    return pd.concat(non_empty, ignore_index=True)


def build_combined_qa(consolidated: list[dict[str, pd.DataFrame]]) -> OrderedDict[str, pd.DataFrame]:
    return OrderedDict(
        [
            ("Metrics_By_File", combine_tables([item["metrics"] for item in consolidated])),
            ("Validation_By_File", combine_tables([item["validation"] for item in consolidated])),
            ("Change_Log", combine_tables([item["change_log"] for item in consolidated])),
            ("Alias_Update_Request", combine_tables([item["alias"] for item in consolidated])),
            ("Reference_Update_Request", combine_tables([item["reference"] for item in consolidated])),
            ("Reference_Update_Request_Clean", combine_tables([item["reference_clean"] for item in consolidated])),
            ("Ref_Rejected_GenericToken", combine_tables([item["reference_rejected_generic"] for item in consolidated])),
            ("Ref_Needs_Human_Review", combine_tables([item["reference_needs_review"] for item in consolidated])),
            ("Extended_Surgical_Decision", combine_tables([item["extended"] for item in consolidated])),
            ("Precision_Risk_Rows", combine_tables([item["precision"] for item in consolidated])),
            ("False_Positive_Screen", combine_tables([item["false_positive"] for item in consolidated])),
            ("Trusted_Generic_Token_QC", combine_tables([item["trusted_generic_qc"] for item in consolidated])),
            ("Potential_Missed_Surgical_Rows", combine_tables([item["missed"] for item in consolidated])),
            ("Review_Queue_Cluster_Summary", combine_tables([item["clusters"] for item in consolidated])),
            ("Excluded_Surgicalish_Screen", combine_tables([item["excluded"] for item in consolidated])),
            ("Independent_FN_Screen", combine_tables([item["independent_fn"] for item in consolidated])),
            ("Workflow_Recommendations", workflow_recommendations()),
        ]
    )


def archive_old_shared_outputs(output_paths: list[Path], shared_dir: Path | None, dry_run: bool) -> list[dict[str, Any]]:
    if shared_dir is None or not shared_dir.exists():
        return []
    expected = {path.name for path in output_paths}
    stamp = re.sub(r"[^0-9A-Za-z_-]+", "_", TIMESTAMP).strip("_")
    archive_dir = ARCHIVE_DIR / stamp
    archive_rows: list[dict[str, Any]] = []
    for path in sorted(shared_dir.glob("*_FY20??_ML_Map_Mapped*.xlsx")):
        if path.name in expected:
            continue
        target = archive_dir / path.name
        counter = 1
        while target.exists():
            target = archive_dir / f"{path.stem}_{counter}{path.suffix}"
            counter += 1
        if not dry_run:
            archive_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(target))
        archive_rows.append(
            {
                "Output_File": str(path),
                "Published": "ARCHIVED",
                "Shared_Path": str(target),
                "Reason": "Archived superseded mapped workbook before publishing current country/year files",
            }
        )
    return archive_rows


def publish_current_files(output_paths: list[Path], shared_dir: Path | None, dry_run: bool) -> list[dict[str, Any]]:
    if shared_dir is None:
        publish_rows = []
        for path in output_paths:
            publish_rows.append({"Output_File": str(path), "Published": "NO", "Shared_Path": "", "Reason": "Shared folder not found"})
        return publish_rows

    publish_rows = archive_old_shared_outputs(output_paths, shared_dir, dry_run)
    for path in output_paths:
        target = shared_dir / path.name
        if not dry_run:
            shutil.copy2(path, target)
        publish_rows.append(
            {
                "Output_File": str(path),
                "Published": "YES",
                "Shared_Path": str(target),
                "Reason": "Copied latest current version over existing country/year workbook",
            }
        )
    return publish_rows


def update_mapping_log(shared_dir: Path | None, consolidated: list[dict[str, pd.DataFrame]], publish_rows: list[dict[str, Any]]) -> None:
    if shared_dir is None:
        return
    log_path = shared_dir / "MAPPING_IMPROVEMENT_LOG.xlsx"
    new_rows = combine_tables([item["change_log"] for item in consolidated])
    if not new_rows.empty:
        publish_df = pd.DataFrame(publish_rows)
        new_rows["Published_To_Shared"] = "YES"
        if not publish_df.empty:
            map_shared = dict(zip(publish_df["Output_File"], publish_df["Shared_Path"], strict=False))
            new_rows["Shared_Path"] = new_rows["Output_File"].map(map_shared).fillna("")
        new_rows["Log_Update_Timestamp"] = TIMESTAMP

    existing = pd.DataFrame()
    if log_path.exists():
        try:
            existing = pd.read_excel(log_path, sheet_name="Log", dtype=str).fillna("")
        except Exception:
            try:
                existing = pd.read_excel(log_path, sheet_name=0, dtype=str).fillna("")
            except Exception:
                existing = pd.DataFrame()

    full_log = pd.concat([existing, new_rows], ignore_index=True) if not new_rows.empty else existing
    latest_metrics = combine_tables([item["metrics"] for item in consolidated])
    validation = combine_tables([item["validation"] for item in consolidated])
    publish_df = pd.DataFrame(publish_rows)
    write_workbook(
        log_path,
        OrderedDict(
            [
                ("Log", full_log),
                ("Latest_Run_Metrics", latest_metrics),
                ("Latest_Run_Validation", validation),
                ("Published_Files", publish_df),
            ]
        ),
    )


def assert_expected_inputs(input_dir: Path) -> list[Path]:
    missing = [name for name in EXPECTED_FILES if not (input_dir / name).exists()]
    if missing:
        missing_text = "\n".join(f"- {name}" for name in missing)
        raise FileNotFoundError(f"Expected six input files, but these are missing:\n{missing_text}")
    return [input_dir / name for name in EXPECTED_FILES]


def process_one(path: Path, master_keys: wf.MasterKeys) -> tuple[Path, Path, dict[str, pd.DataFrame]]:
    SOURCE_TEXT_NORM_CACHE.clear()
    country, year = parse_country_year(path)
    start = time.perf_counter()
    log_step(f"Reading {path.name}")
    raw = read_raw(path)
    baseline = ensure_base_columns(raw)
    log_step(f"{path.name}: building evidence")
    before_ev = wf.build_evidence(baseline, master_keys)
    log_step(f"{path.name}: building baseline metrics")
    before_metrics = metrics_snapshot(country, year, "A0 Baseline", baseline, before_ev, 0, full_recall_screen=False)

    log_step(f"{path.name}: applying governed adjudicated aliases")
    adjudicated, alias_changes = apply_governed_family_aliases(baseline)
    adjudicated_ev = wf.build_evidence(adjudicated, master_keys)
    log_step(f"{path.name}: routing rows")
    improved, ev, route_changes = route_file(
        adjudicated,
        master_keys,
        baseline=adjudicated,
        ev=adjudicated_ev,
    )
    changes = pd.concat([alias_changes, route_changes], ignore_index=True)
    runtime = time.perf_counter() - start
    log_step(f"{path.name}: building improved metrics and validation")
    after_metrics = metrics_snapshot(country, year, "A1 Recall/Evidence Remap", improved, ev, runtime)
    validation = extra_validations(improved, ev, master_keys, country)

    output_path = OUT_DIR / path.name
    report_path = REPORT_DIR / f"{country}_FY{year}_Surgical_Mapping_QA_Report.xlsx"
    log_step(f"{path.name}: building workbook and QA tables")
    workbook_tables, qa_tables, consolidated = build_output_tables(
        country,
        year,
        path,
        output_path,
        report_path,
        baseline,
        improved,
        ev,
        before_metrics,
        after_metrics,
        validation,
        changes,
        runtime,
    )

    log_step(f"Writing remapped workbook {output_path.name}")
    write_workbook(output_path, workbook_tables)
    print(f"[{TIMESTAMP}] Writing QA report {report_path.name}", flush=True)
    write_workbook(report_path, qa_tables)

    fail_count = int(validation["Status"].astype(str).eq("FAIL").sum())
    print(
        f"[{TIMESTAMP}] Completed {country} FY{year}: "
        f"trusted={after_metrics.get('Trusted rows', 0):,}, "
        f"review={after_metrics.get('Review rows', 0):,}, "
        f"excluded={after_metrics.get('Excluded rows', 0):,}, "
        f"validation_failures={fail_count}",
        flush=True,
    )
    del raw, baseline, before_ev, adjudicated, adjudicated_ev, improved, ev, workbook_tables, qa_tables
    SOURCE_TEXT_NORM_CACHE.clear()
    gc.collect()
    return output_path, report_path, consolidated


def main() -> None:
    global OUT_DIR, REPORT_DIR, MASTER_PATH

    parser = argparse.ArgumentParser(description="Remap all six surgical import mapping workbooks.")
    parser.add_argument("--input-dir", type=Path, default=INPUT_DIR)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--reports-dir", type=Path, default=REPORT_DIR)
    parser.add_argument("--master", type=Path, default=MASTER_PATH)
    parser.add_argument("--only", help="Optional single workbook filename for test runs.")
    parser.add_argument("--no-publish", action="store_true", help="Do not copy the six current files to the shared folder.")
    args = parser.parse_args()

    OUT_DIR = args.out_dir
    REPORT_DIR = args.reports_dir
    MASTER_PATH = args.master

    patch_workflow_rules()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    if args.only:
        only_path = args.input_dir / args.only
        if not only_path.exists():
            raise FileNotFoundError(f"Requested --only workbook does not exist: {only_path}")
        inputs = [only_path]
    else:
        inputs = assert_expected_inputs(args.input_dir)
    shared_dir = resolve_shared_dir()
    if shared_dir is None and not args.no_publish:
        print("WARNING: shared delivery folder was not found; local outputs will still be written.", flush=True)

    print(f"[{TIMESTAMP}] Loading master reference {MASTER_PATH}", flush=True)
    master_keys = wf.build_master_keys(MASTER_PATH)

    output_paths: list[Path] = []
    report_paths: list[Path] = []
    consolidated: list[dict[str, pd.DataFrame]] = []
    for path in inputs:
        output_path, report_path, combined = process_one(path, master_keys)
        output_paths.append(output_path)
        report_paths.append(report_path)
        consolidated.append(combined)

    combined_path = REPORT_DIR / "All_Countries_Surgical_Mapping_QA_Report.xlsx"
    print(f"[{TIMESTAMP}] Writing combined QA report {combined_path.name}", flush=True)
    write_workbook(combined_path, build_combined_qa(consolidated))

    publish_rows = publish_current_files(output_paths, shared_dir, args.no_publish)
    if not args.no_publish:
        update_mapping_log(shared_dir, consolidated, publish_rows)
    publish_table = pd.DataFrame(publish_rows)
    publish_report = REPORT_DIR / "Published_Files.xlsx"
    write_workbook(publish_report, OrderedDict([("Published_Files", publish_table)]))

    fail_table = combine_tables([item["validation"] for item in consolidated])
    failures = fail_table.loc[fail_table["Status"].astype(str).eq("FAIL")] if not fail_table.empty else pd.DataFrame()
    print(f"[{TIMESTAMP}] Batch remap complete. Validation failures: {len(failures):,}", flush=True)
    if not failures.empty:
        print(failures[["Country", "Year", "Validation", "Observed", "Target"]].to_string(index=False), flush=True)
    print(f"[{TIMESTAMP}] Local outputs: {OUT_DIR}", flush=True)
    if shared_dir is not None and not args.no_publish:
        print(f"[{TIMESTAMP}] Published current six workbooks to: {shared_dir}", flush=True)


if __name__ == "__main__":
    main()
