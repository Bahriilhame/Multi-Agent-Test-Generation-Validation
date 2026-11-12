"""Collect baseline pytest line and branch coverage for a task workspace."""

from pathlib import Path
import json
import subprocess
import sys
from typing import Any


def collect_coverage(workspace: Path, *, timeout_seconds: int = 600,
                     report_path: Path | None = None) -> dict[str, Any]:
    """Run pytest-cov in an existing repository; never edit application sources."""
    workspace = workspace.resolve(strict=True)
    report_path = (report_path or (workspace / ".swebench_coverage.json")).resolve()
    if report_path.exists() and not report_path.is_relative_to(workspace):
        raise ValueError("Refusing to overwrite a coverage report outside the workspace")
    command = [sys.executable, "-m", "pytest", "--cov", "--cov-branch",
               f"--cov-report=json:{report_path}", "--cov-report=term"]
    result = subprocess.run(command, cwd=workspace, capture_output=True, text=True,
                            timeout=timeout_seconds)
    report: dict[str, Any] = {
        "command": command,
        "exit_code": result.returncode,
        "stdout": result.stdout[-12000:],
        "stderr": result.stderr[-12000:],
        "report_path": str(report_path),
    }
    if report_path.exists():
        raw = json.loads(report_path.read_text(encoding="utf-8"))
        totals = raw.get("totals", {})
        report.update({
            "line_percent": totals.get("percent_covered", 0.0),
            "branch_percent": totals.get("percent_covered_branches", 0.0),
            "covered_lines": totals.get("covered_lines", 0),
            "total_lines": totals.get("num_statements", 0),
            "covered_branches": totals.get("covered_branches", 0),
            "total_branches": totals.get("num_branches", 0),
        })
    return report

