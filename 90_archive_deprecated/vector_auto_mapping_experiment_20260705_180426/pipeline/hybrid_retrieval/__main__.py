"""Command-line entry points for the hybrid retrieval experiment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .experiment import run_experiment, write_new_target_candidates
from .objects import build_retrieval_objects
from .reports import write_all_reports, write_evaluation_report


def _expand_inputs(paths: list[str]) -> list[str]:
    expanded: list[str] = []
    for raw_path in paths:
        path = Path(raw_path)
        if path.is_dir():
            for workbook in sorted(path.glob("*_ML_Map_Mapped*.xlsx")):
                if not workbook.name.startswith("~$"):
                    expanded.append(str(workbook))
        elif path.exists() and not path.name.startswith("~$"):
            expanded.append(str(path))
    return expanded


def cmd_build_objects(args: argparse.Namespace) -> None:
    objects = build_retrieval_objects(args.reference, reference_version=args.reference_version)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    objects.to_csv(output, index=False, encoding="utf-8-sig")
    counts = objects["object_type"].value_counts().to_dict()
    print(json.dumps({"output": str(output), "rows": int(len(objects)), "object_types": counts}, indent=2))


def cmd_build_indexes(args: argparse.Namespace) -> None:
    objects_path = Path(args.objects)
    config_path = Path(args.config)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    counts: dict[str, int] = {}
    rows = 0
    if objects_path.exists():
        objects = pd.read_csv(objects_path)
        rows = int(len(objects))
        if "object_type" in objects.columns:
            counts = {str(k): int(v) for k, v in objects["object_type"].value_counts().to_dict().items()}

    manifest = {
        "status": "built",
        "index_mode": "local_in_memory_proxy",
        "note": (
            "The experiment uses auditable local lexical indexes and a deterministic "
            "hashed n-gram vector proxy at run time. No production vector store is "
            "created by this command."
        ),
        "config": str(config_path),
        "retrieval_objects": str(objects_path),
        "object_rows": rows,
        "object_type_counts": counts,
    }
    output.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "rows": rows}, indent=2))


def cmd_run_experiment(args: argparse.Namespace) -> None:
    inputs = _expand_inputs(args.input)
    if not inputs:
        raise SystemExit("No input workbooks found.")
    summary = run_experiment(
        input_paths=inputs,
        retrieval_objects_path=args.objects,
        config_path=args.config,
        output_dir=args.output_dir,
        sample_size_per_tier=args.sample_size,
    )
    print(json.dumps({"output_dir": args.output_dir, "inputs": len(inputs), "summary": summary}, indent=2))


def cmd_discover_targets(args: argparse.Namespace) -> None:
    input_path = Path(args.input)
    if input_path.suffix.lower() in {".xlsx", ".xlsm"}:
        audit = pd.read_excel(input_path)
    else:
        audit = pd.read_csv(input_path)
    write_new_target_candidates(audit.fillna(""), Path(args.output))
    print(json.dumps({"output": args.output, "source_rows": int(len(audit))}, indent=2))


def cmd_report(args: argparse.Namespace) -> None:
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_evaluation_report(args.experiment_results, output_path)
    print(json.dumps({"output": str(output_path)}, indent=2))


def cmd_write_all_reports(args: argparse.Namespace) -> None:
    write_all_reports(args.output_dir, args.reports_dir)
    print(json.dumps({"reports_dir": args.reports_dir}, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m pipeline.hybrid_retrieval")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_objects = subparsers.add_parser("build-objects", help="Build retrieval objects from the latest master reference.")
    build_objects.add_argument("--reference", required=True)
    build_objects.add_argument("--output", default="outputs/retrieval_objects.csv")
    build_objects.add_argument("--reference-version", default="Surg_Brand_model_list_Master_03July26 Updated")
    build_objects.set_defaults(func=cmd_build_objects)

    build_indexes = subparsers.add_parser("build-indexes", help="Write an index manifest for the local experiment.")
    build_indexes.add_argument("--config", default="configs/hybrid_retrieval_experiment.yaml")
    build_indexes.add_argument("--objects", default="outputs/retrieval_objects.csv")
    build_indexes.add_argument("--output", default="outputs/hybrid_retrieval_index_manifest.json")
    build_indexes.set_defaults(func=cmd_build_indexes)

    run = subparsers.add_parser("run-experiment", help="Run A/B/C/D hybrid retrieval variants.")
    run.add_argument("--input", nargs="+", required=True, help="Workbook paths or folders containing mapped workbooks.")
    run.add_argument("--objects", default="outputs/retrieval_objects.csv")
    run.add_argument("--config", default="configs/hybrid_retrieval_experiment.yaml")
    run.add_argument("--output-dir", default="outputs")
    run.add_argument("--sample-size", type=int, default=250, help="Rows sampled per workbook output tier.")
    run.set_defaults(func=cmd_run_experiment)

    discover = subparsers.add_parser("discover-targets", help="Generate new-target discovery workbook from an audit file.")
    discover.add_argument("--input", default="outputs/retrieval_audit.csv")
    discover.add_argument("--config", default="configs/hybrid_retrieval_experiment.yaml")
    discover.add_argument("--output", default="outputs/new_target_candidates.xlsx")
    discover.set_defaults(func=cmd_discover_targets)

    report = subparsers.add_parser("report", help="Generate the evaluation report.")
    report.add_argument("--experiment-results", default="outputs")
    report.add_argument("--output", default="reports/hybrid_vector_evaluation_report.md")
    report.set_defaults(func=cmd_report)

    all_reports = subparsers.add_parser("write-all-reports", help="Generate all markdown reports.")
    all_reports.add_argument("--output-dir", default="outputs")
    all_reports.add_argument("--reports-dir", default="reports")
    all_reports.set_defaults(func=cmd_write_all_reports)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
