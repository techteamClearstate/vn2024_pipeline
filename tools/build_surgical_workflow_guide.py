from __future__ import annotations

import base64
from datetime import datetime
from pathlib import Path


ROOT = Path(r"C:\Users\Administrator\Documents\Working Folder\vn2024_pipeline")
SHARED = Path(
    r"G:\共享云端硬盘\New EIU Gateway\0. Gateway Ops & Databases\Import Data Master\6. Workflow\Surgicals\Claude code\1. Mapped Results"
)
LOGO = Path(r"C:\Users\Administrator\.codex\skills\clearstate-html-design\assets\clearstate-asset-3x-8.png")
OUT_NAME = "Surgical_Mapping_Workflow_Guide.html"


def logo_data_uri() -> str:
    if not LOGO.exists():
        return ""
    encoded = base64.b64encode(LOGO.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def build_html() -> str:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logo_src = logo_data_uri()
    return r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Clearstate Surgical Import Mapping Workflow Guide</title>
  <style>
    :root {
      --navy: #172638;
      --ink: #243244;
      --muted: #637083;
      --line: #d9e1ea;
      --soft: #f5f7fa;
      --pale: #eef3f8;
      --blue: #2e6f95;
      --teal: #16827a;
      --green: #2d7d46;
      --amber: #a86d00;
      --red: #b3453f;
      --white: #ffffff;
      --shadow: 0 12px 34px rgba(23, 38, 56, 0.12);
      --radius: 8px;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      color: var(--ink);
      background: #ffffff;
      font-family: Arial, Helvetica, sans-serif;
      line-height: 1.5;
      letter-spacing: 0;
    }

    a { color: var(--blue); text-decoration: none; }
    a:hover { text-decoration: underline; }

    .topbar {
      position: sticky;
      top: 0;
      z-index: 20;
      background: rgba(255,255,255,0.96);
      border-bottom: 1px solid var(--line);
      backdrop-filter: blur(8px);
    }

    .topbar-inner {
      max-width: 1240px;
      margin: 0 auto;
      min-height: 68px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
      padding: 12px 28px;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 14px;
      min-width: 240px;
    }

    .brand img {
      width: 142px;
      height: auto;
      display: block;
    }

    .brand-title {
      font-size: 13px;
      color: var(--muted);
      border-left: 1px solid var(--line);
      padding-left: 14px;
      white-space: nowrap;
    }

    .nav {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }

    .nav a {
      padding: 7px 10px;
      border-radius: 6px;
      color: var(--ink);
      font-size: 13px;
    }

    .nav a:hover { background: var(--pale); text-decoration: none; }

    .hero {
      background:
        linear-gradient(90deg, rgba(23,38,56,0.97), rgba(23,38,56,0.88)),
        repeating-linear-gradient(135deg, rgba(255,255,255,0.06) 0 1px, transparent 1px 34px);
      color: var(--white);
      border-bottom: 1px solid rgba(255,255,255,0.2);
    }

    .hero-inner {
      max-width: 1240px;
      margin: 0 auto;
      padding: 54px 28px 40px;
      display: grid;
      grid-template-columns: minmax(0, 1.35fr) minmax(300px, 0.65fr);
      gap: 34px;
      align-items: start;
    }

    .eyebrow {
      color: #b7d7e8;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      margin-bottom: 12px;
    }

    h1 {
      margin: 0 0 18px;
      font-size: clamp(34px, 4.2vw, 58px);
      line-height: 1.03;
      letter-spacing: 0;
      max-width: 920px;
    }

    .hero p {
      margin: 0;
      color: #d8e6ee;
      font-size: 18px;
      max-width: 850px;
    }

    .hero-panel {
      background: rgba(255,255,255,0.08);
      border: 1px solid rgba(255,255,255,0.18);
      border-radius: var(--radius);
      padding: 18px;
    }

    .hero-panel h2 {
      color: #ffffff;
      margin: 0 0 10px;
      font-size: 18px;
    }

    .hero-panel dl {
      margin: 0;
      display: grid;
      grid-template-columns: 122px 1fr;
      gap: 8px 10px;
      font-size: 13px;
    }

    .hero-panel dt { color: #a9c9db; }
    .hero-panel dd { margin: 0; color: #ffffff; overflow-wrap: anywhere; }

    main {
      max-width: 1240px;
      margin: 0 auto;
      padding: 30px 28px 70px;
    }

    section {
      padding: 34px 0;
      border-bottom: 1px solid var(--line);
    }

    section:last-child { border-bottom: 0; }

    h2 {
      margin: 0 0 12px;
      font-size: 28px;
      line-height: 1.15;
      color: var(--navy);
    }

    h3 {
      margin: 24px 0 10px;
      font-size: 18px;
      color: var(--navy);
    }

    p { margin: 0 0 14px; }

    .section-lead {
      color: var(--muted);
      max-width: 930px;
      font-size: 16px;
    }

    .callout {
      border-left: 4px solid var(--blue);
      background: var(--pale);
      padding: 15px 18px;
      border-radius: 0 var(--radius) var(--radius) 0;
      margin: 18px 0;
    }

    .callout strong { color: var(--navy); }

    .grid {
      display: grid;
      gap: 16px;
    }

    .grid.two { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .grid.three { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .grid.four { grid-template-columns: repeat(4, minmax(0, 1fr)); }

    .card {
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: #fff;
      padding: 18px;
      box-shadow: 0 2px 10px rgba(23,38,56,0.04);
    }

    .card h3, .card h4 {
      margin-top: 0;
      color: var(--navy);
    }

    .card h4 {
      font-size: 15px;
      margin-bottom: 8px;
    }

    .small { font-size: 13px; color: var(--muted); }

    .pill {
      display: inline-flex;
      align-items: center;
      min-height: 22px;
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      background: var(--pale);
      color: var(--navy);
      white-space: nowrap;
    }

    .pill.good { background: #e8f4ec; color: var(--green); }
    .pill.review { background: #fff3d9; color: var(--amber); }
    .pill.stop { background: #fae9e7; color: var(--red); }

    .flow-wrap {
      margin-top: 22px;
      display: grid;
      grid-template-columns: minmax(0, 1.05fr) minmax(320px, 0.95fr);
      gap: 20px;
      align-items: start;
    }

    .flow {
      display: grid;
      gap: 10px;
      padding: 16px;
      background: var(--soft);
      border: 1px solid var(--line);
      border-radius: var(--radius);
    }

    .step {
      position: relative;
      display: grid;
      grid-template-columns: 34px 1fr 18px;
      gap: 12px;
      align-items: center;
      min-height: 62px;
      padding: 12px;
      background: #ffffff;
      border: 1px solid var(--line);
      border-radius: var(--radius);
      cursor: pointer;
      transition: border-color 0.15s ease, transform 0.15s ease, box-shadow 0.15s ease;
      text-align: left;
      width: 100%;
      color: inherit;
      font: inherit;
    }

    .step:hover,
    .step.active {
      border-color: var(--blue);
      box-shadow: var(--shadow);
      transform: translateY(-1px);
    }

    .num {
      width: 34px;
      height: 34px;
      border-radius: 50%;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      background: var(--navy);
      color: #fff;
      font-size: 13px;
      font-weight: 700;
    }

    .step-title {
      font-weight: 700;
      color: var(--navy);
      margin-bottom: 2px;
    }

    .step-note {
      font-size: 13px;
      color: var(--muted);
    }

    .chev {
      color: var(--blue);
      font-weight: 700;
    }

    .detail-panel {
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: 20px;
      background: #ffffff;
      box-shadow: var(--shadow);
      min-height: 420px;
      position: sticky;
      top: 88px;
    }

    .detail-panel h3 {
      margin-top: 0;
      font-size: 21px;
    }

    .detail-panel ul, .detail-panel ol { padding-left: 20px; }
    .detail-panel li { margin-bottom: 7px; }

    .mini-flow {
      display: grid;
      grid-template-columns: repeat(5, minmax(120px, 1fr));
      gap: 10px;
      margin: 20px 0;
      align-items: stretch;
    }

    .mini-node {
      border: 1px solid var(--line);
      background: #fff;
      border-radius: var(--radius);
      padding: 14px;
      min-height: 100px;
    }

    .mini-node strong {
      display: block;
      color: var(--navy);
      margin-bottom: 6px;
    }

    .mini-node span {
      color: var(--muted);
      font-size: 13px;
    }

    .table-scroll {
      overflow-x: auto;
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: #fff;
      margin: 14px 0 4px;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      min-width: 760px;
      font-size: 13px;
    }

    th {
      text-align: left;
      background: var(--pale);
      color: var(--navy);
      border-bottom: 1px solid var(--line);
      padding: 10px 12px;
      vertical-align: top;
    }

    td {
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
    }

    tr:last-child td { border-bottom: 0; }
    code {
      background: #eef3f8;
      padding: 1px 5px;
      border-radius: 4px;
      font-size: 12px;
      color: #14324a;
    }

    .metric {
      border-top: 4px solid var(--blue);
    }

    .metric strong {
      display: block;
      color: var(--navy);
      font-size: 22px;
      margin-bottom: 4px;
    }

    .decision {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
      margin-top: 16px;
    }

    .decision .card { min-height: 240px; }

    .footer {
      background: var(--navy);
      color: #d8e6ee;
      padding: 22px 28px;
      font-size: 13px;
    }

    .footer-inner {
      max-width: 1240px;
      margin: 0 auto;
      display: flex;
      gap: 16px;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
    }

    @media (max-width: 980px) {
      .hero-inner, .flow-wrap, .grid.two, .grid.three, .grid.four, .decision {
        grid-template-columns: 1fr;
      }
      .detail-panel { position: static; }
      .mini-flow { grid-template-columns: 1fr; }
      .nav { justify-content: flex-start; }
      .topbar-inner { align-items: flex-start; flex-direction: column; }
      .brand-title { white-space: normal; }
    }

    @media (max-width: 640px) {
      .topbar-inner, .hero-inner, main { padding-left: 18px; padding-right: 18px; }
      h1 { font-size: 34px; }
      h2 { font-size: 24px; }
      .hero-panel dl { grid-template-columns: 1fr; }
      .brand { min-width: 0; flex-wrap: wrap; }
      .brand img { width: 128px; }
    }
  </style>
</head>
<body>
  <header class="topbar">
    <div class="topbar-inner">
      <div class="brand">
        <img src="__LOGO_SRC__" alt="Clearstate">
        <div class="brand-title">Surgical import mapping wiki</div>
      </div>
      <nav class="nav" aria-label="Guide navigation">
        <a href="#overview">Overview</a>
        <a href="#flow">Flow</a>
        <a href="#references">References</a>
        <a href="#examples">Examples</a>
        <a href="#outputs">Outputs</a>
        <a href="#metrics">Metrics</a>
        <a href="#governance">Governance</a>
      </nav>
    </div>
  </header>

  <section class="hero">
    <div class="hero-inner">
      <div>
        <div class="eyebrow">Current-release documentation</div>
        <h1>Surgical Import Mapping Workflow Guide</h1>
        <p>This wiki explains how the mapping system reads messy customs shipment text, proposes surgical brand and product mappings, validates them against the master surgical reference, and separates dashboard-ready rows from review-only and excluded rows.</p>
      </div>
      <aside class="hero-panel" aria-label="Document metadata">
        <h2>Document Control</h2>
        <dl>
          <dt>Folder</dt>
          <dd>1. Mapped Results</dd>
          <dt>Countries</dt>
          <dd>India, Pakistan, Vietnam</dd>
          <dt>Years</dt>
          <dd>FY2024, FY2025</dd>
          <dt>Generated</dt>
          <dd>__GENERATED_AT__</dd>
          <dt>Status</dt>
          <dd>Explains current mapping workflow and QA controls</dd>
        </dl>
      </aside>
    </div>
  </section>

  <main>
    <section id="overview">
      <h2>Workflow Overview</h2>
      <p class="section-lead">The system is designed to mimic how a trained analyst would map import rows: preserve the raw shipment text, search for known manufacturers and product clues, compare possible candidates against the master product list, reject obvious non-surgical rows, and send uncertain surgical-looking rows to review instead of silently excluding them.</p>

      <div class="callout">
        <strong>Human-like operating principle:</strong> the workflow does not trust one clue by itself. A family/model name, product phrase, manufacturer, HS code, and exclusion screen are considered together. The final dashboard row must be auditable back to evidence in the shipment text and a valid master-reference key.
      </div>

      <div class="grid four">
        <div class="card metric">
          <strong>1</strong>
          <span>Preserve original text, then normalize for matching.</span>
        </div>
        <div class="card metric">
          <strong>2</strong>
          <span>Generate multiple candidates using aliases, fuzzy match, TF-IDF, and rules.</span>
        </div>
        <div class="card metric">
          <strong>3</strong>
          <span>Validate candidates against the latest surgical master list.</span>
        </div>
        <div class="card metric">
          <strong>4</strong>
          <span>Route rows to Trusted Dashboard, Review Queue, or Excluded/Unmapped.</span>
        </div>
      </div>

      <h3>How the workflow behaves like a human analyst</h3>
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Human analyst action</th>
              <th>Workflow equivalent</th>
              <th>Why it matters</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Read the shipment description in full.</td>
              <td>Build normalized text from <code>Detailed_Product</code>, importer, exporter, HS code, and existing mapped fields while preserving the original raw fields.</td>
              <td>Messy customs text often contains the only product clue, but the original wording must remain visible for audit.</td>
            </tr>
            <tr>
              <td>Look for brand, family, and product names.</td>
              <td>Apply manufacturer aliases, family aliases, product synonyms, abbreviation rules, misspelling variants, and customs phrase rules.</td>
              <td>Examples include <code>DES</code> as drug-eluting stent, <code>PTCA</code> as angioplasty balloon/catheter context, and <code>cannulae</code>/<code>canula</code> as cannula variants.</td>
            </tr>
            <tr>
              <td>Check whether a product belongs in surgical scope.</td>
              <td>Use surgical product evidence and exclusion screens for dental, veterinary, cosmetic, lab/IVD, imaging-only, ophthalmic/intraocular, radiotherapy, donation, and non-surgical capital equipment.</td>
              <td>Rows such as vaccines, refrigerators, ECG machines, CT scanners, and dental-only items must not become surgical dashboard rows.</td>
            </tr>
            <tr>
              <td>Confirm the chosen mapping exists in the master list.</td>
              <td>Family-tier dashboard rows must match <code>Segment | Sub-segment | Product | Player | Model/ Family Name</code>. Category-tier rows must match <code>Segment | Sub-segment | Product</code>.</td>
              <td>This prevents fuzzy or semantic matches from inventing unsupported dashboard mappings.</td>
            </tr>
            <tr>
              <td>Flag uncertainty for review.</td>
              <td>Route generic-token, fuzzy-only, semantic-only, manufacturer-only, extended-HS, and reference-gap rows to <code>Review_Queue</code>.</td>
              <td>Recall improves because possible surgical rows are captured for review instead of being silently dropped.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section id="flow">
      <h2>Visual Workflow</h2>
      <p class="section-lead">Double-click any step below to view what the workflow does, what evidence is generated, and which output sheets capture the result. The same detail panel also opens with a single click for easier navigation.</p>

      <div class="flow-wrap">
        <div class="flow" role="list" aria-label="Surgical mapping workflow steps">
          <button class="step active" data-step="1" role="listitem" type="button">
            <span class="num">1</span>
            <span><span class="step-title">Load raw import workbook</span><span class="step-note">Read RawData and preserve original shipment text.</span></span>
            <span class="chev">›</span>
          </button>
          <button class="step" data-step="2" role="listitem" type="button">
            <span class="num">2</span>
            <span><span class="step-title">Load surgical reference</span><span class="step-note">Use latest master and strict no-generic reference sheets.</span></span>
            <span class="chev">›</span>
          </button>
          <button class="step" data-step="3" role="listitem" type="button">
            <span class="num">3</span>
            <span><span class="step-title">Normalize text</span><span class="step-note">Standardize punctuation, case, spacing, and variants.</span></span>
            <span class="chev">›</span>
          </button>
          <button class="step" data-step="4" role="listitem" type="button">
            <span class="num">4</span>
            <span><span class="step-title">Generate candidates</span><span class="step-note">Combine exact, alias, fuzzy, TF-IDF, HS-rule, and semantic retrieval.</span></span>
            <span class="chev">›</span>
          </button>
          <button class="step" data-step="5" role="listitem" type="button">
            <span class="num">5</span>
            <span><span class="step-title">Score evidence</span><span class="step-note">Separate product, family, manufacturer, HS, generic, and exclusion evidence.</span></span>
            <span class="chev">›</span>
          </button>
          <button class="step" data-step="6" role="listitem" type="button">
            <span class="num">6</span>
            <span><span class="step-title">Validate against master list</span><span class="step-note">Require latest reference keys before dashboard inclusion.</span></span>
            <span class="chev">›</span>
          </button>
          <button class="step" data-step="7" role="listitem" type="button">
            <span class="num">7</span>
            <span><span class="step-title">Apply exclusions and conflicts</span><span class="step-note">Screen imaging, lab, dental, veterinary, cosmetic, ophthalmic, and capital equipment.</span></span>
            <span class="chev">›</span>
          </button>
          <button class="step" data-step="8" role="listitem" type="button">
            <span class="num">8</span>
            <span><span class="step-title">Route each row</span><span class="step-note">Trusted Dashboard, Review Queue, or Excluded/Unmapped.</span></span>
            <span class="chev">›</span>
          </button>
          <button class="step" data-step="9" role="listitem" type="button">
            <span class="num">9</span>
            <span><span class="step-title">Rebuild dashboard</span><span class="step-note">Aggregate trusted rows with numeric quantity and value checks.</span></span>
            <span class="chev">›</span>
          </button>
          <button class="step" data-step="10" role="listitem" type="button">
            <span class="num">10</span>
            <span><span class="step-title">QA, log, and learn</span><span class="step-note">Create QA tables, update aliases/rules, and track precision and recall.</span></span>
            <span class="chev">›</span>
          </button>
        </div>

        <aside class="detail-panel" aria-live="polite">
          <h3 id="detail-title">1. Load raw import workbook</h3>
          <div id="detail-body"></div>
        </aside>
      </div>

      <h3>Candidate-to-routing logic</h3>
      <div class="mini-flow" aria-label="Candidate routing flowchart">
        <div class="mini-node"><strong>Raw text</strong><span>Detailed product, importer, exporter, HS code, quantity, value.</span></div>
        <div class="mini-node"><strong>Candidate set</strong><span>Exact, alias, fuzzy, word/char TF-IDF, semantic, and HS-rule candidates.</span></div>
        <div class="mini-node"><strong>Evidence scores</strong><span>Product, family, manufacturer, HS, generic-token risk, exclusion conflicts.</span></div>
        <div class="mini-node"><strong>Master validation</strong><span>Latest family key or category key must pass before trusted inclusion.</span></div>
        <div class="mini-node"><strong>Routing</strong><span>Trusted, review, or excluded with an auditable reason code.</span></div>
      </div>
    </section>

    <section id="references">
      <h2>Reference Information</h2>
      <p class="section-lead">The reference list is the authority. Matching tools can suggest candidates, but the final dashboard mapping must validate against the master product list.</p>

      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Reference source</th>
              <th>Location</th>
              <th>How the workflow uses it</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Master surgical brand/model list</td>
              <td><code>C:\Users\Administrator\Documents\Working Folder\vn2024_pipeline\reference\brand_model\Surg_Brand_model_list_Master_03July26.xlsx</code></td>
              <td><code>Updated</code> is the full latest surgical reference. It defines valid family-tier and category-tier keys.</td>
            </tr>
            <tr>
              <td>Strict no-generic reference</td>
              <td>Same workbook, sheet <code>Updated (excl. generic)</code></td>
              <td>Used to prevent trusted mappings from relying only on generic/common family names such as <code>March</code>, <code>Express</code>, <code>Elite</code>, <code>Target</code>, or <code>Light Source</code>.</td>
            </tr>
            <tr>
              <td>Compiled reference database</td>
              <td><code>C:\Users\Administrator\Documents\Working Folder\vn2024_pipeline\reference\reference.sqlite</code></td>
              <td>Reusable local reference store for deterministic matching and audit queries.</td>
            </tr>
            <tr>
              <td>Term lists and mappings</td>
              <td><code>reference\term_lists.csv</code>, <code>reference\term_mappings.csv</code>, <code>reference\list_catalog.csv</code></td>
              <td>Source for surgical keywords, exclusion terms, mapping terms, and list catalog metadata.</td>
            </tr>
            <tr>
              <td>Company reference</td>
              <td><code>reference\companies\List_of_companies_v1.0_Master.xlsx</code></td>
              <td>Supports manufacturer/player detection and alias learning.</td>
            </tr>
            <tr>
              <td>Run and iteration log</td>
              <td><code>G:\共享云端硬盘\...\1. Mapped Results\MAPPING_IMPROVEMENT_LOG.xlsx</code></td>
              <td>Excel log of iterations, timestamps, row/value movement, QA findings, and improvement notes.</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="callout">
        <strong>Reference-compliance rule:</strong> a fuzzy, semantic, or LLM-generated suggestion can help find a candidate, but it cannot become a <code>Trusted_Dashboard</code> row unless the final tuple exists in the latest master reference.
      </div>
    </section>

    <section id="examples">
      <h2>Concrete Mapping Examples</h2>
      <p class="section-lead">These examples show how the workflow separates strong surgical mappings from review-only and excluded rows.</p>

      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Example</th>
              <th>Shipment clues</th>
              <th>Workflow decision</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Terumo guidewire</td>
              <td><code>Ni-Ti alloy guide wire</code>, <code>Catheter guide wire set</code>, importer/exporter include Terumo.</td>
              <td><span class="pill good">Trusted candidate</span></td>
              <td>Strong product phrase, manufacturer evidence, and a valid master reference tuple such as <code>PVH | Peripheral Vascular | Guidewires | Terumo | Runthrough</code>. If no exclusion conflict appears, this is dashboard-defensible.</td>
            </tr>
            <tr>
              <td>Vicryl surgical sutures</td>
              <td><code>VICRYL</code>, <code>sterile surgical sutures</code>, Ethicon/J&amp;J terms, HS 3006.</td>
              <td><span class="pill review">Extended HS review</span></td>
              <td>The product is surgical-looking, but extended-HS business scope must be decided. The row is isolated in <code>Extended_Surgical_Decision</code> instead of silently excluded.</td>
            </tr>
            <tr>
              <td>Abbott Xience DES</td>
              <td><code>coronary artery stent</code>, <code>Xience</code>, Abbott terms.</td>
              <td><span class="pill review">Reference or alias review</span></td>
              <td>Strong surgical evidence. If the latest master tuple is missing or naming differs, create <code>Reference_Update_Request</code> or <code>Alias_Update_Request</code> rather than forcing an unsupported trusted mapping.</td>
            </tr>
            <tr>
              <td>March token in vaccine text</td>
              <td><code>Production date: March 2023</code>, vaccine/pharmaceutical language.</td>
              <td><span class="pill stop">Excluded</span></td>
              <td><code>March</code> is a generic token. Vaccine/pharma terms are strong negative evidence. The row must not map to APT Medical / March guiding catheters.</td>
            </tr>
            <tr>
              <td>Express in food or non-device text</td>
              <td><code>YOFLEX EXPRESS</code> or other non-device wording.</td>
              <td><span class="pill stop">Excluded</span></td>
              <td><code>Express</code> is a generic token and cannot create a Boston Scientific stent mapping without product and manufacturer support.</td>
            </tr>
            <tr>
              <td>Excimer laser for refractive errors</td>
              <td>Ophthalmic/refractive laser terms and eye-care company context.</td>
              <td><span class="pill review">Precision-risk review</span></td>
              <td>Even if a surgical-looking mapping is possible, ophthalmic or capital-equipment conflicts require review unless the business explicitly approves scope.</td>
            </tr>
          </tbody>
        </table>
      </div>

      <h3>What gets excluded before dashboard inclusion</h3>
      <div class="grid three">
        <div class="card">
          <h4>Non-surgical healthcare scope</h4>
          <p class="small">Dental-only, veterinary-only, cosmetic/aesthetic-only, lab/IVD-only, ophthalmic/intraocular-only, cochlear/hearing, donation/humanitarian, vaccine/pharmaceutical, and general medical supplies.</p>
        </div>
        <div class="card">
          <h4>Equipment conflicts</h4>
          <p class="small">CT/MRI, ultrasound machine, angiography machine, ECG machine, defibrillator, refrigerator, body warmer, intraoral scanner, laser/dry imager, linear accelerator, cyclotron, and radiotherapy equipment.</p>
        </div>
        <div class="card">
          <h4>Generic-token traps</h4>
          <p class="small"><code>March</code>, <code>Express</code>, <code>Target</code>, <code>Elite</code>, <code>Essential</code>, <code>Light Source</code>, <code>Hydra</code>, <code>Zero</code>, <code>Therapy</code>, and similar terms require supporting product and manufacturer evidence.</p>
        </div>
      </div>
    </section>

    <section id="outputs">
      <h2>Output Workbook Structure</h2>
      <p class="section-lead">Each country-year workbook is organized so dashboard rows, review rows, and excluded rows reconcile back to <code>RawData</code>. The workbook tabs are not interchangeable: some are dashboard outputs, some are review work queues, and some are audit or learning tables that explain why the workflow made each decision.</p>

      <div class="decision">
        <div class="card">
          <span class="pill good">Trusted Dashboard</span>
          <h3>Dashboard-ready rows</h3>
          <p>Rows with surgical scope, latest reference validation, sufficient product evidence, no strong exclusion conflict, and no generic-token-only trigger.</p>
          <p class="small">Typical output sheets: <code>Trusted_Dashboard</code>, <code>Dashboard_Rebuild</code>, or country-specific dashboard sheets.</p>
        </div>
        <div class="card">
          <span class="pill review">Review Queue</span>
          <h3>Captured but unresolved</h3>
          <p>Surgical-looking rows with weak evidence, extended-HS products, reference gaps, semantic-only matches, fuzzy-only matches, manufacturer-only clues, or conflict terms.</p>
          <p class="small">Supporting outputs include <code>Candidate_Table</code>, <code>Extended_Surgical_Decision</code>, <code>Reference_Update_Request</code>, and <code>Alias_Update_Request</code>.</p>
        </div>
        <div class="card">
          <span class="pill stop">Excluded / Unmapped</span>
          <h3>Outside current scope</h3>
          <p>Rows with no surgical evidence or clear non-surgical evidence and no countervailing surgical signal.</p>
          <p class="small">The recall-hunting screen checks excluded rows for surgical keywords so high-value surgical rows are not silently missed.</p>
        </div>
      </div>

      <h3>How humans should use the output tabs</h3>
      <p class="section-lead">Start with the validation and metrics tabs, then work from the highest-risk or highest-value review tabs into reusable alias, rule, or reference updates. Do not manually add rows to <code>Trusted_Dashboard</code>; record the correction and rerun the workflow so the evidence and reconciliation remain auditable.</p>

      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Tab or sheet</th>
              <th>What it means</th>
              <th>Primary use case</th>
              <th>How humans should interact with it</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><code>RawData</code></td>
              <td>Original shipment-level source rows with stable <code>UniqueID</code>, product text, importer, exporter, HS code, quantity, and value.</td>
              <td>Source of truth for reconciliation and audit.</td>
              <td>Do not edit. Use it to verify the exact customs wording behind any mapping or review decision.</td>
            </tr>
            <tr>
              <td><code>Trusted_Dashboard</code></td>
              <td>Rows considered dashboard-ready: surgical scope, latest-reference valid, sufficient product evidence, and no unresolved exclusion or generic-token conflict.</td>
              <td>Trusted row-level surgical mapping for business reporting.</td>
              <td>Use for reporting. If a row is wrong, log the correction through the review, alias, rule, or reference-update process and rerun; do not hand-edit the trusted output.</td>
            </tr>
            <tr>
              <td><code>Review_Queue</code></td>
              <td>Surgical-looking or high-value uncertain rows that need human or business review before dashboard inclusion.</td>
              <td>Manual review workbench for recall improvement.</td>
              <td>Prioritize high-value rows, repeated clusters, reference gaps, extended-HS products, and generic-token risks. Record the decision and convert repeat patterns into reusable rules.</td>
            </tr>
            <tr>
              <td><code>Excluded_Unmapped</code></td>
              <td>Rows outside current surgical scope or rows with no enough surgical evidence after screening.</td>
              <td>Audit of non-dashboard rows and false-negative checks.</td>
              <td>Usually leave unchanged. Spot-check high-value rows and rows surfaced in surgical-keyword screens before confirming they are truly out of scope.</td>
            </tr>
            <tr>
              <td><code>Dashboard_Rebuild</code></td>
              <td>Aggregated dashboard view rebuilt from trusted rows after converting quantity and value fields to numeric measures.</td>
              <td>Dashboard upload, rollup comparison, and final reporting.</td>
              <td>Use as the reporting aggregate. Do not manually type fixes here; fix the underlying row routing or reference rule and rerun.</td>
            </tr>
            <tr>
              <td><code>Candidate_Table</code></td>
              <td>All candidate mappings considered for each row, with source method, rank, evidence scores, master-validation status, and routing decision.</td>
              <td>Explain why the workflow chose, reviewed, or rejected a mapping.</td>
              <td>Use when a reviewer asks, "Why did this map here?" Compare candidates and evidence before approving an alias or reference change.</td>
            </tr>
            <tr>
              <td><code>Mapping_Decision_Log</code></td>
              <td>Row-level final decision log with route, reason code, evidence terms, risk flags, and reference status.</td>
              <td>Audit trail for final routing.</td>
              <td>Use to trace a row from raw text to final tier. Reviewer corrections should update the decision log or correction tracker, then flow into rules on the next run.</td>
            </tr>
            <tr>
              <td><code>Extended_Surgical_Decision</code></td>
              <td>Rows that look surgical but sit in extended HS scope, such as sutures, mesh, hemostats, wound-management items, or other products pending scope approval.</td>
              <td>Business-scope decision table.</td>
              <td>Decide whether each product family belongs in the dashboard scope. Until approved, keep these rows in review rather than silently excluding them.</td>
            </tr>
            <tr>
              <td><code>Alias_Update_Request</code></td>
              <td>Suggested manufacturer, family, product, abbreviation, misspelling, and customs-phrase aliases discovered during review.</td>
              <td>Turn repeated manual corrections into reusable matching knowledge.</td>
              <td>Approve only aliases with clear evidence. After approval, add them to the maintained alias/rule tables and rerun the workflow.</td>
            </tr>
            <tr>
              <td><code>Reference_Update_Request</code></td>
              <td>Rows that appear surgical but do not validate against the latest master reference key.</td>
              <td>Identify master-list gaps or naming conflicts.</td>
              <td>Send to the master-reference owner. Do not force these rows into <code>Trusted_Dashboard</code> until the master is updated or the row validates to an existing key.</td>
            </tr>
            <tr>
              <td><code>Precision_Risk_Rows</code></td>
              <td>Rows with trusted or near-trusted mappings that include conflict terms, generic tokens, exclusion patterns, or weak evidence.</td>
              <td>Quality-control queue for false-positive prevention.</td>
              <td>Review before release, especially high-value rows. Move unresolved conflicts to <code>Review_Queue</code> or exclusion, unless there is an explicit approved override.</td>
            </tr>
            <tr>
              <td><code>Potential_Missed_Surgical</code></td>
              <td>Rows not trusted but containing high-signal surgical terms such as endoscopy, catheter, guidewire, stent, cannula, suture, mesh, valve, dialysis, stapler, or clip.</td>
              <td>Recall-hunting list.</td>
              <td>Use to find false negatives. Promote rows to review or trusted only when product evidence, master validation, and scope checks support the change.</td>
            </tr>
            <tr>
              <td><code>Excluded_Surgicalish_Screen</code></td>
              <td>Excluded rows that still contain surgical-looking language.</td>
              <td>High-sensitivity false-negative audit.</td>
              <td>Sample high-value and repeated patterns. If a pattern is truly surgical, create an alias, product rule, HS rule, or reference update request.</td>
            </tr>
            <tr>
              <td><code>Review_Queue_Cluster_Summary</code></td>
              <td>Review rows grouped by normalized phrase, HS code, importer/exporter, manufacturer hints, family hints, value, and repeated pattern.</td>
              <td>Reduce review burden by reviewing repeated clusters instead of isolated rows.</td>
              <td>Review the highest-value clusters first. One approved cluster decision can become a reusable rule for many rows.</td>
            </tr>
            <tr>
              <td><code>Specific_Examples</code> or <code>Unresolved_Examples</code></td>
              <td>Concrete rows or clusters used to explain fixed issues, risky mappings, and remaining decisions.</td>
              <td>Reviewer training and handoff.</td>
              <td>Use as examples when explaining the workflow to new reviewers or when deciding whether a rule should be generalized.</td>
            </tr>
            <tr>
              <td><code>Gold_Label_Template</code></td>
              <td>Human-labeling template with true scope, true mapping, reviewer, review date, confidence, reason, and correction type.</td>
              <td>Build the ground truth needed to measure real precision and recall.</td>
              <td>Label priority samples first: precision-risk trusted rows, high-value review rows, extended-HS rows, surgical-keyword excluded rows, and stratified clean trusted rows.</td>
            </tr>
            <tr>
              <td><code>Metrics_Summary</code></td>
              <td>Row/value split, precision and recall proxies, review burden, high-value unresolved rows, runtime, and cost where applicable.</td>
              <td>Track whether each iteration improves accuracy and efficiency.</td>
              <td>Read this before and after each run. A useful run should improve capture recall or review efficiency without breaking trusted validation or precision guardrails.</td>
            </tr>
            <tr>
              <td><code>Validation</code></td>
              <td>Release gates such as row/value reconciliation, master-reference validation, strict no-generic validation, aggregation checks, and trusted anomaly counts.</td>
              <td>Go/no-go release control.</td>
              <td>Do not release if a required check fails. Fix the underlying mapping, reference, or aggregation issue first.</td>
            </tr>
            <tr>
              <td><code>Change_Log</code></td>
              <td>Iteration timestamp, changed rules, changed aliases, row/value movement, QA results, unresolved issues, and release notes.</td>
              <td>Version history and audit narrative.</td>
              <td>Use to understand what changed since the prior run. The shared folder keeps the current version, while historical detail lives in version control and the log.</td>
            </tr>
            <tr>
              <td><code>Experiment_Matrix</code></td>
              <td>A0-A10 test results for alias expansion, fuzzy matching, TF-IDF, semantic retrieval, evidence scoring, LLM agents, and active learning.</td>
              <td>Decide which workflow changes to adopt, reject, or test further.</td>
              <td>Update after controlled tests. Do not adopt a method unless it improves recall or efficiency without unacceptable precision loss.</td>
            </tr>
            <tr>
              <td><code>Evidence_Scoring_Model</code></td>
              <td>Feature definitions, weights, penalties, thresholds, and routing logic for product, family, manufacturer, HS, TF-IDF, semantic, generic-token, and exclusion evidence.</td>
              <td>Explain the scoring model behind routing.</td>
              <td>Use when tuning thresholds or explaining why a row is trusted versus review-only.</td>
            </tr>
            <tr>
              <td><code>Routing_Rules</code></td>
              <td>Exact rules for <code>Trusted_Dashboard</code>, <code>Review_Queue</code>, and <code>Excluded_Unmapped</code>.</td>
              <td>Business rule reference.</td>
              <td>Use to align reviewers. Any change to these rules should be logged and tested against the validation gates.</td>
            </tr>
            <tr>
              <td><code>Active_Learning_Updates</code></td>
              <td>Approved corrections converted into alias, rule, exclusion, HS-scope, generic-token, or reference-update actions.</td>
              <td>Prevent the same manual correction from recurring.</td>
              <td>After approval, feed these updates into maintained rule/reference files and rerun. Track whether repeat review burden declines.</td>
            </tr>
            <tr>
              <td><code>Workflow_Recommendations</code></td>
              <td>Prioritized operational recommendations for immediate fixes, controlled experiments, deferred items, and methods to avoid.</td>
              <td>Next-action planning.</td>
              <td>Use at release review to decide what should be fixed in the next iteration.</td>
            </tr>
          </tbody>
        </table>
      </div>

      <h3>How to handle a consolidated map file</h3>
      <div class="callout">
        <strong>Current folder rule:</strong> the mapped-results folder keeps one current workbook for each country-year, plus the Excel improvement log and this HTML guide. A separate row-level consolidated map workbook is not kept here by default because it would add another output workbook beyond the six current country-year files.
      </div>
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Need</th>
              <th>Where to look</th>
              <th>What to do</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Country-year row-level mapping</td>
              <td><code>G:\共享云端硬盘\New EIU Gateway\0. Gateway Ops &amp; Databases\Import Data Master\6. Workflow\Surgicals\Claude code\1. Mapped Results</code>, in the six current mapped workbooks.</td>
              <td>Open the relevant country-year workbook and use <code>RawData</code>, <code>Trusted_Dashboard</code>, <code>Review_Queue</code>, and <code>Excluded_Unmapped</code> joined by <code>UniqueID</code>.</td>
            </tr>
            <tr>
              <td>Cross-country metrics, QA status, and iteration history</td>
              <td><code>MAPPING_IMPROVEMENT_LOG.xlsx</code> in the same mapped-results folder.</td>
              <td>Use this as the consolidated management view for what changed, current QA status, row/value movement, and improvement tracking.</td>
            </tr>
            <tr>
              <td>Combined QA workbook across all six files</td>
              <td><code>D:\vn2024_remapped_current\reports\All_Countries_Surgical_Mapping_QA_Report.xlsx</code></td>
              <td>Use this working-folder report for detailed cross-country QA. Release it to the shared folder only if the folder owner approves adding a QA workbook beyond the six mapped outputs.</td>
            </tr>
            <tr>
              <td>New consolidated row-level map</td>
              <td>Generate from the six current workbooks, not by manually merging edited copies.</td>
              <td>Build it with <code>Country</code>, <code>Fiscal_Year</code>, <code>Source_File</code>, <code>UniqueID</code>, output tier, mapped tuple, evidence fields, and value/quantity. Store it in the working output package unless the shared-folder file policy is changed.</td>
            </tr>
          </tbody>
        </table>
      </div>

      <h3>Recommended reviewer sequence</h3>
      <div class="mini-flow" aria-label="Reviewer workflow for output tabs">
        <div class="mini-node"><strong>1. Check release gates</strong><span>Open <code>Validation</code> and <code>Metrics_Summary</code> first.</span></div>
        <div class="mini-node"><strong>2. Use trusted outputs</strong><span>Report from <code>Trusted_Dashboard</code> and <code>Dashboard_Rebuild</code>.</span></div>
        <div class="mini-node"><strong>3. Prioritize review</strong><span>Start with <code>Precision_Risk_Rows</code>, high-value <code>Review_Queue</code>, and <code>Extended_Surgical_Decision</code>.</span></div>
        <div class="mini-node"><strong>4. Capture recall gaps</strong><span>Review <code>Potential_Missed_Surgical</code>, <code>Excluded_Surgicalish_Screen</code>, and cluster summaries.</span></div>
        <div class="mini-node"><strong>5. Convert learning</strong><span>Approve alias, rule, and reference requests, then rerun and compare metrics.</span></div>
      </div>

      <h3>Files kept in the mapped-results folder</h3>
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>File type</th>
              <th>Expected files</th>
              <th>Rule</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Mapped outputs</td>
              <td><code>India_FY2024</code>, <code>India_FY2025</code>, <code>Pakistan_FY2024</code>, <code>Pakistan_FY2025</code>, <code>Vietnam_FY2024</code>, <code>Vietnam_FY2025</code></td>
              <td>Keep exactly one latest workbook per country-year. Do not accumulate dated copies in this folder.</td>
            </tr>
            <tr>
              <td>Improvement log</td>
              <td><code>MAPPING_IMPROVEMENT_LOG.xlsx</code></td>
              <td>Tracks iterations, biggest changes, timestamps, QA outcomes, and key workflow improvements in Excel format.</td>
            </tr>
            <tr>
              <td>Workflow guide</td>
              <td><code>Surgical_Mapping_Workflow_Guide.html</code></td>
              <td>Current wiki-style explanation of the mapping process, references, metrics, and QA controls.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section id="metrics">
      <h2>Optimization Metrics</h2>
      <p class="section-lead">The workflow optimizes for high recall while keeping the trusted dashboard defensible. Precision around 90% is acceptable if recall improves materially, but trusted rows must still pass reference validation and exclusion checks.</p>

      <div class="grid two">
        <div class="card">
          <h3>Recall</h3>
          <p><strong>Meaning in this workflow:</strong> of all true surgical import rows, how many did the workflow capture either in <code>Trusted_Dashboard</code> or <code>Review_Queue</code>?</p>
          <p><strong>Why it matters:</strong> low recall means surgical value is hidden in <code>Excluded_Unmapped</code>. The process therefore routes uncertain surgical-looking rows to review instead of dropping them.</p>
          <p><code>Capture recall = (Trusted surgical rows + Review surgical rows) / All true surgical rows</code></p>
        </div>
        <div class="card">
          <h3>Precision</h3>
          <p><strong>Meaning in this workflow:</strong> of rows included in <code>Trusted_Dashboard</code>, how many are truly in surgical scope and correctly mapped?</p>
          <p><strong>Why it matters:</strong> dashboard users need defensible outputs. Trusted precision is protected by master-reference validation, product evidence, generic-token guardrails, and exclusion screens.</p>
          <p><code>Trusted precision = Correct trusted surgical rows / All trusted rows</code></p>
        </div>
      </div>

      <h3>QA checks before release</h3>
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Check</th>
              <th>Target</th>
              <th>Purpose</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Trusted latest master validation failures</td>
              <td>0</td>
              <td>No dashboard family/category tuple should be outside the latest master reference.</td>
            </tr>
            <tr>
              <td>Trusted strict no-generic failures</td>
              <td>0</td>
              <td>No trusted family row should rely only on a generic reference row.</td>
            </tr>
            <tr>
              <td>Dashboard aggregation mismatches</td>
              <td>0</td>
              <td><code>Quantity</code> and <code>Total_Value_USD</code> must aggregate numerically and reconcile to trusted raw rows.</td>
            </tr>
            <tr>
              <td>Trusted rows with explicit exclusion scope flags</td>
              <td>0</td>
              <td>Rows with dental, veterinary, lab, imaging, ophthalmic, radiotherapy, donation, or capital-equipment conflicts should not be trusted without override.</td>
            </tr>
            <tr>
              <td>High-value surgical rows silently excluded</td>
              <td>0 or near 0</td>
              <td>Excluded rows are screened for surgical keywords, clustered, and moved to review when evidence is present.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section id="governance">
      <h2>Workflow Governance and Continuous Improvement</h2>
      <p class="section-lead">The mapping workflow improves through a repeatable active-learning loop. Human review is not a one-off correction; each correction should become a reusable alias, rule, exclusion term, or reference-update request.</p>

      <div class="grid three">
        <div class="card">
          <h3>Candidate Table</h3>
          <p class="small">Shows all considered candidates per row, including source method, evidence scores, master validation, and final routing decision. This is the audit trail for why a row was or was not mapped.</p>
        </div>
        <div class="card">
          <h3>Alias and Rule Tables</h3>
          <p class="small">Capture manufacturer aliases, family aliases, product synonyms, abbreviations, misspellings, customs phrases, negative terms, generic tokens, HS scope rules, and product disambiguation rules.</p>
        </div>
        <div class="card">
          <h3>Gold Labels</h3>
          <p class="small">A human-labeled evaluation table used to calculate real precision and recall, not only proxy metrics. Prioritize high-value review rows, extended-HS rows, precision-risk trusted rows, and excluded surgical-keyword clusters.</p>
        </div>
      </div>

      <h3>Active learning loop</h3>
      <div class="mini-flow" aria-label="Active learning loop flowchart">
        <div class="mini-node"><strong>Review row</strong><span>Human confirms surgical scope, mapping, exclusion, or ambiguity.</span></div>
        <div class="mini-node"><strong>Classify correction</strong><span>Alias, rule, reference gap, exclusion issue, HS scope, or remap.</span></div>
        <div class="mini-node"><strong>Update knowledge</strong><span>Add reusable alias/rule or reference-update request.</span></div>
        <div class="mini-node"><strong>Rerun mapping</strong><span>Regenerate workbook and QA report from the same logic.</span></div>
        <div class="mini-node"><strong>Measure change</strong><span>Track recall, precision, review burden, false positives, false negatives, runtime, and LLM cost.</span></div>
      </div>

      <h3>Optional LLM agents</h3>
      <p>LLMs are used only after deterministic candidate generation. They should not act as a one-shot raw-row-to-final-mapping system. Their output must be structured JSON and must pass master-reference validation before any trusted dashboard inclusion.</p>
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Agent</th>
              <th>Trigger</th>
              <th>Expected output</th>
              <th>Guardrail</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Scope Agent</td>
              <td>High-value review rows and excluded rows with surgical terms.</td>
              <td>Surgical / non-surgical / ambiguous label with evidence terms.</td>
              <td>Cannot directly create trusted mappings.</td>
            </tr>
            <tr>
              <td>Resolver Agent</td>
              <td>Multiple close candidates or product/family/manufacturer conflict.</td>
              <td>Selected candidate, confidence, reason, and human-review flag.</td>
              <td>Selected tuple must exist in the master reference before trusted inclusion.</td>
            </tr>
            <tr>
              <td>Conflict Agent</td>
              <td>Trusted rows with exclusion terms or generic-token risk.</td>
              <td>Keep, review, exclude, or remap recommendation.</td>
              <td>Strong exclusion conflicts move rows out of trusted unless manually approved.</td>
            </tr>
            <tr>
              <td>Recall Hunter Agent</td>
              <td>High-value review/excluded clusters and repeated unknown phrases.</td>
              <td>Likely missed surgical rows plus suggested aliases, rules, and reference updates.</td>
              <td>Suggestions become deterministic rules or review items before production use.</td>
            </tr>
            <tr>
              <td>QC Agent</td>
              <td>Before final release and after major rule updates.</td>
              <td>False-positive candidates, false-negative candidates, and unresolved issues.</td>
              <td>Independent check of trusted precision and recall hunting outputs.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </main>

  <footer class="footer">
    <div class="footer-inner">
      <span>Clearstate surgical import mapping workflow guide</span>
      <span>Generated __GENERATED_AT__</span>
    </div>
  </footer>

  <script>
    const stepDetails = {
      "1": {
        title: "1. Load raw import workbook",
        body: `
          <p><strong>What happens:</strong> the pipeline reads the country-year workbook and treats <code>RawData</code> as the row-level source of truth.</p>
          <ul>
            <li>Original fields such as <code>Detailed_Product</code>, <code>Importer</code>, <code>Exporter</code>, <code>HS_Code</code>, <code>Quantity</code>, and <code>Total_Value_USD</code> are preserved.</li>
            <li>A stable <code>UniqueID</code> is used to reconcile trusted, review, and excluded outputs back to RawData.</li>
            <li>No mapping decision is allowed to break row-count or value reconciliation.</li>
          </ul>
          <p><strong>Audit point:</strong> <code>Trusted_Dashboard</code> + <code>Review_Queue</code> + <code>Excluded_Unmapped</code> should exactly reconcile to RawData where that three-way structure is used.</p>`
      },
      "2": {
        title: "2. Load surgical reference",
        body: `
          <p><strong>What happens:</strong> the latest surgical master list is loaded before candidate generation.</p>
          <ul>
            <li><code>Updated</code> defines the full latest surgical reference.</li>
            <li><code>Updated (excl. generic)</code> is used as a stricter control against generic family names.</li>
            <li>Family-tier trusted keys require <code>Segment | Sub-segment | Product | Player | Model/ Family Name</code>.</li>
            <li>Category-tier trusted keys require <code>Segment | Sub-segment | Product</code>.</li>
          </ul>
          <p><strong>Example:</strong> a row may mention <code>Xience</code> and coronary stent terms. If the latest master does not contain the final Abbott / Xience / DES tuple, the row is routed to reference review rather than forced into the dashboard.</p>`
      },
      "3": {
        title: "3. Normalize text",
        body: `
          <p><strong>What happens:</strong> the workflow creates normalized matching text while keeping the original shipment wording unchanged.</p>
          <ul>
            <li>Lowercase conversion, punctuation cleanup, whitespace normalization, and hyphen/underscore handling.</li>
            <li>Variant expansion for terms such as <code>cannula</code>, <code>cannulae</code>, and <code>canula</code>.</li>
            <li>Abbreviation expansion for terms such as <code>DES</code>, <code>BMS</code>, <code>PTCA</code>, <code>CRT-D</code>, <code>ICD</code>, <code>TAVI</code>, and <code>TAVR</code>.</li>
          </ul>
          <p><strong>Why it matters:</strong> customs descriptions are inconsistent. Normalization lets the system find surgical evidence without altering the raw text used for audit.</p>`
      },
      "4": {
        title: "4. Generate candidates",
        body: `
          <p><strong>What happens:</strong> the workflow keeps multiple plausible candidates instead of choosing the first apparent match.</p>
          <ul>
            <li><strong>Exact and alias match:</strong> direct manufacturer, family, product, abbreviation, and customs-phrase rules.</li>
            <li><strong>Fuzzy match:</strong> catches spelling noise and truncated names, but fuzzy-only results go to review.</li>
            <li><strong>Word TF-IDF:</strong> improves recall for product phrases such as stent system, guidewire, catheter, suture, mesh, trocar, stapler, implant, endoscopy, and dialysis.</li>
            <li><strong>Character TF-IDF:</strong> helps with punctuation, spelling variants, and partial model/family terms.</li>
            <li><strong>Semantic retrieval:</strong> can discover candidate rows missed by lexical rules, but semantic-only matches remain review-only.</li>
          </ul>
          <p><strong>Output:</strong> <code>Candidate_Table</code> records candidate rank, source method, scores, validation status, and routing decision.</p>`
      },
      "5": {
        title: "5. Score evidence",
        body: `
          <p><strong>What happens:</strong> the workflow replaces one generic match-confidence label with separate evidence features.</p>
          <ul>
            <li>Positive evidence: product phrase, family alias, manufacturer alias, category match, HS compatibility, fuzzy score, word TF-IDF, char TF-IDF, semantic score.</li>
            <li>Negative evidence: exclusion terms, generic-token risk, product/category conflict, and master-reference failure.</li>
            <li>Priority evidence: high-value unresolved rows and repeated clusters.</li>
          </ul>
          <p><strong>Example:</strong> <code>VICRYL sterile surgical sutures</code> has strong product and family evidence but may remain in Extended HS review until the business confirms HS 3006 dashboard scope.</p>`
      },
      "6": {
        title: "6. Validate against master list",
        body: `
          <p><strong>What happens:</strong> every trusted candidate is checked against the latest reference before dashboard inclusion.</p>
          <ul>
            <li>Family-tier rows must pass the full latest master key.</li>
            <li>Category-tier rows must pass the latest category key.</li>
            <li>Rows that fail latest-reference validation are routed to <code>Review_Queue</code> and, where appropriate, <code>Reference_Update_Request</code>.</li>
          </ul>
          <p><strong>Guardrail:</strong> Fuzzy, semantic, and LLM suggestions cannot invent a trusted tuple outside the master list.</p>`
      },
      "7": {
        title: "7. Apply exclusions and conflicts",
        body: `
          <p><strong>What happens:</strong> exclusion and conflict rules run before final dashboard inclusion.</p>
          <ul>
            <li>Excluded or reviewed categories include dental, veterinary, cosmetic/aesthetic, lab/IVD, imaging-only, ophthalmic/intraocular, cochlear/hearing, donation/humanitarian, radiotherapy, linear accelerator/cyclotron, and non-surgical capital equipment.</li>
            <li>Conflict terms include <code>CT scanner</code>, <code>MRI</code>, <code>ultrasound machine</code>, <code>ECG machine</code>, <code>defibrillator</code>, <code>refrigerator</code>, <code>body warmer</code>, <code>laser imager</code>, <code>intraoral scanner</code>, and <code>reagent</code>.</li>
            <li>Generic tokens such as <code>March</code>, <code>Express</code>, <code>Elite</code>, and <code>Target</code> require supporting product and manufacturer evidence.</li>
          </ul>
          <p><strong>Example:</strong> <code>Production date: March 2023</code> in a vaccine row is not APT Medical / March. It is excluded because the product context conflicts with surgical scope.</p>`
      },
      "8": {
        title: "8. Route each row",
        body: `
          <p><strong>What happens:</strong> each row receives a final routing decision and reason code.</p>
          <ul>
            <li><strong><code>Trusted_Dashboard</code>:</strong> surgical scope, master-valid, strong product evidence, no exclusion conflict, no generic-token-only match. Humans use this for reporting, not manual row edits.</li>
            <li><strong><code>Review_Queue</code>:</strong> surgical-looking but weak evidence, extended-HS, reference gap, alias gap, fuzzy-only, semantic-only, manufacturer-only, high-value uncertain, or conflicting evidence. Humans review these rows and convert repeat decisions into reusable rules.</li>
            <li><strong><code>Excluded_Unmapped</code>:</strong> no surgical evidence or clear non-surgical scope without countervailing surgical evidence. Humans usually spot-check only high-value or surgical-keyword exceptions.</li>
            <li><strong><code>Mapping_Decision_Log</code>:</strong> records the route, reason code, evidence terms, risk flags, and reference status for audit.</li>
          </ul>
          <p><strong>Recall principle:</strong> uncertain surgical-looking rows go to review, not silent exclusion.</p>`
      },
      "9": {
        title: "9. Rebuild dashboard",
        body: `
          <p><strong>What happens:</strong> trusted rows are aggregated into the dashboard output.</p>
          <ul>
            <li><code>Quantity</code> is converted to numeric before aggregation.</li>
            <li><code>Total_Value_USD</code> is summed and reconciled to trusted source rows.</li>
            <li><code>Dashboard_Rebuild</code> is generated from current trusted rows rather than manually edited.</li>
            <li>The row-level trusted source remains <code>Trusted_Dashboard</code>; the grouped dashboard view is the aggregation layer.</li>
          </ul>
          <p><strong>Release check:</strong> dashboard aggregation value and quantity mismatches must be zero.</p>`
      },
      "10": {
        title: "10. QA, log, and learn",
        body: `
          <p><strong>What happens:</strong> the workflow produces QA outputs and converts reviewer corrections into reusable knowledge.</p>
          <ul>
            <li>Start with <code>Validation</code> and <code>Metrics_Summary</code> to check release gates, row/value movement, precision, recall, review burden, and runtime.</li>
            <li>QA outputs include <code>Precision_Risk_Rows</code>, <code>Potential_Missed_Surgical</code>, <code>Excluded_Surgicalish_Screen</code>, <code>Extended_Surgical_Decision</code>, <code>Reference_Update_Request</code>, <code>Alias_Update_Request</code>, cluster summaries, and metrics.</li>
            <li>Human corrections become alias updates, product rules, exclusion rules, HS-scope rules, generic-token rules, or reference-update requests.</li>
            <li><code>Gold_Label_Template</code> captures reviewed truth labels so precision and recall can move from proxy estimates to measured values.</li>
            <li>The Excel improvement log records timestamp, iteration, row/value movement, precision/recall impact, and unresolved decisions across all six country-year files.</li>
          </ul>
          <p><strong>Continuous improvement:</strong> rerun the pipeline after every approved rule/reference update and compare precision, recall, review burden, and runtime to the previous baseline.</p>`
      }
    };

    const detailTitle = document.getElementById("detail-title");
    const detailBody = document.getElementById("detail-body");
    const buttons = document.querySelectorAll(".step");

    function showStep(stepId) {
      const detail = stepDetails[stepId];
      if (!detail) return;
      buttons.forEach(button => button.classList.toggle("active", button.dataset.step === stepId));
      detailTitle.textContent = detail.title;
      detailBody.innerHTML = detail.body;
    }

    buttons.forEach(button => {
      button.addEventListener("click", () => showStep(button.dataset.step));
      button.addEventListener("dblclick", () => showStep(button.dataset.step));
    });

    showStep("1");
  </script>
</body>
</html>
'''.replace("__LOGO_SRC__", logo_src).replace("__GENERATED_AT__", generated_at)


def update_about() -> None:
    about = SHARED / "_ABOUT.txt"
    if not about.exists():
        return

    text = about.read_text(encoding="utf-8")
    original = text

    stale_qa_block = "Current QA workbook:\n- Pakistan_FY2024_SurgicalOnly_QA.xlsx\n\n"
    if stale_qa_block in text:
        text = text.replace(
            stale_qa_block,
            (
                "QA reports and supporting audit workbooks are generated by the pipeline "
                "and retained in the working folder unless explicitly released here.\n\n"
            ),
        )

    if OUT_NAME not in text:
        anchor = "Iteration and QA log:\n- MAPPING_IMPROVEMENT_LOG.xlsx\n"
        insert = (
            "Iteration and QA log:\n"
            "- MAPPING_IMPROVEMENT_LOG.xlsx\n\n"
            "Workflow guide:\n"
            f"- {OUT_NAME}\n"
        )
        if anchor in text:
            text = text.replace(anchor, insert)
        else:
            text = text.rstrip() + f"\n\nWorkflow guide:\n- {OUT_NAME}\n"

    if text != original:
        about.write_text(text, encoding="utf-8", newline="\n")


def main() -> None:
    html = build_html()
    local_out = ROOT / "docs" / OUT_NAME
    shared_out = SHARED / OUT_NAME

    local_out.parent.mkdir(parents=True, exist_ok=True)
    SHARED.mkdir(parents=True, exist_ok=True)

    local_out.write_text(html, encoding="utf-8", newline="\n")
    shared_out.write_text(html, encoding="utf-8", newline="\n")
    update_about()

    print(f"Wrote {local_out}")
    print(f"Wrote {shared_out}")


if __name__ == "__main__":
    main()
