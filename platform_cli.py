"""Generic project inspection entry point.

Usage: python platform_cli.py inspect PATH [--output report.json]
"""

import argparse
import json
import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from adapters import detect_project
from adapters.input_sources import materialize_source
from config.settings import (
    BASE_DIR,
    DOCKER_TIMEOUT_SECONDS,
    MAX_ITERATIONS,
    MIN_RELEVANCE_SCORE,
    RUNNER_IMAGE,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect a project for SmartTest-AI adapter support")
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect", help="detect languages, tests, configuration and adapter support")
    inspect.add_argument("path", type=Path)
    inspect.add_argument("--output", type=Path)
    run = sub.add_parser("run", help="run the generic Python agent workflow in Docker")
    run.add_argument("source", help="directory, .zip archive, or HTTPS/SSH Git URL")
    run.add_argument("--model", help="Ollama model name (defaults to OLLAMA_MODEL / qwen2.5-coder:7b)")
    run.add_argument("--iterations", type=int, default=MAX_ITERATIONS)
    run.add_argument("--min-quality", type=float, default=MIN_RELEVANCE_SCORE)
    run.add_argument("--timeout", type=int, default=DOCKER_TIMEOUT_SECONDS)
    run.add_argument("--docker-image", default=RUNNER_IMAGE, help="Docker image with the project's dependencies, pytest and pytest-cov preinstalled")
    run.add_argument("--task-statement", type=Path, help="Optional UTF-8 file containing an issue description or task context")
    args = parser.parse_args()
    if args.command == "inspect":
        report = detect_project(args.path).to_dict()
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
        return 0 if report["supported"] else 2

    if args.iterations < 1 or args.iterations > 5:
        parser.error("--iterations must be between 1 and 5")
    if args.timeout < 1:
        parser.error("--timeout must be a positive number")
    if args.model:
        os.environ["OLLAMA_MODEL"] = args.model
    source_key = Path(args.source).stem if not args.source.startswith(("https://", "ssh://", "git@")) else args.source.rsplit("/", 1)[-1].removesuffix(".git")
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", source_key).strip("._")[:60] or "project"
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    run_dir = BASE_DIR / "experiments" / "projects" / safe_name / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    try:
        source_root, source_kind = materialize_source(args.source, run_dir / "source")
        from graph.generic_workflow import build_generic_workflow
        workflow = build_generic_workflow()
        task_context = args.task_statement.read_text(encoding="utf-8") if args.task_statement else ""
        state = workflow.invoke({
            "project_path": str(source_root), "project_name": safe_name, "run_id": run_id,
            "run_dir": str(run_dir), "iteration": 0, "max_iterations": args.iterations,
            "min_quality_score": args.min_quality, "timeout_seconds": args.timeout,
            "docker_image": args.docker_image, "source_kind": source_kind, "errors": [], "task_context": task_context,
        })
        report = state.get("final_report", {})
        report["source_kind"] = source_kind
        report["model"] = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
        (run_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        (run_dir / "report.md").write_text("# SmartTest-AI generic run\n\n" + "```json\n" + json.dumps(report, ensure_ascii=False, indent=2) + "\n```\n", encoding="utf-8")
        print(json.dumps({"run_id": run_id, "run_dir": str(run_dir), "status": report.get("status"), "coverage_before": report.get("coverage_before"), "coverage_after": report.get("coverage_after"), "critic": report.get("critic")}, ensure_ascii=False, indent=2))
        return 0 if not state.get("run_error") else 1
    except Exception as error:
        (run_dir / "error.txt").write_text(f"{type(error).__name__}: {error}\n", encoding="utf-8")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
