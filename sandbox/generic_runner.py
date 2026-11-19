"""Disposable Docker execution for arbitrary Python project snapshots."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from adapters.base import IGNORED_DIRS

EXCLUDED_FILES = {".env", ".env.local", ".env.production", "secrets.json", "id_rsa", ".npmrc", ".pypirc", "credentials", "credentials.json"}


def ensure_runner_image(image: str = "smarttest-runner:latest") -> None:
    """Build the platform's reusable base image once when Docker lacks it."""
    available = subprocess.run(["docker", "image", "inspect", image], check=False, capture_output=True, text=True)
    if available.returncode == 0:
        return
    dockerfile = Path(__file__).resolve().parent / "runner" / "Dockerfile"
    build = subprocess.run(
        ["docker", "build", "-t", image, "-f", str(dockerfile), str(dockerfile.parent)],
        check=False, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
    )
    if build.returncode:
        raise RuntimeError("Docker image build failed:\n" + (build.stdout + build.stderr)[-5000:])


def _copy_project(source: Path, destination: Path, excluded_root: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    for current, dirs, files in os.walk(source, followlinks=False):
        current_path = Path(current)
        dirs[:] = [
            name for name in dirs
            if name not in IGNORED_DIRS | {"experiments", "datasets", "htmlcov", "reports"}
            and not (current_path / name).is_symlink()
            and not (current_path / name).resolve().is_relative_to(excluded_root)
        ]
        rel = current_path.relative_to(source)
        target_dir = destination / rel
        target_dir.mkdir(parents=True, exist_ok=True)
        for name in files:
            src = current_path / name
            if src.is_symlink() or name.lower() in EXCLUDED_FILES or name.startswith(".env.") or src.suffix.lower() in {".pem", ".key", ".p12", ".pfx"}:
                continue
            try:
                shutil.copy2(src, target_dir / name)
            except OSError as error:
                raise RuntimeError(f"Unable to stage project file {src}: {error}") from error


def run_in_docker(
    project_root: str | Path,
    run_dir: str | Path,
    generated_tests: str,
    *,
    timeout_seconds: int = 120,
    image: str = "smarttest-runner:latest",
) -> dict[str, Any]:
    """Run existing and generated tests in a constrained, offline container.

    The user's project is copied to a disposable staging directory with symlinks,
    Git metadata, virtualenvs and common secret files excluded. Docker is the only
    process that executes that snapshot; no project Python code is imported here.
    """
    root = Path(project_root).expanduser().resolve()
    run = Path(run_dir).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(root)
    run.mkdir(parents=True, exist_ok=True)
    app = run / "runtime" / "app"
    results = run / "runtime" / "results"
    if app.exists():
        shutil.rmtree(app)
    if results.exists():
        shutil.rmtree(results)
    app.parent.mkdir(parents=True, exist_ok=True)
    _copy_project(root, app, run)
    generated_dir = app / "smarttest_generated"
    generated_dir.mkdir()
    generated_file = generated_dir / "test_generated.py"
    generated_file.write_text(generated_tests.rstrip() + "\n", encoding="utf-8")
    results.mkdir(parents=True)
    (results / "coverage.ini").write_text(
        "[run]\nsource = /app\nbranch = True\nomit =\n    */tests/*\n    */test_*.py\n    */smarttest_generated/*\n    */conftest.py\n",
        encoding="utf-8",
    )

    if image == "smarttest-runner:latest":
        ensure_runner_image(image)
    else:
        available = subprocess.run(["docker", "image", "inspect", image], check=False, capture_output=True, text=True)
        if available.returncode:
            raise RuntimeError(f"Docker image {image!r} is not built. Build it first with dependencies, pytest and pytest-cov.")
    if "," in str(app) or "," in str(results):
        raise ValueError("Docker bind mount paths cannot contain commas.")

    command = [
        "docker", "run", "--rm", "--network", "none", "--read-only",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--user", "65534:65534", "--pids-limit", "64", "--memory", "1g", "--cpus", "1",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=256m,mode=1777",
        "--mount", f"type=bind,source={app},target=/app,readonly",
        "--mount", f"type=bind,source={results},target=/tmp/test-results",
        "-e", "PYTHONDONTWRITEBYTECODE=1", "-e", "PYTEST_ADDOPTS=-p no:cacheprovider",
        "-e", "COVERAGE_FILE=/tmp/test-results/.coverage",
        image, "python", "-m", "pytest", "/app", "-v", "-p", "no:cacheprovider",
        "--cov=/app", "--cov-config=/tmp/test-results/coverage.ini", "--cov-branch", "--cov-report=json:/tmp/test-results/coverage.json",
        "--cov-report=term-missing",
    ]
    started = time.perf_counter()
    container_name = "smarttest-" + uuid.uuid4().hex[:12]
    command[3:3] = ["--name", container_name]
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout_seconds)
        output = (result.stdout + "\n" + result.stderr)[-20000:]
        exit_code = result.returncode
    except subprocess.TimeoutExpired as error:
        def decode(value):
            if isinstance(value, bytes):
                return value.decode("utf-8", errors="replace")
            return value or ""
        output = (decode(error.stdout) + "\n" + decode(error.stderr) + f"\nTimeout after {timeout_seconds}s")[-20000:]
        exit_code = 124
    finally:
        try:
            subprocess.run(["docker", "rm", "-f", container_name], check=False, capture_output=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            pass
    duration = round(time.perf_counter() - started, 3)
    (run / "logs").mkdir(exist_ok=True)
    (run / "logs" / "pytest-docker.txt").write_text(output, encoding="utf-8")
    report_path = results / "coverage.json"
    coverage = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else None
    return {
        "exit_code": exit_code,
        "passed": _summary_count(output, "passed"),
        "failed": _summary_count(output, "failed"),
        "errors": _summary_count(output, "error"),
        "generated_passed": len(re.findall(r"smarttest_generated[\\/]test_generated\.py::.*?\s+PASSED", output)),
        "generated_failed": len(re.findall(r"smarttest_generated[\\/]test_generated\.py::.*?\s+(?:FAILED|ERROR)", output)),
        "generated_passed_tests": _generated_test_names(output, "PASSED"),
        "generated_failed_tests": _generated_test_names(output, "FAILED|ERROR"),
        "failure_details": _failure_details(output),
        "missing_dependencies": sorted(set(re.findall(r"No module named ['\"]([^'\"]+)['\"]", output))),
        "duration_seconds": duration,
        "output": output,
        "coverage": coverage,
        "container_policy": {
            "network": "none", "root_filesystem": "read-only", "capabilities": "all dropped",
            "no_new_privileges": True, "memory": "1g", "cpus": 1, "pids": 64, "user": "65534:65534",
            "project_mount": "read-only", "results_mount": "writable temporary run directory",
        },
    }


def _summary_count(output: str, name: str) -> int:
    noun = "errors?" if name == "error" else re.escape(name)
    found = re.findall(rf"\b(\d+)\s+{noun}\b", output.lower())
    return int(found[-1]) if found else 0


def _generated_test_names(output: str, outcome: str) -> list[str]:
    matches = re.findall(
        rf"(?m)^smarttest_generated[\\/]test_generated\.py::([^\s]+)\s+(?:{outcome})\b",
        output,
    )
    return sorted({name.split("[", 1)[0] for name in matches})


def _failure_details(output: str) -> str:
    match = re.search(r"=+ FAILURES =+\s*(.*?)(?=\n=+ (?:tests coverage|short test summary)|\Z)", output, re.DOTALL)
    if match:
        return match.group(1).strip()
    match = re.search(r"=+ ERRORS =+\s*(.*?)(?=\n=+ (?:tests coverage|short test summary)|\Z)", output, re.DOTALL)
    return match.group(1).strip() if match else ""


def summarize_failure_details(output: str, *, limit: int = 1200) -> str:
    """Reduce pytest tracebacks to each failed test's name and actionable cause."""
    headers = list(re.finditer(r"(?m)^_{3,}\s*(.*?)\s*_{3,}\s*$", output))
    summaries = []
    for index, header in enumerate(headers):
        name = header.group(1).strip()
        if "test_" not in name:
            continue
        end = headers[index + 1].start() if index + 1 < len(headers) else len(output)
        section = output[header.end():end]
        lines = section.splitlines()
        causes = [
            line.strip()[2:].strip()
            for line in lines
            if line.lstrip().startswith("E ")
            and re.search(r"(?:AssertionError|IntegrityError|NameError|TypeError|ValueError|KeyError|IndexError|ImportError|ModuleNotFoundError|TimeoutError)", line)
        ]
        cause = causes[-1] if causes else "pytest reported a failure; inspect the detailed log"
        assertion = next(
            (line.strip()[1:].strip() for line in lines if re.match(r"^>\s+.*\bassert\b", line)),
            None,
        )
        detail = f"{name}: {cause}"
        if assertion and "AssertionError" in cause:
            detail += f"; {assertion}"
        summaries.append(detail)
    rendered = "\n".join(f"- {item}" for item in summaries[:8])
    return rendered[:limit] if rendered else output.strip()[-limit:]
