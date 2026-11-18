"""Generic project inspection entry point.

Usage: python platform_cli.py inspect PATH [--output report.json]
"""

import argparse
import json
from pathlib import Path

from adapters import detect_project


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect a project for SmartTest-AI adapter support")
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect", help="detect languages, tests, configuration and adapter support")
    inspect.add_argument("path", type=Path)
    inspect.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = detect_project(args.path).to_dict()
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["supported"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
