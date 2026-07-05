#!/usr/bin/env python3
"""Build a static CodeGraph for the repository."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.codegraph import CodeGraph  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a static Python CodeGraph")
    parser.add_argument("--format", choices=("json", "markdown", "dot"), default="markdown")
    parser.add_argument("--output", type=Path, help="write graph to this file instead of stdout")
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root to scan")
    args = parser.parse_args()

    graph = CodeGraph.from_repo(args.root)
    if args.format == "json":
        content = graph.to_json()
    elif args.format == "dot":
        content = graph.to_dot()
    else:
        content = graph.to_markdown()

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content + "\n", encoding="utf-8")
    else:
        print(content)


if __name__ == "__main__":
    main()
