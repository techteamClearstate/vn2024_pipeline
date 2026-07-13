import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

const [payloadPath, outputPath, previewDir] = process.argv.slice(2);
if (!payloadPath || !outputPath || !previewDir) {
  throw new Error("Usage: node build_prediction_audit_workbook.mjs <payload.json> <output.xlsx> <preview_dir>");
}

const nodeModules = process.env.CODEX_NODE_MODULES;
if (!nodeModules) {
  throw new Error("CODEX_NODE_MODULES must point to the bundled Codex node_modules directory.");
}
const artifactModule = pathToFileURL(
  path.join(nodeModules, "@oai", "artifact-tool", "dist", "artifact_tool.mjs"),
).href;
const { SpreadsheetFile, Workbook } = await import(artifactModule);

const payload = JSON.parse(await fs.readFile(payloadPath, "utf8"));
const workbook = Workbook.create();
const COLORS = {
  ink: "#0E0E0E",
  blue: "#0047AB",
  blueLight: "#EAF1FB",
  gray: "#777777",
  grayLight: "#F3F4F6",
  line: "#D8DEE8",
  white: "#FFFFFF",
  green: "#D9EAD3",
  amber: "#FFF2CC",
  red: "#F4CCCC",
};

function colName(index) {
  let n = index + 1;
  let result = "";
  while (n > 0) {
    n -= 1;
    result = String.fromCharCode(65 + (n % 26)) + result;
    n = Math.floor(n / 26);
  }
  return result;
}

function normalize(value) {
  if (value === null || value === undefined) return null;
  if (typeof value === "boolean") return value ? 1 : 0;
  return value;
}

function writeRows(sheet, startRow, startCol, rows, chunkSize = 5000) {
  if (!rows.length) return;
  const width = rows[0].length;
  for (let offset = 0; offset < rows.length; offset += chunkSize) {
    const chunk = rows.slice(offset, offset + chunkSize).map((row) => row.map(normalize));
    const row1 = startRow + offset;
    const row2 = row1 + chunk.length - 1;
    const col1 = colName(startCol);
    const col2 = colName(startCol + width - 1);
    sheet.getRange(`${col1}${row1}:${col2}${row2}`).values = chunk;
  }
}

function writeObjectRows(sheet, startRow, rows, columns, chunkSize = 5000) {
  for (let offset = 0; offset < rows.length; offset += chunkSize) {
    const chunk = rows.slice(offset, offset + chunkSize).map((row) =>
      columns.map((column) => normalize(row[column.key])),
    );
    writeRows(sheet, startRow + offset, 0, chunk, chunkSize);
  }
}

function setColumnWidths(sheet, widths, lastRow) {
  widths.forEach((width, index) => {
    const col = colName(index);
    sheet.getRange(`${col}1:${col}${Math.max(lastRow, 8)}`).format.columnWidth = width;
  });
}

function addTitle(sheet, title, note, lastCol) {
  sheet.showGridLines = false;
  sheet.mergeCells(`A1:${lastCol}1`);
  sheet.mergeCells(`A2:${lastCol}2`);
  sheet.getRange("A1").values = [[title]];
  sheet.getRange("A2").values = [[note]];
  sheet.getRange(`A1:${lastCol}1`).format = {
    fill: COLORS.ink,
    font: { bold: true, color: COLORS.white, size: 18 },
    verticalAlignment: "center",
  };
  sheet.getRange(`A2:${lastCol}2`).format = {
    fill: COLORS.blueLight,
    font: { color: COLORS.ink, italic: true },
    wrapText: true,
    verticalAlignment: "center",
  };
  sheet.getRange(`A1:${lastCol}1`).format.rowHeight = 28;
  sheet.getRange(`A2:${lastCol}2`).format.rowHeight = 34;
}

function addDataSheet({
  name,
  title,
  note,
  columns,
  rows,
  tableName,
  widths,
  numberFormats = {},
  formulaColumns = {},
}) {
  if (rows.length + 4 > 1_048_576) {
    throw new Error(`${name} has ${rows.length} data rows and exceeds the Excel worksheet row limit.`);
  }
  const sheet = workbook.worksheets.add(name);
  const lastCol = colName(columns.length - 1);
  const headerRow = 4;
  const firstDataRow = 5;
  const lastDataRow = firstDataRow + rows.length - 1;
  addTitle(sheet, title, note, lastCol);
  sheet.getRange(`A${headerRow}:${lastCol}${headerRow}`).values = [columns.map((c) => c.label)];
  sheet.getRange(`A${headerRow}:${lastCol}${headerRow}`).format = {
    fill: COLORS.blue,
    font: { bold: true, color: COLORS.white },
    wrapText: true,
    verticalAlignment: "center",
    borders: { preset: "all", style: "thin", color: COLORS.line },
  };
  sheet.getRange(`A${headerRow}:${lastCol}${headerRow}`).format.rowHeight = 32;
  if (rows.length) {
    writeObjectRows(sheet, firstDataRow, rows, columns);
    sheet.getRange(`A${firstDataRow}:${lastCol}${lastDataRow}`).format = {
      font: { color: COLORS.ink, size: 10 },
      borders: { preset: "all", style: "thin", color: COLORS.line },
      verticalAlignment: "top",
    };
    for (const [columnIndexText, formatCode] of Object.entries(numberFormats)) {
      const columnIndex = Number(columnIndexText);
      const letter = colName(columnIndex);
      sheet.getRange(`${letter}${firstDataRow}:${letter}${lastDataRow}`).format.numberFormat = formatCode;
    }
    for (const [columnIndexText, formula] of Object.entries(formulaColumns)) {
      const columnIndex = Number(columnIndexText);
      const letter = colName(columnIndex);
      sheet.getRange(`${letter}${firstDataRow}`).formulasR1C1 = [[formula]];
      if (lastDataRow > firstDataRow) {
        sheet.getRange(`${letter}${firstDataRow}:${letter}${lastDataRow}`).fillDown();
      }
    }
    const table = sheet.tables.add(`A${headerRow}:${lastCol}${lastDataRow}`, true, tableName);
    table.style = "TableStyleMedium2";
    table.showBandedRows = true;
    table.showFilterButton = true;
  }
  sheet.freezePanes.freezeRows(headerRow);
  setColumnWidths(sheet, widths, Math.max(lastDataRow, headerRow));
  return { sheet, lastDataRow, lastCol };
}

const readMe = workbook.worksheets.add("Read Me");
addTitle(
  readMe,
  "Prediction funnel audit — review-only authority",
  `Run ${payload.meta.run_id} | Registry ${payload.meta.registry_version} | SQLite authority: ${payload.meta.sqlite_path}`,
  "H",
);
let readRow = 4;
for (const section of payload.read_me_sections) {
  readMe.mergeCells(`A${readRow}:H${readRow}`);
  readMe.getRange(`A${readRow}`).values = [[section.title]];
  readMe.getRange(`A${readRow}:H${readRow}`).format = {
    fill: COLORS.blue,
    font: { bold: true, color: COLORS.white },
  };
  readRow += 1;
  for (const item of section.rows) {
    readMe.mergeCells(`B${readRow}:H${readRow}`);
    readMe.getRange(`A${readRow}:B${readRow}`).values = [[item[0], item[1]]];
    readMe.getRange(`A${readRow}`).format = { fill: COLORS.grayLight, font: { bold: true, color: COLORS.ink } };
    readMe.getRange(`B${readRow}:H${readRow}`).format = { wrapText: true, verticalAlignment: "top" };
    readRow += 1;
  }
  readRow += 1;
}
readMe.freezePanes.freezeRows(2);
setColumnWidths(readMe, [24, 18, 18, 18, 18, 18, 18, 18], readRow);

const funnelColumns = payload.funnel_columns;
const funnel = addDataSheet({
  name: "Funnel",
  title: "Candidate and terminal funnel",
  note: "Candidate states are not final routing. S13 is terminal routing; S14 is presentation only. Overall duplicates each physical row exactly once.",
  columns: funnelColumns,
  rows: payload.funnel,
  tableName: "FunnelTable",
  widths: [14, 18, 12, 24, 10, 28, 12, 16, 22, 14, 16, 14, 12, 12, 12, 12, 14, 14, 16, 14, 14, 16, 14, 14],
  numberFormats: { 9: "#,##0", 10: "$#,##0.00", 11: "#,##0.000000", 12: "#,##0", 13: "#,##0", 14: "#,##0", 15: "#,##0", 16: "$#,##0.00", 17: "#,##0", 18: "$#,##0.00", 19: "#,##0.000000", 20: "#,##0", 21: "$#,##0.00", 22: "#,##0.000000", 23: "0.00%" },
  formulaColumns: { 16: "=IFERROR(RC[-6]/RC[-5],\"\")", 23: "=IFERROR(RC[-2]/RC[-5],\"\")" },
});

const removal = addDataSheet({
  name: "Removal Cube",
  title: "Removal and risk cube",
  note: "Primary reasons are additive. Secondary reasons are nonadditive diagnostics and must not be summed into removals. <Unmapped> is distinct from a genuine Unspecified label.",
  columns: payload.removal_columns,
  rows: payload.removal_cube,
  tableName: "RemovalCubeTable",
  widths: [14, 18, 12, 10, 24, 28, 12, 14, 28, 28, 34, 22, 22, 22, 14, 16, 14, 12, 12, 12, 12, 14, 14, 16, 14, 14, 16, 14, 14],
  numberFormats: { 14: "#,##0", 15: "$#,##0.00", 16: "#,##0.000000", 17: "#,##0", 18: "#,##0", 19: "#,##0", 20: "#,##0", 21: "$#,##0.00", 22: "#,##0", 23: "$#,##0.00", 24: "#,##0.000000", 25: "#,##0", 26: "$#,##0.00", 27: "#,##0.000000", 28: "0.00%" },
  formulaColumns: { 21: "=IFERROR(RC[-6]/RC[-5],\"\")", 28: "=IFERROR(RC[-2]/RC[-5],\"\")" },
});

const review = addDataSheet({
  name: "Review Samples",
  title: "Reviewer-ready deterministic sample",
  note: "Exactly 25 rows per output: 12 purposeful targets plus 13 deterministic stratified random rows. Purposeful rows do not support weighted population estimates. Recommendations are shadow-only.",
  columns: payload.review_columns,
  rows: payload.review_samples,
  tableName: "ReviewSamplesTable",
  widths: payload.review_columns.map((column) => {
    if (["evidence", "shadow_recommendation", "detailed_product", "reviewer_rationale"].includes(column.key)) return 34;
    if (["source_row_id", "sample_stratum", "target_category", "primary_reason"].includes(column.key)) return 22;
    return 15;
  }),
  numberFormats: {
    [payload.review_columns.findIndex((c) => c.key === "inclusion_probability")]: "0.000000",
    [payload.review_columns.findIndex((c) => c.key === "sample_weight")]: "0.000",
    [payload.review_columns.findIndex((c) => c.key === "value_usd")]: "$#,##0.00",
    [payload.review_columns.findIndex((c) => c.key === "volume")]: "#,##0.000000",
  },
});
const surgicalColumn = payload.review_columns.findIndex((c) => c.key === "surgical_relevance");
const mappingColumn = payload.review_columns.findIndex((c) => c.key === "mapping_correctness");
if (review.lastDataRow >= 5 && surgicalColumn >= 0) {
  const letter = colName(surgicalColumn);
  review.sheet.getRange(`${letter}5:${letter}${review.lastDataRow}`).dataValidation = {
    rule: { type: "list", values: ["Surgical", "Not surgical", "Uncertain"] },
  };
}
if (review.lastDataRow >= 5 && mappingColumn >= 0) {
  const letter = colName(mappingColumn);
  review.sheet.getRange(`${letter}5:${letter}${review.lastDataRow}`).dataValidation = {
    rule: { type: "list", values: ["Correct", "Incorrect", "Uncertain"] },
  };
}

const recall = workbook.worksheets.add("Recall Risks");
addTitle(
  recall,
  "Complete recall-risk inventory summary",
  "Counts are complete SQLite inventories, not samples. The workbook carries the aggregate plus high-value evidence; query recall_risk_inventory for every row-level record.",
  "I",
);
recall.getRange("A4:I4").values = [["Output", "Label", "Risk type", "Current tier", "Transactions", "Value USD", "Volume", "Weighted ASP", "Inventory scope"]];
recall.getRange("A4:I4").format = { fill: COLORS.blue, font: { bold: true, color: COLORS.white }, wrapText: true };
writeRows(recall, 5, 0, payload.recall_summary.map((row) => [
  row.output_file_id, row.output_label, row.risk_type, row.current_output_tier,
  row.transaction_count, row.value_usd, row.volume,
  row.volume ? row.value_usd / row.volume : null, "Complete SQLite inventory",
]));
const summaryLast = 4 + payload.recall_summary.length;
if (payload.recall_summary.length) {
  recall.getRange(`E5:E${summaryLast}`).format.numberFormat = "#,##0";
  recall.getRange(`F5:F${summaryLast}`).format.numberFormat = "$#,##0.00";
  recall.getRange(`G5:G${summaryLast}`).format.numberFormat = "#,##0.000000";
  recall.getRange(`H5:H${summaryLast}`).format.numberFormat = "$#,##0.00";
}
const evidenceHeader = summaryLast + 3;
recall.mergeCells(`A${evidenceHeader}:I${evidenceHeader}`);
recall.getRange(`A${evidenceHeader}`).values = [["High-value evidence (bounded workbook projection; complete detail remains in SQLite)"]];
recall.getRange(`A${evidenceHeader}:I${evidenceHeader}`).format = { fill: COLORS.ink, font: { bold: true, color: COLORS.white } };
const evidenceColumns = payload.recall_evidence_columns;
const evidenceColumnLast = colName(evidenceColumns.length - 1);
recall.getRange(`A${evidenceHeader + 1}:${evidenceColumnLast}${evidenceHeader + 1}`).values = [evidenceColumns.map((c) => c.label)];
recall.getRange(`A${evidenceHeader + 1}:${evidenceColumnLast}${evidenceHeader + 1}`).format = { fill: COLORS.blue, font: { bold: true, color: COLORS.white }, wrapText: true };
writeRows(recall, evidenceHeader + 2, 0, payload.recall_evidence.map((row) => evidenceColumns.map((column) => row[column.key])));
recall.freezePanes.freezeRows(4);
setColumnWidths(recall, [14, 18, 26, 14, 14, 16, 14, 16, 34], evidenceHeader + 2 + payload.recall_evidence.length);

const qc = addDataSheet({
  name: "Reconciliation QC",
  title: "Reconciliation and acceptance controls",
  note: "Publication fails closed on FAIL. Value tolerance is $0.01; volume tolerance is 0.000001. WARN is retained for documented non-blocking source limitations.",
  columns: payload.qc_columns,
  rows: payload.reconciliation_qc,
  tableName: "ReconciliationQCTable",
  widths: [14, 22, 34, 22, 22, 14, 14, 12, 42, 22],
  numberFormats: { 5: "$#,##0.000000", 6: "#,##0.000000" },
});
const qcStatusIndex = payload.qc_columns.findIndex((c) => c.key === "status");
if (qc.lastDataRow >= 5 && qcStatusIndex >= 0) {
  const statusLetter = colName(qcStatusIndex);
  qc.sheet.getRange(`${statusLetter}5:${statusLetter}${qc.lastDataRow}`).conditionalFormats.add("containsText", {
    text: "FAIL", format: { fill: COLORS.red, font: { bold: true, color: COLORS.ink } },
  });
  qc.sheet.getRange(`${statusLetter}5:${statusLetter}${qc.lastDataRow}`).conditionalFormats.add("containsText", {
    text: "WARN", format: { fill: COLORS.amber, font: { bold: true, color: COLORS.ink } },
  });
  qc.sheet.getRange(`${statusLetter}5:${statusLetter}${qc.lastDataRow}`).conditionalFormats.add("containsText", {
    text: "PASS", format: { fill: COLORS.green, font: { bold: true, color: COLORS.ink } },
  });
}

const lineage = workbook.worksheets.add("Source Lineage");
addTitle(
  lineage,
  "Source lineage and immutable baselines",
  "Absolute paths, SHA-256 hashes, row counts, and numeric-status totals identify the governed inputs used by this run.",
  "Q",
);
lineage.getRange("A4:Q4").values = [[
  "Output", "Label", "Country", "FY", "Source path", "Complete-source path", "Format", "Ingestion mode",
  "Completeness basis", "Expected rows", "Observed rows", "SHA-256", "Bytes", "Value USD", "Volume",
  "Missing/invalid value", "Missing/invalid volume",
]];
lineage.getRange("A4:Q4").format = { fill: COLORS.blue, font: { bold: true, color: COLORS.white }, wrapText: true };
writeRows(lineage, 5, 0, payload.source_lineage.map((row) => [
  row.output_file_id, row.output_label, row.country, row.fiscal_year, row.source_path, row.complete_source_path,
  row.source_format, row.ingestion_mode, row.completeness_basis, row.expected_rows, row.observed_rows,
  row.source_sha256, row.source_bytes, row.value_usd, row.volume,
  `${row.missing_value_count}/${row.invalid_value_count}`, `${row.missing_volume_count}/${row.invalid_volume_count}`,
]));
const sourceLast = 4 + payload.source_lineage.length;
lineage.getRange(`J5:K${sourceLast}`).format.numberFormat = "#,##0";
lineage.getRange(`M5:M${sourceLast}`).format.numberFormat = "#,##0";
lineage.getRange(`N5:N${sourceLast}`).format.numberFormat = "$#,##0.00";
lineage.getRange(`O5:O${sourceLast}`).format.numberFormat = "#,##0.000000";
const manifestHeader = sourceLast + 3;
lineage.mergeCells(`A${manifestHeader}:Q${manifestHeader}`);
lineage.getRange(`A${manifestHeader}`).values = [["Baseline manifest"]];
lineage.getRange(`A${manifestHeader}:Q${manifestHeader}`).format = { fill: COLORS.ink, font: { bold: true, color: COLORS.white } };
lineage.getRange(`A${manifestHeader + 1}:H${manifestHeader + 1}`).values = [["Artifact type", "Path", "SHA-256", "Bytes", "Transactions", "Value USD", "Volume", "Run ID"]];
lineage.getRange(`A${manifestHeader + 1}:H${manifestHeader + 1}`).format = { fill: COLORS.blue, font: { bold: true, color: COLORS.white }, wrapText: true };
writeRows(lineage, manifestHeader + 2, 0, payload.baseline_manifest.map((row) => [
  row.artifact_type, row.path, row.sha256, row.bytes, row.transaction_count, row.value_usd, row.volume, row.run_id,
]));
lineage.freezePanes.freezeRows(4);
setColumnWidths(lineage, [14, 18, 16, 10, 40, 40, 12, 34, 40, 14, 14, 34, 14, 16, 14, 18, 18], manifestHeader + 2 + payload.baseline_manifest.length);

const inspection = await workbook.inspect({
  kind: "workbook,sheet,table,formula",
  maxChars: 12000,
  tableMaxRows: 4,
  tableMaxCols: 8,
  options: { maxResults: 200 },
});
await fs.mkdir(previewDir, { recursive: true });
await fs.writeFile(path.join(previewDir, "workbook_inspection.json"), JSON.stringify(inspection, null, 2));

const previewRanges = {
  "Read Me": "A1:H32",
  Funnel: "A1:X22",
  "Removal Cube": "A1:AC22",
  "Review Samples": "A1:R20",
  "Recall Risks": "A1:I28",
  "Reconciliation QC": "A1:J24",
  "Source Lineage": "A1:Q24",
};
for (const [sheetName, range] of Object.entries(previewRanges)) {
  const preview = await workbook.render({ sheetName, range, scale: 1, format: "png" });
  const fileName = `${sheetName.toLowerCase().replaceAll(" ", "_")}.png`;
  await fs.writeFile(path.join(previewDir, fileName), new Uint8Array(await preview.arrayBuffer()));
}
const reviewerPreview = await workbook.render({
  sheetName: "Review Samples",
  range: "AF1:AS20",
  scale: 1,
  format: "png",
});
await fs.writeFile(
  path.join(previewDir, "review_samples_reviewer_fields.png"),
  new Uint8Array(await reviewerPreview.arrayBuffer()),
);

await fs.mkdir(path.dirname(outputPath), { recursive: true });
const tempOutput = `${outputPath}.building`;
const spreadsheet = await SpreadsheetFile.exportXlsx(workbook);
await spreadsheet.save(tempOutput);
await fs.rename(tempOutput, outputPath);
console.log(JSON.stringify({ output: outputPath, sheets: previewRanges, rows: {
  funnel: payload.funnel.length,
  removal_cube: payload.removal_cube.length,
  review_samples: payload.review_samples.length,
  recall_summary: payload.recall_summary.length,
  reconciliation_qc: payload.reconciliation_qc.length,
} }));
