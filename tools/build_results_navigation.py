"""Build the governed, static results-navigation hub.

The site is a read-only view over the prediction-audit SQLite authority.  It
does not modify mapped workbooks, reference data, reviewer decisions, or the
production dashboard.  Publish the generated directory as one linked set.
"""

from __future__ import annotations

import argparse
import html
import json
import sqlite3
from collections import defaultdict
from datetime import date
from pathlib import Path

from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "outputs/20260712_recall_audit_v3/prediction_audit.sqlite"
DEFAULT_OUT = ROOT / "outputs/results_navigation"
WB_DIR = ROOT / "outputs/remapped_current"
DIMENSIONS = {
    "segment": "segment",
    "sub_segment": "sub_segment",
    "product": "product",
    "manufacturer": "manufacturer",
    "family": "family",
}
MACRO = {
    "Vietnam": {"population": 100_987_686, "gdp": 476_324_572_783.807},
    "India": {"population": 1_450_935_791, "gdp": 3_760_813_470_500.86},
    "Pakistan": {"population": 251_269_164, "gdp": 371_747_087_751.306},
}
WB_SOURCE = "https://api.worldbank.org/v2/country/VNM;IND;PAK"


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def aggregate(conn: sqlite3.Connection) -> tuple[list[dict], list[dict]]:
    totals = []
    for row in conn.execute(
        """SELECT output_file_id,country,fiscal_year,output_tier,count(*),
                  coalesce(sum(value_usd),0),coalesce(sum(volume),0)
             FROM row_fact GROUP BY 1,2,3,4 ORDER BY 1,4"""
    ):
        totals.append(dict(zip(
            ("file", "country", "year", "tier", "rows", "value", "volume"), row
        )))

    detail = []
    for key, column in DIMENSIONS.items():
        sql = f"""SELECT output_file_id,country,fiscal_year,output_tier,
                         coalesce(nullif(trim({column}),''),'<Unmapped>'),
                         count(*),coalesce(sum(value_usd),0),coalesce(sum(volume),0)
                    FROM row_fact GROUP BY 1,2,3,4,5 ORDER BY 1,4,7 DESC"""
        for row in conn.execute(sql):
            detail.append(dict(zip(
                ("file", "country", "year", "tier", "name", "rows", "value", "volume"), row
            )) | {"dimension": key})
    return totals, detail


def workbook_schemas() -> list[dict]:
    schemas = []
    for path in sorted(WB_DIR.glob("*_ML_Map_Mapped.xlsx")):
        wb = load_workbook(path, read_only=True, data_only=False)
        sheets = []
        for ws in wb.worksheets:
            header = []
            if ws.max_row:
                header = [str(v) if v is not None else "" for v in next(ws.iter_rows(min_row=1, max_row=1, values_only=True))]
            sheets.append({"name": ws.title, "rows": ws.max_row, "columns": header})
        schemas.append({"file": path.name, "sheets": sheets})
        wb.close()
    return schemas


def shell(title: str, active: str, body: str, script: str = "") -> str:
    nav = [("index.html", "Overview"), ("quality.html", "Weekend scorecard"), ("comparison.html", "Compare results"),
           ("outputs.html", "Outputs & tracking"), ("schemas.html", "Data schemas")]
    links = "".join(f'<a class="{("active" if label == active else "")}" href="{href}">{label}</a>' for href, label in nav)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title>
<link rel="stylesheet" href="assets/site.css"></head><body>
<header><div class="brand"><div><b>Clearstate</b><small>Surgical mapping results</small></div></div>
<nav aria-label="Primary">{links}</nav></header><main>{body}</main>
<footer>Read-only navigation layer · Authority: audit v3 · Generated {date.today().isoformat()} · <a href="https://data.worldbank.org/" target="_blank" rel="noopener">2024 population and GDP: World Bank</a></footer>
<script src="assets/data.js"></script><script src="assets/site.js"></script>{script}</body></html>"""


def write_site(out: Path, totals: list[dict], detail: list[dict], schemas: list[dict]) -> None:
    assets = out / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    packed_detail = [[x[k] for k in ("file", "country", "year", "tier", "name",
                                     "rows", "value", "volume", "dimension")]
                     for x in detail]
    payload = {"totals": totals, "detail": packed_detail, "schemas": schemas, "macro": MACRO,
               "metadata": {"audit": "20260712_recall_audit_v3", "macro_year": 2024,
                            "world_bank": WB_SOURCE, "detail_fields":
                            ["file", "country", "year", "tier", "name", "rows", "value", "volume", "dimension"]}}
    unpack = ";RESULTS_DATA.detail=RESULTS_DATA.detail.map(r=>Object.fromEntries(RESULTS_DATA.metadata.detail_fields.map((k,i)=>[k,r[i]])));"
    (assets / "data.js").write_text("window.RESULTS_DATA=" + json.dumps(payload, separators=(",", ":")) + unpack, encoding="utf-8")

    css = """:root{--ink:#111827;--muted:#667085;--blue:#0047ab;--line:#d9dee7;--bg:#f5f7fa;--good:#067647;--warn:#b54708;--bad:#b42318;--r:7px}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 Inter,Segoe UI,Arial,sans-serif}header{background:#fff;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;padding:13px max(20px,calc((100% - 1440px)/2));gap:24px}.brand{display:flex;align-items:center;gap:10px;white-space:nowrap}.brand small{display:block;color:var(--muted)}.mark{display:grid;place-items:center;width:36px;height:36px;background:var(--blue);color:#fff;border-radius:6px;font-weight:800}nav{display:flex;gap:4px;flex-wrap:wrap}nav a{color:#344054;text-decoration:none;padding:8px 10px;border-radius:5px}nav a:hover,nav a.active{background:#eef4ff;color:var(--blue)}main{max-width:1440px;margin:auto;padding:26px 20px 50px}.eyebrow{color:var(--blue);font-weight:700;text-transform:uppercase;letter-spacing:.08em;font-size:11px}h1{font-size:30px;line-height:1.15;margin:6px 0 8px}h2{font-size:20px;margin:28px 0 12px}h3{font-size:15px;margin:0 0 7px}p{margin:6px 0 12px}.muted{color:var(--muted)}.notice{background:#fff7ed;border-left:4px solid var(--warn);padding:12px 14px;margin:18px 0}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.card{background:#fff;border:1px solid var(--line);border-radius:var(--r);padding:15px}.card a{color:var(--blue);font-weight:650}.kpi{font-size:25px;font-weight:750}.toolbar{display:flex;gap:10px;align-items:end;flex-wrap:wrap;background:#fff;border:1px solid var(--line);padding:12px;border-radius:var(--r);position:sticky;top:0;z-index:2}.toolbar label{display:grid;gap:4px;color:var(--muted);font-size:12px}.toolbar select,.toolbar input{font:inherit;padding:7px 9px;border:1px solid #aeb7c5;border-radius:5px;background:#fff;min-width:135px}.table-wrap{overflow:auto;background:#fff;border:1px solid var(--line);border-radius:var(--r);margin-top:12px}table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:9px 11px;border-bottom:1px solid #e7eaf0;white-space:nowrap}th{position:sticky;top:0;background:#f9fafb;color:#475467;font-size:12px}td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}.bar{height:7px;background:#e8edf5;border-radius:5px;overflow:hidden;min-width:90px}.bar i{display:block;height:100%;background:var(--blue)}.status{display:inline-block;padding:2px 7px;border-radius:20px;font-size:12px;background:#eef4ff;color:var(--blue)}.flag-low{color:var(--bad);font-weight:700}.flag-mid{color:var(--warn);font-weight:700}.flag-ok{color:var(--good);font-weight:700}.schema details{background:#fff;border:1px solid var(--line);border-radius:var(--r);margin:8px 0}.schema summary{cursor:pointer;padding:12px 14px;font-weight:650}.schema .inside{padding:0 14px 14px}.columns{display:flex;flex-wrap:wrap;gap:5px}.columns code{background:#f2f4f7;padding:3px 6px;border-radius:4px;font-size:11px}.destination{display:flex;justify-content:space-between;gap:16px;align-items:center}.destination p{margin:2px 0}.links a{display:block;margin:5px 0}footer{max-width:1440px;margin:auto;padding:15px 20px 35px;color:var(--muted);border-top:1px solid var(--line)}@media(max-width:800px){header{align-items:flex-start;flex-direction:column}.grid{grid-template-columns:1fr}.toolbar{position:static}.destination{align-items:flex-start;flex-direction:column}h1{font-size:25px}}"""
    (assets / "site.css").write_text(css, encoding="utf-8")

    js = r"""const D=window.RESULTS_DATA;const $=(s)=>document.querySelector(s);const money=n=>'$'+(n>=1e9?(n/1e9).toFixed(2)+'B':n>=1e6?(n/1e6).toFixed(1)+'M':n.toLocaleString(undefined,{maximumFractionDigits:0}));const integer=n=>Math.round(n).toLocaleString();const pct=n=>(100*n).toFixed(1)+'%';function totals(year,tier){return D.totals.filter(x=>x.year==year&&x.tier==tier)}function trusted(country,year){return D.totals.find(x=>x.country==country&&x.year==year&&x.tier==='Trusted')}function renderOverview(){if(!$('#country-cards'))return;const y='2024',v=trusted('Vietnam',y);$('#country-cards').innerHTML=['Vietnam','India','Pakistan'].map(c=>{const x=trusted(c,y),all=D.totals.filter(z=>z.country===c&&z.year===y).reduce((a,z)=>a+z.value,0);return `<article class="card"><span class="status">${c} FY${y}</span><div class="kpi">${money(x.value)}</div><p>Trusted mapped value · ${integer(x.rows)} rows</p><p class="muted">Trusted share of all import value: ${pct(x.value/all)}</p></article>`}).join('');const rows=['India','Pakistan'].map(c=>{const x=trusted(c,y),m=D.macro[c],vm=D.macro.Vietnam;const popExpected=v.value*m.population/vm.population,gdpExpected=v.value*m.gdp/vm.gdp;return `<tr><td>${c}</td><td class="num">${money(x.value)}</td><td class="num">${(m.population/vm.population).toFixed(2)}×</td><td class="num">${money(popExpected)}</td><td class="num flag-${x.value/popExpected<.25?'low':x.value/popExpected<.6?'mid':'ok'}">${pct(x.value/popExpected)}</td><td class="num">${(m.gdp/vm.gdp).toFixed(2)}×</td><td class="num">${money(gdpExpected)}</td><td class="num flag-${x.value/gdpExpected<.25?'low':x.value/gdpExpected<.6?'mid':'ok'}">${pct(x.value/gdpExpected)}</td></tr>`}).join('');$('#benchmark-body').innerHTML=rows}
function renderComparison(){if(!$('#comparison-body'))return;const year=$('#year').value,tier=$('#tier').value,dim=$('#dimension').value,q=$('#search').value.toLowerCase();let rows=D.detail.filter(x=>x.year===year&&x.tier===tier&&x.dimension===dim&&x.name.toLowerCase().includes(q));const map={};for(const x of rows)(map[x.name]??={name:x.name,Vietnam:0,India:0,Pakistan:0,vr:0,ir:0,pr:0})[x.country]=x.value,(map[x.name][x.country[0].toLowerCase()+'r']=x.rows);rows=Object.values(map).sort((a,b)=>(b.Vietnam+b.India+b.Pakistan)-(a.Vietnam+a.India+a.Pakistan));const max=Math.max(1,...rows.map(x=>x.Vietnam+x.India+x.Pakistan));$('#row-count').textContent=`${integer(rows.length)} categories`;$('#comparison-body').innerHTML=rows.map(x=>`<tr><td>${x.name}</td><td class="num">${money(x.Vietnam)}</td><td class="num">${money(x.India)}</td><td class="num">${money(x.Pakistan)}</td><td class="num">${x.Vietnam? (x.India/x.Vietnam).toFixed(2)+'×':'—'}</td><td class="num">${x.Vietnam? (x.Pakistan/x.Vietnam).toFixed(2)+'×':'—'}</td><td><div class="bar"><i style="width:${100*(x.Vietnam+x.India+x.Pakistan)/max}%"></i></div></td></tr>`).join('')||'<tr><td colspan="7">No matching categories.</td></tr>'}function initComparison(){if(!$('#comparison-body'))return;['year','tier','dimension','search'].forEach(id=>$('#'+id).addEventListener(id==='search'?'input':'change',renderComparison));renderComparison()}
function renderSchemas(){if(!$('#schemas'))return;$('#schemas').innerHTML=D.schemas.map(w=>`<section class="schema"><h2>${w.file}</h2>${w.sheets.map(s=>`<details><summary>${s.name} · ${integer(Math.max(0,s.rows-1))} data rows · ${s.columns.length} columns</summary><div class="inside"><div class="columns">${s.columns.filter(Boolean).map(c=>`<code>${c}</code>`).join('')}</div></div></details>`).join('')}</section>`).join('')}document.addEventListener('DOMContentLoaded',()=>{renderOverview();initComparison();renderSchemas()});"""
    (assets / "site.js").write_text(js, encoding="utf-8")

    overview = """<div class="eyebrow">Current results at a glance</div><h1>Understand the mapped results before opening a workbook</h1><p class="muted">One governed entry point for market totals, category comparisons, files, and field definitions.</p><div id="country-cards" class="grid"></div><h2>Vietnam benchmark sense-check</h2><p>FY2024 Trusted value is compared with what India and Pakistan would show if they scaled exactly with Vietnam by population or nominal GDP.</p><div class="notice"><b>Interpretation:</b> this is a reasonableness signal, not a market-size forecast. Trade capture, local manufacturing, coding practice, healthcare intensity, pricing, and recall differ by country.</div><div class="table-wrap"><table><thead><tr><th>Market</th><th class="num">Actual Trusted</th><th class="num">Population vs VN</th><th class="num">Population-scaled</th><th class="num">Actual / expected</th><th class="num">GDP vs VN</th><th class="num">GDP-scaled</th><th class="num">Actual / expected</th></tr></thead><tbody id="benchmark-body"></tbody></table></div><h2>Where to go</h2><div class="grid"><article class="card"><h3>Weekend scorecard</h3><p>See what changed, what did not, and why accuracy is not yet a measured percentage.</p><a href="quality.html">Open scorecard →</a></article><article class="card"><h3>Compare results</h3><p>Slice exact Trusted, Review, or Excluded value by family, manufacturer, product, or business hierarchy.</p><a href="comparison.html">Open comparison →</a></article><article class="card"><h3>Outputs & tracking</h3><p>Know which report answers which question and open the current governed artifact.</p><a href="outputs.html">Open directory →</a></article><article class="card"><h3>Data schemas</h3><p>See every sheet and column in each current mapped workbook.</p><a href="schemas.html">Open schemas →</a></article></div>"""
    (out / "index.html").write_text(shell("Results navigation", "Overview", overview), encoding="utf-8")

    quality = """<div class="eyebrow">Weekend change, in plain English</div><h1>Recall and precision scorecard</h1><p class="muted">Measured change compares audit v2 with audit v3 over the same 3,573,729 source rows.</p><div class="grid"><article class="card"><span class="status">Realized recall</span><div class="kpi">0</div><p>additional Trusted rows</p></article><article class="card"><span class="status">Realized value</span><div class="kpi">$0</div><p>additional Trusted import value</p></article><article class="card"><span class="status">Realized volume</span><div class="kpi">0</div><p>additional Trusted units</p></article></div><div class="notice"><b>Why zero?</b> The weekend work was review-only. All 365 recovery proposals still have blank approvals, so governed reference files and production workbooks were deliberately not changed.</div><h2>What improved even though production did not move?</h2><div class="grid"><article class="card"><h3>Safer recall candidates</h3><div class="kpi">$232.3M</div><p>of evidence-backed rows are now organized for human review: $178.0M held at reference validation plus $54.3M held by the scope guard.</p><p class="muted">This is an opportunity pool, not a promised gain. The conservative planning estimate remains about $180M until reviewers approve individual proposals.</p></article><article class="card"><h3>False recovery avoided</h3><div class="kpi">64%</div><p>of the first, naive “recognized family” pool proved spurious and was kept out. That protects precision while looking for recall.</p></article><article class="card"><h3>Precision measurement</h3><div class="kpi">0 / 150</div><p>review samples have business labels. A defensible accuracy percentage will appear only after analysts complete them.</p></article></div><h2>Is mAP the right score?</h2><p>No. Mean Average Precision (mAP) measures ranked search or detection results. This mapping workflow does not produce a ranked result list, so an mAP percentage for value or volume would be misleading. The business scores used here are:</p><div class="grid"><article class="card"><h3>Recall / coverage</h3><p>How many relevant rows, dollars, and units reach Trusted status. The measured weekend change is zero; the review opportunity is shown separately.</p></article><article class="card"><h3>Precision / correctness</h3><p>Of the rows released as Trusted, how many are genuinely surgical and correctly mapped. This awaits the 150 analyst labels.</p></article><article class="card"><h3>Value and volume</h3><p>These are business weights, not accuracy scores. We report their movement alongside row counts.</p></article></div><h2>Examples of identified improvements</h2><div class="table-wrap"><table><thead><tr><th>Example candidate</th><th class="num">Value</th><th>What the system improved</th><th>Current status</th></tr></thead><tbody><tr><td>APT Medical — March</td><td class="num">$55.8M</td><td>Connected description evidence to a governed family-alias proposal.</td><td>Awaiting analyst approval</td></tr><tr><td>Intromedic — Mirocam</td><td class="num">$39.8M</td><td>Recovered a recognizable product family for review without auto-releasing it.</td><td>Awaiting analyst approval</td></tr><tr><td>Intuitive Surgical — Monopolar Curved Scissors</td><td class="num">$14.3M</td><td>Turned a high-value blocked cluster into a traceable proposal with evidence.</td><td>Awaiting analyst approval</td></tr><tr><td>Terumo — Spectra Optia</td><td class="num">$12.3M</td><td>Separated a credible surgical candidate from broad manufacturer-only matches.</td><td>Awaiting analyst approval</td></tr></tbody></table></div><h2>What happens next?</h2><p>Analysts approve only credible proposal rows and label the 150 review samples. The operator then rebuilds the governed references, reruns Pakistan → India → Vietnam, and compares the new output with audit v3. That next comparison will convert approved opportunities into measured recall gain and provide the first defensible precision score.</p>"""
    (out / "quality.html").write_text(shell("Weekend recall and precision", "Weekend scorecard", quality), encoding="utf-8")

    comparison = """<div class="eyebrow">Exact cross-market comparison</div><h1>Compare totals, families, and manufacturers</h1><p class="muted">All values reconcile to the audit-v3 row authority. Blank mapped dimensions are shown as &lt;Unmapped&gt;; genuine Unspecified labels remain distinct.</p><div class="toolbar"><label>Fiscal year<select id="year"><option>2024</option><option>2025</option></select></label><label>Routing tier<select id="tier"><option>Trusted</option><option>Review</option><option>Excluded</option></select></label><label>Breakdown<select id="dimension"><option value="family">Family</option><option value="manufacturer">Manufacturer</option><option value="product">Product</option><option value="segment">Segment</option><option value="sub_segment">Sub-segment</option></select></label><label>Find category<input id="search" type="search" placeholder="Type to filter"></label><span id="row-count" class="status"></span></div><div class="table-wrap"><table><thead><tr><th>Category</th><th class="num">Vietnam</th><th class="num">India</th><th class="num">Pakistan</th><th class="num">India / VN</th><th class="num">Pakistan / VN</th><th>Combined scale</th></tr></thead><tbody id="comparison-body"></tbody></table></div><div class="notice"><b>How to use:</b> start with Trusted, then switch to Review to see where apparent market gaps may be mapping-recall gaps rather than real commercial differences.</div>"""
    (out / "comparison.html").write_text(shell("Compare results", "Compare results", comparison), encoding="utf-8")

    outputs = """<div class="eyebrow">Current governed outputs</div><h1>Reports and result tracking</h1><p class="muted">Open the artifact that matches the business question. Links are relative to the shared delivery folder.</p><div class="grid links"><article class="card"><h3>Market dashboard</h3><p>Current production result views and market rollups.</p><a href="../Dashboard.html">Open Dashboard.html →</a></article><article class="card"><h3>Recall funnel dashboard</h3><p>Why rows were kept or held, examples, hotspots, and the what-if gate simulator.</p><a href="../Recall_Funnel_Dashboard.html">Open recall dashboard →</a></article><article class="card"><h3>Mapped workbooks</h3><p>Six current row-level deliverables.</p><a href="../../1. Mapped Results/Vietnam_FY2024_ML_Map_Mapped.xlsx">Vietnam FY2024</a><a href="../../1. Mapped Results/Vietnam_FY2025_ML_Map_Mapped.xlsx">Vietnam FY2025</a><a href="../../1. Mapped Results/India_FY2024_ML_Map_Mapped.xlsx">India FY2024</a><a href="../../1. Mapped Results/India_FY2025_ML_Map_Mapped.xlsx">India FY2025</a><a href="../../1. Mapped Results/Pakistan_FY2024_ML_Map_Mapped.xlsx">Pakistan FY2024</a><a href="../../1. Mapped Results/Pakistan_FY2025_ML_Map_Mapped.xlsx">Pakistan FY2025</a></article><article class="card"><h3>Manual review</h3><p>Governed venues for recall approvals and measured-precision labels.</p><a href="../../4. Manual Mapped Files/Prediction_Funnel_and_Review.xlsx">Prediction review workbook</a><a href="../Recall_Recovery_Proposals.xlsx">Recall recovery proposals</a></article><article class="card"><h3>Tracking & lineage</h3><p>What changed, current output bounds, and source lineage.</p><a href="../../5. Documentation/DATA_UPDATES_LOG.md">Data updates log</a><a href="../../5. Documentation/OUTPUT_TRACKER.md">Output tracker</a><a href="../../5. Documentation/DATA_LINEAGE.md">Data lineage</a></article><article class="card"><h3>Workflow guide</h3><p>Plain-language explanation of the mapping stages and governance loop.</p><a href="../Surgical_Mapping_Workflow_Guide.html">Open guide →</a></article></div>"""
    (out / "outputs.html").write_text(shell("Outputs and tracking", "Outputs & tracking", outputs), encoding="utf-8")

    schemas_body = """<div class="eyebrow">Workbook dictionary</div><h1>Current mapped-output schemas</h1><p class="muted">Expand a worksheet to see its exact column names. Row counts come from workbook metadata and include the current generated view.</p><div class="notice"><b>Core distinction:</b> RawData is the row-level source of truth inside each mapped workbook; Trusted_Dashboard contains only rows passing release gates; Review_Queue holds unresolved rows and must not be added to market totals.</div><div id="schemas"></div>"""
    (out / "schemas.html").write_text(shell("Data schemas", "Data schemas", schemas_body), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    conn = sqlite3.connect(f"file:{Path(args.db).resolve().as_posix()}?mode=ro", uri=True)
    totals, detail = aggregate(conn)
    conn.close()
    write_site(Path(args.out), totals, detail, workbook_schemas())
    print(f"Built results navigation: {Path(args.out).resolve()}")
    print(f"Totals: {len(totals)}; comparison groups: {len(detail)}")


if __name__ == "__main__":
    main()
