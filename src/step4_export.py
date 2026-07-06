"""
Step 4 — Export
===============
Write the enriched dataset to a styled .xlsx:
  * Sheet 'RawData'   — all rows; Tier-1 family rows highlighted green, Tier-2
                        category rows yellow (conditional-format rules). The
                        dimension columns (Segment / Sub-segment / Product_V0 /
                        Family / Manufacturer) are already standardized in the
                        mapping stage (step3.standardize_for_dashboard), and it
                        carries per-shipment ASP_USD plus numeric Quantity /
                        Total_Value_USD, so the Dashboard formulas aggregate over
                        those columns directly — no separate Dash_* helpers.
  * Sheet 'Summary'   — match counts grouped by Tier / Segment / Sub-segment /
                        Product_V0 (blank dimensions shown as "Unspecified").
  * Sheet 'Dashboard' — line items at OU (Segment) × Sub-OU (Sub-segment) ×
                        Product × Family × Manufacturer for THIS workbook's
                        import country. Every metric is a live Excel formula
                        that aggregates the matching RawData shipments:
                          Total_Revenue_USD = SUMIFS(Total_Value_USD)
                          Total_Volume      = SUMIFS(Quantity)
                          Min_ASP / Max_ASP = MINIFS / MAXIFS of per-shipment ASP
                          Avg_ASP           = Total_Revenue / Total_Volume
                        so the whole sheet recomputes if RawData is filtered/edited.
                        Rows are product-banded (alternating shades) for quick
                        visual separation; category-only lines stay yellow.

The cross-country interactive Dashboard.html and per-country dashboard_<country>.csv
slice remain value-based (lower/upper bounds) — only the workbook sheet is the
single-country, formula-driven ASP view.
"""
import re
import shutil

import pandas as pd
from xlsxwriter.utility import xl_col_to_name, xl_range

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import settings as cfg


# The Dashboard line-item dimensions, in the RawData columns the formulas key on.
DASH_DIM_COLS = [cfg.DASHBOARD_OU_COL, "Sub-segment", "Product_V0",
                 "Family", "Manufacturer"]


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", str(name)).strip("_") or "unknown"


def _combine_dashboards(this_country: pd.DataFrame) -> pd.DataFrame:
    """Persist this run's country slice, then concat every country slice present
    into one cross-country Dashboard (separate-file-per-country model)."""
    part = cfg.INTERMEDIATE / f"{cfg.DASHBOARD_PARTIAL_PREFIX}{_slug(cfg.IMPORT_COUNTRY)}.csv"
    this_country.to_csv(part, index=False)
    parts = sorted(cfg.INTERMEDIATE.glob(f"{cfg.DASHBOARD_PARTIAL_PREFIX}*.csv"))
    combined = pd.concat([pd.read_csv(p) for p in parts], ignore_index=True)
    return combined.sort_values(["Country", "OU", "Sub_OU", "Upper_Bound_USD"],
                                ascending=[True, True, True, False])


def _build_dashboard(matched: pd.DataFrame) -> pd.DataFrame:
    """Value-based line-item lower/upper bounds at
    Country × OU (Segment) × Sub-OU (Sub-segment) × Product × Family × Manufacturer.

    Feeds the cross-country dashboard_<country>.csv slice and the interactive
    Dashboard.html — NOT the workbook sheet (that one is formula-driven ASP).
    Each bound row contributes to the UPPER bound; only Tier-1 family rows (named
    family) contribute to the LOWER bound. The dimension columns are already
    standardized in the mapping stage (step3.standardize_for_dashboard): category
    rows carry Family="Unspecified" and a trade-party-derived Manufacturer, and
    blank bound dims are labelled "Unspecified".
    """
    d = matched.copy()
    d["_value"] = pd.to_numeric(d[cfg.VALUE_COL], errors="coerce").fillna(0.0)
    named = d[cfg.TIER_COL] == "family"          # only Tier-1 backs the lower bound
    # "Country" = the import market this source file represents (a constant).
    d["_country"] = cfg.IMPORT_COUNTRY
    d["_ou"]      = d[cfg.DASHBOARD_OU_COL].fillna("").replace("", cfg.UNSPECIFIED_LABEL)
    d["_subou"]   = d["Sub-segment"].fillna("").replace("", cfg.UNSPECIFIED_LABEL)
    d["_product"] = d["Product_V0"].fillna("").replace("", cfg.UNSPECIFIED_LABEL)
    d["_family"]  = d["Family"].fillna("").replace("", cfg.UNSPECIFIED_LABEL)
    d["_mfr"]     = d["Manufacturer"].fillna("").replace("", cfg.UNSPECIFIED_LABEL)

    keys = ["_country", "_ou", "_subou", "_product", "_family", "_mfr"]
    g = d.groupby(keys, dropna=False)
    dash = pd.DataFrame({
        "Upper_Bound_USD":       g["_value"].sum(),
        "Upper_Bound_Shipments": g.size(),
    })
    lower = d[named].groupby(keys)
    dash["Lower_Bound_USD"]       = lower["_value"].sum()
    dash["Lower_Bound_Shipments"] = lower.size()
    dash = dash.fillna(0.0).reset_index()
    dash.columns = ["Country", "OU", "Sub_OU", "Product", "Family", "Manufacturer",
                    "Upper_Bound_USD", "Upper_Bound_Shipments",
                    "Lower_Bound_USD", "Lower_Bound_Shipments"]
    dash["Lower_Bound_Shipments"] = dash["Lower_Bound_Shipments"].astype(int)
    dash["Upper_Bound_Shipments"] = dash["Upper_Bound_Shipments"].astype(int)
    dash = dash[["Country", "OU", "Sub_OU", "Product", "Family", "Manufacturer",
                 "Lower_Bound_USD", "Upper_Bound_USD",
                 "Lower_Bound_Shipments", "Upper_Bound_Shipments"]]
    return dash.sort_values(
        ["Country", "OU", "Sub_OU", "Upper_Bound_USD"],
        ascending=[True, True, True, False])


def _numeric_rawdata(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of the full row set with Quantity / Total_Value_USD / ASP_USD
    coerced to numbers so the Dashboard's SUMIFS / MINIFS / MAXIFS evaluate (the
    mapped CSV is read as text; text cells aggregate to 0). The dimension columns
    the formulas key on (Segment / Sub-segment / Product_V0 / Family / Manufacturer)
    and the per-shipment ASP_USD are already standardized in the mapping stage
    (step3.standardize_for_dashboard) — no Dash_* helper columns are added here."""
    df = df.copy()
    for col in [cfg.VALUE_COL, "Quantity", cfg.ASP_COL]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _surgical_bound(df: pd.DataFrame) -> pd.DataFrame:
    """Bound (family+category) rows within the core SURGICAL scope that also PASS
    the reference-taxonomy gate (DQ 2026-07): only rows whose (Segment, Sub-segment,
    Product) tuple is in the latest reference and which carry no negative-scope cue
    (Dash_Include == "Y") feed the trusted Dashboard / rollups. The widened
    (Extended) matches are surfaced on the Scope tab; the parked (non-reference /
    excluded) rows are surfaced on the QA tab. Both stay in RawData."""
    m = df[cfg.TIER_COL].isin(cfg.DASHBOARD_BOUND_TIERS)
    if cfg.SCOPE_COL in df.columns:
        m &= df[cfg.SCOPE_COL] == cfg.SCOPE_SURGICAL_LABEL
    if cfg.DASH_INCLUDE_COL in df.columns:
        m &= df[cfg.DASH_INCLUDE_COL] == "Y"
    return df[m]


def _formula_dashboard_dims(df: pd.DataFrame) -> pd.DataFrame:
    """Unique line-item dimension rows (this country only) that the Dashboard
    sheet lists — metrics are attached later as formulas, not values. Groups the
    surgical-scope bound rows on the standardized real dimension columns."""
    bound = _surgical_bound(df)
    dims = (bound.groupby(DASH_DIM_COLS, dropna=False)
                 .size().reset_index()[DASH_DIM_COLS])
    dims.insert(0, "Country", cfg.IMPORT_COUNTRY)
    dims.columns = ["Country", "OU", "Sub_OU", "Product", "Family", "Manufacturer"]
    return dims.sort_values(["OU", "Sub_OU", "Product", "Family", "Manufacturer"]) \
               .reset_index(drop=True)


def _output_path() -> Path:
    """Country-stamped workbook so each market's output coexists."""
    return cfg.OUTPUTS_DIR / f"{_slug(cfg.IMPORT_COUNTRY)}_ML_Map_Mapped.xlsx"


def _mirror_country_folder() -> str:
    country = str(cfg.IMPORT_COUNTRY).strip()
    configured = getattr(cfg, "OUTPUT_MIRROR_COUNTRY_FOLDERS", {})
    return configured.get(country.lower(), _slug(country).upper())


def _mirror_outputs(paths: list[Path]) -> Path | None:
    mirror_root = getattr(cfg, "OUTPUT_MIRROR_ROOT", None)
    if not mirror_root:
        return None

    dest = (Path(mirror_root) / "outputs" /
            _mirror_country_folder() / cfg.OUTPUT_MIRROR_RUN_DIR)
    try:
        dest.mkdir(parents=True, exist_ok=True)
        copied = []
        for src in paths:
            if src.exists():
                shutil.copy2(src, dest / src.name)
                copied.append(src.name)
    except OSError as exc:
        print(f"  [export] mirror skipped: {dest} ({exc})")
        return None

    if copied:
        print(f"  [export] mirrored {len(copied)} file(s) to {dest}")
    return dest


def _rollup_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Category → Manufacturer → Family roll-up of the surgical-scope bound rows,
    with Revenue (Σ value), Volume (Σ qty), Min/Max per-shipment ASP and shipment
    count. Feeds both roll-up tabs (outline + flat table). Sorted by category then
    revenue so the biggest brands/families sit at the top of each block."""
    d = _surgical_bound(df).copy()
    d["_rev"] = pd.to_numeric(d[cfg.VALUE_COL], errors="coerce").fillna(0.0)
    d["_vol"] = pd.to_numeric(d["Quantity"], errors="coerce").fillna(0.0)
    d["_asp"] = pd.to_numeric(d[cfg.ASP_COL], errors="coerce")
    for k in ["Product_V0", "Manufacturer", "Family"]:
        d[k] = d[k].fillna("").replace("", cfg.UNSPECIFIED_LABEL)
    g = d.groupby(["Product_V0", "Manufacturer", "Family"], dropna=False)
    roll = pd.DataFrame({
        "Revenue_USD": g["_rev"].sum(),
        "Volume":      g["_vol"].sum(),
        "Min_ASP":     g["_asp"].min(),
        "Max_ASP":     g["_asp"].max(),
        "Shipments":   g.size(),
    }).reset_index()
    return roll.sort_values(["Product_V0", "Revenue_USD"],
                            ascending=[True, False]).reset_index(drop=True)


def _write_tab_guidance(wb, ws, start_col: int, instruction: str,
                        total_rows: int, mapped_rows: int, hdr) -> None:
    """Add visible workbook guidance and high-level mapped-file statistics.

    The guidance block is written to columns outside each tab's data table so it
    does not change the exported data layout, formulas, filters or downstream
    copy/paste workflows.
    """
    note_fmt = wb.add_format({"font_name": "Arial", "font_size": 9,
                              "text_wrap": True, "valign": "top"})
    num_fmt = wb.add_format({"font_name": "Arial", "font_size": 9,
                             "num_format": "#,##0"})
    pct_fmt = wb.add_format({"font_name": "Arial", "font_size": 9,
                             "num_format": "0.0%"})
    ws.set_column(start_col, start_col, 18)
    ws.set_column(start_col + 1, start_col + 1, 44)
    ws.write(0, start_col, "Tab Instructions", hdr)
    ws.write(0, start_col + 1, instruction, note_fmt)
    ws.write(1, start_col, "Total Rows", hdr)
    ws.write_number(1, start_col + 1, int(total_rows), num_fmt)
    ws.write(2, start_col, "Mapped Rows", hdr)
    ws.write_number(2, start_col + 1, int(mapped_rows), num_fmt)
    ws.write(3, start_col, "Mapped %", hdr)
    mapped_pct = (mapped_rows / total_rows) if total_rows else 0
    ws.write_number(3, start_col + 1, mapped_pct, pct_fmt)


def _write_scope_sheet(wb, ws, cols: list, last_raw: int, hdr) -> None:
    """Formula-driven trusted-surgical vs Extended-review breakdown.

    Surgical rows use the same Dash_Include="Y" criterion as the Dashboard.
    Extended rows are visible as pending review, but they do not feed the trusted
    dashboard or rollups.
    """
    if cfg.SCOPE_COL not in cols:
        ws.write(0, 0, "Scope breakdown unavailable "
                       "(Match_Scope column not present in RawData).", hdr)
        return
    L = {n: xl_col_to_name(cols.index(n)) for n in
         [cfg.VALUE_COL, "Quantity", cfg.SCOPE_COL, cfg.TIER_COL,
          cfg.DASH_INCLUDE_COL, cfg.QA_STATUS_COL]
         if n in cols}
    val, qty = L[cfg.VALUE_COL], L["Quantity"]
    sc, ti = L[cfg.SCOPE_COL], L[cfg.TIER_COL]
    di, qa = L.get(cfg.DASH_INCLUDE_COL), L.get(cfg.QA_STATUS_COL)

    def rng(c):
        return f"RawData!${c}$2:${c}${last_raw}"

    def crit(pairs):
        parts = [f'{rng(col)},"{value}"' for col, value in pairs if col]
        return "," + ",".join(parts) if parts else ""

    money = wb.add_format({"num_format": "#,##0", "font_name": "Arial", "font_size": 9})
    cnt   = wb.add_format({"num_format": "#,##0", "font_name": "Arial", "font_size": 9})
    lbl   = wb.add_format({"font_name": "Arial", "font_size": 9, "bold": True})
    note  = wb.add_format({"font_name": "Arial", "font_size": 8, "italic": True,
                           "font_color": "#666666"})

    heads = ["Scope", "Lower_Revenue_USD (family)", "Upper_Revenue_USD (family+category)",
             "Total_Volume", "Matched_Shipments"]
    for ci, h in enumerate(heads):
        ws.write(0, ci, h, hdr)
    ws.set_column(0, 0, 16)
    ws.set_column(1, 2, 30, money)
    ws.set_column(3, 3, 16, money)
    ws.set_column(4, 4, 18, cnt)

    extended_pairs = [(qa, cfg.QA_REVIEW_EXT)] if qa else [(sc, cfg.SCOPE_EXTENDED_LABEL)]
    rows = [
        (cfg.SCOPE_SURGICAL_LABEL,
         crit([(sc, cfg.SCOPE_SURGICAL_LABEL), (di, "Y")])),
        ("Extended pending review",
         crit(extended_pairs)),
        ("Total", None),
    ]
    # Upper bound = the bound tiers (family+category), gated on Match_Tier — NOT on
    # a non-blank Family — because the family/manufacturer re-rank now predicts a
    # brand for many non-bound rows too, so "Family<>''" no longer means "bound".
    bt = sorted(cfg.DASHBOARD_BOUND_TIERS)
    for i, (label, row_crit) in enumerate(rows):
        r = i + 1
        ws.write_string(r, 0, label, lbl)
        if row_crit is None:
            lower = "=SUM(B2:B3)"
            upper = "=SUM(C2:C3)"
            vol = "=SUM(D2:D3)"
            ships = "=SUM(E2:E3)"
        else:
            lower = f'=SUMIFS({rng(val)}{row_crit},{rng(ti)},"family")'
            upper = "=" + "+".join(
                f'SUMIFS({rng(val)}{row_crit},{rng(ti)},"{t}")' for t in bt)
            vol = "=" + "+".join(
                f'SUMIFS({rng(qty)}{row_crit},{rng(ti)},"{t}")' for t in bt)
            ships = "=" + "+".join(
                f'COUNTIFS({row_crit[1:]},{rng(ti)},"{t}")' for t in bt)
        ws.write_formula(r, 1, lower, money)
        ws.write_formula(r, 2, upper, money)
        ws.write_formula(r, 3, vol,   money)
        ws.write_formula(r, 4, ships, cnt)

    ws.write(len(rows) + 2, 0,
             f"Surgical = HS4 in {sorted(cfg.SURGICAL_HS4)}; Extended = all other "
             f"HS4 recovered by the widened match and parked as pending review. "
             f"Bound = family+category rows (Match_Tier in {bt}). The Dashboard/"
             f"rollups show trusted Surgical rows only.", note)
    ws.freeze_panes(1, 0)


def _write_rollup_outline_sheet(wb, ws, roll: pd.DataFrame, hdr) -> None:
    """Collapsible Excel outline: Product Category subtotal rows (level 0) that
    expand to Manufacturer subtotals (level 1) and then Family detail (level 2),
    each carrying Revenue/Volume/Min/Max ASP. The +/- outline buttons sit on the
    (top) subtotal rows so the user rolls up to category then drops down to
    brands/families. Values are a surgical-scope snapshot.

    Each hierarchy level gets its own colour band (dark→light green) so the
    depth is obvious at a glance: category = dark green (white text), manufacturer
    = medium green, family = pale green."""
    heads = ["Product Category / Manufacturer / Family",
             "Revenue_USD", "Volume", "Min_ASP", "Max_ASP", "Shipments"]
    for ci, h in enumerate(heads):
        ws.write(0, ci, h, hdr)
    ws.set_column(0, 0, 52)
    ws.set_column(1, 2, 16)
    ws.set_column(3, 4, 12)
    ws.set_column(5, 5, 12)
    ws.outline_settings(True, False, True, True)   # symbols on the top summary row

    # Per-level colour palette (dark→light) so each tier is visually distinct.
    CAT_BG,  CAT_FONT = "#1A4D3C", "#FFFFFF"    # level 0 — dark green
    MFR_BG,  MFR_FONT = "#A9CCBB", "#0F2E23"    # level 1 — medium green
    FAM_BG,  FAM_FONT = "#E8F1EC", "#33453D"    # level 2 — pale green

    def _fmt(bg, font_color, *, bold=False, indent=0, num=None):
        spec = {"font_name": "Arial", "font_size": 9, "bg_color": bg,
                "font_color": font_color, "border": 1, "border_color": "#FFFFFF"}
        if bold:
            spec["bold"] = True
        if indent:
            spec["indent"] = indent
        if num:
            spec["num_format"] = num
        return wb.add_format(spec)

    cat_txt = _fmt(CAT_BG, CAT_FONT, bold=True)
    cat_num = _fmt(CAT_BG, CAT_FONT, bold=True, num="#,##0")
    cat_asp = _fmt(CAT_BG, CAT_FONT, bold=True, num="#,##0.00")
    mfr_txt = _fmt(MFR_BG, MFR_FONT, bold=True, indent=1)
    mfr_num = _fmt(MFR_BG, MFR_FONT, bold=True, indent=1, num="#,##0")
    mfr_asp = _fmt(MFR_BG, MFR_FONT, bold=True, indent=1, num="#,##0.00")
    fam_txt = _fmt(FAM_BG, FAM_FONT, indent=2)
    fam_num = _fmt(FAM_BG, FAM_FONT, indent=2, num="#,##0")
    fam_asp = _fmt(FAM_BG, FAM_FONT, indent=2, num="#,##0.00")

    def agg(sub):
        return (sub["Revenue_USD"].sum(), sub["Volume"].sum(),
                sub["Min_ASP"].min(), sub["Max_ASP"].max(), int(sub["Shipments"].sum()))

    r = 1
    for cat, csub in roll.groupby("Product_V0", sort=True):
        rev, vol, mn, mx, sh = agg(csub)
        ws.set_row(r, None, None, {"level": 0})
        ws.write_string(r, 0, str(cat), cat_txt)
        ws.write_number(r, 1, rev, cat_num)
        ws.write_number(r, 2, vol, cat_num)
        ws.write(r, 3, mn if pd.notna(mn) else "", cat_asp)
        ws.write(r, 4, mx if pd.notna(mx) else "", cat_asp)
        ws.write_number(r, 5, sh, cat_num)
        r += 1
        for mfr, msub in csub.groupby("Manufacturer", sort=True):
            rev, vol, mn, mx, sh = agg(msub)
            ws.set_row(r, None, None, {"level": 1})
            ws.write_string(r, 0, str(mfr), mfr_txt)
            ws.write_number(r, 1, rev, mfr_num)
            ws.write_number(r, 2, vol, mfr_num)
            ws.write(r, 3, mn if pd.notna(mn) else "", mfr_asp)
            ws.write(r, 4, mx if pd.notna(mx) else "", mfr_asp)
            ws.write_number(r, 5, sh, mfr_num)
            r += 1
            for _, fr in msub.iterrows():
                ws.set_row(r, None, None, {"level": 2, "hidden": True})
                ws.write_string(r, 0, str(fr["Family"]), fam_txt)
                ws.write_number(r, 1, fr["Revenue_USD"], fam_num)
                ws.write_number(r, 2, fr["Volume"], fam_num)
                ws.write(r, 3, fr["Min_ASP"] if pd.notna(fr["Min_ASP"]) else "", fam_asp)
                ws.write(r, 4, fr["Max_ASP"] if pd.notna(fr["Max_ASP"]) else "", fam_asp)
                ws.write_number(r, 5, int(fr["Shipments"]), fam_num)
                r += 1
    ws.freeze_panes(1, 0)


def _qa_frames(matched: pd.DataFrame) -> list:
    """Value-based QA tables (DQ 2026-07), computed from the FULL matched set (not
    the row-capped RawData) so the numbers are complete even for India: QA-status
    breakdown, reference alignment, negative-scope exclusions, top non-reference
    labels, and manufacturer-only matches. Each is (title, DataFrame)."""
    d = matched.copy()
    d["_rev"] = pd.to_numeric(d[cfg.VALUE_COL], errors="coerce").fillna(0.0)
    tier  = d[cfg.TIER_COL].fillna("")
    bound = tier.isin(cfg.DASHBOARD_BOUND_TIERS)
    surg  = (d[cfg.SCOPE_COL] == cfg.SCOPE_SURGICAL_LABEL) if cfg.SCOPE_COL in d.columns \
            else pd.Series(True, index=d.index)
    inc   = (d[cfg.DASH_INCLUDE_COL] == "Y") if cfg.DASH_INCLUDE_COL in d.columns \
            else pd.Series(False, index=d.index)
    flag  = d[cfg.SCOPE_FLAG_COL].fillna("") if cfg.SCOPE_FLAG_COL in d.columns \
            else pd.Series("", index=d.index)
    frames = []

    if cfg.QA_STATUS_COL in d.columns:
        qs = (d.assign(_s=d[cfg.QA_STATUS_COL].fillna(""))
                .groupby("_s").agg(Rows=("_rev", "size"), Revenue_USD=("_rev", "sum"))
                .reset_index().rename(columns={"_s": "QA_Status"})
                .sort_values("Revenue_USD", ascending=False))
        frames.append(("QA status — all matched rows", qs))

    bs = d[bound & surg]
    v, iv = bs[inc.loc[bs.index]], bs[~inc.loc[bs.index]]
    align = pd.DataFrame({
        "Check": ["Reference-valid (feeds Dashboard)",
                  "Non-reference / excluded (parked as Review)",
                  "Total bound surgical rows"],
        "Rows": [len(v), len(iv), len(bs)],
        "Revenue_USD": [v["_rev"].sum(), iv["_rev"].sum(), bs["_rev"].sum()],
    })
    frames.append(("Reference alignment — surgical bound rows", align))

    sf = d[bound & (flag != "")]
    if len(sf):
        sfg = (sf.groupby(cfg.SCOPE_FLAG_COL)
                 .agg(Rows=("_rev", "size"), Revenue_USD=("_rev", "sum"))
                 .reset_index().rename(columns={cfg.SCOPE_FLAG_COL: "Scope_Flag"})
                 .sort_values("Revenue_USD", ascending=False))
    else:
        sfg = pd.DataFrame({"Scope_Flag": ["(none)"], "Rows": [0], "Revenue_USD": [0.0]})
    frames.append(("Negative-scope exclusions parked as Review (bound rows)", sfg))

    nr = d[bound & surg & ~inc & (flag == "")]
    nrg = (nr.groupby(["Segment", "Sub-segment", "Product_V0"])
             .agg(Rows=("_rev", "size"), Revenue_USD=("_rev", "sum"))
             .reset_index().sort_values("Revenue_USD", ascending=False).head(25))
    frames.append(("Top non-reference product labels (excluded from Dashboard)", nrg))

    mo = d[tier == "manufacturer"]
    if len(mo):
        mog = (mo.groupby("Manufacturer")
                 .agg(Rows=("_rev", "size"), Revenue_USD=("_rev", "sum"))
                 .reset_index().sort_values("Revenue_USD", ascending=False).head(20))
    else:
        mog = pd.DataFrame({"Manufacturer": ["(none)"], "Rows": [0], "Revenue_USD": [0.0]})
    frames.append(("Manufacturer-only matches (audit only — NOT a product mapping)", mog))
    return frames


def _write_qa_sheet(wb, ws, frames: list, hdr) -> None:
    """Stack the QA tables on one sheet with section titles. Revenue columns are
    money-formatted. Gives every workbook a mandatory data-quality view: what is
    reference-valid vs parked, why, and where the biggest non-reference value is."""
    title = wb.add_format({"bold": True, "font_name": "Arial", "font_size": 10,
                           "font_color": "#1A4D3C"})
    money = wb.add_format({"num_format": "#,##0", "font_name": "Arial", "font_size": 9})
    cell  = wb.add_format({"font_name": "Arial", "font_size": 9})
    ws.set_column(0, 0, 44)
    ws.set_column(1, 1, 26)
    ws.set_column(2, 5, 20)
    r = 0
    ws.write(r, 0, "QA / Data-Quality Review — reference-strict gate (DQ 2026-07). "
                   "Non-reference, unspecified and out-of-scope rows are parked as "
                   "Review (kept in RawData, QA_Status column) and excluded from the "
                   "trusted Dashboard/Rollup/Scope.", title)
    r += 2
    for name, fr in frames:
        ws.write(r, 0, name, title)
        r += 1
        cols = list(fr.columns)
        for ci, c in enumerate(cols):
            ws.write(r, ci, str(c), hdr)
        r += 1
        for _, row in fr.iterrows():
            for ci, c in enumerate(cols):
                val = row[c]
                is_num = isinstance(val, (int, float)) and not isinstance(val, bool)
                if is_num and pd.notna(val) and ("Revenue" in str(c) or "USD" in str(c)):
                    ws.write_number(r, ci, float(val), money)
                elif is_num and pd.notna(val):
                    ws.write_number(r, ci, float(val), cell)
                else:
                    ws.write(r, ci, "" if (val is None or (is_num and pd.isna(val))) else str(val), cell)
            r += 1
        r += 2
    ws.freeze_panes(1, 0)


def _write_workbook(out_xlsx: Path, df: pd.DataFrame, summary: pd.DataFrame,
                    dims: pd.DataFrame, rollup: pd.DataFrame,
                    qa_frames: list, total_source_rows: int,
                    mapped_source_rows: int) -> None:
    """Write RawData, Summary and the formula-driven Dashboard sheet.

    `df` must already carry standardized dimension columns and numeric
    Quantity / Total_Value_USD / ASP_USD (see _numeric_rawdata); `dims` is the
    unique Dashboard line-item dimension set (see _formula_dashboard_dims). The
    Dashboard formulas aggregate over the real RawData columns directly.
    """
    cols = list(df.columns)
    n_raw = len(df)
    last_raw = n_raw + 1                      # last RawData row in A1 terms

    writer = pd.ExcelWriter(out_xlsx, engine="xlsxwriter")
    df.to_excel(writer, sheet_name="RawData", index=False)
    summary.to_excel(writer, sheet_name="Summary", index=False)
    dims.to_excel(writer, sheet_name="Dashboard", index=False, startrow=1, header=False)

    wb  = writer.book
    ws1 = writer.sheets["RawData"]
    ws2 = writer.sheets["Summary"]
    ws3 = writer.sheets["Dashboard"]

    green  = wb.add_format({"bg_color": cfg.GREEN_FILL,
                            "font_name": "Arial", "font_size": 9})
    yellow = wb.add_format({"bg_color": cfg.YELLOW_FILL,
                            "font_name": "Arial", "font_size": 9})
    hdr    = wb.add_format({"bold": True, "bg_color": cfg.HEADER_FILL,
                            "font_color": cfg.HEADER_FONT, "border": 1,
                            "font_name": "Arial", "font_size": 9})
    money  = wb.add_format({"num_format": "#,##0", "font_name": "Arial", "font_size": 9})
    asp_fmt = wb.add_format({"num_format": "#,##0.00", "font_name": "Arial", "font_size": 9})

    # ── RawData ────────────────────────────────────────────────────────────
    ws1.set_column(0, len(cols) - 1, 14)
    for name, width in [("Detailed_Product", 60), ("Segment", 38),
                        ("Sub-segment", 28), ("Manufacturer", 28),
                        ("Product_V0", 30), ("Family", 25),
                        ("Match_Status", 14)]:
        if name in cols:
            idx = cols.index(name)
            ws1.set_column(idx, idx, width)
    for name, fmt in [(cfg.VALUE_COL, money), ("Quantity", money),
                      (cfg.ASP_COL, asp_fmt)]:
        if name in cols:
            idx = cols.index(name)
            ws1.set_column(idx, idx, 14, fmt)

    ws1.freeze_panes(1, 0)
    ws1.autofilter(0, 0, n_raw, len(cols) - 1)
    for ci, col in enumerate(cols):
        ws1.write(0, ci, col, hdr)
    _write_tab_guidance(
        wb, ws1, len(cols) + 2,
        "Row-level mapped output. Use filters to inspect Match_Status, Match_Tier, "
        "confidence and standardized Segment/Sub-segment/Product/Family/Manufacturer fields.",
        total_source_rows, mapped_source_rows, hdr)

    # Tier-aware highlighting: green = family (Tier-1), yellow = category (Tier-2)
    tier_col = xl_col_to_name(cols.index(cfg.TIER_COL))
    rng = xl_range(1, 0, n_raw, len(cols) - 1)
    ws1.conditional_format(rng, {"type": "formula",
        "criteria": f'=${tier_col}2="family"', "format": green})
    ws1.conditional_format(rng, {"type": "formula",
        "criteria": f'=${tier_col}2="category"', "format": yellow})

    # ── Summary ────────────────────────────────────────────────────────────
    ws2.set_column(0, len(summary.columns) - 1, 32)
    ws2.freeze_panes(1, 0)
    ws2.autofilter(0, 0, len(summary), len(summary.columns) - 1)
    for ci, col in enumerate(summary.columns):
        ws2.write(0, ci, col, hdr)
    _write_tab_guidance(
        wb, ws2, len(summary.columns) + 2,
        "Grouped count of mapped rows by tier and standardized dimensions. Blank "
        "dimensions are shown as Unspecified for easier filtering.",
        total_source_rows, mapped_source_rows, hdr)

    # ── Dashboard (formula-driven, single country, product-banded) ─────────
    dcols = ["Country", "OU", "Sub_OU", "Product", "Family", "Manufacturer",
             "Total_Revenue_USD", "Total_Volume", "Min_ASP", "Max_ASP", "Avg_ASP"]
    for ci, col in enumerate(dcols):
        ws3.write(0, ci, col, hdr)
    widths = {"Country": 16, "OU": 34, "Sub_OU": 26, "Product": 30,
              "Family": 26, "Manufacturer": 22, "Total_Revenue_USD": 18,
              "Total_Volume": 14, "Min_ASP": 12, "Max_ASP": 12, "Avg_ASP": 12}
    for ci, col in enumerate(dcols):
        ws3.set_column(ci, ci, widths[col])

    # Banded cell formats: each product block gets one of two alternating shades
    # so the different products are easy to separate at a glance; category-only
    # (Unspecified-family) lines stay yellow. Fill is combined with the number
    # format because a cell can carry only one format object.
    _fmt_cache: dict = {}

    def _cell_fmt(bg: str, kind: str):
        key = (bg, kind)
        if key not in _fmt_cache:
            spec = {"font_name": "Arial", "font_size": 9, "bg_color": bg,
                    "border": 1, "border_color": "#BFBFBF"}
            if kind == "money":
                spec["num_format"] = "#,##0"
            elif kind == "asp":
                spec["num_format"] = "#,##0.00"
            _fmt_cache[key] = wb.add_format(spec)
        return _fmt_cache[key]

    # RawData column letters the formulas aggregate over (real standardized cols).
    L = {name: xl_col_to_name(cols.index(name)) for name in
         [cfg.VALUE_COL, "Quantity", cfg.ASP_COL, cfg.SCOPE_COL,
          cfg.DASH_INCLUDE_COL, *DASH_DIM_COLS]
         if name in cols}

    # Every Dashboard formula is also scoped to Surgical rows so the widened
    # (Extended) matches never leak into these trusted numbers.
    scope_crit = (f',RawData!${L[cfg.SCOPE_COL]}$2:${L[cfg.SCOPE_COL]}${last_raw}'
                  f',"{cfg.SCOPE_SURGICAL_LABEL}"') if cfg.SCOPE_COL in L else ""
    # …and gated to reference-valid, in-scope rows (Dash_Include="Y") so the
    # non-reference / unspecified / excluded rows never contribute (DQ 2026-07).
    include_crit = (f',RawData!${L[cfg.DASH_INCLUDE_COL]}$2:${L[cfg.DASH_INCLUDE_COL]}'
                    f'${last_raw},"Y"') if cfg.DASH_INCLUDE_COL in L else ""

    def _crit(er: int) -> str:
        pairs = [
            (L[cfg.DASHBOARD_OU_COL], f"$B{er}"),
            (L["Sub-segment"],        f"$C{er}"),
            (L["Product_V0"],         f"$D{er}"),
            (L["Family"],             f"$E{er}"),
            (L["Manufacturer"],       f"$F{er}"),
        ]
        return "".join(
            f",RawData!${c}$2:${c}${last_raw},{ref}"
            for c, ref in pairs) + scope_crit + include_crit

    prev_block, band = None, 0
    for i, row in enumerate(dims.itertuples(index=False)):
        er = i + 2                            # A1 row of this Dashboard line item
        block = (row.OU, row.Sub_OU, row.Product)
        if block != prev_block:               # new product block → flip the shade
            band ^= 1
            prev_block = block
        bg = (cfg.YELLOW_FILL if row.Family == cfg.UNSPECIFIED_LABEL
              else cfg.DASH_BAND_FILLS[band])

        for ci, val in enumerate([row.Country, row.OU, row.Sub_OU, row.Product,
                                  row.Family, row.Manufacturer]):
            ws3.write_string(er - 1, ci, val, _cell_fmt(bg, "text"))

        crit = _crit(er)
        rev = f"=SUMIFS(RawData!${L[cfg.VALUE_COL]}$2:${L[cfg.VALUE_COL]}${last_raw}{crit})"
        vol = f"=SUMIFS(RawData!${L['Quantity']}$2:${L['Quantity']}${last_raw}{crit})"
        mn  = (f'=IF(H{er}=0,"",_xlfn.MINIFS('
               f"RawData!${L[cfg.ASP_COL]}$2:${L[cfg.ASP_COL]}${last_raw}{crit}))")
        mx  = (f'=IF(H{er}=0,"",_xlfn.MAXIFS('
               f"RawData!${L[cfg.ASP_COL]}$2:${L[cfg.ASP_COL]}${last_raw}{crit}))")
        avg = f'=IF(H{er}=0,"",G{er}/H{er})'
        ws3.write_formula(er - 1, 6, rev, _cell_fmt(bg, "money"))
        ws3.write_formula(er - 1, 7, vol, _cell_fmt(bg, "money"))
        ws3.write_formula(er - 1, 8, mn,  _cell_fmt(bg, "asp"))
        ws3.write_formula(er - 1, 9, mx,  _cell_fmt(bg, "asp"))
        ws3.write_formula(er - 1, 10, avg, _cell_fmt(bg, "asp"))

    ws3.freeze_panes(1, 0)
    ws3.autofilter(0, 0, len(dims), len(dcols) - 1)
    _write_tab_guidance(
        wb, ws3, len(dcols) + 2,
        "Formula-driven surgical-scope dashboard. Revenue, volume and ASP metrics "
        "recalculate from RawData when mapped rows are edited or filtered.",
        total_source_rows, mapped_source_rows, hdr)

    # ── Scope (Surgical vs Extended vs Total, formula-driven) ──────────────
    ws4 = wb.add_worksheet("Scope")
    _write_scope_sheet(wb, ws4, cols, last_raw, hdr)
    _write_tab_guidance(
        wb, ws4, 7,
        "Formula-driven scope split showing Surgical, Extended and Total mapped "
        "bounds. Dashboard and rollups intentionally use Surgical rows only.",
        total_source_rows, mapped_source_rows, hdr)

    # ── Roll-up tab (Category → Manufacturer → Family, collapsible outline) ─
    ws5 = wb.add_worksheet("Rollup")
    _write_rollup_outline_sheet(wb, ws5, rollup, hdr)
    _write_tab_guidance(
        wb, ws5, 7,
        "Collapsible Product Category → Manufacturer → Family roll-up for "
        "surgical-scope mapped rows. Use Excel outline controls to expand detail.",
        total_source_rows, mapped_source_rows, hdr)

    # ── QA tab (reference alignment, scope flags, non-reference labels) ─────
    ws6 = wb.add_worksheet("QA")
    _write_qa_sheet(wb, ws6, qa_frames, hdr)

    writer.close()
    print(f"  [export] wrote {out_xlsx.name} "
          f"({n_raw:,} rows, {len(summary):,} summary rows, "
          f"{len(dims):,} dashboard lines, {len(rollup):,} rollup rows, "
          f"QA tab for {cfg.IMPORT_COUNTRY})")


def run_export() -> Path:
    cfg.OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    out_xlsx = _output_path()
    df = pd.read_csv(cfg.MAPPED_CSV, dtype=str, low_memory=False)

    matched = df[df["Match_Status"] == "Matched"]

    # Summary — relabel blank dimensions as "Unspecified" (no blank rows).
    sm = matched.copy()
    for c in ["Segment", "Sub-segment", "Product_V0"]:
        sm[c] = sm[c].fillna("").replace("", cfg.UNSPECIFIED_LABEL)
    summary = (sm.groupby([cfg.TIER_COL, "Segment", "Sub-segment", "Product_V0"],
                          dropna=False)
                 .size().reset_index(name="Match_Count")
                 .sort_values("Match_Count", ascending=False))

    # Value-based bounds feed the cross-country CSV slice + interactive HTML.
    # Kept SURGICAL-scope only (as before the scope was widened) so the trusted
    # cross-country numbers stay comparable; the widened Extended matches show on
    # the workbook's Scope tab instead.
    surg_bound = _surgical_bound(matched)
    dashboard = _combine_dashboards(_build_dashboard(surg_bound))

    # Workbook sheets: single-country, formula-driven ASP view + roll-up tabs.
    # Dimensions are already standardized in the mapping stage; here we only
    # coerce the numeric measure columns so the SUMIFS/MINIFS/MAXIFS evaluate.
    total_source_rows = len(df)
    mapped_source_rows = int((df["Match_Status"] == "Matched").sum())
    df_raw = _numeric_rawdata(df)
    # Excel caps a worksheet at 1,048,576 rows (incl. header). Very large markets
    # (e.g. India ~2.0M rows) overflow the RawData sheet, so for those we write
    # only the matched rows — the Dashboard/Scope/Rollup formulas key on non-blank
    # Family (bound rows ⊂ matched); unmatched rows never satisfy their criteria,
    # so the numbers are identical. The full row set stays in the CSV/TSV cache.
    if len(df_raw) > cfg.XLSX_MAX_ROWS - 1:
        kept = df_raw[df_raw["Match_Status"] == "Matched"].reset_index(drop=True)
        note = f"writing {len(kept):,} matched rows only"
        # A handful of very large markets (e.g. India FY2025 ~1.1M matched rows)
        # still overflow the sheet even after keeping only matched rows. Retain
        # the highest-Total_Value rows up to the Excel cap so the workbook holds
        # the material value; the complete matched set stays in the CSV, and the
        # authoritative $ bounds come from the (full) dashboard slice above.
        if len(kept) > cfg.XLSX_MAX_ROWS - 1:
            cap = cfg.XLSX_MAX_ROWS - 1
            kept = (kept.sort_values(cfg.VALUE_COL, ascending=False)
                        .head(cap).reset_index(drop=True))
            note = (f"matched rows also exceed the cap — writing the top "
                    f"{len(kept):,} by {cfg.VALUE_COL}")
        print(f"  [export] RawData {len(df_raw):,} rows exceeds Excel limit "
              f"({cfg.XLSX_MAX_ROWS:,}); {note} "
              f"(full set remains in {cfg.MAPPED_CSV.name}).")
        df_raw = kept
    dims   = _formula_dashboard_dims(df_raw)
    rollup = _rollup_frame(df_raw)
    # QA tables computed from the FULL matched set (not the row-capped df_raw) so
    # the reference-alignment / scope-flag figures are complete for large markets.
    qa = _qa_frames(matched)
    _write_workbook(out_xlsx, df_raw, summary, dims, rollup, qa,
                    total_source_rows, mapped_source_rows)

    # Interactive, cross-country dashboard site (client-side filtering) that
    # links back to the methodology page. Rebuilt every export from the same
    # combined slices so it always reflects every country present.
    from src.dashboard_html import build_dashboard_html
    html_path = cfg.OUTPUTS_DIR / cfg.DASHBOARD_HTML_NAME
    html_path.write_text(build_dashboard_html(dashboard), encoding="utf-8")
    print(f"  [export] wrote {html_path.name} "
          f"({dashboard['Country'].nunique()} country/countries, "
          f"filterable in-browser)")

    mirror_sources = [out_xlsx, html_path]
    for name in (
        cfg.METHODOLOGY_HTML_NAME,
        Path(cfg.METHODOLOGY_HTML_NAME).with_suffix(".pdf").name,
    ):
        companion = cfg.OUTPUTS_DIR / name
        if companion.exists():
            mirror_sources.append(companion)
    _mirror_outputs(mirror_sources)

    return out_xlsx


if __name__ == "__main__":
    print("Step 4 — Export")
    run_export()
