"""SWE-bench Lite adapter.

The `run-tests` mode measures generated-test behavior on the base revision. It
does NOT score instance resolution. `official-eval` delegates patch evaluation
to the upstream SWE-bench harness and requires genuine model patches.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from config.settings import BASE_DIR

DATASET = "SWE-bench/SWE-bench_Lite"


def load_instances(split: str = "test", *, with_metadata: bool = False):
    try:
        from datasets import load_dataset
    except (ImportError, AttributeError) as error:
        raise RuntimeError("Install the optional SWE-bench dependencies: pip install -r requirements-swebench.txt") from error
    dataset = load_dataset(DATASET, split=split)
    rows = [dict(row) for row in dataset]
    return (rows, getattr(dataset, "_fingerprint", None)) if with_metadata else rows


def public_instance(instance: dict) -> dict:
    """Drop gold patch fields so task prep cannot leak answers to the model."""
    fields = ("instance_id", "repo", "base_commit", "problem_statement", "version", "issue_url", "pr_url")
    return {key: instance.get(key) for key in fields if key in instance}


def prepare(args) -> int:
    instances, fingerprint = load_instances(args.split, with_metadata=True)
    if args.instance_id:
        wanted = set(args.instance_id)
        instances = [row for row in instances if row.get("instance_id") in wanted]
        missing = wanted - {row.get("instance_id") for row in instances}
        if missing:
            raise ValueError(f"Instance IDs not found in {DATASET}/{args.split}: {sorted(missing)}")
    elif args.limit:
        import random
        instances = random.Random(args.seed).sample(instances, min(args.limit, len(instances)))
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    output = BASE_DIR / "experiments" / "swebench" / run_id
    output.mkdir(parents=True)
    manifest = {"benchmark": "swebench-lite", "dataset": DATASET, "dataset_fingerprint": fingerprint, "split": args.split, "seed": args.seed, "run_id": run_id, "task_count": len(instances), "protocol": "base-revision generated-test analysis; not official SWE-bench resolution"}
    for instance in instances:
        task_id = str(instance.get("instance_id", ""))
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", task_id):
            raise ValueError(f"Unexpected SWE-bench instance ID: {task_id!r}")
        folder = output / "tasks" / task_id
        folder.mkdir(parents=True)
        (folder / "task.json").write_text(json.dumps(public_instance(instance), ensure_ascii=False, indent=2), encoding="utf-8")
        (folder / "problem_statement.md").write_text(str(instance.get("problem_statement", "")), encoding="utf-8")
    (output / "metadata.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "report.md").write_text(
        f"# SWE-bench Lite task preparation\n\n- Run: `{run_id}`\n- Split: `{args.split}`\n- Prepared tasks: {len(instances)}\n\nGold patch and test patch fields were excluded. This artifact is for test-generation research on base revisions; it does not report a SWE-bench resolved score.\n",
        encoding="utf-8",
    )
    print(json.dumps({"run_id": run_id, "run_dir": str(output), "tasks": len(instances)}, indent=2))
    return 0


def _git(*args: str, cwd: Path | None = None, timeout: int = 900) -> None:
    result = subprocess.run(["git", *args], check=False, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"Git command failed ({result.returncode}): {(result.stderr or result.stdout)[-2500:]}")


def run_tests(args) -> int:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+__[A-Za-z0-9_.-]+-\d+", args.instance_id):
        raise ValueError("instance ID must use SWE-bench's owner__repo-number format")
    instances, fingerprint = load_instances(args.split, with_metadata=True)
    task = next((row for row in instances if row.get("instance_id") == args.instance_id), None)
    if task is None:
        raise ValueError(f"Instance {args.instance_id} not found in {DATASET}/{args.split}")
    repo = str(task.get("repo", ""))
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError(f"Unexpected repository field in official dataset: {repo!r}")
    commit = str(task.get("base_commit", ""))
    if not re.fullmatch(r"[0-9a-fA-F]{7,64}", commit):
        raise ValueError("Dataset base_commit is not a valid Git SHA")
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    run_dir = BASE_DIR / "experiments" / "swebench-tests" / args.instance_id / run_id
    run_dir.mkdir(parents=True)
    source = run_dir / "source"
    source.mkdir()
    _git("init", str(source))
    _git("-C", str(source), "remote", "add", "origin", f"https://github.com/{repo}.git")
    _git("-C", str(source), "fetch", "--depth", "1", "origin", commit)
    _git("-C", str(source), "checkout", "--detach", "FETCH_HEAD")
    issue_file = run_dir / "problem_statement.md"
    issue_file.write_text(str(task.get("problem_statement", "")), encoding="utf-8")
    from graph.generic_workflow import build_generic_workflow
    state = build_generic_workflow().invoke({
        "project_path": str(source), "project_name": args.instance_id, "run_id": run_id,
        "run_dir": str(run_dir), "iteration": 0, "max_iterations": args.iterations,
        "min_quality_score": args.min_quality, "timeout_seconds": args.timeout,
        "docker_image": args.docker_image, "task_context": issue_file.read_text(encoding="utf-8"), "errors": [],
    })
    report = state.get("final_report", {})
    report.update({"benchmark": "SWE-bench Lite", "dataset_fingerprint": fingerprint, "instance_id": args.instance_id, "repository": repo, "base_commit": commit, "evaluation_protocol": "generated-test execution on base revision; not an official SWE-bench resolution score"})
    (run_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "benchmark_results.json").write_text(json.dumps({
        "benchmark": "swebench-lite-test-generation", "instance_id": args.instance_id,
        "status": report.get("status"), "coverage_before": report.get("coverage_before"),
        "coverage_after": report.get("coverage_after"), "critic": report.get("critic"),
        "execution": report.get("execution"), "protocol": report["evaluation_protocol"],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"run_id": run_id, "run_dir": str(run_dir), "status": report.get("status"), "protocol": report["evaluation_protocol"]}, ensure_ascii=False, indent=2))
    return 0 if not state.get("run_error") else 1


def official_eval(args) -> int:
    if os.name == "nt":
        raise RuntimeError("The official SWE-bench harness uses Unix resource controls. Run it from WSL2/Linux with Docker available; see README for the command.")
    predictions = Path(args.predictions).expanduser().resolve()
    if not predictions.is_file():
        raise FileNotFoundError(predictions)
    run_id = args.run_id or (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8])
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", run_id):
        raise ValueError("run-id may contain only letters, digits, underscore, dot and hyphen")
    output = BASE_DIR / "experiments" / "swebench-official" / run_id
    output.mkdir(parents=True, exist_ok=False)
    command = [sys.executable, "-m", "swebench.harness.run_evaluation", "--dataset_name", DATASET,
               "--split", args.split, "--predictions_path", str(predictions), "--max_workers", str(args.workers), "--run_id", run_id]
    if args.instance_id:
        command.extend(["--instance_ids", *args.instance_id])
    (output / "command.json").write_text(json.dumps({"command": command, "warning": "Official harness applies prediction patches and is distinct from generated-test experiments."}, indent=2), encoding="utf-8")
    result = subprocess.run(command, check=False, cwd=output, text=True, encoding="utf-8", errors="replace", timeout=args.timeout)
    (output / "harness.log").write_text((result.stdout or "") + "\n" + (result.stderr or ""), encoding="utf-8")
    harness_report = output / "logs" / "evaluation" / run_id / "results.json"
    if harness_report.is_file():
        (output / "benchmark_results.json").write_text(harness_report.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Official harness exit code: {result.returncode}; artifacts: {output}")
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="SWE-bench Lite dataset, test-generation adapter and official patch evaluator")
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare", help="download/filter instances without exporting gold patches")
    prep.add_argument("--split", default="test")
    prep.add_argument("--limit", type=int, default=1)
    prep.add_argument("--seed", type=int, default=42)
    prep.add_argument("--instance-id", action="append")
    prep.set_defaults(func=prepare)
    tests = sub.add_parser("run-tests", help="clone one base revision and run test-generation workflow")
    tests.add_argument("--instance-id", required=True)
    tests.add_argument("--split", default="test")
    tests.add_argument("--iterations", type=int, default=1)
    tests.add_argument("--timeout", type=int, default=120)
    tests.add_argument("--min-quality", type=float, default=70)
    tests.add_argument("--docker-image", default="smarttest-runner:latest")
    tests.set_defaults(func=run_tests)
    official = sub.add_parser("official-eval", help="run upstream SWE-bench patch-resolution harness")
    official.add_argument("--predictions", required=True, help="official JSONL with instance_id, model_name_or_path and model_patch")
    official.add_argument("--split", default="test")
    official.add_argument("--workers", type=int, default=1)
    official.add_argument("--run-id")
    official.add_argument("--timeout", type=int, default=86400)
    official.add_argument("--instance-id", action="append")
    official.set_defaults(func=official_eval)
    args = parser.parse_args()
    if getattr(args, "limit", 1) < 1:
        parser.error("--limit must be positive")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
