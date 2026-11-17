"""Build CSV and Markdown summaries from completed experiment runs."""

import argparse
import csv
import json
from pathlib import Path

from experiments.tracking import EXPERIMENTS_DIR

FIELDS = [
    "benchmark", "mode", "run_id", "status", "coverage_before",
    "coverage_after", "coverage_delta_percentage_points",
    "branch_coverage_before", "branch_coverage_after",
]


def collect_runs(root: Path) -> list[dict]:
    rows = []
    for result_path in root.glob("*/*/benchmark_results.json"):
        metadata_path = result_path.with_name("metadata.json")
        if not metadata_path.exists():
            continue
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        result = json.loads(result_path.read_text(encoding="utf-8"))
        rows.append({key: result.get(key, metadata.get(key)) for key in FIELDS})
    return sorted(rows, key=lambda row: (row["benchmark"] or "", row["mode"] or "", row["run_id"] or ""))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=EXPERIMENTS_DIR)
    args = parser.parse_args()
    rows = collect_runs(args.root)
    args.root.mkdir(parents=True, exist_ok=True)
    with (args.root / "comparison.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    lines = ["# Comparaison des expériences", "", "| " + " | ".join(FIELDS) + " |", "|" + "|".join(["---"] * len(FIELDS)) + "|"]
    lines.extend("| " + " | ".join(str(row.get(field, "")) for field in FIELDS) + " |" for row in rows)
    (args.root / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(rows)} expériences indexées dans {args.root}")


if __name__ == "__main__":
    main()
