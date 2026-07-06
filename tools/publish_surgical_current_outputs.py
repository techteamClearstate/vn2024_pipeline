from __future__ import annotations

from collections import OrderedDict
from datetime import datetime
from pathlib import Path
import shutil

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
CURRENT_DIR = Path(r"D:\vn2024_remapped_current")
REPORT_DIR = CURRENT_DIR / "reports"
SHARED_DIR = Path(
    r"G:\共享云端硬盘\New EIU Gateway\0. Gateway Ops & Databases\Import Data Master\6. Workflow\Surgicals\Claude code\1. Mapped Results"
)
ARCHIVE_DIR = Path(r"D:\vn2024_remapped_staging\shared_folder_old_duplicates")
TIMESTAMP = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
EXPECTED_FILES = [
    "Pakistan_FY2024_ML_Map_Mapped.xlsx",
    "Pakistan_FY2025_ML_Map_Mapped.xlsx",
    "India_FY2024_ML_Map_Mapped.xlsx",
    "India_FY2025_ML_Map_Mapped.xlsx",
    "Vietnam_FY2024_ML_Map_Mapped.xlsx",
    "Vietnam_FY2025_ML_Map_Mapped.xlsx",
]


def write_workbook(path: Path, tables: OrderedDict[str, pd.DataFrame]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        writer.book.use_zip64()
        for sheet_name, frame in tables.items():
            if frame is None or frame.empty:
                frame = pd.DataFrame({"Note": ["No rows"]})
            frame.to_excel(writer, sheet_name=sheet_name[:31], index=False)
            worksheet = writer.sheets[sheet_name[:31]]
            worksheet.freeze_panes(1, 0)
            worksheet.autofilter(0, 0, min(len(frame), 1_048_575), max(len(frame.columns) - 1, 0))
            for idx, column in enumerate(frame.columns[:60]):
                sample = frame.iloc[:, idx].head(100).map(lambda value: "" if pd.isna(value) else str(value))
                width = min(max([len(str(column)), *sample.map(len).tolist()]) + 2, 44)
                worksheet.set_column(idx, idx, width)


def read_sheet(path: Path, sheet_name: str) -> pd.DataFrame:
    try:
        frame = pd.read_excel(path, sheet_name=sheet_name)
    except ValueError:
        return pd.DataFrame()
    if "Note" in frame.columns and len(frame.columns) == 1:
        return pd.DataFrame()
    return frame


def report_path_for(output_name: str) -> Path:
    country, year = output_name.split("_FY", 1)
    year = year.split("_", 1)[0]
    return REPORT_DIR / f"{country}_FY{year}_Surgical_Mapping_QA_Report.xlsx"


def add_file_meta(frame: pd.DataFrame, output_name: str) -> pd.DataFrame:
    if frame.empty:
        return frame
    country, year = output_name.split("_FY", 1)
    frame = frame.copy()
    frame.insert(0, "Country", country)
    frame.insert(1, "Year", year.split("_", 1)[0])
    frame.insert(2, "Source_File", output_name)
    return frame


def combine_sheet(sheet_name: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for output_name in EXPECTED_FILES:
        path = report_path_for(output_name)
        frame = read_sheet(path, sheet_name)
        if not frame.empty and not {"Country", "Year"}.issubset(frame.columns):
            frame = add_file_meta(frame, output_name)
        frames.append(frame)
    frames = [frame for frame in frames if frame is not None and not frame.empty]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def metrics_for_log(metrics: pd.DataFrame) -> pd.DataFrame:
    if metrics.empty:
        return pd.DataFrame()
    improved = metrics.loc[metrics.get("Run", "").astype(str).str.contains("A1", na=False)].copy()
    if improved.empty:
        improved = metrics.copy()
    keep = [
        "Country",
        "Year",
        "Run",
        "RawData rows",
        "RawData value",
        "Trusted rows",
        "Trusted value",
        "Review rows",
        "Review value",
        "Excluded rows",
        "Excluded value",
        "Surgicalish excluded rows",
        "Surgicalish excluded value",
        "Trusted precision proxy",
        "Trusted recall proxy rows",
        "Trusted recall proxy value",
        "Capture recall proxy rows",
        "Capture recall proxy value",
        "Trusted precision-risk rows",
        "Trusted precision-risk value",
        "High-value review rows >=50K",
        "High-value review value >=50K",
        "Runtime seconds",
        "LLM calls",
        "LLM token cost USD",
    ]
    for column in keep:
        if column not in improved.columns:
            improved[column] = ""
    improved = improved[keep].copy()
    improved.insert(0, "Log_Update_Timestamp", TIMESTAMP)
    improved["Process_Version"] = "A1 Recall/Evidence Remap"
    improved["Business_Priority"] = "Higher recall with auditable, master-valid trusted dashboard"
    improved["Trusted_Reference_Guardrail"] = "Trusted rows require latest master tuple/category validation"
    improved["Output_Package"] = str(CURRENT_DIR)
    return improved


def build_acceptance(validation: pd.DataFrame) -> pd.DataFrame:
    if validation.empty:
        return pd.DataFrame()
    for column in ["Country", "Year", "Status"]:
        if column not in validation.columns:
            validation[column] = ""
    summary = (
        validation.assign(Status=validation["Status"].astype(str))
        .groupby(["Country", "Year", "Status"], dropna=False)
        .size()
        .reset_index(name="Check_Count")
    )
    failures = validation.loc[validation["Status"].astype(str).eq("FAIL")].copy()
    failures["Log_Update_Timestamp"] = TIMESTAMP
    return pd.concat(
        [
            summary.assign(Table="Status_Summary"),
            failures.assign(Table="Failure_Detail"),
        ],
        ignore_index=True,
        sort=False,
    )


def archive_duplicate_shared_outputs() -> pd.DataFrame:
    archive_rows: list[dict[str, str]] = []
    allowed = set(EXPECTED_FILES)
    for item in SHARED_DIR.glob("*_FY*_ML_Map_Mapped*.xlsx"):
        if item.name in allowed:
            continue
        target_dir = ARCHIVE_DIR / datetime.now().strftime("%Y%m%d_%H%M%S")
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / item.name
        shutil.move(str(item), str(target))
        archive_rows.append(
            {
                "Archived_Timestamp": TIMESTAMP,
                "Original_Path": str(item),
                "Archive_Path": str(target),
                "Reason": "Removed duplicate/non-current mapped output from shared folder",
            }
        )
    return pd.DataFrame(archive_rows)


def publish_outputs() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for name in EXPECTED_FILES:
        source = CURRENT_DIR / name
        if not source.exists():
            raise FileNotFoundError(f"Missing current output: {source}")
        target = SHARED_DIR / name
        shutil.copy2(source, target)
        rows.append(
            {
                "Published_Timestamp": TIMESTAMP,
                "Source_File": str(source),
                "Shared_File": str(target),
                "File_Name": name,
                "File_Size_Bytes": target.stat().st_size,
                "Shared_LastWriteTime": datetime.fromtimestamp(target.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "Status": "Published current version",
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    missing_outputs = [name for name in EXPECTED_FILES if not (CURRENT_DIR / name).exists()]
    missing_reports = [str(report_path_for(name)) for name in EXPECTED_FILES if not report_path_for(name).exists()]
    if missing_outputs or missing_reports:
        raise FileNotFoundError(
            "Missing required files before publishing:\n"
            + "\n".join([*missing_outputs, *missing_reports])
        )

    archived = archive_duplicate_shared_outputs()
    published = publish_outputs()

    metrics = combine_sheet("Baseline_vs_Improved")
    validation = combine_sheet("Validation")
    changes = combine_sheet("Changes_Applied")
    alias = combine_sheet("Alias_Update_Request")
    reference = combine_sheet("Reference_Update_Request")
    extended = combine_sheet("Extended_Surgical_Decision")
    precision = combine_sheet("Precision_Risk_Rows")
    missed = combine_sheet("Potential_Missed_Surgical")
    clusters = combine_sheet("Review_Queue_Clusters")
    excluded = combine_sheet("Excluded_Surgicalish")
    recommendations = combine_sheet("Workflow_Recommendations")

    combined_qa = OrderedDict(
        [
            ("Metrics_By_File", metrics),
            ("Validation_By_File", validation),
            ("Change_Log", changes),
            ("Alias_Update_Request", alias),
            ("Reference_Update_Request", reference),
            ("Extended_Surgical_Decision", extended),
            ("Precision_Risk_Rows", precision),
            ("Potential_Missed_Surgical", missed),
            ("Review_Queue_Clusters", clusters),
            ("Excluded_Surgicalish", excluded),
            ("Workflow_Recommendations", recommendations),
            ("Published_Files", published),
            ("Archived_Duplicates", archived),
        ]
    )
    write_workbook(REPORT_DIR / "All_Countries_Surgical_Mapping_QA_Report.xlsx", combined_qa)

    log_tables = OrderedDict(
        [
            ("Mapping_Log", metrics_for_log(metrics)),
            ("File_Run_Summary", metrics),
            ("Acceptance_Checks", build_acceptance(validation)),
            ("Published_Files", published),
            ("Archived_Duplicates", archived),
            ("Iteration_Details", changes),
            ("Alias_Update_Request", alias),
            ("Reference_Update_Request", reference),
            ("Extended_Surgical_Decision", extended),
            ("Workflow_Recommendations", recommendations),
        ]
    )
    write_workbook(SHARED_DIR / "MAPPING_IMPROVEMENT_LOG.xlsx", log_tables)

    published.to_excel(REPORT_DIR / "Published_Files.xlsx", index=False)
    print(f"Published {len(published)} current workbooks to {SHARED_DIR}")
    print(f"Combined QA report: {REPORT_DIR / 'All_Countries_Surgical_Mapping_QA_Report.xlsx'}")
    print(f"Mapping log: {SHARED_DIR / 'MAPPING_IMPROVEMENT_LOG.xlsx'}")
    if not archived.empty:
        print(f"Archived {len(archived)} duplicate mapped output files")


if __name__ == "__main__":
    main()
