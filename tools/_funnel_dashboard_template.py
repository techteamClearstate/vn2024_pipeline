"""HTML/CSS/JS template for build_funnel_dashboard.py.

Kept in its own module so the data-assembly logic stays readable. The string
contains four placeholders replaced at build time:
  __PAYLOAD__  the embedded JSON data cube (already <>&-escaped)
  __GEN__      generated-at timestamp
  __RUN__      run id
  __REG__      registry version
Uses str.replace (not str.format), so literal { } in CSS/JS are safe.
"""

TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Recall Funnel Dashboard — Surgical Import-Data Enrichment</title>
<style>
:root{
  --ink:#12203a; --muted:#5b6b82; --line:#e3e8ef; --paper:#f6f8fb; --white:#fff;
  --blue:#1f5fbf; --blue-d:#16407f;
  --green:#1f9d61; --amber:#e0a021; --red:#d64545; --slate:#7a8aa0;
  --pgreen:#e6f5ee; --pamber:#fbf1d9; --pred:#fbe6e6; --pblue:#e8f0fb;
  --shadow:0 1px 3px rgba(18,32,58,.08),0 1px 2px rgba(18,32,58,.06);
}
*{box-sizing:border-box}
body{margin:0;font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:var(--ink);background:var(--paper)}
h1,h2,h3{line-height:1.2;margin:0 0 .4em}
h2{font-size:22px;margin-top:.2em}
h3{font-size:16px}
a{color:var(--blue)}
p{margin:.4em 0 .8em}
.wrap{max-width:1180px;margin:0 auto;padding:0 20px 80px}
header.hero{background:linear-gradient(135deg,#12203a,#1f3c66);color:#fff;padding:26px 0 20px}
header.hero .wrap{padding-bottom:0}
header.hero h1{font-size:26px;margin-bottom:6px}
header.hero .sub{color:#c6d5ec;font-size:14px;max-width:820px}
.meta{color:#9db4d6;font-size:12px;margin-top:10px}
nav.tabs{position:sticky;top:0;z-index:20;background:var(--white);border-bottom:1px solid var(--line);box-shadow:var(--shadow)}
nav.tabs .wrap{display:flex;gap:2px;flex-wrap:wrap;padding-top:0;padding-bottom:0}
nav.tabs button{appearance:none;border:0;background:transparent;color:var(--muted);font:600 14px/1 inherit;padding:14px 14px;cursor:pointer;border-bottom:3px solid transparent}
nav.tabs button:hover{color:var(--ink)}
nav.tabs button.active{color:var(--blue-d);border-bottom-color:var(--blue)}
section.tab{display:none;padding-top:22px}
section.tab.active{display:block}
.card{background:var(--white);border:1px solid var(--line);border-radius:10px;padding:18px 20px;margin:14px 0;box-shadow:var(--shadow)}
.card.tight{padding:14px 16px}
.grid{display:grid;gap:14px}
.g3{grid-template-columns:repeat(3,1fr)}
.g2{grid-template-columns:repeat(2,1fr)}
@media(max-width:760px){.g3,.g2{grid-template-columns:1fr}}
.controls{display:flex;gap:16px;flex-wrap:wrap;align-items:flex-end;margin:6px 0 4px}
.controls label{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);margin-bottom:4px;font-weight:700}
select,.seg{font:inherit;font-size:14px}
select{padding:7px 10px;border:1px solid var(--line);border-radius:8px;background:var(--white);color:var(--ink)}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:8px;overflow:hidden}
.seg button{appearance:none;border:0;background:var(--white);color:var(--muted);padding:7px 12px;cursor:pointer;font-weight:600}
.seg button+button{border-left:1px solid var(--line)}
.seg button.active{background:var(--blue);color:#fff}
.chk{display:inline-flex;align-items:center;gap:6px;font-size:13px;color:var(--muted);cursor:pointer}
.kpi{display:flex;flex-direction:column;gap:2px}
.kpi .n{font-size:26px;font-weight:800;letter-spacing:-.01em}
.kpi .l{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;font-weight:700}
.kpi .s{font-size:12px;color:var(--muted)}
.tier-T{color:var(--green)} .tier-R{color:var(--amber)} .tier-E{color:var(--red)}
.dot{display:inline-block;width:10px;height:10px;border-radius:2px;vertical-align:baseline;margin-right:5px}
.bg-T{background:var(--green)} .bg-R{background:var(--amber)} .bg-E{background:var(--red)} .bg-B{background:var(--blue)}
.stackbar{display:flex;height:22px;border-radius:5px;overflow:hidden;background:var(--paper);border:1px solid var(--line)}
.stackbar span{display:block;height:100%}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:13px;color:var(--muted);margin:8px 0}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{text-align:right;padding:7px 9px;border-bottom:1px solid var(--line);white-space:nowrap}
th:first-child,td:first-child{text-align:left;white-space:normal}
thead th{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.04em;position:sticky;top:52px;background:var(--white)}
tbody tr:hover{background:var(--pblue)}
.scroll{overflow:auto;max-height:none}
.barcell{position:relative;min-width:180px}
.barrow{display:flex;align-items:center;gap:10px}
.barrow .lab{flex:0 0 210px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.barrow .bar{flex:1}
.barrow .val{flex:0 0 120px;text-align:right;font-variant-numeric:tabular-nums;color:var(--muted)}
.funnelstep{margin:0 0 4px;padding:10px 12px;border:1px solid var(--line);border-radius:9px;background:var(--white)}
.funnelstep.zero{opacity:.6;padding:6px 12px}
.funnelstep .top{display:flex;justify-content:space-between;gap:12px;align-items:baseline}
.funnelstep .name{font-weight:700}
.funnelstep .plain{color:var(--muted);font-size:12.5px;margin:2px 0 6px}
.funnelbar{height:24px;border-radius:5px;overflow:hidden;display:flex;background:var(--paper);border:1px solid var(--line)}
.funnelbar span{height:100%}
.numgrid{display:flex;gap:18px;flex-wrap:wrap;font-size:12.5px;color:var(--muted);margin-top:6px}
.numgrid b{color:var(--ink)}
.pill{display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:700}
.pill.T{background:var(--pgreen);color:#12724a}.pill.R{background:var(--pamber);color:#8a6410}.pill.E{background:var(--pred);color:#a12d2d}
.note{background:var(--pblue);border-left:3px solid var(--blue);padding:10px 14px;border-radius:0 8px 8px 0;font-size:13.5px;margin:12px 0}
.warn{background:var(--pamber);border-left:3px solid var(--amber);padding:10px 14px;border-radius:0 8px 8px 0;font-size:13.5px;margin:12px 0}
.muted{color:var(--muted)} .small{font-size:12.5px}
.flow{display:flex;align-items:stretch;gap:0;flex-wrap:wrap;margin:8px 0 2px}
.flowbox{flex:1 1 150px;min-width:140px;border:1px solid var(--line);border-radius:9px;padding:10px 12px;background:var(--white);display:flex;flex-direction:column;justify-content:center}
.flowbox .n{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);font-weight:700}
.flowbox .t{font-weight:700;margin-top:2px}
.flowbox .d{font-size:12px;color:var(--muted);margin-top:3px}
.flowbox.gate{border-color:var(--amber);background:var(--pamber)}
.flowarrow{display:flex;align-items:center;color:var(--slate);font-size:20px;padding:0 8px}
.flowout{flex:1.2 1 160px;min-width:150px;display:flex;flex-direction:column;gap:5px;justify-content:center}
.flowout .o{border-radius:7px;padding:6px 10px;font-size:12.5px;font-weight:700;color:#fff}
@media(max-width:720px){.flowarrow{transform:rotate(90deg);padding:6px 0;justify-content:center;width:100%}}
.reasonline{font-size:12px;color:var(--muted);margin-top:4px}
.stagecard h3{margin-bottom:2px}
.stagecard .why{color:var(--muted);font-size:13px}
.examples{margin-top:8px;border-top:1px dashed var(--line);padding-top:7px}
.examples summary{cursor:pointer;color:var(--blue-d);font-weight:700;font-size:12.5px;list-style:none}
.examples summary::-webkit-details-marker{display:none}
.examples summary:before{content:'▸ ';color:var(--blue)}
.examples[open] summary:before{content:'▾ '}
.examples table{margin-top:7px;font-size:12px}
.examples td{vertical-align:top;white-space:normal;min-width:95px}
.examples td.desc{min-width:260px;max-width:420px}
.gategrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:9px;margin:12px 0}
.gatecheck{display:flex;gap:9px;align-items:flex-start;border:1px solid var(--line);border-radius:8px;padding:10px;background:var(--white)}
.gatecheck input{margin-top:3px;accent-color:var(--blue)}
.gatecheck .stage{font-size:11px;color:var(--muted);display:block}
.simresult{border-left:4px solid var(--blue);padding-left:14px}
.btn{font:600 13px/1 inherit;border:1px solid var(--line);border-radius:7px;background:var(--white);color:var(--ink);padding:8px 11px;cursor:pointer}
.btn:hover{border-color:var(--blue);color:var(--blue-d)}
.btn.primary{background:var(--blue);color:#fff;border-color:var(--blue)}
.notearea{width:100%;min-height:150px;border:1px solid var(--line);border-radius:8px;padding:10px;font:13px/1.45 ui-monospace,SFMono-Regular,Consolas,monospace;color:var(--ink);background:var(--paper)}
.status{font-size:12px;color:var(--green);min-height:18px;margin-top:5px}
.foot{color:var(--muted);font-size:12px;margin-top:30px;border-top:1px solid var(--line);padding-top:14px}
code{background:var(--paper);border:1px solid var(--line);border-radius:4px;padding:1px 5px;font-size:12.5px}
</style>
</head>
<body>
<header class="hero"><div class="wrap">
  <h1>Recall Funnel Dashboard</h1>
  <div class="sub">A plain-language, traceable view of the surgical import-data enrichment pipeline:
   what each step does, how much data is <b>kept</b> versus <b>lost</b> after every step, and where recall is lost — and can be recovered. Review-only.</div>
  <div class="meta">Authority: prediction_audit.sqlite · run <b>__RUN__</b> · registry __REG__ · generated __GEN__</div>
</div></header>

<nav class="tabs"><div class="wrap" id="tabnav"></div></nav>

<div class="wrap">
  <div id="scopebanner"></div>
  <section class="tab" id="tab-overview"></section>
  <section class="tab" id="tab-funnel"></section>
  <section class="tab" id="tab-simulator"></section>
  <section class="tab" id="tab-breakdown"></section>
  <section class="tab" id="tab-hotspots"></section>
  <section class="tab" id="tab-recovery"></section>
  <section class="tab" id="tab-steps"></section>
  <section class="tab" id="tab-glossary"></section>
  <div class="foot" id="foot"></div>
</div>

<script>
const DATA = __PAYLOAD__;
const TIERK = {Trusted:'T',Review:'R',Excluded:'E'};
const METRICS = [
  {key:'tx', i:0, label:'Transactions'},
  {key:'val',i:1, label:'Value (USD)'},
  {key:'vol',i:2, label:'Volume (units)'},
];
const state = {tab:'overview', scope:'ALL', metric:1, dim:'segment', step:'', mode:'population', hideUnmapped:false,
  enabledGates:Object.fromEntries(DATA.simulator.gates.map(g=>[g.key,true]))};

// ---- formatting -----------------------------------------------------------
const nf = new Intl.NumberFormat('en-US');
function fmtInt(n){return nf.format(Math.round(n||0));}
function fmtMoney(n){n=n||0;const a=Math.abs(n);
  if(a>=1e9)return '$'+(n/1e9).toFixed(2)+'B';
  if(a>=1e6)return '$'+(n/1e6).toFixed(1)+'M';
  if(a>=1e3)return '$'+(n/1e3).toFixed(0)+'k';
  return '$'+fmtInt(n);}
function fmtVol(n){n=n||0;const a=Math.abs(n);
  if(a>=1e9)return (n/1e9).toFixed(2)+'B';
  if(a>=1e6)return (n/1e6).toFixed(1)+'M';
  if(a>=1e3)return (n/1e3).toFixed(0)+'k';
  return fmtInt(n);}
function fmtM(arr){const m=state.metric;const v=arr?arr[m]:0;return m===0?fmtInt(v):m===1?fmtMoney(v):fmtVol(v);}
function mv(arr){return arr?(arr[state.metric]||0):0;}
function pct(a,b){if(!b)return '0%';return (100*a/b).toFixed(a/b<0.1?1:0)+'%';}
function esc(s){return (s==null?'':String(s)).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function metricName(){return METRICS[state.metric].label;}
function madd(a,b){return [0,1,2].map(i=>(a?.[i]||0)+(b?.[i]||0));}
function msum(rows,key='m'){return rows.reduce((a,r)=>madd(a,r[key]||[0,0,0]),[0,0,0]);}

// ---- concrete row examples ----------------------------------------------
function exampleIdsForCell(stage,reason){
  const files=state.scope==='ALL'?DATA.files.map(f=>f.id):[state.scope];let out=[];
  files.forEach(fid=>{const st=(DATA.examples.cells[fid]||{})[stage]||{};
    if(reason!=null)out=out.concat(st[reason]||[]);else Object.values(st).forEach(ids=>out=out.concat(ids));});
  return uniqExamples(out,10);
}
function uniqExamples(ids,cap=10){const seen=new Set();return ids.filter(id=>{const k=String(id);if(seen.has(k)||!DATA.examples.rows[k])return false;seen.add(k);return true;})
  .sort((a,b)=>(DATA.examples.rows[String(b)].value||0)-(DATA.examples.rows[String(a)].value||0)).slice(0,cap);}
function exampleTable(ids){const use=uniqExamples(ids,10);if(!use.length)return '<p class="small muted">No sampled rows for this slice.</p>';
  return `<div class="scroll"><table><thead><tr><th>Description</th><th>Maker</th><th>Family</th><th>Mapped product</th><th>Segment</th><th>Value</th><th>QA status</th><th>Source</th></tr></thead><tbody>${use.map(id=>{const r=DATA.examples.rows[String(id)];return `<tr><td class="desc">${esc(r.description)}</td><td>${esc(r.maker)}</td><td>${esc(r.family)}</td><td>${esc(r.product)}</td><td>${esc(r.segment)}</td><td>${fmtMoney(r.value)}</td><td>${esc(r.qa)}</td><td>${esc(r.file)} row ${fmtInt(r.source_row)}</td></tr>`;}).join('')}</tbody></table></div>`;}
function exampleDetails(ids,label='Show concrete examples'){const use=uniqExamples(ids,10);return `<details class="examples"><summary>${esc(label)} (${use.length})</summary>${exampleTable(use)}</details>`;}

function scopes(){return [{id:'ALL',label:'All markets (combined)'}].concat(DATA.files.map(f=>({id:f.id,label:f.label})));}

// ---- controls -------------------------------------------------------------
function scopeSelect(){
  return '<label>Market-year</label><select onchange="state.scope=this.value;render()">'+
    scopes().map(s=>`<option value="${s.id}" ${s.id===state.scope?'selected':''}>${esc(s.label)}</option>`).join('')+'</select>';
}
function metricSeg(){
  return '<div><label>Measure</label><div class="seg">'+METRICS.map(m=>
    `<button class="${m.i===state.metric?'active':''}" onclick="state.metric=${m.i};render()">${m.label}</button>`).join('')+'</div></div>';
}

// ---- TAB: overview --------------------------------------------------------
function renderOverview(){
  const F=DATA.funnel[state.scope]; const tot=F.total;
  const T=F.trusted,R=F.review,E=F.excluded;
  const el=document.getElementById('tab-overview');
  const bar=stack3(T,R,E,tot);
  // top 2 loss reasons across steps
  const reasons=[];
  F.steps.forEach(s=>s.reasons.forEach(r=>reasons.push({stage:s.short,stageid:s.stage,reason:r.reason,tier:r.tier,m:r.m})));
  reasons.sort((a,b)=>b.m[1]-a.m[1]);
  const lostVal=R[1]+E[1];
  const top=reasons.slice(0,2);
  el.innerHTML=`
  <div class="card">
    <h2>The workflow at a glance</h2>
    <div class="flow">
      <div class="flowbox"><span class="n">Step 1</span><span class="t">Load</span><span class="d">every shipment row from the source file</span></div>
      <div class="flowarrow">&#8594;</div>
      <div class="flowbox"><span class="n">Step 2</span><span class="t">Match to master</span><span class="d">brand/model &#8594; category &#8594; maker</span></div>
      <div class="flowarrow">&#8594;</div>
      <div class="flowbox gate"><span class="n">Steps 3&#8211;6 &#9888;</span><span class="t">Quality gates</span><span class="d">reference-master check &#9888; · scope &amp; imaging guards &#9888;</span></div>
      <div class="flowarrow">&#8594;</div>
      <div class="flowout">
        <span class="o bg-T">&#10003; Trusted &#8212; ready to use</span>
        <span class="o bg-R">&#9679; Review &#8212; recall backlog</span>
        <span class="o bg-E">&#10007; Excluded &#8212; out of scope</span>
      </div>
    </div>
    <p class="small muted" style="margin-top:6px">&#9888; marks the two steps where most recall is lost (see <b>Recall hotspots</b>). Every row ends in exactly one bucket — nothing is deleted.</p>
  </div>
  <div class="card">
    <h2>Start here — what this pipeline produces</h2>
    <p>Every shipment row from the customs source is read, then matched against a curated surgical brand/model master and pushed through a
    series of quality gates. Each row ends in exactly one of three buckets. <b>Nothing is ever deleted</b> — lower-confidence rows are parked, not lost.</p>
    <div class="grid g3">
      ${tierCard('Trusted',T,tot)}
      ${tierCard('Review',R,tot)}
      ${tierCard('Excluded',E,tot)}
    </div>
    <div style="margin-top:14px">
      <div class="legend"><span><span class="dot bg-T"></span>Trusted</span><span><span class="dot bg-R"></span>Review</span><span><span class="dot bg-E"></span>Excluded</span>
      <span class="muted">· share of ${metricName().toLowerCase()} · ${esc(scopeLabel())}</span></div>
      ${bar}
    </div>
    <div class="controls" style="margin-top:14px">${scopeSelect()}${metricSeg()}</div>
  </div>

  <div class="card">
    <h2>How to use each bucket</h2>
    <div class="grid g3">
      ${DATA.tiers.map(t=>`<div><div class="pill ${TIERK[t]}">${t}</div><h3 style="margin-top:8px">${esc(DATA.tier_plain[t].short)}</h3><p class="small muted">${esc(DATA.tier_plain[t].text)}</p></div>`).join('')}
    </div>
  </div>

  <div class="card">
    <h2>Where recall is lost — the short answer</h2>
    <p>Of the ${fmtMoney(tot[1])} entering, <b>${fmtMoney(T[1])}</b> is Trusted and <b class="tier-R">${fmtMoney(lostVal)}</b> is held back (Review + Excluded).
    Two production gates account for most of that:</p>
    <table style="margin-top:6px"><thead><tr><th>Gate (step)</th><th>Why held back</th><th>Transactions</th><th>Value</th><th>Share of held-back value</th></tr></thead><tbody>
    ${top.map(r=>`<tr><td><b>${esc(r.stage)}</b></td><td class="muted">${esc(prettyReason(r.reason))}</td><td>${fmtInt(r.m[0])}</td><td>${fmtMoney(r.m[1])}</td><td>${pct(r.m[1],lostVal)}</td></tr>`).join('')}
    </tbody></table>
    <div class="note">Open <b>Recall hotspots</b> for the full ranking and the safe recovery levers, or <b>The funnel</b> to see the step-by-step drop-off.</div>
  </div>`;
}
function scopeLabel(){const s=scopes().find(x=>x.id===state.scope);return s?s.label:state.scope;}
function tierCard(t,arr,tot){const k=TIERK[t];
  return `<div class="card tight"><div class="kpi"><span class="l tier-${k}">${t}</span>
    <span class="n">${fmtMoney(arr[1])}</span>
    <span class="s">${fmtInt(arr[0])} rows · ${pct(arr[1],tot[1])} of value</span></div></div>`;}
function stack3(T,R,E,tot){const tv=Math.max(mv(tot),1);
  const seg=(arr,cls)=>{const w=100*mv(arr)/tv;return w>0?`<span class="${cls}" style="width:${w}%" title="${fmtM(arr)}"></span>`:'';};
  return `<div class="stackbar">${seg(T,'bg-T')}${seg(R,'bg-R')}${seg(E,'bg-E')}</div>
    <div class="legend"><span class="tier-T">Trusted ${fmtM(T)} (${pct(mv(T),mv(tot))})</span>
    <span class="tier-R">Review ${fmtM(R)} (${pct(mv(R),mv(tot))})</span>
    <span class="tier-E">Excluded ${fmtM(E)} (${pct(mv(E),mv(tot))})</span></div>`;}

// ---- TAB: funnel ----------------------------------------------------------
function renderFunnel(){
  const F=DATA.funnel[state.scope];const tot=F.total;const tv=Math.max(mv(tot),1);
  const el=document.getElementById('tab-funnel');
  let steps='';
  F.steps.forEach(s=>{
    const lost=mv(s.lost),ent=mv(s.entering),ret=mv(s.retained);
    const zero=lost<=0;
    const wEnter=100*ent/tv;
    const wRet=ent>0?100*ret/ent:0, wRev=ent>0?100*mv(s.lost_review)/ent:0, wExc=ent>0?100*mv(s.lost_excluded)/ent:0;
    steps+=`<div class="funnelstep ${zero?'zero':''}">
      <div class="top"><span class="name">${esc(s.stage)} · ${esc(s.short)}</span>
        <span class="small muted">${zero?'passes everything through':`− ${fmtM(s.lost)} lost (${pct(lost,ent)} of entering)`}</span></div>
      ${zero?'':`<div class="plain">${esc((DATA.stage_plain[s.stage]||{}).what||'')}</div>`}
      <div class="funnelbar" style="width:${Math.max(wEnter,2)}%" title="entering ${fmtM(s.entering)}">
        <span class="bg-T" style="width:${wRet}%" title="Continues (Trusted path): ${fmtM(s.retained)}"></span>
        <span class="bg-R" style="width:${wRev}%" title="Leaves → Review: ${fmtM(s.lost_review)}"></span>
        <span class="bg-E" style="width:${wExc}%" title="Leaves → Excluded: ${fmtM(s.lost_excluded)}"></span>
      </div>
      ${zero?'':`<div class="numgrid">
        <span>Entering: <b>${fmtM(s.entering)}</b></span>
        <span class="tier-R">→ Review: <b>${fmtM(s.lost_review)}</b></span>
        <span class="tier-E">→ Excluded: <b>${fmtM(s.lost_excluded)}</b></span>
        <span class="tier-T">Continues: <b>${fmtM(s.retained)}</b> (${pct(ret,tv)} of start)</span>
      </div>
      ${s.reasons.length?`<div class="reasonline">Reasons: ${s.reasons.map(r=>`${esc(prettyReason(r.reason))} <span class="pill ${TIERK[r.tier]}">${r.tier[0]}</span> ${fmtM(r.m)}`).join(' · ')}</div>`:''}`}
      ${zero?'':exampleDetails(exampleIdsForCell(s.stage),`Show rows held back at ${s.short}`)}
    </div>`;
  });
  el.innerHTML=`
  <div class="card">
    <h2>The recall funnel — step by step</h2>
    <p class="muted">Read top to bottom. Each green bar is the data still on the <b>Trusted</b> path <i>entering</i> that step; the amber/red tail is what leaves at that step (to Review / Excluded). Bars shrink as the funnel narrows. Attribution is <b>additive</b> — every row is counted once, at the single step where it left the Trusted path.</p>
    <div class="controls">${scopeSelect()}${metricSeg()}</div>
    <div class="legend"><span><span class="dot bg-T"></span>Continues (Trusted path)</span><span><span class="dot bg-R"></span>Leaves → Review</span><span><span class="dot bg-E"></span>Leaves → Excluded</span></div>
  </div>
  <div class="card">
    <div class="funnelstep" style="background:var(--pblue);border-color:var(--blue)">
      <div class="top"><span class="name">Start · all extracted rows</span><span class="small muted">${fmtM(tot)} · ${esc(scopeLabel())}</span></div>
    </div>
    ${steps}
    <div class="funnelstep" style="background:var(--pgreen);border-color:var(--green)">
      <div class="top"><span class="name tier-T">End · Trusted</span><span class="small"><b>${fmtM(F.trusted)}</b> — ${pct(mv(F.trusted),tv)} of start kept</span></div>
    </div>
  </div>
  ${state.scope==='ALL'?`<div class="warn"><b>Reading the combined view:</b> India FY2025 is loaded from the complete CSV and attributes its held-back rows at <code>Final routing</code> (Unmapped / manufacturer-only) rather than at Reference validation, because that source lacks reference-status columns. Per-file views are cleaner — switch the market selector above.</div>`:''}`;
}

// ---- TAB: what-if gate simulator ----------------------------------------
function simForFiles(fileIds){
  const groups=DATA.simulator.groups.filter(g=>fileIds.includes(g.file));
  const baseline=msum(fileIds.map(fid=>({m:DATA.funnel[fid].trusted})));
  const locked=msum(fileIds.map(fid=>({m:(DATA.simulator.locked[fid]||{}).m||[0,0,0]})));
  const enabledMask=DATA.simulator.gates.reduce((m,g)=>m+(state.enabledGates[g.key]?g.bit:0),0);
  let direct=[0,0,0],still=[0,0,0],released=[0,0,0];const directIds=[],releasedIds=[];const heldBy={};
  DATA.simulator.gates.forEach(g=>heldBy[g.key]={m:[0,0,0],ids:[]});
  groups.forEach(gr=>{
    if(state.enabledGates[gr.gate])return;
    released=madd(released,gr.m);releasedIds.push(...(gr.examples||[]));
    const remaining=gr.mask&enabledMask;
    if(!remaining){direct=madd(direct,gr.m);directIds.push(...(gr.examples||[]));return;}
    const catchGate=DATA.simulator.gates.find(g=>(remaining&g.bit)!==0);
    if(catchGate){heldBy[catchGate.key].m=madd(heldBy[catchGate.key].m,gr.m);heldBy[catchGate.key].ids.push(...(gr.examples||[]));still=madd(still,gr.m);}
  });
  return {groups,baseline,locked,direct,still,released,heldBy,directIds:uniqExamples(directIds,10),releasedIds:uniqExamples(releasedIds,10)};
}
function simResult(){const ids=state.scope==='ALL'?DATA.files.map(f=>f.id):[state.scope];return simForFiles(ids);}
function setAllGates(on){DATA.simulator.gates.forEach(g=>state.enabledGates[g.key]=on);render();}
function gateChecks(){return DATA.simulator.gates.map(g=>`<label class="gatecheck"><input type="checkbox" data-gate="${esc(g.key)}" ${state.enabledGates[g.key]?'checked':''} onchange="state.enabledGates['${esc(g.key)}']=this.checked;render()"><span><b>${esc(g.label)}</b><span class="stage">${esc(g.stage)} · ${state.enabledGates[g.key]?'ON — production-like':'OFF — test release'}</span></span></label>`).join('');}
function simFileRows(){return DATA.files.filter(f=>state.scope==='ALL'||f.id===state.scope).map(f=>{const r=simForFiles([f.id]);const sim=madd(r.baseline,r.direct);return `<tr><td>${esc(f.label)}</td><td>${fmtM(r.baseline)}</td><td class="tier-T">${fmtM(sim)}</td><td class="tier-T">+ ${fmtM(r.direct)}</td><td class="tier-R">${fmtM(r.still)}</td><td>${fmtM(r.locked)}</td></tr>`;}).join('');}
function simNoteText(){const r=simResult();const off=DATA.simulator.gates.filter(g=>!state.enabledGates[g.key]);const ex=r.directIds.slice(0,5).map(id=>{const x=DATA.examples.rows[String(id)];return `- ${x.file} row ${x.source_row}: ${x.description} | maker=${x.maker} | family=${x.family} | product=${x.product} | value=${fmtMoney(x.value)}`;});
  return `What-if adjudication request — REVIEW ONLY\nScope: ${scopeLabel()}\nGate(s) tested as off: ${off.length?off.map(g=>g.label).join(', '):'none (production-like baseline)'}\n\nI think ${off.length?off.map(g=>g.label).join(' / '):'the current gates'} may be too strict for this slice. The simulator estimates ${fmtInt(r.direct[0])} rows / ${fmtMoney(r.direct[1])} would clear directly; ${fmtInt(r.still[0])} rows / ${fmtMoney(r.still[1])} would likely still be held by another enabled gate.\n\nExamples that clear all enabled gates:\n${ex.length?ex.join('\n'):'- None in this toggle state'}\n\nRequested next step: adjudicate these examples in Recall_Recovery_Proposals.xlsx (or the governed review workbook), record the business rationale, then apply any approved change through reference/ and a governed rerun. This simulation does not change production.`;}
function copySimNote(){const t=simNoteText();const done=()=>document.getElementById('sim-status').textContent='Copied adjudication note.';if(navigator.clipboard&&window.isSecureContext)navigator.clipboard.writeText(t).then(done).catch(()=>fallbackCopy(t,done));else fallbackCopy(t,done);}
function fallbackCopy(t,done){const a=document.createElement('textarea');a.value=t;document.body.appendChild(a);a.select();document.execCommand('copy');a.remove();done();}
function downloadSimNote(){const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([simNoteText()],{type:'text/plain'}));a.download='Recall_Gate_What_If_Note.txt';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);document.getElementById('sim-status').textContent='Downloaded adjudication note.';}
function renderSimulator(){
  const el=document.getElementById('tab-simulator');const r=simResult();const simulated=madd(r.baseline,r.direct);const disabled=DATA.simulator.gates.filter(g=>!state.enabledGates[g.key]);
  const heldRows=DATA.simulator.gates.map(g=>({g,x:r.heldBy[g.key]})).filter(x=>x.x.m[0]>0);
  const locked=(DATA.simulator.locked[state.scope]||r).m||r.locked;const lockedReasons=(DATA.simulator.locked[state.scope]||{}).reasons||[];
  el.innerHTML=`<div class="card"><h2>What-if gate playground</h2>
    <div class="warn"><b>Discussion simulator — not production.</b> Turning a gate off changes only this page. Recovery dynamics and downstream remapping are not modelled. Any useful insight must go through analyst adjudication, governed <code>reference/</code> changes, a rerun, and re-audit.</div>
    <div class="controls">${scopeSelect()}${metricSeg()}<button class="btn" onclick="setAllGates(true)">Reset: all gates on</button><button class="btn" onclick="setAllGates(false)">Test: all gates off</button></div>
    <p class="small muted">Checked = gate remains active. Uncheck one or more gates to ask which rows could move toward Trusted. Each non-Trusted row has one primary blocking gate; secondary rule hits show which other enabled gate would likely still hold it.</p>
    <div class="gategrid">${gateChecks()}</div></div>

  <div class="card simresult"><h2>Simulated result · ${esc(scopeLabel())}</h2>
    <div class="grid g3"><div class="kpi"><span class="l">Baseline Trusted</span><span class="n">${fmtM(r.baseline)}</span><span class="s">all production gates on</span></div>
      <div class="kpi"><span class="l tier-T">Simulated Trusted</span><span class="n tier-T">${fmtM(simulated)}</span><span class="s">baseline + rows clearing every enabled gate</span></div>
      <div class="kpi"><span class="l tier-R">Likely held elsewhere</span><span class="n tier-R">${fmtM(r.still)}</span><span class="s">released by primary gate, caught by another</span></div></div>
    <div class="numgrid"><span>Primary-gate release pool: <b>${fmtM(r.released)}</b></span><span class="tier-T">Flows directly to Trusted: <b>${fmtM(r.direct)}</b></span><span class="tier-R">Likely caught by another gate: <b>${fmtM(r.still)}</b></span></div>
    ${exampleDetails(r.directIds,'Show examples that clear all enabled gates')}
  </div>

  ${heldRows.length?`<div class="card"><h3>Where released rows would likely be caught next</h3><p class="small muted">Exclusive split: if several secondary gates hit, the first enabled gate in pipeline order receives the row, so totals do not double-count.</p><table><thead><tr><th>Likely next gate</th><th>Transactions</th><th>Value</th><th>Volume</th><th>Examples</th></tr></thead><tbody>${heldRows.map(({g,x})=>`<tr><td>${esc(g.label)}</td><td>${fmtInt(x.m[0])}</td><td>${fmtMoney(x.m[1])}</td><td>${fmtVol(x.m[2])}</td><td>${exampleDetails(x.ids,'Show')}</td></tr>`).join('')}</tbody></table></div>`:''}

  <div class="card"><h3>Per-file reconciliation</h3><div class="scroll"><table><thead><tr><th>Market-year</th><th>Baseline Trusted</th><th>Simulated Trusted</th><th>Direct gain</th><th>Still held elsewhere</th><th>Locked / not toggleable</th></tr></thead><tbody>${simFileRows()}</tbody></table></div></div>

  <div class="card"><h3>Locked coverage and attribution blocks</h3><p><b>S13 Final routing is shown but cannot be toggled.</b> These rows are coverage gaps or an audit-source attribution artifact, not a single production gate that can honestly be switched off.</p><div class="numgrid"><span>Locked here: <b>${fmtM(locked)}</b></span></div>${lockedReasons.length?`<table><thead><tr><th>Reason</th><th>Rows</th><th>Value</th></tr></thead><tbody>${lockedReasons.map(x=>`<tr><td>${esc(prettyReason(x.reason))}</td><td>${fmtInt(x.m[0])}</td><td>${fmtMoney(x.m[1])}</td></tr>`).join('')}</tbody></table>`:''}<div class="warn small"><b>India FY2025 caveat:</b> its audit source lacks reference-status columns, so many losses appear at S13 rather than S07. They are visible here but intentionally locked until the next audit carries those fields.</div></div>

  <div class="card"><h2>Turn an insight into an analyst request</h2><p>Use the gate guidance below, then copy or download a traceable note. Review proposed rows in <a href="Recall_Recovery_Proposals.xlsx">Recall_Recovery_Proposals.xlsx</a>; leave <code>Approved</code> blank until a business reviewer decides.</p>
    <div class="grid g2">${DATA.simulator.gates.map(g=>`<div class="card tight"><h3>${esc(g.label)}</h3><p class="small">${esc(g.guidance)}</p><span class="pill ${state.enabledGates[g.key]?'T':'R'}">${state.enabledGates[g.key]?'currently on':'being tested off'}</span></div>`).join('')}</div>
    <textarea class="notearea" readonly>${esc(simNoteText())}</textarea><div class="controls"><button class="btn primary" onclick="copySimNote()">Copy adjudication note</button><button class="btn" onclick="downloadSimNote()">Download note</button><a class="btn" href="../../docs/Surgical_Mapping_Workflow_Guide.html">Open adjudication workflow</a></div><div id="sim-status" class="status"></div></div>`;
}

// ---- TAB: breakdown -------------------------------------------------------
function renderBreakdown(){
  const el=document.getElementById('tab-breakdown');
  const dimOpts=DATA.dimensions.map(d=>`<option value="${d.key}" ${d.key===state.dim?'selected':''}>${esc(d.label)}</option>`).join('');
  const stepsWithLoss=Object.keys(DATA.loss_by_stage[state.scope]||{}).sort((a,b)=>(DATA.stage_order[a]||0)-(DATA.stage_order[b]||0));
  const stepOpts=stepsWithLoss.map(s=>`<option value="${s}" ${s===state.step?'selected':''}>${esc(s)} · ${esc((DATA.stage_plain[s]||{}).short||DATA.stage_label[s]||s)}</option>`).join('');
  const controls=`<div class="controls">
    ${scopeSelect()}
    <div><label>Break down by</label><select onchange="state.dim=this.value;render()">${dimOpts}</select></div>
    <div><label>View</label><div class="seg">
      <button class="${state.mode==='population'?'active':''}" onclick="state.mode='population';render()">Kept vs lost</button>
      <button class="${state.mode==='step'?'active':''}" onclick="state.mode='step';render()">Loss at one step</button></div></div>
    ${state.mode==='step'?`<div><label>Step</label><select onchange="state.step=this.value;render()"><option value="">— pick a step —</option>${stepOpts}</select></div>`:''}
    ${metricSeg()}
    <label class="chk"><input type="checkbox" ${state.hideUnmapped?'checked':''} onchange="state.hideUnmapped=this.checked;render()"> hide &lt;Unmapped&gt;</label>
  </div>
  <p class="small muted" style="margin:2px 0 0"><b>&lt;Unmapped&gt;</b> = never matched any product (a coverage gap); <b>Unspecified</b> = matched, but this dimension was left blank. They are different — tick “hide &lt;Unmapped&gt;” to see the mapped population only.</p>`;

  let body='';
  if(state.mode==='population'){
    let rows=(DATA.population[state.scope]||{})[state.dim]||[];
    if(state.hideUnmapped)rows=rows.filter(r=>r.label!=='<Unmapped>');
    rows=rows.map(r=>({...r,tot:r.T[state.metric]+r.R[state.metric]+r.E[state.metric]})).sort((a,b)=>b.tot-a.tot);
    const maxTot=Math.max(1,...rows.map(r=>r.tot));
    body=`<div class="card"><h2>Kept vs lost by ${esc(dimLabel())}</h2>
      <p class="muted">Each bar is one ${esc(dimLabel().toLowerCase())} slice, split into Trusted / Review / Excluded ${metricName().toLowerCase()}. The green share is the recall rate for that slice.</p>
      <div class="legend"><span><span class="dot bg-T"></span>Trusted</span><span><span class="dot bg-R"></span>Review</span><span><span class="dot bg-E"></span>Excluded</span></div>
      <div class="scroll">${rows.map(r=>{
        const w=100*r.tot/maxTot;const tv=Math.max(r.tot,1);
        const seg=(a,c)=>{const x=100*a[state.metric]/tv;return x>0?`<span class="${c}" style="width:${x}%"></span>`:'';};
        return `<div class="barrow"><div class="lab" title="${esc(r.label)}">${esc(r.label)}</div>
          <div class="bar"><div class="stackbar" style="width:${Math.max(w,1)}%">${seg(r.T,'bg-T')}${seg(r.R,'bg-R')}${seg(r.E,'bg-E')}</div></div>
          <div class="val">${fmtM([r.tot,r.tot,r.tot].map((_,i)=>i===state.metric?r.tot:0))}<span class="muted"> · ${pct(r.T[state.metric],r.tot)} kept</span></div></div>`;
      }).join('')||'<p class="muted">No data.</p>'}</div>
      ${tableToggle('pop')}
      <div id="pop-table" style="display:none">${popTable(rows)}</div>
    </div>`;
  } else {
    if(!state.step){body=`<div class="card"><p class="muted">Pick a step above to see where its held-back ${metricName().toLowerCase()} concentrates.</p></div>`;}
    else{
      let rows=((DATA.loss_by_stage[state.scope]||{})[state.step]||{})[state.dim]||[];
      if(state.hideUnmapped)rows=rows.filter(r=>r.label!=='<Unmapped>');
      rows=rows.slice().sort((a,b)=>b.m[state.metric]-a.m[state.metric]);
      const total=rows.reduce((s,r)=>s+r.m[state.metric],0);
      const maxV=Math.max(1,...rows.map(r=>r.m[state.metric]));
      body=`<div class="card"><h2>${esc(state.step)} · ${esc((DATA.stage_plain[state.step]||{}).short||'')} — losses by ${esc(dimLabel())}</h2>
        <p class="muted">${esc((DATA.stage_plain[state.step]||{}).what||'')} Showing held-back ${metricName().toLowerCase()} attributed to this step.</p>
        <div class="scroll">${rows.map(r=>{
          const w=100*r.m[state.metric]/maxV;
          return `<div class="barrow"><div class="lab" title="${esc(r.label)}">${esc(r.label)}</div>
            <div class="bar"><div class="stackbar" style="width:${Math.max(w,1)}%"><span class="bg-R" style="width:100%"></span></div></div>
            <div class="val">${fmtM(r.m)}<span class="muted"> · ${pct(r.m[state.metric],total)}</span></div></div>`;
        }).join('')||'<p class="muted">No losses at this step for this slice.</p>'}</div>
      </div>`;
    }
  }
  el.innerHTML=controls+body;
}
function dimLabel(){const d=DATA.dimensions.find(x=>x.key===state.dim);return d?d.label:state.dim;}
function tableToggle(id){return `<button class="seg" style="margin-top:10px;padding:6px 10px;border-radius:8px;cursor:pointer;background:var(--white);border:1px solid var(--line)" onclick="var t=document.getElementById('${id}-table');t.style.display=t.style.display==='none'?'block':'none'">Show / hide data table</button>`;}
function popTable(rows){
  return `<div class="scroll"><table><thead><tr><th>${esc(dimLabel())}</th>
   <th>Trusted</th><th>Review</th><th>Excluded</th><th>Total</th><th>Recall %</th></tr></thead><tbody>
   ${rows.map(r=>`<tr><td>${esc(r.label)}</td><td class="tier-T">${fmtM(r.T)}</td><td class="tier-R">${fmtM(r.R)}</td><td class="tier-E">${fmtM(r.E)}</td><td>${fmtM([r.tot,r.tot,r.tot].map((_,i)=>i===state.metric?r.tot:0))}</td><td>${pct(r.T[state.metric],r.tot)}</td></tr>`).join('')}
   </tbody></table></div>`;
}

// ---- TAB: hotspots --------------------------------------------------------
function renderHotspots(){
  const el=document.getElementById('tab-hotspots');
  const F=DATA.funnel[state.scope];const lostVal=F.review[1]+F.excluded[1];
  const reasons=[];
  F.steps.forEach(s=>s.reasons.forEach(r=>reasons.push({stage:s.stage,short:s.short,reason:r.reason,tier:r.tier,m:r.m})));
  reasons.sort((a,b)=>b.m[1]-a.m[1]);
  // cumulative share
  let cum=0;const rrows=reasons.map(r=>{cum+=r.m[1];return {...r,cum};});
  // per-file summary
  const perFile=DATA.files.map(f=>{
    const ff=DATA.funnel[f.id];const lv=ff.review[1]+ff.excluded[1];
    const rs=[];ff.steps.forEach(s=>s.reasons.forEach(x=>rs.push({stage:s.short,reason:x.reason,v:x.m[1]})));
    rs.sort((a,b)=>b.v-a.v);const t=rs[0]||{stage:'—',reason:'',v:0};
    return {label:f.label,trusted:ff.trusted[1],lost:lv,top:t};
  });
  el.innerHTML=`
  <div class="card">
    <h2>Recall hotspots — which steps hurt most</h2>
    <div class="controls">${scopeSelect()}</div>
    <p class="muted">Ranked by held-back <b>value</b> for ${esc(scopeLabel())}. Total held back: <b class="tier-R">${fmtMoney(lostVal)}</b> across ${fmtInt(F.review[0]+F.excluded[0])} rows.</p>
    <div class="scroll"><table><thead><tr><th>#</th><th>Step</th><th>Reason held back</th><th>To</th><th>Transactions</th><th>Value</th><th>Share</th><th>Cumulative</th><th>Examples</th></tr></thead><tbody>
    ${rrows.map((r,i)=>`<tr><td>${i+1}</td><td><b>${esc(r.stage)}</b> <span class="muted small">${esc(r.short)}</span></td><td class="muted">${esc(prettyReason(r.reason))}</td><td><span class="pill ${TIERK[r.tier]}">${r.tier}</span></td><td>${fmtInt(r.m[0])}</td><td>${fmtMoney(r.m[1])}</td><td>${pct(r.m[1],lostVal)}</td><td>${pct(r.cum,lostVal)}</td><td>${exampleDetails(exampleIdsForCell(r.stage,r.reason),'Show')}</td></tr>`).join('')}
    </tbody></table></div>
  </div>

  <div class="card">
    <h2>The two dominant steps &amp; how to recover recall safely</h2>
    <div class="grid g2">
      <div class="card tight" style="border-left:3px solid var(--amber)">
        <h3>1 · Reference-master validation (S07)</h3>
        <p class="small">By far the largest drain: a mapped product is held back when its <b>Segment × Sub-segment × Product</b> tuple is not yet in the governed master.</p>
        <p class="small"><b>Safe recovery:</b> many are <i>loose matches</i> (spacing/punctuation) or real surgical products simply missing from the master. Surface the high-value ones, adjudicate, add to <code>reference/</code>, and rerun. This is the biggest recall lever and does not weaken precision.</p>
      </div>
      <div class="card tight" style="border-left:3px solid var(--red)">
        <h3>2 · Ophthalmic / imaging guard (S12)</h3>
        <p class="small">The final precision guard flags rows that read as ophthalmic/imaging equipment unless they carry strong independent surgical evidence (e.g. MRI-conditional implants). Genuine surgical products with that evidence still pass.</p>
        <p class="small"><b>Safe recovery:</b> review whether genuine surgical products (e.g. MRI-conditional implants) are being caught by a stray imaging keyword, and refine the scope whitelist. Smaller lever than S07, and needs care to protect precision.</p>
      </div>
    </div>
    <div class="note">Recovery is <b>review-only</b> here — surface the opportunity, then run it through the normal adjudication → <code>reference/</code> → governed rerun loop. The <b>Review</b> bucket is the working backlog; prioritise by value in the Breakdowns tab.</div>
  </div>

  <div class="card">
    <h2>Per-file recall snapshot</h2>
    <div class="scroll"><table><thead><tr><th>Market-year</th><th>Trusted value</th><th>Held-back value</th><th>Kept %</th><th>Biggest single drain</th></tr></thead><tbody>
    ${perFile.map(f=>`<tr><td>${esc(f.label)}</td><td class="tier-T">${fmtMoney(f.trusted)}</td><td class="tier-R">${fmtMoney(f.lost)}</td><td>${pct(f.trusted,f.trusted+f.lost)}</td><td class="muted">${esc(f.top.stage)} — ${esc(prettyReason(f.top.reason))} (${fmtMoney(f.top.v)})</td></tr>`).join('')}
    </tbody></table></div>
  </div>`;
}

// ---- TAB: steps -----------------------------------------------------------
function renderSteps(){
  const el=document.getElementById('tab-steps');
  const F=DATA.funnel[state.scope];
  const byStage={};F.steps.forEach(s=>byStage[s.stage]=s);
  const order=Object.keys(DATA.stage_plain).sort((a,b)=>(DATA.stage_order[a]||0)-(DATA.stage_order[b]||0));
  el.innerHTML=`<div class="card"><h2>Every step, in plain language</h2>
    <div class="controls">${scopeSelect()}${metricSeg()}</div>
    <p class="muted">The pipeline runs these steps in order. "Held back here" counts rows attributed to this step (additive, no double-counting). Most filtering lands at Reference validation and the final guards by design.</p></div>
    ${order.map((sid,i)=>{const p=DATA.stage_plain[sid];const s=byStage[sid];
      const held=s?s.lost:[0,0,0];const heldAny=(held[1]||0)>0||(held[0]||0)>0;
      return `<div class="card stagecard"><h3>${i+1}. ${esc(sid)} · ${esc(p.short)}</h3>
        <p>${esc(p.what)}</p><p class="why"><b>Why:</b> ${esc(p.why)}</p>
        ${s?`<div class="numgrid"><span>Held back here: <b class="${heldAny?'tier-R':'muted'}">${heldAny?fmtM(held):'none'}</b></span>
          ${heldAny?`<span class="tier-R">Review ${fmtM(s.lost_review)}</span><span class="tier-E">Excluded ${fmtM(s.lost_excluded)}</span>`:''}</div>`:'<div class="numgrid"><span class="muted">Structural step — no rows leave here.</span></div>'}
      </div>`;}).join('')}`;
}

// ---- TAB: glossary --------------------------------------------------------
function renderGlossary(){
  const el=document.getElementById('tab-glossary');
  el.innerHTML=`
  <div class="card"><h2>Glossary &amp; how to read the numbers</h2>
   <div class="grid g2">
    <div><h3>The three buckets</h3><ul class="small">
      <li><b class="tier-T">Trusted</b> — passed every gate; use for the revenue dashboard.</li>
      <li><b class="tier-R">Review</b> — real evidence but a gate not cleared; the recall-recovery backlog.</li>
      <li><b class="tier-E">Excluded</b> — no accepted evidence or out of scope.</li></ul></div>
    <div><h3>Vocabulary in your terms</h3><ul class="small">
      <li><b>OU</b> = Segment · <b>Sub-OU</b> = Sub-segment · <b>Device</b> = Product</li>
      <li><b>Family</b> = brand/model family · <b>Manufacturer</b> = maker</li>
      <li><b>ASP</b> = value ÷ volume (weighted; blank when volume is 0)</li>
      <li><b>&lt;Unmapped&gt;</b> (never matched) is kept distinct from <b>Unspecified</b> (matched but dimension blank)</li></ul></div>
   </div></div>
  <div class="card"><h3>Measures</h3><ul class="small">
    <li><b>Transactions</b> — count of shipment rows.</li>
    <li><b>Value (USD)</b> — sum of valid Total_Value_USD.</li>
    <li><b>Volume (units)</b> — sum of valid Quantity.</li>
    <li>Rows with missing/invalid value or volume are still counted as transactions but contribute 0 to value/volume sums.</li></ul></div>
  <div class="card"><h3>Traceability</h3>
    <p class="small">Every number here is aggregated from the row-grain SQLite authority
    <code>outputs/${esc(DATA.run_id)}/prediction_audit.sqlite</code> (registry ${esc(String(DATA.registry_version))}).
    The additive funnel groups <code>row_fact</code> by <code>removal_stage_id</code> + <code>primary_reason</code>,
    so each row is attributed exactly once. This dashboard is <b>review-only</b>: it never changes production routing,
    reference lists, or published workbooks.</p></div>
  <div class="warn"><b>Attribution caveat (India FY2025):</b> loaded from the complete CSV, it attributes held-back rows at
   <code>Final routing</code> (Unmapped / manufacturer-only) instead of Reference validation, because the CSV lacks the
   reference-status columns the workbook files carry. Compare markets one at a time for the cleanest read.</div>`;
}

// ---- TAB: recovery --------------------------------------------------------
const SAFETY_CLS={'High confidence':'T','Medium — adjudicate first':'R','Lower — coverage work':'R','Lowest — new evidence needed':'E','Mostly correct exclusions':'E'};
function renderRecovery(){
  const el=document.getElementById('tab-recovery');
  const R=DATA.recovery[state.scope]; const meta=DATA.recovery_meta;
  const F=DATA.funnel[state.scope]; const heldRows=F.review[0]+F.excluded[0]; const heldVal=F.review[1]+F.excluded[1];
  const order=meta.order;
  const rows=order.map(b=>({id:b, ...meta.buckets[b], m:R.buckets[b]}));
  const maxV=Math.max(1,...rows.map(r=>r.m[1]));
  const bucketCards=rows.map(r=>{
    const cls=SAFETY_CLS[r.safety]||'R'; const w=100*r.m[1]/maxV;
    return `<div class="card tight" style="border-left:4px solid var(--${cls==='T'?'green':cls==='R'?'amber':'red'})">
      <div class="top" style="display:flex;justify-content:space-between;gap:10px;align-items:baseline">
        <h3 style="margin:0">${esc(r.label)}</h3><span class="pill ${cls}">${esc(r.safety)}</span></div>
      <div class="numgrid"><span><b>${fmtMoney(r.m[1])}</b> value</span><span>${fmtInt(r.m[0])} rows</span><span>${pct(r.m[1],heldVal)} of held-back value</span></div>
      <div class="stackbar" style="margin:6px 0"><span class="bg-${cls}" style="width:${Math.max(w,1)}%"></span></div>
      <p class="small muted" style="margin:4px 0 2px"><b>Signal:</b> ${esc(r.signal)}</p>
      <p class="small" style="margin:2px 0"><b>What we can do:</b> ${esc(r.action)}</p>
    </div>`;}).join('');
  el.innerHTML=`
  <div class="card">
    <h2>Can we recover recall — safely?</h2>
    <div class="controls">${scopeSelect()}</div>
    <p class="muted">We are <b>not</b> chasing recall aggressively. This splits the <b class="tier-R">${fmtMoney(heldVal)}</b> of held-back value
     (${fmtInt(heldRows)} rows) into buckets ordered by how <b>safe</b> recovery would be. Everything here is <b>review-only</b>: it points to work
     for the normal adjudication → <code>reference/</code> → governed-rerun loop; nothing is auto-applied.</p>
    <div class="grid g2" style="margin-top:6px">${bucketCards}</div>
  </div>
  ${s07CrossCheck(R,meta)}
  ${clusterCard('Safest first — mis-guarded surgical to whitelist','clusters_misguarded',['Family'],R)}
  ${clusterCard('Evidenced recovery candidates (family maps to one master category AND appears in the description)','clusters_loose',['Manufacturer','Family'],R,'Only description-evidenced clusters are shown (the family actually appears in the text). Still verify each in context before approving — a family word can appear coincidentally.',true)}
  ${clusterCard('Coverage work — manufacturer recognised, product missing','clusters_mfr',['Manufacturer'],R)}
  <div class="note">Suggested order of work: (1) whitelist the mis-guarded surgical families — highest confidence; (2) adjudicate the <b>“Clean”</b> loose-match clusters first (family maps to one specific master category); (3) add genuinely-missing products to the master; (4) plan lexicon expansion for the largest manufacturer-only makers. Track accepted decisions through the existing adjudication workbooks, then rerun and re-audit.</div>`;
}
function s07CrossCheck(R,meta){
  if(!meta.master_available || !R.s07_classes)return '';
  const order=meta.s07_class_order; const cls=R.s07_classes;
  const tot=order.reduce((s,k)=>s+(cls[k]?cls[k][1]:0),0);
  if(tot<=0)return '';
  const CLS_COLOR={clean_evidenced:'green',not_in_master:'blue',ambiguous_multi:'amber',ambiguous_generic:'red',clean_unevidenced:'slate'};
  const maxV=Math.max(1,...order.map(k=>cls[k]?cls[k][1]:0));
  return `<div class="card">
    <h3>Loose-match, cross-checked against the brand master</h3>
    <p class="small muted">The recognised-family pool (S07) split by what the master says <b>and</b> whether the family actually appears in the product description. Only the <b style="color:var(--green)">Safe lever</b> slice (maps to one master category AND is evidenced in the text) is a real recovery. The <b>Likely spurious</b> slice is a family match that is <i>not</i> in the description (e.g. a cataract lens tagged “Trauma Plates And Screws”) — this is why S07 held it back, and why we do not chase recall aggressively.</p>
    ${order.map(k=>{const m=cls[k]||[0,0,0];const w=100*m[1]/maxV;const col=CLS_COLOR[k]||'slate';
      return `<div class="barrow"><div class="lab" title="${esc(meta.s07_classes[k])}">${esc(meta.s07_classes[k].split(' — ')[0])}</div>
        <div class="bar"><div class="stackbar" style="width:${Math.max(w,1)}%"><span style="width:100%;background:var(--${col})"></span></div></div>
        <div class="val">${fmtMoney(m[1])}<span class="muted"> · ${pct(m[1],tot)} · ${fmtInt(m[0])} rows</span></div></div>`;}).join('')}
    <p class="small muted" style="margin-top:6px">${esc(meta.s07_classes.clean_evidenced)}.</p>
  </div>`;
}
const CLS_LABEL={clean_evidenced:'✓ Safe lever',not_in_master:'＋ Add to master',ambiguous_multi:'~ Ambiguous',ambiguous_generic:'⚠ Generic/date',clean_unevidenced:'✗ Likely spurious'};
const CLS_TXTCOL={clean_evidenced:'#12724a',not_in_master:'#16407f',ambiguous_multi:'#8a6410',ambiguous_generic:'#a12d2d',clean_unevidenced:'#5b6b82'};
function clusterCard(title,key,cols,R,warn,showMaster){
  const rows=(R[key]||[]);
  if(!rows.length)return '';
  const total=rows.reduce((s,r)=>s+r.m[1],0);
  const extra = showMaster ? '<th>Master check</th><th>Master category</th>' : '';
  return `<div class="card"><h3>${esc(title)}</h3>
    ${warn?`<div class="warn small">${esc(warn)}</div>`:''}
    <div class="scroll"><table><thead><tr>${cols.map(c=>`<th>${esc(c)}</th>`).join('')}${extra}<th>Transactions</th><th>Value</th><th>Share of shown</th><th>Examples</th></tr></thead><tbody>
    ${rows.map(r=>{const me=showMaster?`<td style="color:${CLS_TXTCOL[r.cls]||'inherit'}">${esc(CLS_LABEL[r.cls]||'')}</td><td class="small muted">${esc(r.mcat||'')}</td>`:'';
      return `<tr>${r.k.map(x=>`<td>${esc(x)}</td>`).join('')}${me}<td>${fmtInt(r.m[0])}</td><td>${fmtMoney(r.m[1])}</td><td>${pct(r.m[1],total)}</td><td>${exampleDetails(r.examples||[],'Show')}</td></tr>`;}).join('')}
    </tbody></table></div>
    <p class="small muted">Top ${rows.length} shown for ${esc(scopeLabel())}, ranked by value.</p></div>`;
}

// ---- reasons prettifier ---------------------------------------------------
const REASON_PRETTY={
  'reference_tuple_invalid':'Product not in the reference master',
  'ophthalmic_imaging_conflict':'Reads as ophthalmic / imaging equipment',
  'scope_exclusion':'Out-of-scope keyword (vet / dental / cosmetic / lab / imaging)',
  'Unmapped':'Never matched any product',
  'Audit - manufacturer only':'Only the manufacturer was recognised',
  'Review - unspecified category':'Category dimensions blank',
  'Review - not in latest reference':'Player/family absent from master',
  'Review - reference category conflict':'Exists under a different category',
  'Review - surgical product in Extended HS scope':'Surgical product outside core HS scope',
  'Review - generic-token mapping anomaly':'Generic token + capital-equipment description',
  'trusted_reference_valid_surgical':'Trusted',
  'generic_or_token_anomaly':'Generic / date-token anomaly',
  'extended_hs_false_positive_risk':'Extended-HS false-positive risk',
  'review_required':'Sent to review',
  'excluded_no_accepted_candidate':'No accepted candidate',
};
function prettyReason(r){if(REASON_PRETTY[r])return REASON_PRETTY[r];
  if(r&&r.indexOf('negative_conflict')===0)return 'Negative/accessory conflict';return r;}

// ---- shell ----------------------------------------------------------------
const TABS=[['overview','Overview'],['funnel','The funnel'],['simulator','What-if playground'],['breakdown','Breakdowns'],['hotspots','Recall hotspots'],['recovery','Recovery options'],['steps','Steps explained'],['glossary','Glossary']];
function render(){
  document.getElementById('tabnav').innerHTML=TABS.map(([k,l])=>`<button class="${k===state.tab?'active':''}" onclick="state.tab='${k}';render()">${l}</button>`).join('');
  document.getElementById('scopebanner').innerHTML = state.scope==='ALL'
    ? '<div class="warn" style="margin-top:14px;margin-bottom:0">Combined view — <b>India FY2025</b> attributes its held-back rows at <b>Final routing</b> (Unmapped / manufacturer-only) rather than at Reference validation, because its CSV source lacks reference-status columns. For the cleanest read of where recall is lost, pick a single market with the selector in each tab.</div>'
    : '';
  document.querySelectorAll('section.tab').forEach(s=>s.classList.remove('active'));
  document.getElementById('tab-'+state.tab).classList.add('active');
  ({overview:renderOverview,funnel:renderFunnel,simulator:renderSimulator,breakdown:renderBreakdown,hotspots:renderHotspots,recovery:renderRecovery,steps:renderSteps,glossary:renderGlossary}[state.tab])();
  document.getElementById('foot').innerHTML=`Generated ${esc(DATA.generated_at)} · run ${esc(DATA.run_id)} · code ${esc(String(DATA.code_commit).slice(0,10))} · review-only reporting view · numbers reconcile to prediction_audit.sqlite<br>See also: <a href="../../docs/Surgical_Mapping_Workflow_Guide.html">Surgical Mapping Workflow Guide</a> · proposals: <a href="Recall_Recovery_Proposals.xlsx">Recall_Recovery_Proposals.xlsx</a> · worklist: <a href="Recall_Recovery_Candidates.csv">Recall_Recovery_Candidates.csv</a>`;
  window.scrollTo({top:0,behavior:'instant'});
}
render();
</script>
</body>
</html>
"""
