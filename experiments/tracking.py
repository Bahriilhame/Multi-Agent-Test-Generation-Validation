"""Persistent run metadata and reports for benchmark experiments."""

from __future__ import annotations

import json
import ast
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from config.settings import BASE_DIR

EXPERIMENTS_DIR = BASE_DIR / "experiments"


def _git_value(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args], cwd=BASE_DIR, capture_output=True,
            text=True, check=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def _package_version(package: str) -> str | None:
    try:
        from importlib.metadata import version
        return version(package)
    except Exception:
        return None


def new_run(benchmark: str, mode: str, project_name: str) -> dict[str, Any]:
    """Create an isolated run directory and its initial metadata."""
    timestamp = datetime.now(timezone.utc)
    run_id = f"{timestamp.strftime('%Y%m%dT%H%M%SZ')}_{mode}_{uuid4().hex[:8]}"
    run_dir = EXPERIMENTS_DIR / benchmark / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "logs").mkdir()
    metadata = {
        "run_id": run_id,
        "benchmark": benchmark,
        "benchmark_version": "local-checkout-v1" if benchmark == "checkout" else None,
        "mode": mode,
        "project_name": project_name,
        "started_at": timestamp.isoformat(),
        "git_commit": _git_value("rev-parse", "HEAD"),
        "git_dirty": bool(_git_value("status", "--porcelain")),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "model": os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b"),
        "docker_image": "smarttest-runner:latest",
        "pytest_version": _package_version("pytest"),
        "coverage_version": _package_version("coverage"),
        "command": sys.argv,
    }
    save_json(run_dir / "metadata.json", metadata)
    return {"run_id": run_id, "run_dir": str(run_dir), "metadata": metadata}


def save_json(path: str | Path, payload: Any) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def copy_if_present(source: str | Path | None, destination: str | Path) -> None:
    if not source:
        return
    source_path = Path(source)
    if source_path.is_file():
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source_path.read_bytes())


def finalize_run(state: dict[str, Any], status: str = "completed") -> None:
    run_dir_value = state.get("run_dir")
    if not run_dir_value:
        return
    run_dir = Path(run_dir_value)
    metadata_path = run_dir / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["finished_at"] = datetime.now(timezone.utc).isoformat()
    metadata["status"] = status
    metadata["stage"] = state.get("run_stage", "finalized")
    save_json(metadata_path, metadata)

    # Recover artifacts written before an exception interrupted the workflow.
    if state.get("coverage_report_path") is None:
        candidate = run_dir / "coverage_before.json"
        if candidate.exists():
            state["coverage_report_path"] = str(candidate)
            try:
                totals = json.loads(candidate.read_text(encoding="utf-8")).get("totals", {})
                state.setdefault("coverage_before", totals.get("percent_covered"))
                state.setdefault("branch_coverage_before", totals.get("percent_branches_covered"))
            except (OSError, json.JSONDecodeError):
                pass
    if not state.get("generated_test_file"):
        generated = run_dir / "generated_tests" / "test_generated_checkout.py"
        if generated.exists():
            state["generated_test_file"] = str(generated)
            try:
                tree = ast.parse(generated.read_text(encoding="utf-8"))
                count = sum(
                    isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name.startswith("test_")
                    for node in ast.walk(tree)
                )
                state.setdefault("generated_test_count", count)
            except (OSError, SyntaxError):
                pass
    if state.get("critic_result") is None:
        critic_path = run_dir / "critic_result.json"
        if critic_path.exists():
            try:
                state["critic_result"] = json.loads(critic_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass

    for key, filename in (
        ("coverage_report_path", "coverage_before.json"),
        ("coverage_after_report_path", "coverage_after.json"),
    ):
        copy_if_present(state.get(key), run_dir / filename)
    test_results = state.get("test_results")
    if isinstance(test_results, dict) and test_results.get("output"):
        (run_dir / "logs" / "docker_pytest.txt").write_text(
            test_results["output"], encoding="utf-8"
        )
    copy_if_present(
        state.get("generated_test_file"),
        run_dir / "generated_tests" / "test_generated.py",
    )

    before = state.get("coverage_before")
    after = state.get("coverage_after")
    results = {
        "run_id": state.get("run_id"),
        "benchmark": metadata.get("benchmark"),
        "mode": metadata.get("mode"),
        "status": state.get("validation_status", status),
        "stage": state.get("run_stage", "completed" if status == "passed" else "incomplete"),
        "error": state.get("run_error"),
        "coverage_before": before,
        "coverage_after": after,
        "coverage_delta_percentage_points": round(after - before, 2)
        if isinstance(before, (float, int)) and isinstance(after, (float, int)) else None,
        "branch_coverage_before": state.get("branch_coverage_before"),
        "branch_coverage_after": state.get("branch_coverage_after"),
        "generated_test_count": state.get("generated_test_count"),
        "relevance_score": state.get("relevance_score"),
        "relevance_feedback": state.get("relevance_feedback"),
        "test_results": {
            key: value for key, value in (test_results or {}).items()
            if key != "output"
        },
        "critic": state.get("critic_result"),
    }
    save_json(run_dir / "benchmark_results.json", results)
    _write_markdown(run_dir / "report.md", metadata, results)


def _write_markdown(path: Path, metadata: dict[str, Any], results: dict[str, Any]) -> None:
    def shown(value: Any) -> str:
        return "non mesuré" if value is None else str(value)

    lines = [
        f"# Expérience {metadata['run_id']}", "",
        f"- Benchmark : `{metadata['benchmark']}`",
        f"- Mode : `{metadata['mode']}`",
        f"- Statut : `{results.get('status')}`",
        f"- Commit : `{metadata.get('git_commit') or 'inconnu'}`",
        f"- Modèle : `{metadata.get('model')}`", "",
        "## Résultats", "",
        "| Mesure | Avant | Après | Écart |",
        "|---|---:|---:|---:|",
        f"| Couverture lignes (%) | {shown(results.get('coverage_before'))} | {shown(results.get('coverage_after'))} | {shown(results.get('coverage_delta_percentage_points'))} |",
        f"| Couverture branches (%) | {shown(results.get('branch_coverage_before'))} | {shown(results.get('branch_coverage_after'))} | — |",
        f"| Score critique (sur 100) | — | {shown(results.get('relevance_score'))} | — |",
        "",
        "> La couverture indique les lignes/branches exécutées. Elle ne prouve pas à elle seule que les tests détectent les défauts.",
        "", "## Résultats pytest", "", "```json",
        json.dumps(results.get("test_results"), ensure_ascii=False, indent=2, default=str),
        "```", "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
