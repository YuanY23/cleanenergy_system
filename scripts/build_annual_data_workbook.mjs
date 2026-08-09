import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

function arg(name) {
  const index = process.argv.indexOf(name);
  if (index < 0 || index + 1 >= process.argv.length) {
    throw new Error(`missing required argument ${name}`);
  }
  return process.argv[index + 1];
}

const annualPath = arg("--annual");
const sourcesPath = arg("--sources");
const outputPath = arg("--output");
const annualCsv = await fs.readFile(annualPath, "utf8");
const sourcesCsv = await fs.readFile(sourcesPath, "utf8");
const workbook = await Workbook.fromCSV(annualCsv, { sheetName: "Annual_8784" });
await workbook.fromCSV(sourcesCsv, { sheetName: "Source_Register" });

const annual = workbook.worksheets.getItem("Annual_8784");
const sources = workbook.worksheets.getItem("Source_Register");
const used = annual.getUsedRange(true);
if (used.rowCount !== 8785) {
  throw new Error(`Annual_8784 must contain one header plus 8784 hours, got ${used.rowCount}`);
}

const headerStyle = {
  fill: "#17365D",
  font: { bold: true, color: "#FFFFFF" },
  verticalAlignment: "center",
  wrapText: true,
  borders: { preset: "outside", style: "thin", color: "#AAB7C4" },
};
annual.getRangeByIndexes(0, 0, 1, used.columnCount).format = headerStyle;
annual.freezePanes.freezeRows(1);
annual.showGridLines = false;
annual.getRangeByIndexes(0, 0, used.rowCount, used.columnCount).format.rowHeight = 18;
annual.getRange("A:B").format.columnWidth = 24;
annual.getRange("C:H").format.columnWidth = 18;
annual.tables.add(`A1:H${used.rowCount}`, true, "AnnualWeatherTable");

const sourceUsed = sources.getUsedRange(true);
sources.getRangeByIndexes(0, 0, 1, sourceUsed.columnCount).format = headerStyle;
sources.freezePanes.freezeRows(1);
sources.showGridLines = false;
sources.getRangeByIndexes(0, 0, sourceUsed.rowCount, sourceUsed.columnCount).format.wrapText = true;
sources.getRange("A:B").format.columnWidth = 26;
sources.getRange("C:C").format.columnWidth = 20;
sources.getRange("D:D").format.columnWidth = 45;
sources.getRange("E:R").format.columnWidth = 18;
sources.tables.add(`A1:R${sourceUsed.rowCount}`, true, "SourceRegistryTable");

const summary = workbook.worksheets.add("Monthly_Audit");
summary.showGridLines = false;
summary.getRange("A1:H1").merge();
summary.getRange("A1").values = [["2024年8784小时气象与风光资源审计"]];
summary.getRange("A1:H1").format = {
  fill: "#0F6B5D",
  font: { bold: true, color: "#FFFFFF", size: 18 },
  rowHeight: 34,
  verticalAlignment: "center",
};
summary.getRange("A3:B7").values = [
  ["研究年度", 2024],
  ["有效小时", 8784],
  ["生产气象源", "ERA5小时单层数据"],
  ["负荷性质", "公开尺度校准的合成情景，非SCADA实测"],
  ["碳口径", "0.6479位置法与0.8325零碳园区口径分列"],
];
summary.getRange("A3:A7").format = { fill: "#DDEBF7", font: { bold: true } };
summary.getRange("A3:B7").format.borders = { preset: "outside", style: "thin", color: "#AAB7C4" };
summary.getRange("A9:G9").values = [[
  "月份", "平均100m风速(m/s)", "平均辐照度(W/m²)", "平均气温(°C)",
  "光伏容量因子", "风电容量因子(未校准)", "风电容量因子(校准)",
]];
summary.getRange("A9:G9").format = headerStyle;

const annualRows = annual.getRange(`A2:H${used.rowCount}`).values;
const monthRanges = [];
for (let month = 1; month <= 12; month += 1) {
  const indices = [];
  for (let i = 0; i < annualRows.length; i += 1) {
    const raw = annualRows[i][1];
    const text = raw instanceof Date ? raw.toISOString() : String(raw);
    const parsedMonth = Number(text.slice(5, 7));
    if (parsedMonth === month) indices.push(i + 2);
  }
  if (indices.length === 0) throw new Error(`missing rows for month ${month}`);
  monthRanges.push([indices[0], indices[indices.length - 1]]);
}

for (let month = 1; month <= 12; month += 1) {
  const row = 9 + month;
  const [startRow, endRow] = monthRanges[month - 1];
  summary.getRange(`A${row}`).values = [[`${month}月`]];
  const sourceColumns = ["C", "D", "E", "F", "G", "H"];
  sourceColumns.forEach((column, offset) => {
    summary.getCell(row - 1, offset + 1).formulas = [[
      `=AVERAGE('Annual_8784'!$${column}$${startRow}:$${column}$${endRow})`,
    ]];
  });
}
summary.getRange("B10:G21").format.numberFormat = "0.000";
summary.getRange("A9:G21").format.borders = {
  insideHorizontal: { style: "thin", color: "#D9E2F3" },
  bottom: { style: "thin", color: "#AAB7C4" },
};
summary.getRange("A:A").format.columnWidth = 12;
summary.getRange("B:G").format.columnWidth = 22;
summary.freezePanes.freezeRows(9);

const chart = summary.charts.add("line", {
  chartType: "line",
  title: "月度风电容量因子校准前后对比",
  hasLegend: false,
});
const uncalibrated = chart.series.add("风电容量因子(未校准)");
uncalibrated.categoryFormula = "'Monthly_Audit'!$A$10:$A$21";
uncalibrated.formula = "'Monthly_Audit'!$F$10:$F$21";
uncalibrated.fill = "#5B9BD5";
const calibrated = chart.series.add("风电容量因子(校准)");
calibrated.categoryFormula = "'Monthly_Audit'!$A$10:$A$21";
calibrated.formula = "'Monthly_Audit'!$G$10:$G$21";
calibrated.fill = "#70AD47";
chart.hasLegend = false;
chart.xAxis = { axisType: "textAxis" };
chart.yAxis = { numberFormatCode: "0.00", min: 0, max: 1 };
chart.setPosition("I3", "Q19");
summary.getRange("I20:L20").merge();
summary.getRange("I20").values = [["蓝色：未校准"]];
summary.getRange("I20:L20").format = { font: { bold: true, color: "#5B9BD5" } };
summary.getRange("M20:Q20").merge();
summary.getRange("M20").values = [["绿色：校准后"]];
summary.getRange("M20:Q20").format = { font: { bold: true, color: "#70AD47" } };

const readme = workbook.worksheets.add("README");
readme.showGridLines = false;
readme.getRange("A1:F1").merge();
readme.getRange("A1").values = [["零碳工业园区年度数据包说明"]];
readme.getRange("A1:F1").format = {
  fill: "#17365D",
  font: { bold: true, color: "#FFFFFF", size: 18 },
  rowHeight: 34,
};
readme.getRange("A3:B10").values = [
  ["正式用途", "8784小时规划、全年回放与孤网保供分析的数据审计附件"],
  ["生产源", "ERA5；NASA POWER仅作月度交叉校核，Global Wind Atlas仅作长期偏差敏感性"],
  ["时间口径", "保留UTC与Asia/Shanghai，本表覆盖2024-01-01 00:00至2024-12-31 23:00"],
  ["真实性边界", "气象为再分析数据，负荷为透明合成情景，均不表述为园区实测"],
  ["工作表", "Annual_8784、Monthly_Audit、Source_Register、README"],
  ["数据污染控制", "仅消费显式传入的data/processed文件，不读取outputs或根目录旧工作簿"],
  ["碳口径", "企业位置法与国家零碳园区试行方法分别核算，禁止混算"],
  ["更新方式", "先重建原始数据与manifest，再重新生成本工作簿"],
];
readme.getRange("A3:A10").format = { fill: "#DDEBF7", font: { bold: true } };
readme.getRange("A3:B10").format.wrapText = true;
readme.getRange("A:A").format.columnWidth = 22;
readme.getRange("B:B").format.columnWidth = 90;

const summaryCheck = await workbook.inspect({
  kind: "table",
  range: "Monthly_Audit!A1:G21",
  include: "values,formulas",
  tableMaxRows: 21,
  tableMaxCols: 7,
});
const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "final formula error scan",
});
if (!errors.ndjson.includes("matched 0 entries")) {
  throw new Error(`workbook formula error scan failed: ${errors.ndjson}`);
}

await fs.mkdir(path.dirname(outputPath), { recursive: true });
const preview = await workbook.render({ sheetName: "Monthly_Audit", range: "A1:Q21", scale: 1.4 });
await fs.writeFile(
  path.join(path.dirname(outputPath), "annual_data_audit_preview.png"),
  new Uint8Array(await preview.arrayBuffer()),
);
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
process.stdout.write(`${summaryCheck.ndjson}\n${outputPath}\n`);
