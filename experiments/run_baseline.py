"""Run the handwritten checkout tests in the same isolated Docker setup."""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from pathlib import Path

from config.settings import BASE_DIR, PROJECT_DIR, TESTS_DIR
from experiments.tracking import new_run, save_json, _write_markdown, finalize_run


def main() -> int:
    run = new_run("checkout", "baseline", "SmartTest-AI")
    run_dir = Path(run["run_dir"])
    app_dir = run_dir / "runtime" / "app"
    results_dir = run_dir / "runtime" / "results"
    (app_dir / "shop").mkdir(parents=True)
    (app_dir / "tests").mkdir(parents=True)
    results_dir.mkdir(parents=True)
    shutil.copy2(PROJECT_DIR / "checkout.py", app_dir / "shop" / "checkout.py")
    shutil.copy2(TESTS_DIR / "test_checkout.py", app_dir / "tests" / "test_checkout.py")

    dockerfile = BASE_DIR / "sandbox" / "runner" / "Dockerfile"
    image = "smarttest-runner:latest"
    try:
        build = subprocess.run(
            ["docker", "build", "-t", image, "-f", str(dockerfile), str(dockerfile.parent)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
        )
    except subprocess.TimeoutExpired as error:
        (run_dir / "logs" / "docker_build.txt").write_text(
            f"Docker image build timed out after {error.timeout} seconds.\n", encoding="utf-8"
        )
        finalize_run({"run_dir": str(run_dir), "run_id": run["run_id"], "validation_status": "error",
                      "run_error": "Docker image build timeout"}, "error")
        return 1
    (run_dir / "logs" / "docker_build.txt").write_text(build.stdout + "\n" + build.stderr, encoding="utf-8")
    if build.returncode:
        save_json(run_dir / "benchmark_results.json", {
            "run_id": run["run_id"], "benchmark": "checkout", "mode": "baseline",
            "status": "error", "error": "Docker image build failed",
        })
        finalize_run({"run_dir": str(run_dir), "run_id": run["run_id"], "validation_status": "error"}, "error")
        return build.returncode

    command = [
        "docker", "run", "--rm", "--network", "none", "--read-only",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--pids-limit", "64", "--memory", "512m", "--cpus", "1",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m,mode=1777",
        "--mount", f"type=bind,source={app_dir.resolve()},target=/app,readonly",
        "--mount", f"type=bind,source={results_dir.resolve()},target=/tmp/test-results",
        "-e", "PYTEST_ADDOPTS=--cov-branch",
        image,
    ]
    started = time.perf_counter()
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    duration = round(time.perf_counter() - started, 3)
    output = result.stdout + "\n" + result.stderr
    (run_dir / "logs" / "docker_pytest.txt").write_text(output, encoding="utf-8")

    coverage_path = results_dir / "coverage_after.json"
    coverage = None
    if coverage_path.exists():
        import json
        data = json.loads(coverage_path.read_text(encoding="utf-8"))
        coverage = data.get("totals", {})
    parsed = {key: int(match.group(1)) if (match := re.search(rf"(\d+)\s+{key}", output)) else 0
              for key in ("passed", "failed", "errors", "skipped")}
    save_json(run_dir / "baseline_coverage.json", coverage or {})
    results = {
        "run_id": run["run_id"], "benchmark": "checkout", "mode": "baseline",
        "status": "passed" if result.returncode == 0 and coverage is not None else "failed",
        "coverage_before": coverage.get("percent_covered") if coverage else None,
        "coverage_after": coverage.get("percent_covered") if coverage else None,
        "coverage_delta_percentage_points": 0 if coverage else None,
        "branch_coverage_before": coverage.get("percent_branches_covered") if coverage else None,
        "branch_coverage_after": coverage.get("percent_branches_covered") if coverage else None,
        "test_results": {**parsed, "duration_seconds": duration, "coverage": coverage},
    }
    save_json(run_dir / "benchmark_results.json", results)
    metadata = run["metadata"] | {"status": results["status"]}
    _write_markdown(run_dir / "report.md", metadata, results)
    from datetime import datetime, timezone
    run["metadata"]["finished_at"] = datetime.now(timezone.utc).isoformat()
    run["metadata"]["status"] = results["status"]
    save_json(run_dir / "metadata.json", run["metadata"])
    print(f"Run baseline : {run_dir}")
    print(f"Tests: {parsed}; couverture: {results['coverage_after']}; branches: {results['branch_coverage_after']}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
