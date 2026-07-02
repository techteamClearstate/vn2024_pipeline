"""
Central configuration for the VN 2024 ML Map enrichment pipeline.
Edit paths and tuning parameters here.
"""
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────
ROOT          = Path(__file__).resolve().parent.parent
DATA_DIR      = ROOT / "data"
UPLOADS_DIR   = DATA_DIR / "uploads"          # put source .xlsx files here
INTERMEDIATE  = DATA_DIR / "intermediate"     # cached TSV / pickles
OUTPUTS_DIR   = ROOT / "outputs"

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
# Reference brand/model list. Swapped (2026-07) from Surg_Brand_model_list_V0.xlsx
# to the richer master "List of companies by sub-OU" (5,094 families / 1,216
# companies vs 3,714 / 957). Its header sits on a lower row and its columns are
# named differently, so V0_HEADER_ROW + V0_SOURCE_COLS normalize it to the
# logical V0_COLS names the pipeline uses everywhere downstream.
V0_REFERENCE_XLSX = UPLOADS_DIR / "List_of_companies_v1.0_Master.xlsx"

# Sheet names
VN_SHEET = "RawData"
V0_SHEET = "List of companies by sub-OU"
# Header row (0-indexed) in the reference sheet; None → pandas default (row 0).
V0_HEADER_ROW = 7
# Map the reference file's own column names → the logical V0_COLS values below.
# (Set to None to use the reference columns as-is, i.e. already V0-named.)
V0_SOURCE_COLS = {
    "Operating Unit (OU)":          "Segment",
    "Sub Operating Unit (Sub-OU)":  "Sub-segment",
    "Product Category":             "Product",
    "Company":                      "Player",
    "Family":                       "Model/ Family Name",
}

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
# Tier-2 (category) cache files
CATEGORY_LEX_PKL     = INTERMEDIATE / "category_lex.pkl"      # phrase → category record
HS8_SEGMENT_PKL      = INTERMEDIATE / "hs8_segment.pkl"       # HS8 → {segment, share}
MATCHED_CATEGORY_JSON = INTERMEDIATE / "matched_category.json"  # per-row category hit

# Final output — the workbook is country-stamped at export time
# (outputs/<Country>_ML_Map_Mapped.xlsx) so each market's output coexists; the
# Dashboard sheet inside still combines every market's slice. See
# step4_export._output_path().

# ── Column mapping (V0 reference → output) ─────────────────────────────────
# V0 'Updated' sheet columns used for the lookup
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
# V0 reference but are too generic to safely match. Suppressed regardless of
# their presence in the reference file.
BLACKLIST = {
    "accessories", "accessory", "others", "other", "curve", "drill tool", "kick",
    "doro", "blade", "steel", "agent", "reagent", "normal", "plain", "basic",
    "monitor", "camera", "circuit", "extension", "linear", "advance", "classic",
    "generator", "navigator", "freedom", "electrode", "electrodes", "monopolar",
    "bipolar", "scalpel", "forceps", "forcep", "retractors", "retractor",
    "venous", "arterial", "mesh", "wire", "needle", "sensor", "filters", "filter",
    "clamp", "clamps", "scissors", "scissor", "trocar", "trocars", "polyester",
    "polyamide", "suture", "sutures", "screw", "screws", "clip", "clips",
    "sheath", "sheaths", "probe", "probes", "catheter", "catheters", "adapter",
    "adaptors", "cartridge", "powered", "revolution", "compact", "pioneer",
    "liberty", "vision", "signal", "system", "guide", "guides", "ring", "rings",
    "patch", "patches", "core", "tubing", "tube", "tubes", "sleeve", "marker",
    "markers", "balloon", "valve", "valves", "drill", "burr", "burrs", "nail",
    "nails", "plate", "plates", "ultimate", "nano", "supreme", "edge", "falcon",
    "legend", "hero", "atlas", "apex", "sigma", "echo", "iris", "line", "work",
    "mass", "deep", "arch", "arise", "dawn", "rise", "reed", "reef", "moon",
    "wave", "sonic", "smooth", "flex", "force", "power", "super", "ultra",
    "multi", "micro", "mini", "max", "mega", "omni", "uni", "dual", "tri",
    "pro", "plus", "one", "two", "next", "new", "smart", "easy", "fast", "quick",
    "clear", "clean", "safe", "sure", "true", "full", "open", "free", "soft",
    "hard", "light", "dark", "high", "low", "long", "short", "thin", "wide",
    "round", "flat", "sharp", "rigid", "delta", "omega", "alpha", "beta",
    "gamma", "prime", "star", "gold", "silver", "blue", "green", "red", "white",
    "black", "chrome",
}

# ── Tier-2 category mapping ────────────────────────────────────────────────
# Curated qualifier→Product map (Tier-2 "high" confidence). Each key is a
# normalized multi-word phrase searched in the description; the value is the
# canonical V0 Product label whose Segment/Sub-segment are resolved from the
# reference at build time. Seeded from description-bigram frequency analysis.
CATEGORY_QUALIFIER_MAP = {
    "coronary stent":         "Drug Eluting Stents",
    "artery stent":           "Drug Eluting Stents",
    "drug eluting stent":     "Drug Eluting Stents",
    "ureteral stent":         "Ureteral Stents",
    "biliary stent":          "Biliary Stents",
    "carotid stent":          "Carotid Stents",
    "stent graft":            "TEVAR Thoracic Stent Grafts",
    "ptca balloon":           "PTCA Balloons",
    "ureteral balloon":       "Ureteral Balloons",
    "guide wire":             "Guidewires",
    "guidewire":              "Guidewires",
    "diagnostic catheter":    "Diagnostic Catheter",
    "guiding catheter":       "Guiding Catheters",
    "ablation catheter":      "Ablation Catheter",
    "ureteral catheter":      "Ureteral Catheters",
    "intramedullary nail":    "Intramedullary Nails",
    "mechanical heart valve": "Mechanical Heart Valves",
    # Sub-OU-safe reinstatements: each qualifier phrase resolves to a Product
    # with one unambiguous Sub-segment, so a blacklisted bare head ("plate",
    # "suture", "mesh", "cannula") is recovered ONLY when its qualifier pins the
    # Sub-OU. Ambiguous qualifiers are deliberately omitted ("tibial plate" can
    # be a knee tray; bare "screw" has no Trauma Sub-OU in the reference).
    "locking plate":          "Plate",                            # Trauma | Plate
    "locked plate":           "Plate",
    "bone plate":             "Plate",
    "compression plate":      "Plate",
    "absorbable suture":      "Conventional Suture - Absorbable",   # Surgical Innovations | Sutures
    "non absorbable suture":  "Conventional Suture - Non-Absorbable",
    "surgical suture":        "Conventional Suture - Non-Absorbable",
    "hernia mesh":            "Synthetic Mesh",                   # Surgical Innovations | Hernia
    "surgical mesh":          "Synthetic Mesh",
    "arterial cannula":       "Cannulae - Arterial",              # Cardiac Surgery | Extracorporeal Therapies
    "aortic cannula":         "Cannulae - Arterial",
    "venous cannula":         "Cannulae - Venous",
    "femoral cannula":        "Cannulae - Femoral",
}

# Bare category heads eligible for the HS8-dominant-segment fallback (Tier-2
# "low" confidence). A head matched with no qualifier is mapped via HS8.
# "valve" was removed: bare "valve" hits were dominated by accessories/parts
# (valve caps, valvulotomes, inflation-pump valves) rather than implants.
CATEGORY_HEADS = {
    "stent", "catheter", "balloon", "guidewire", "nail",
    "sheath", "graft", "cannula",
}

# Accessory / tool / part cues that disqualify a Tier-2 category hit regardless
# of confidence: when any of these appear in the description the row is NOT the
# device itself but an accessory, instrument, or consumable around it (e.g. a
# stent cutter, a valve cap, an inflation pump, a valvulotome). Applied as a
# precision guard before any category phrase/head is accepted.
CATEGORY_NEGATIVE_CUES = {
    "valvulotome", "valvotome", "cutter", "breaker", "punch", "holder",
    "tray", "rack", "simulator", "trainer", "stopcock", "obturator",
    "dummy", "valve cap", "pump to", "pump for", "measuring kit",
    "size measuring",
}

# Generic 2-token reference Product labels too vague to map a Segment safely.
# Excluded from the label-derived ("med" confidence) lexicon source.
GENERIC_LABEL_BLACKLIST = {
    "hand instruments", "access devices", "laser systems",
    "other catheters", "electrosurgical devices",
}

# HS8→segment fallback only fires when the HS8's dominant segment among Tier-1
# matches accounts for at least this share; otherwise Segment is left blank.
HS8_SEGMENT_MIN_SHARE = 0.70

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
MANUFACTURER_ALIASES = {
    "Medtronic":          ["medtronic", "covidien"],
    "B. Braun":           ["b braun", "aesculap"],
    "J&J":                ["johnson johnson", "depuy", "ethicon"],
    "Boston Scientific":  ["boston scientific"],
    "Abbott":             ["abbott"],
    "Terumo":             ["terumo"],
    "Olympus":            ["olympus"],
    "Karl Storz":         ["karl storz"],
    "Stryker":            ["stryker"],
    "Smith & Nephew":     ["smith nephew"],
    "Zimmer Biomet":      ["zimmer biomet", "zimmer", "biomet"],
    "Biotronik":          ["biotronik"],
    "Penumbra":           ["penumbra"],
    "Asahi Intecc":       ["asahi intecc"],
    "Teleflex":           ["teleflex"],
    "MicroPort":          ["microport"],
    "Meril":              ["meril"],
    "Cordis":             ["cordis"],
    "Getinge":            ["getinge"],
    "Nipro":              ["nipro"],
    "Nuvasive":           ["nuvasive"],
    "Mani":               ["mani inc", "mani hanoi"],
    "Mindray":            ["mindray"],
    "Canwell Medical":    ["canwell"],
    "Medikit":            ["medikit"],
    "Cook Medical":       ["cook medical"],
    "Richard Wolf":       ["richard wolf"],
    "BD":                 ["becton dickinson", "bard"],
    "Merit Medical":      ["merit medical"],
    "Gore Medical":       ["w l gore", "gore associates"],
}

# Rows whose trade-party text contains any of these are excluded from Tier-3:
# veterinary / animal-health shipments are out of human-surgical scope and were
# a visible false-positive source (e.g. "mindray animal medical").
MANUFACTURER_EXCLUDE_CUES = {"veterinary", "veterinari", "animal"}

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
