"""
Interactive dashboard site (HTML)
=================================
Render the combined multi-country Dashboard as a single self-contained,
filterable HTML page that matches the methodology site's theme and links back to
it. The pipeline regenerates this on every export (step4), so it always reflects
the latest slices in data/intermediate/.

The whole dataset (~a couple thousand line items) is embedded as JSON and
filtered client-side with vanilla JS — no server, no build step, no external JS.
"""
import datetime
import json

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import settings as cfg


def build_dashboard_html(df) -> str:
    """Return the full HTML for the interactive Country dashboard."""
    recs = []
    for _, r in df.iterrows():
        recs.append({
            "c":  str(r["Country"]),
            "ou": str(r["OU"]),
            "s":  str(r["Sub_OU"]),
            "p":  str(r["Product"]),
            "f":  str(r["Family"]),
            "m":  str(r["Manufacturer"]),
            "lo": round(float(r["Lower_Bound_USD"])),
            "up": round(float(r["Upper_Bound_USD"])),
            "ls": int(r["Lower_Bound_Shipments"]),
            "us": int(r["Upper_Bound_Shipments"]),
        })
    data_json = json.dumps(recs, ensure_ascii=False, separators=(",", ":"))
    countries = sorted(df["Country"].unique())
    meta = {
        "generated": datetime.date.today().isoformat(),
        "markets": len(countries),
        "lines": len(df),
        "method_href": cfg.METHODOLOGY_HTML_NAME,
        "unspecified": cfg.UNSPECIFIED_LABEL,
    }
    return (_TEMPLATE
            .replace("__DATA__", data_json)
            .replace("__META__", json.dumps(meta, ensure_ascii=False)))


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Import Value Dashboard — Country Comparison</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Mono:wght@400;500&family=Instrument+Sans:ital,wght@0,400;0,500;0,600;1,400&display=swap" rel="stylesheet">
<style>
  :root{
    --ink:#0f0f0f; --ink-2:#3a3a3a; --ink-3:#7a7a7a;
    --paper:#f7f4ef; --paper-2:#ede9e1; --paper-3:#e0dbd0;
    --accent:#1a4d3c; --accent-2:#c9733b; --accent-3:#2d6a9f;
    --green:#d4edda; --green-txt:#155724;
    --rule:#c8c2b5; --card:#fffdf9;
  }
  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
  html{scroll-behavior:smooth;}
  body{background:var(--paper);color:var(--ink);font-family:'Instrument Sans',sans-serif;font-size:15px;line-height:1.6;-webkit-font-smoothing:antialiased;}

  .sidebar{position:fixed;top:0;left:0;width:220px;height:100vh;background:var(--accent);padding:40px 24px;display:flex;flex-direction:column;gap:4px;z-index:100;overflow-y:auto;}
  .sidebar-brand{font-family:'DM Serif Display',serif;font-size:15px;color:#fff;opacity:.95;margin-bottom:28px;line-height:1.3;letter-spacing:-0.01em;}
  .sidebar-brand span{display:block;font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.18em;text-transform:uppercase;opacity:.6;margin-bottom:6px;}
  .nav-section{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.16em;text-transform:uppercase;color:rgba(255,255,255,.5);margin:22px 0 8px;}
  .nav-link{color:rgba(255,255,255,.82);text-decoration:none;font-size:13.5px;padding:7px 12px;border-radius:6px;transition:background .15s,color .15s;cursor:pointer;}
  .nav-link:hover{background:rgba(255,255,255,.1);color:#fff;}
  .nav-link.active{background:rgba(255,255,255,.18);color:#fff;}

  .main{margin-left:220px;padding:56px 56px 120px;max-width:1180px;}
  .page-header{margin-bottom:34px;padding-bottom:28px;border-bottom:2px solid var(--ink);}
  .page-header::before{content:'INTERACTIVE ANALYSIS';display:block;font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.18em;color:var(--accent-2);margin-bottom:14px;}
  .page-title{font-family:'DM Serif Display',serif;font-size:clamp(30px,3.6vw,44px);line-height:1.1;letter-spacing:-0.02em;margin-bottom:14px;}
  .page-title em{font-style:italic;color:var(--accent);}
  .page-meta{display:flex;gap:24px;flex-wrap:wrap;margin-top:16px;}
  .meta-item{display:flex;flex-direction:column;gap:2px;}
  .meta-label{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.12em;text-transform:uppercase;color:var(--ink-3);}
  .meta-value{font-size:13.5px;font-weight:500;}

  .card{background:var(--card);border:1px solid var(--rule);border-radius:12px;padding:22px 24px;margin-bottom:26px;}
  .card-label{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.18em;text-transform:uppercase;color:var(--accent-2);margin-bottom:16px;}

  .pill-row{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:18px;}
  .pill{font-family:'Instrument Sans',sans-serif;font-size:13px;font-weight:500;padding:7px 15px;border:1px solid var(--rule);background:var(--paper-2);color:var(--ink-2);border-radius:20px;cursor:pointer;transition:all .15s;}
  .pill:hover{border-color:var(--accent);}
  .pill.on{background:var(--accent);border-color:var(--accent);color:#fff;}

  .filters{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;align-items:end;}
  .field{display:flex;flex-direction:column;gap:5px;}
  .field label{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.12em;text-transform:uppercase;color:var(--ink-3);}
  .field select,.field input{font-family:'Instrument Sans',sans-serif;font-size:13.5px;padding:8px 10px;border:1px solid var(--rule);border-radius:7px;background:var(--paper);color:var(--ink);}
  .field select:focus,.field input:focus{outline:none;border-color:var(--accent);}
  .btn{font-family:'Instrument Sans',sans-serif;font-size:13px;font-weight:500;padding:9px 16px;border:1px solid var(--accent);background:transparent;color:var(--accent);border-radius:7px;cursor:pointer;transition:all .15s;}
  .btn:hover{background:var(--accent);color:#fff;}

  .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin-bottom:26px;}
  .kpi{background:var(--card);border:1px solid var(--rule);border-radius:12px;padding:18px 20px;}
  .kpi .k-label{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.12em;text-transform:uppercase;color:var(--ink-3);margin-bottom:8px;}
  .kpi .k-val{font-family:'DM Serif Display',serif;font-size:27px;line-height:1;color:var(--ink);}
  .kpi .k-sub{font-size:11.5px;color:var(--ink-3);margin-top:6px;}
  .kpi.lower .k-val{color:var(--accent);}
  .kpi.upper .k-val{color:var(--accent-3);}
  .kpi.gap   .k-val{color:var(--accent-2);}

  table{width:100%;border-collapse:collapse;font-size:13px;}
  .cmp td,.cmp th{padding:10px 12px;text-align:left;border-bottom:1px solid var(--paper-3);}
  .cmp th{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-3);}
  .cmp .num{text-align:right;font-variant-numeric:tabular-nums;}
  .bar{position:relative;height:16px;border-radius:4px;background:var(--paper-3);overflow:hidden;min-width:120px;}
  .bar .lo{position:absolute;left:0;top:0;height:100%;background:var(--accent);}
  .bar .gp{position:absolute;top:0;height:100%;background:var(--accent-2);opacity:.85;}

  .tbl-wrap{overflow-x:auto;}
  .lines{width:100%;border-collapse:collapse;font-size:12.5px;}
  .lines th{position:sticky;top:0;background:var(--paper-2);font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-2);padding:9px 10px;text-align:left;cursor:pointer;user-select:none;border-bottom:2px solid var(--rule);white-space:nowrap;}
  .lines th.num{text-align:right;}
  .lines th:hover{color:var(--accent);}
  .lines th .arr{color:var(--accent-2);font-size:9px;}
  .lines td{padding:8px 10px;border-bottom:1px solid var(--paper-3);vertical-align:top;}
  .lines td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap;}
  .lines tr:hover td{background:var(--paper-2);}
  .lines .unspec{color:var(--ink-3);font-style:italic;}
  .tag{display:inline-block;font-family:'DM Mono',monospace;font-size:9px;padding:2px 7px;border-radius:10px;background:var(--paper-3);color:var(--ink-2);}
  .tag.c{background:var(--accent);color:#fff;}
  .count-note{font-size:11.5px;color:var(--ink-3);margin:12px 2px 0;}
  .empty{padding:40px;text-align:center;color:var(--ink-3);}
  @media(max-width:820px){.sidebar{display:none;}.main{margin-left:0;padding:32px 20px 80px;}}
</style>
</head>
<body>
<nav class="sidebar">
  <div class="sidebar-brand"><span>Report</span>ML Map<br>Import Analysis</div>
  <div class="nav-section">Analysis</div>
  <a class="nav-link active">Country Dashboard</a>
  <a class="nav-link" id="lnk-method">Methodology</a>
  <div class="nav-section">Jump to</div>
  <a class="nav-link" href="#filters">Filters</a>
  <a class="nav-link" href="#compare">Country Comparison</a>
  <a class="nav-link" href="#items">Line Items</a>
</nav>

<main class="main">
  <header class="page-header">
    <h1 class="page-title">Import Value —<br><em>Country Dashboard</em></h1>
    <div class="page-meta">
      <div class="meta-item"><span class="meta-label">Markets</span><span class="meta-value" id="m-markets"></span></div>
      <div class="meta-item"><span class="meta-label">Line Items</span><span class="meta-value" id="m-lines"></span></div>
      <div class="meta-item"><span class="meta-label">Generated</span><span class="meta-value" id="m-gen"></span></div>
      <div class="meta-item"><span class="meta-label">Bound Metric</span><span class="meta-value">Total Value (USD)</span></div>
    </div>
  </header>

  <section class="card" id="filters">
    <div class="card-label">Filters</div>
    <div class="pill-row" id="country-pills"></div>
    <div class="filters">
      <div class="field"><label>OU (Segment)</label><select id="f-ou"></select></div>
      <div class="field"><label>Sub-OU (Sub-segment)</label><select id="f-sub"></select></div>
      <div class="field"><label>Manufacturer</label><select id="f-mfr"></select></div>
      <div class="field"><label>Family / Product search</label><input id="f-text" type="text" placeholder="e.g. stent, guidewire"></div>
      <div class="field"><label>Min upper bound (USD)</label><input id="f-min" type="number" min="0" step="10000" placeholder="0"></div>
      <div class="field"><button class="btn" id="reset">Reset filters</button></div>
    </div>
  </section>

  <div class="kpis" id="kpis"></div>

  <section class="card" id="compare">
    <div class="card-label">Country Comparison — lower vs upper bound</div>
    <table class="cmp"><thead><tr>
      <th>Country</th><th class="num">Lower (USD)</th><th class="num">Upper (USD)</th>
      <th class="num">Gap (USD)</th><th class="num">Lines</th><th style="width:34%">Lower &nbsp;<span style="color:var(--accent-2)">Gap</span></th>
    </tr></thead><tbody id="cmp-body"></tbody></table>
  </section>

  <section class="card" id="items">
    <div class="card-label">Line Items</div>
    <div class="tbl-wrap"><table class="lines"><thead><tr id="lines-head"></tr></thead><tbody id="lines-body"></tbody></table></div>
    <div class="count-note" id="count-note"></div>
  </section>
</main>

<script>
const DATA = __DATA__;
const META = __META__;
const UNSPEC = META.unspecified;
document.getElementById('m-markets').textContent = META.markets;
document.getElementById('m-lines').textContent = META.lines.toLocaleString('en-US');
document.getElementById('m-gen').textContent = META.generated;
document.getElementById('lnk-method').href = META.method_href;

const usd = n => '$' + Math.round(n).toLocaleString('en-US');
const uniq = k => [...new Set(DATA.map(d => d[k]))].sort((a,b)=>a.localeCompare(b));

const COLS = [
  {k:'c', t:'Country',      num:false},
  {k:'ou',t:'OU',           num:false},
  {k:'s', t:'Sub-OU',       num:false},
  {k:'p', t:'Product',      num:false},
  {k:'f', t:'Family',       num:false},
  {k:'m', t:'Manufacturer', num:false},
  {k:'lo',t:'Lower USD',    num:true},
  {k:'up',t:'Upper USD',    num:true},
  {k:'us',t:'Shipments',    num:true},
];

const state = {countries:new Set(), ou:'', sub:'', mfr:'', text:'', min:0, sort:'up', dir:-1};

// ── Country pills ──────────────────────────────────────────────────────────
const pillWrap = document.getElementById('country-pills');
function buildPills(){
  const all = uniq('c');
  const mkPill = (label,val)=>{const b=document.createElement('div');b.className='pill';b.textContent=label;b.dataset.v=val;b.onclick=()=>togglePill(val,b);pillWrap.appendChild(b);return b;};
  mkPill('All countries','__ALL__').classList.add('on');
  all.forEach(c=>mkPill(c,c));
}
function togglePill(val,el){
  if(val==='__ALL__'){state.countries.clear();
    [...pillWrap.children].forEach(p=>p.classList.toggle('on',p.dataset.v==='__ALL__'));
  }else{
    el.classList.toggle('on');
    if(el.classList.contains('on')) state.countries.add(val); else state.countries.delete(val);
    pillWrap.querySelector('[data-v="__ALL__"]').classList.toggle('on',state.countries.size===0);
  }
  render();
}

// ── Selects ────────────────────────────────────────────────────────────────
function fillSelect(id,key,label){
  const sel=document.getElementById(id);
  sel.innerHTML='<option value="">All '+label+'</option>'+uniq(key).map(v=>`<option value="${esc(v)}">${esc(v)}</option>`).join('');
}
function esc(s){return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}

// ── Filtering ──────────────────────────────────────────────────────────────
function filtered(){
  const t=state.text.trim().toLowerCase();
  return DATA.filter(d=>{
    if(state.countries.size && !state.countries.has(d.c)) return false;
    if(state.ou  && d.ou!==state.ou)  return false;
    if(state.sub && d.s !==state.sub) return false;
    if(state.mfr && d.m !==state.mfr) return false;
    if(state.min && d.up < state.min) return false;
    if(t && !(d.f.toLowerCase().includes(t)||d.p.toLowerCase().includes(t)||d.s.toLowerCase().includes(t)||d.ou.toLowerCase().includes(t))) return false;
    return true;
  });
}

// ── Render ─────────────────────────────────────────────────────────────────
function render(){
  const rows=filtered();
  renderKpis(rows); renderCompare(rows); renderTable(rows);
}
function renderKpis(rows){
  const lo=rows.reduce((a,d)=>a+d.lo,0), up=rows.reduce((a,d)=>a+d.up,0), gap=up-lo;
  const cov=up? (lo/up*100):0;
  const cards=[
    {c:'lower',l:'Lower Bound',v:usd(lo),s:'named-family value'},
    {c:'upper',l:'Upper Bound',v:usd(up),s:'family + category value'},
    {c:'gap',  l:'Gap (Unspecified)',v:usd(gap),s:(up?gap/up*100:0).toFixed(1)+'% of upper'},
    {c:'',     l:'Coverage',v:cov.toFixed(1)+'%',s:'lower ÷ upper'},
    {c:'',     l:'Line Items',v:rows.length.toLocaleString('en-US'),s:'matching filters'},
  ];
  document.getElementById('kpis').innerHTML=cards.map(k=>
    `<div class="kpi ${k.c}"><div class="k-label">${k.l}</div><div class="k-val">${k.v}</div><div class="k-sub">${k.s}</div></div>`).join('');
}
function renderCompare(rows){
  const by={};
  rows.forEach(d=>{(by[d.c]=by[d.c]||{lo:0,up:0,n:0}); by[d.c].lo+=d.lo; by[d.c].up+=d.up; by[d.c].n++;});
  const names=Object.keys(by).sort((a,b)=>by[b].up-by[a].up);
  const maxUp=Math.max(1,...names.map(n=>by[n].up));
  document.getElementById('cmp-body').innerHTML = names.length? names.map(n=>{
    const o=by[n], gap=o.up-o.lo;
    const loW=o.up/maxUp*100*(o.lo/o.up||0), gpW=o.up/maxUp*100*(gap/o.up||0);
    return `<tr><td><strong>${esc(n)}</strong></td>
      <td class="num">${usd(o.lo)}</td><td class="num">${usd(o.up)}</td>
      <td class="num">${usd(gap)}</td><td class="num">${o.n.toLocaleString('en-US')}</td>
      <td><div class="bar"><div class="lo" style="width:${loW}%"></div><div class="gp" style="left:${loW}%;width:${gpW}%"></div></div></td></tr>`;
  }).join('') : `<tr><td colspan="6" class="empty">No rows match the current filters.</td></tr>`;
}
function renderTable(rows){
  const head=document.getElementById('lines-head');
  head.innerHTML=COLS.map(c=>{
    const arr=state.sort===c.k?`<span class="arr">${state.dir<0?'▼':'▲'}</span>`:'';
    return `<th class="${c.num?'num':''}" data-k="${c.k}">${c.t} ${arr}</th>`;
  }).join('');
  head.querySelectorAll('th').forEach(th=>th.onclick=()=>{
    const k=th.dataset.k;
    if(state.sort===k) state.dir*=-1; else {state.sort=k;state.dir=COLS.find(c=>c.k===k).num?-1:1;}
    render();
  });
  const sc=COLS.find(c=>c.k===state.sort);
  rows.sort((a,b)=>{let x=a[state.sort],y=b[state.sort];
    if(sc.num) return (x-y)*state.dir;
    return String(x).localeCompare(String(y))*state.dir;});
  const cell=(v,key)=>{
    const un=(v===UNSPEC)?' class="unspec"':'';
    if(key==='c') return `<td><span class="tag c">${esc(v)}</span></td>`;
    return `<td${un}>${esc(v)}</td>`;
  };
  const body=document.getElementById('lines-body');
  const CAP=1500, shown=rows.slice(0,CAP);
  body.innerHTML= rows.length? shown.map(d=>
    `<tr>${cell(d.c,'c')}${cell(d.ou,'ou')}${cell(d.s,'s')}${cell(d.p,'p')}${cell(d.f,'f')}${cell(d.m,'m')}`+
    `<td class="num">${usd(d.lo)}</td><td class="num">${usd(d.up)}</td><td class="num">${d.us.toLocaleString('en-US')}</td></tr>`).join('')
    : `<tr><td colspan="9" class="empty">No rows match the current filters.</td></tr>`;
  const tot=rows.reduce((a,d)=>a+d.up,0);
  document.getElementById('count-note').textContent =
    `Showing ${Math.min(rows.length,CAP).toLocaleString('en-US')} of ${rows.length.toLocaleString('en-US')} line items · upper-bound total ${usd(tot)}`+
    (rows.length>CAP?` (first ${CAP} shown — narrow the filters to see more)`:'');
}

// ── Wire up ─────────────────────────────────────────────────────────────────
buildPills();
fillSelect('f-ou','ou','OUs'); fillSelect('f-sub','s','Sub-OUs'); fillSelect('f-mfr','m','Manufacturers');
document.getElementById('f-ou').onchange = e=>{state.ou=e.target.value;render();};
document.getElementById('f-sub').onchange= e=>{state.sub=e.target.value;render();};
document.getElementById('f-mfr').onchange= e=>{state.mfr=e.target.value;render();};
document.getElementById('f-text').oninput= e=>{state.text=e.target.value;render();};
document.getElementById('f-min').oninput = e=>{state.min=+e.target.value||0;render();};
document.getElementById('reset').onclick = ()=>{
  state.countries.clear();state.ou='';state.sub='';state.mfr='';state.text='';state.min=0;state.sort='up';state.dir=-1;
  document.getElementById('f-ou').value='';document.getElementById('f-sub').value='';
  document.getElementById('f-mfr').value='';document.getElementById('f-text').value='';document.getElementById('f-min').value='';
  [...pillWrap.children].forEach(p=>p.classList.toggle('on',p.dataset.v==='__ALL__'));
  render();
};
render();
</script>
</body>
</html>
"""
