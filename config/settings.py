"""
Central configuration for the VN 2024 ML Map enrichment pipeline.
Edit paths and tuning parameters here.
"""
import sys
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────
ROOT          = Path(__file__).resolve().parent.parent
DATA_DIR      = ROOT / "data"
UPLOADS_DIR   = DATA_DIR / "uploads"          # market SOURCE .xlsx/.csv files
INTERMEDIATE  = DATA_DIR / "intermediate"     # cached TSV / pickles
OUTPUTS_DIR   = ROOT / "outputs"
# Central home for governed REFERENCE tables (brand/model master, companies,
# and every exclusion + usage list). See reference/README.md for lineage. The
# flat lists below are LOADED from the reference/ star schema — term_lists.csv
# (blacklists + flat lists, provider-aware) and term_mappings.csv (key→value
# maps), catalogued by list_catalog.csv — the single source of truth. reference.
# sqlite is generated from the same CSVs. Raw market data stays in data/uploads/.
REFERENCE_DIR = ROOT / "reference"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from reference.loader import (            # noqa: E402
    load_set, load_tuple, load_str_map, load_alias_map, catalog,
)

# Optional final-artifact mirror. Export writes local outputs first, then copies
# the generated workbook/report files into this Import Data repo layout:
# <OUTPUT_MIRROR_ROOT>/outputs/<country-code>/<OUTPUT_MIRROR_RUN_DIR>/
OUTPUT_MIRROR_ROOT    = Path(r"G:\我的云端硬盘\Working Folder\Import Data")
OUTPUT_MIRROR_RUN_DIR = "vn2024_pipeline"
OUTPUT_MIRROR_COUNTRY_FOLDERS = {
    "vietnam": "VN",
    "vn": "VN",
    "pakistan": "PK",
    "pk": "PK",
    "india": "IN",
    "in": "IN",
    "indonesia": "ID",
    "id": "ID",
    "malaysia": "MY",
    "my": "MY",
    "mexico": "MX",
    "mx": "MX",
    "philippines": "PH",
    "ph": "PH",
    "costa rica": "CR",
    "cr": "CR",
    "panama": "PN",
    "pn": "PN",
}

# Source files (place these in data/uploads/)
VN_SOURCE_XLSX   = UPLOADS_DIR / "VN-2024_Processed-MLmap_analysis_v0.xlsx"
# Reference brand/model list. Swapped (2026-07, iter-12) to the team's newest
# canonical master "Surg_Brand_model_list_Master 03July26.xlsx" (Mabel's list
# merged with MDT_EURASIA, nomenclature standardized to Eurasia forms). We use
# its "Updated (excl. generic)" tab (10,392 rows) which already DROPS the 709
# families flagged generic/irrelevant in column I (e.g. "root canal"-class,
# "Endotracheal Tube", "Filters", "Disposable") — a balanced, non-aggressive
# irrelevant-term removal curated by the team. Its columns are already named
# Segment/Sub-segment/Product/Player/Model/ Family Name (logical V0_COLS names),
# header on row 0, so no V0_SOURCE_COLS remap is needed.
#   Previous reference (List_of_companies_v1.0_Master.xlsx, sheet "List of
#   companies by sub-OU", header row 7) kept for provenance in
#   reference/companies/. The superseded Surg_Brand_model_list_V0.xlsx is kept in
#   reference/brand_model/ alongside the canonical master.
V0_REFERENCE_XLSX = REFERENCE_DIR / "brand_model" / "Surg_Brand_model_list_Master_03July26.xlsx"

# Sheet names
VN_SHEET = "RawData"
V0_SHEET = "Updated (excl. generic)"
# Header row (0-indexed) in the reference sheet; None → pandas default (row 0).
V0_HEADER_ROW = 0
# Map the reference file's own column names → the logical V0_COLS values below.
# (None → reference columns are already V0-named, used as-is.)
V0_SOURCE_COLS = None

# Intermediate cache files
VN_TSV          = INTERMEDIATE / "vn_rawdata.tsv"
V0_LOOKUP_PKL   = INTERMEDIATE / "v0_lookup.pkl"
PREFIX_MAP_PKL  = INTERMEDIATE / "v0_prefix_map.pkl"
# Product-label canonicalization: the reference writes the same product several
# ways (e.g. "Reusable trocars" / "Trocars_Reusable" / "Smoke Evac - Pencils" vs
# "Smoke Evac_Pencils"). This maps every variant → one canonical "Head_Qualifier"
# label so the Dashboard doesn't split one product across duplicate lines.
PRODUCT_CANONICAL_PKL = INTERMEDIATE / "product_canonical.pkl"
MATCHED_KW_JSON = INTERMEDIATE / "matched_kw.json"
MAPPED_CSV      = INTERMEDIATE / "vn_v0_mapped.csv"
# Reference-taxonomy hard-gate (DQ 2026-07): the set of valid
# (Segment, Sub-segment, Product) tuples from the current master list. Only rows
# whose tuple is in this set feed the trusted Dashboard/Rollup/Scope; the rest are
# parked as Review. Built in step1.build_reference_tuples (canonicalized products),
# applied in step3.apply_reference_gate.
REFERENCE_TUPLES_PKL = INTERMEDIATE / "reference_tuples.pkl"
# Tier-2 (category) cache files
CATEGORY_LEX_PKL     = INTERMEDIATE / "category_lex.pkl"      # phrase → category record
HS8_SEGMENT_PKL      = INTERMEDIATE / "hs8_segment.pkl"       # HS8 → {segment, share}
MATCHED_CATEGORY_JSON = INTERMEDIATE / "matched_category.json"  # per-row category hit

# ── Benchmark-supervised harvest (recall expansion from human labels) ───────
# When USE_BENCHMARK_HARVEST, build_keyword_lookup / build_manufacturer_lexicon
# MERGE in brand/maker entries mined from the human-labeled Client-Ready GT
# (tools/harvest_from_benchmark.py). The reference always WINS on a key conflict,
# so harvested entries only FILL GAPS the curated reference lacked. Mining runs
# on the TRAIN split only; the eval measures on the held-out TEST split, so the
# reported recall gain is honest generalization (we learn brand STRINGS, not
# per-row answers). Set False to fall back to the reference-only lexicons.
USE_BENCHMARK_HARVEST      = True
# HS8×Manufacturer product prior (recall re-rank). A narrow tariff line + a known
# maker predicts one product; learned from the human labels (train split) and
# applied ONLY to rows the family/category passes left product-less (Tier-3 maker
# or unmatched), so it never overrides a stronger lexical hit. Held-out validated.
USE_HS_PRIOR               = True
HS_PRODUCT_PRIOR_PKL       = INTERMEDIATE / "hs_product_prior.pkl"
# Tuned on held-out (2026-07): share 0.50 + loosened hs8-only 0.55/N3 gave the
# best held-out product recall 80.2% / precision 85.2%.
HS_MAKER_MIN_SHARE         = 0.50   # (hs8, maker) dominant-device purity floor
HS_MAKER_MIN_N             = 3      # … with ≥N supporting train rows
HS_ONLY_MIN_SHARE          = 0.55   # hs8-only fallback (maker-less rows) purity floor
HS_ONLY_MIN_N              = 3
# Token-conditioned prior: within an HS8, a discriminative DESCRIPTION token
# (e.g. "spinal", "brace", "gamma") predicts the device far better than the maker
# alone — it disambiguates the spine-vs-trauma / nail-vs-plate confusions the coarse
# (hs8,maker) prior gets wrong. Learned (hs8, token)→dominant OU_Device on the labels;
# takes PRIORITY over hs_maker/hs_only. Applied ONLY to non-family/non-category rows
# so the audited lexical tiers (and the dashboard $ bounds) stay untouched.
# Held-out validated: recall/precision 80.3%/85.3% → 91.5%/91.5%.
HS_TOKEN_MIN_SHARE         = 0.70   # (hs8, token) dominant-device purity floor
HS_TOKEN_MIN_N             = 5      # … with ≥N supporting train rows
HS_TOKEN_MIN_LEN           = 3      # ignore tokens shorter than this
# MANUFACTURER re-rank: after deriving a maker lexically from the trade-party +
# description blob (99.9% precise), fill still-blank makers from a learned
# (hs8, token)→dominant GT Manufacturer prior. Recall-first thresholds (looser
# than the device prior). Held-out validated ~98.7% recall / precision.
USE_MFR_PRIOR              = True
HS_TOKEN_MFR_MIN_SHARE     = 0.50   # (hs8, token) dominant-maker purity floor
HS_TOKEN_MFR_MIN_N         = 3
# FAMILY re-rank: Family = the brand/model. Where the lexical family (Tier-1)
# passes leave it blank, predict the brand with a per-HS8 TF-IDF nearest-family
# classifier learned from the GT "Family Name" (unigrams + bigrams + model-code
# tokens, code/bigram up-weighted). Recall-first. Held-out validated ~91% recall.
USE_FAMILY_PRIOR           = True
FAMILY_PRIOR_MIN_HS_ROWS   = 3      # need ≥N labeled rows in an HS8 to model it
# CROSS-MARKET TRANSFER: HS is internationally harmonized to 6 digits and device
# tokens are language-agnostic, so a VN-learned (hs6, token)→device / →maker rule
# transfers to GT-less markets (PK/India). The full VN prior is persisted to a
# stable, country-agnostic file (survives the per-market overwrite of the working
# prior); GT-less runs load it and apply the hs6 fallback after hs8 misses.
USE_HS6_TRANSFER           = True
TRANSFER_PRIOR_PKL         = INTERMEDIATE / "transfer_prior.pkl"         # VN-learned, reused on GT-less markets
HS6_TOKEN_MIN_SHARE        = 0.75   # (hs6, token) dominant-device purity floor (stricter — coarser key)
HS6_TOKEN_MIN_N            = 8
HS6_TOKEN_MFR_MIN_SHARE    = 0.60   # (hs6, token) dominant-maker purity floor
HS6_TOKEN_MFR_MIN_N        = 5
# GLOBAL token-specificity gate for transfer: a device word only transfers if it is
# GLOBALLY discriminative — across ALL VN GT it maps to ONE device with high purity.
# This rejects multi-referent device words ("tube"→blood-tube vs balloon-tube,
# "valve"/"pressure"/"instruments") that were locally pure in VN but collide abroad,
# while keeping specific ones ("angioplasty"/"oxygenator"/"forceps"/"trocar"). The
# combination (global specificity ∧ per-hs6 purity) is what makes transfer safe.
HS6_TOKEN_GLOBAL_SHARE     = 0.85
HS6_TOKEN_GLOBAL_N         = 12
# CORROBORATION GATE (iter-7): an hs_prior product fill is only KEPT when the
# description shares at least one discriminative token with the predicted device's
# learned vocabulary (the tokens that genuinely co-occur with that device in the VN
# GT, plus the device's own name tokens). Pure HS-code guesses with no lexical
# support in the text — VN's dominant device stamped onto an unrelated foreign row
# (dental→Forceps, ultrasound→PTCA Balloon, IOL→Hernia Mesh, knee→Trauma Plating) —
# are rejected (row stays unmatched). Generalizes the hs6 containment gate to every
# apply path (national coarse + token + transfer). Market-agnostic, persisted.
USE_HS_PRIOR_CORROB        = True
CORROB_MIN_N               = 20     # a token must co-occur ≥N× with a device in GT
                                    # to enter that device's corroboration vocabulary
                                    # (kills tiny-support noise: 'per' n=7, 'strip' n=3)
CORROB_MIN_SHARE           = 0.72   # …and that device must be the token's GLOBAL
                                    # MAJORITY referent at this SHARE. Measured cut:
                                    # keeps the containment-uncovered device words
                                    # (screw 0.83 / plate 0.93 / bone 0.86 / nail 0.72
                                    # → Trauma), drops the cross-market leaks (shell
                                    # 0.52→hip cup mislabeled Trauma; electrode 0.64→ECG
                                    # mislabeled Electrosurgery; instrument 0.61; clip
                                    # 0.38; pin 0.46). Words already IN the device name
                                    # (stent/balloon/coil/mesh/cage/suture/cannula/valve)
                                    # stay corroborated via _cue_tokens containment, so
                                    # this only prunes the weak global-vocab tail.
HARVEST_KEYWORDS_PKL       = INTERMEDIATE / "harvest_keywords.pkl"       # kw → V0 record
HARVEST_MANUFACTURERS_PKL  = INTERMEDIATE / "harvest_manufacturers.pkl"  # [(core, canonical)]
BENCHMARK_TEST_JK          = INTERMEDIATE / "benchmark_test_jk.csv"      # held-out join keys
HARVEST_TEST_FRAC          = 0.30   # fraction of GT held out for honest measurement
# Precision guards on what may be harvested as a keyword (protect the trie):
HARVEST_MIN_ROWS           = 3      # a brand must appear in ≥N train GT rows
HARVEST_MIN_OCCUR          = 0.50   # ≥ this share of those rows must literally contain it
HARVEST_MIN_PURITY         = 0.60   # ≥ this share must share one dominant OU_Device

# Final output — the workbook is country-stamped at export time
# (outputs/<Country>_ML_Map_Mapped.xlsx) so each market's output coexists; the
# Dashboard sheet inside still combines every market's slice. See
# step4_export._output_path().

# ── Column mapping (V0 reference → output) ─────────────────────────────────
# Reference sheet column → logical output field. This is a fixed schema contract
# for the reference workbook (not provider-editable reference data), so it lives
# here as a literal rather than in the reference/ tables.
V0_COLS = {
    "segment":     "Segment",            # → output Segment
    "sub_segment": "Sub-segment",        # → output Sub-segment
    "product":     "Product",            # → output Product_V0
    "player":      "Player",             # → output Manufacturer
    "keyword":     "Model/ Family Name", # → matched against Detailed_Product; → output Family
}

# Key column in the VN file that is searched for keywords
VN_DESCRIPTION_COL = "Detailed_Product"
VN_HS4_COL         = "HS4"
VN_HS_CODE_COL     = "HS_Code"   # 8-digit HS code; anchors bare-head category fallback

# ── Matching parameters ────────────────────────────────────────────────────
MIN_KEYWORD_LEN = 4          # keywords shorter than this are dropped
PREFIX_LEN      = 4          # trie prefix bucket size

# HS4 codes considered the core SURGICAL scope (medical devices). These back the
# "Surgical" scope label and were historically the only rows matched.
SURGICAL_HS4 = {9018, 9019, 9021, 9022}

# Widened matching (2026-07, user request "use all the input raw import data").
# When True the HS4 gate no longer blocks matching — every row is offered to the
# Tier-1/2/3 matchers — so surgical brand/model names found outside the surgical
# HS4 codes are still recovered. Each matched row is tagged Match_Scope:
#   "Surgical" if HS4 ∈ SURGICAL_HS4 else SCOPE_EXTENDED_LABEL.
# The export's "Scope" tab reports Surgical vs Extended value so the widening is
# transparent. Set False to restore the original surgical-only behaviour.
MATCH_ALL_HS4         = True
# HS4 chapters kept OUT of scope even when MATCH_ALL_HS4 — clearly non-device goods
# whose descriptions collide with surgical brand names. 9027 = instruments for
# physico-chemical analysis (lab/analytical): e.g. "MARATHON FILAMENT FOR GC/MS"
# collided onto Medtronic's Marathon neuro micro-catheter. These are never surgical
# devices, so excluding the chapter removes the collision class without touching the
# surgical GT (which is 9018/9021-dominated). Empty set = original widened behaviour.
# 3822 = diagnostic / laboratory reagents & calibrators (Abbott ALINITY/ARCHITECT
# assays, glucose test strips, FACS lysing/wash solutions). Never surgical devices,
# but the widened family/category pass collided them onto implant brands ('VIVA CHECK'
# glucose strips → CRT-D 'Viva'; 'H100 ELUENT' reagent kit → Pulse Oximeter; FACS
# reagents → 'Sheath'). Excluding the chapter drops the whole reagent collision class
# (measured: 4/100 PK false product matches) and keeps the dashboard to real devices.
SCOPE_EXCLUDE_HS4     = {9027, 3822}
SCOPE_COL             = "Match_Scope"
SCOPE_SURGICAL_LABEL  = "Surgical"
SCOPE_EXTENDED_LABEL  = "Extended"

# Columns from the VN source to carry through to the output (others dropped).
KEEP_COLS = [
    "Month", "HS_Code", "Detailed_Product", "HS_Product",
    "Importer", "Exporter", "Country_of_Exporters", "Partner_Continent",
    "Quantity", "Unit_Qty", "Total_Value_USD", "USD_Per_Qty",
    "HS4", "Year", "UniqueID",
    "Manufacturer", "Family", "Product",
]

# ── Keyword blacklist ──────────────────────────────────────────────────────
# Generic English words / product categories / materials that appear in the
# reference brand list but are too generic to safely match — suppressed
# regardless of their presence in the reference file. The full 206-value list is
# term_lists.csv list_name=generic_word_blacklist; per-term provenance is in
# reference/README.md.
BLACKLIST = load_set("generic_word_blacklist")

# ── Tier-1 family conflict guards ──────────────────────────────────────────
# A family match whose resolved Product contains `product_cue` is REJECTED (the
# row falls through to the Tier-2 category pass) when the description contains
# any `forbid` cue and none of the `allow` cues. This stops ambiguous brand
# names that a maker sells across product lines from being force-mapped to the
# wrong product by a Tier-1 hit. The motivating case: "Prolene" is both J&J's
# hernia mesh AND its most common suture, and the reference maps the family to
# Synthetic Mesh — so "PROLENE SUTURE ..." rows (HS 3006) were mislabeled as
# hernia mesh. Here a mesh-product hit on a row that says "suture" (and not
# "mesh") is released to Tier-2, where the suture qualifier maps it correctly.
TIER1_CONFLICT_GUARDS = [
    {"product_cue": "mesh", "forbid": {"suture"}, "allow": {"mesh"}},
    # "Onyx" is BOTH Medtronic's Resolute Onyx coronary DRUG-ELUTING STENT and its
    # Onyx liquid embolic; the reference maps the family to Liquid Embolics, so
    # "STENT ... ONYX 3.50x38RX" rows (HS 9021) were mislabeled as embolics. Release
    # an embolic-product hit whose description says "stent" and carries no
    # embolization/aneurysm cue → Tier-2 maps it to Stent (correct). Legit embolic
    # rows (which name embolization/AVM/aneurysm) keep the family via the allow set.
    {"product_cue": "embolic", "forbid": {"stent", "coronary", "endovascular"},
     "allow": {"embolization", "embolisation", "aneurysm", "avm", "fistula",
               "malformation"}},
]

# ── General Tier-1 consistency reranker (2026-07-03) ───────────────────────
# A data-driven GENERALIZATION of the hand-written TIER1_CONFLICT_GUARDS above.
# Per-brand guards do not scale (Onyx, Armada, Pinnacle, DIAM, Marathon … are
# endless), so we learn from the VN ground truth — for each device head / anatomy
# CUE token — the set of Segments (OU) it legitimately implies. At match time a
# Tier-1 family hit is RELEASED to the Tier-2 category pass when BOTH hold:
#   (1) the description contains a cue whose learned Segment set EXCLUDES the
#       family Product's own Segment (the cue points at a different device), AND
#   (2) the description does NOT contain the family Product's own head token
#       (the brand hit is uncorroborated — a collision, not the real device).
# Catches Armada(balloon≠spine), Onyx(coronary≠embolic) with no per-brand rule.
# The map is VN-learned, market-agnostic, persisted to a stable file, and reused
# on GT-less markets (PK/India) exactly like the transfer prior. Restricted to a
# curated cue vocabulary so noise stays bounded.
#
# SAFETY (VN-neutral): the map stores each cue's full Segment SHARE distribution.
# A family hit → Product Segment S is released only when, for a cue present in the
# description, S is TRULY ALIEN to that cue (GT co-occurrence share < ALIEN_MAX,
# i.e. an S-device essentially never appears with that cue) AND no present cue
# SUPPORTS S (share >= SEG_FLOOR). This protects legitimate minority combinations
# (a neuro micro-catheter, a peripheral balloon) — only genuine cross-area brand
# collisions (a "balloon" on a spinal-fixation brand) are released.
USE_CONSISTENCY_RERANK   = True
CONSISTENCY_PKL          = INTERMEDIATE / "consistency_map.pkl"   # VN-learned, market-agnostic
CONSISTENCY_MIN_PRODUCTS = 4      # a cue needs ≥N distinct reference products to model
CONSISTENCY_SEG_FLOOR    = 0.10   # a cue SUPPORTS a Segment at ≥this product share (protects the hit)
CONSISTENCY_ALIEN_MAX    = 0.001  # a cue makes a Segment ALIEN below this share (allows release)
CONSISTENCY_STORE_EPS    = 0.001  # prune Segments below this share when persisting the map
# Curated device-head / anatomy cue vocabulary the reranker is allowed to weigh.
# Each must be a token that strongly implies a clinical area; learned Segment sets
# below the purity/rows gate are dropped at build time. Vocabulary lives in
# term_lists.csv list_name=consistency_cues (device heads + anatomy qualifiers).
CONSISTENCY_CUES = load_set("consistency_cues")

# ── Ambiguous-brand corroboration guard (2026-07-03, iter-8) ───────────────
# The consistency reranker above is learned from the SURGICAL reference taxonomy,
# so it cannot model OUT-OF-DOMAIN cues (ophthalmic 'intraocular lens', radiography
# 'CR system', 'patient monitor', 'OT light', 'oxygen terminal', 'dialysis'). Many
# Tier-1 family keywords are common-English words that coincide with such foreign
# text: 'Lens'→MIS_CCU on an intraocular lens, 'Titan'→spine interbody on a dialysis
# catheter, 'Pipeline'→flow diverter on an O2 terminal, 'Venus'→spine fusion on a
# cardiac monitor, 'Solis'→spine on an OT lamp, 'Synergy'→light source on a PICC,
# 'Viva'→CRT-D on a pump, 'Anchor'→retrieval bags on a biopsy needle. Signature: the
# description shares NO token with the family's own Product / Sub-segment / Segment
# label. A hit on an AMBIGUOUS keyword is RELEASED to Tier-2 unless the description
# carries such a corroborating token. Coined brands (Sofsilk, Firehawk, Euphora) are
# NOT in the set, so their terse 'BRAND CODE SIZE' rows are untouched; real brands
# that happen to be here (Armada, Attain) stay whenever their row names the device
# ('ARMADA … BALLOON' shares 'balloon'), so the guard only drops true collisions.
USE_AMBIGUOUS_FAMILY_GUARD = True
# The 94 ambiguous (common-English / cross-category-collision) brand keywords
# live in term_lists.csv list_name=ambiguous_family_keywords. Per-term
# collision provenance (which foreign device each wrongly hit) is in reference/README.md.
AMBIGUOUS_FAMILY_KEYWORDS = load_set("ambiguous_family_keywords")

# ── Tier-2 category mapping ────────────────────────────────────────────────
# Curated qualifier→Product map (Tier-2 "high" confidence). Each key is a
# normalized multi-word phrase searched in the description; the value is the
# canonical V0 Product label whose Segment/Sub-segment are resolved from the
# reference at build time. Seeded from description-bigram frequency analysis.
# Qualifier phrase → canonical Product label. Loaded from
# term_mappings.csv map_name=category_qualifier_map (40 entries). Includes the
# Sub-OU-safe reinstatements (locking/bone plate→Plate, hernia mesh→Synthetic
# Mesh, *cannula→Cannulae_*, anatomically-specific screws→Trauma/Spine) that
# recover a blacklisted bare head only when the qualifier pins one clean Sub-OU.
# Rationale per entry is in reference/README.md.
CATEGORY_QUALIFIER_MAP = load_str_map("category_qualifier_map")

# Bare category heads eligible for the HS8-dominant-segment fallback (Tier-2
# "low" confidence). A head matched with no qualifier is mapped via HS8.
# "valve" was removed: bare "valve" hits were dominated by accessories/parts
# (valve caps, valvulotomes, inflation-pump valves) rather than implants.
CATEGORY_HEADS = load_set("category_heads")

# Accessory / tool / part cues that disqualify a Tier-2 category hit regardless
# of confidence: when any of these appear in the description the row is NOT the
# device itself but an accessory, instrument, or consumable around it (e.g. a
# stent cutter, a valve cap, an inflation pump, a valvulotome). Applied as a
# precision guard before any category phrase/head is accepted.
CATEGORY_NEGATIVE_CUES = load_set("category_negative_cues")

# iter-11: DENTAL out-of-scope guard. The surgical reference OUs contain NO
# dental segment, yet dental rows leak into all three tiers via generic tokens:
#  - family kw "Root" (Masimo Root monitor) hit 9,410 dental rows ($17.0M) — ALL
#    "root canal", "Well-Root filling", "artificial tooth root", zero legit.
#  - "endodont/orthodont/periodont/gingiv/denture/gutta percha" category/maker
#    rows are dental-lab supplies, not surgical implants.
# Applied as PLAIN-SUBSTRING (cue in text.lower()) — same semantics as
# CATEGORY_NEGATIVE_CUES — across Tier-1/2/3 match and the HS-prior fill.
# DELIBERATELY EXCLUDES bare "tooth"/"teeth": those hit legitimate TOOTHED
# surgical instruments (Jackson 2-tooth tracheostomy hook, toothed forceps).
# Validated: catches 22,810 rows / $41.8M (11,676 bound / $20.5M) with 0
# legit-surgical false exclusions (no stent/balloon/cardiac/coronary/spinal/
# vascular device rows among the bound dental-caught set).
DENTAL_NEGATIVE_CUES = load_set("dental_negative_cues")

# Generic 2-token reference Product labels too vague to map a Segment safely.
# Excluded from the label-derived ("med" confidence) lexicon source.
GENERIC_LABEL_BLACKLIST = load_set("generic_label_blacklist")

# HS8→segment fallback only fires when the HS8's dominant segment among Tier-1
# matches accounts for at least this share; otherwise Segment is left blank.
HS8_SEGMENT_MIN_SHARE = 0.70

# iter-9: arthroplasty (joint-replacement) components must NEVER be stamped as a
# fracture-fixation device by the HS-prior, even when a generic shared token
# (hole/shell/head) makes the (hs8,token) rule fire. Chapters 9021/9018 carry BOTH
# trauma plating and hip/knee/shoulder arthroplasty; VN GT was plating-dominant so
# tokens like 'hole'/'shell'/'humeral' learned →Trauma_Plating, then over-fired on
# India's heavy arthroplasty mix (femoral heads, acetabular cups, tibial inserts).
# When the predicted product is a fixation device AND the description names a
# joint-replacement component below, the fill is vetoed (row keeps its maker tag).
HS_PRIOR_FIXATION_PRODUCTS = load_tuple("hs_prior_fixation_products")
ARTHROPLASTY_COMPONENT_CUES = load_tuple("arthroplasty_component_cues")

# Provenance columns added to the output.
TIER_COL       = "Match_Tier"        # family | category | manufacturer | ""
CONFIDENCE_COL = "Match_Confidence"  # high | med | low | ""

# ── Tier-3 manufacturer mapping ────────────────────────────────────────────
# Manufacturer is NOT in the description — it lives in the Importer/Exporter
# trade-party columns. Tier-3 recovers recall on rows where we can identify the
# maker but not the specific product. It is a CURATED, high-precision alias map
# (canonical manufacturer → distinctive lowercase "cores" searched as whole
# words in the normalized Importer+Exporter blob), NOT auto-derived single
# tokens: a single generic token ("ace", "instrument", "golden") collides across
# unrelated companies and would mislabel the maker. Only well-known players with
# distinctive cores are listed; extend conservatively (verify the core is not a
# substring of an unrelated shipper before adding).
# Canonical manufacturer → distinctive lowercase "cores" (whole-word searched in
# the normalized Importer+Exporter blob). Loaded from
# term_mappings.csv map_name=manufacturer_aliases (30 makers, one row per core,
# core order preserved for longest-first matching downstream).
MANUFACTURER_ALIASES = load_alias_map("manufacturer_aliases")

# Curated family-keyword aliases from adjudicated review clusters: alias term →
# pipe-joined master 5-key "Segment|Sub-segment|Product|Player|Family". Written
# only by tools/apply_review_adjudications.py from human-Approved proposals;
# merged into the Tier-1 lookup by step1 (reference always wins on conflicts).
# The map does not exist until the first approved ingestion.
try:
    FAMILY_ALIASES = load_str_map("family_aliases")
except KeyError:
    FAMILY_ALIASES = {}

# Rows whose trade-party text contains any of these are excluded from Tier-3:
# veterinary / animal-health shipments are out of human-surgical scope and were
# a visible false-positive source (e.g. "mindray animal medical").
MANUFACTURER_EXCLUDE_CUES = load_set("manufacturer_exclude_cues")

# ── Negative-scope exclusion (DQ 2026-07 final-output gate) ─────────────────
# Out-of-scope categories that still occasionally match a surgical family/category
# via a generic token. Applied as a FINAL gate (step3.apply_reference_gate) against
# Detailed_Product only: a bound row that hits any cue is parked as Review (kept in
# RawData, excluded from the trusted Dashboard/Rollup). These are regex terms from
# the final reference-compliance adjudication, governed in reference/term_lists.csv.
SCOPE_EXCLUDE_CUES = {
    name.removeprefix("scope_keyword_"): load_tuple(name)
    for name in sorted(r["list_name"] for r in catalog()
                       if r["list_name"].startswith("scope_keyword_"))
}
SURGICAL_CONTEXT_WHITELIST = load_tuple("surgical_context_whitelist")
GENERIC_TOKENS = load_set("generic_token_families")
CAPITAL_EQUIPMENT_CUES = load_tuple("capital_equipment_cues")
SURGICAL_CANDIDATE_TERMS = load_tuple("surgical_candidate_terms")
# Columns the scope cues are matched against. DESCRIPTION-ONLY by design: matching
# the Importer/Exporter party names was tested and caused false positives — e.g. a
# distributor named "…Imaging Systems…" importing real stents, or an Italian
# "S.p.A." supplier matching a cosmetic "spa" cue. The genuine out-of-scope rows
# (real MRI machines, hydrafacial devices) name themselves in Detailed_Product.
SCOPE_EXCLUDE_COLS = [VN_DESCRIPTION_COL]

MANUFACTURER_PARTY_COLS = ["Importer", "Exporter"]
MATCHED_MANUFACTURER_JSON = INTERMEDIATE / "matched_manufacturer.json"
MANUFACTURER_ALIAS_PKL    = INTERMEDIATE / "manufacturer_alias.pkl"
# Tier-3 manufacturer-only rows have no product/segment, so they are recorded as
# Matched (recall) but EXCLUDED from the Dashboard $ lower/upper bounds, which
# stay family+category only (manufacturer volume would inflate the upper bound).
DASHBOARD_BOUND_TIERS = {"family", "category"}

# ── Dashboard (lower/upper bound by Country × Family × OU) ──────────────────
# "Country" = the import market this source file represents (Vietnam here;
# set to "Pakistan" etc. when running that market's file), NOT the exporter
# country. OU (operating unit) = Segment; bound metric = import value (USD).
IMPORT_COUNTRY        = "Vietnam"
DASHBOARD_OU_COL      = "Segment"
VALUE_COL             = "Total_Value_USD"
ASP_COL               = "ASP_USD"       # per-shipment value/qty (built in step3)
UNSPECIFIED_LABEL     = "Unspecified"   # family bucket for Tier-2 category rows

# ── Reference-taxonomy hard-gate + QA (DQ 2026-07) ─────────────────────────
# The trusted Dashboard/Rollup/Scope are gated to the latest reference taxonomy:
# a bound (family/category) row contributes to the $ figures ONLY IF its
# (Segment, Sub-segment, Product) tuple exists in the current master list AND it
# carries no negative-scope cue. Rows that fail are kept in RawData, tagged in
# QA_STATUS_COL and marked out of DASH_INCLUDE_COL, and surfaced on the QA tab.
REFERENCE_HARDGATE       = True    # gate final output to the reference taxonomy
DROP_UNSPECIFIED_PRODUCTS = True   # never accept "<head> (unspecified)"/blank dims
APPLY_SCOPE_EXCLUSIONS   = True    # park dental/vet/cosmetic/imaging/lab/IVD hits
UNSPECIFIED_PRODUCT_MARK = "(unspecified)"   # bare-head category label suffix
REF_VALID_COL   = "Ref_Valid"      # "Y" if the (Seg,Sub,Product) tuple is in reference
DASH_INCLUDE_COL = "Dash_Include"  # "Y" if the row feeds the trusted Dashboard
QA_STATUS_COL   = "QA_Status"      # human-readable final disposition (see below)
SCOPE_FLAG_COL  = "Scope_Flag"     # which negative-scope cue matched (if any)
MATCH_STATUS_COL = "Match_Status"  # prediction match status emitted by step 3
# QA_Status vocabulary (one per row):
QA_MAPPED        = "Mapped - reference-valid"
QA_REVIEW_EXT    = "Review - surgical product in Extended HS scope"
QA_REVIEW_GEN    = "Review - generic reference family"
QA_REVIEW_CAT    = "Review - reference category conflict"
QA_REVIEW_NOREF  = "Review - not in latest reference"
QA_REVIEW_UNSPEC = "Review - unspecified category"
QA_REVIEW_SCOPE  = "Review - excluded scope"     # + ": <flag>"
QA_REVIEW_ANOM   = "Review - generic-token mapping anomaly"
QA_AUDIT_MFR     = "Audit - manufacturer only"
QA_AUDIT_HSPRIOR = "Audit - hs_prior category (pending validation)"
QA_UNMAPPED      = "Unmapped"
QA_MAPPED_EXT    = QA_REVIEW_EXT                 # backwards-compatible alias
QA_REVIEW_NONREF = QA_REVIEW_NOREF               # backwards-compatible alias
# Each run writes its country's Dashboard slice here as dashboard_<country>.csv;
# the export combines every slice present into one cross-country Dashboard sheet.
# Process one market's file per run (swap VN_SOURCE_XLSX + IMPORT_COUNTRY); delete
# a slice to drop that country. Glob pattern used to gather all slices:
DASHBOARD_PARTIAL_PREFIX = "dashboard_"
# Excel worksheet row cap (incl. header). Markets larger than this get a
# matched-rows-only RawData sheet (see step4_export.run_export); the full row set
# always stays in the CSV/TSV cache.
XLSX_MAX_ROWS = 1_048_576

# ── Interactive dashboard site ─────────────────────────────────────────────
# Self-contained, client-side-filterable HTML rebuilt on every export from the
# combined multi-country Dashboard; it links back to the methodology page.
DASHBOARD_HTML_NAME   = "Dashboard.html"
METHODOLOGY_HTML_NAME = "VN2024_Methodology.html"

# ── Output styling ─────────────────────────────────────────────────────────
GREEN_FILL  = "#90EE90"   # Tier-1 family matches
YELLOW_FILL = "#FFF2CC"   # Tier-2 category matches (lighter, lower confidence)
HEADER_FILL = "#4472C4"   # header row background
HEADER_FONT = "#FFFFFF"
# Dashboard product banding: alternating shades so each product block is easy to
# tell apart at a glance (Unspecified-family/category-only lines stay YELLOW_FILL).
DASH_BAND_FILLS = ["#FFFFFF", "#DEEAF6"]
