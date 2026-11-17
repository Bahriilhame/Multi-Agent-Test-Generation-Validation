"""Compare mutation scores for handwritten and multi-agent checkout tests."""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import BASE_DIR, PROJECT_DIR, TESTS_DIR
from experiments.tracking import new_run, save_json


IMAGE = "smarttest-mutation-runner:latest"
DOCKERFILE = BASE_DIR / "sandbox" / "mutation" / "Dockerfile"
SOURCE_ROOT = BASE_DIR / "src"


def _latest_successful_generated_tests() -> Path:
    candidates = []
    for metadata_path in (BASE_DIR / "experiments" / "checkout").glob("*/metadata.json"):
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        generated = metadata_path.parent / "generated_tests" / "test_generated_checkout.py"
        if metadata.get("status") == "passed" and generated.exists():
            candidates.append((metadata.get("finished_at", ""), generated))
    if not candidates:
        raise FileNotFoundError("Aucun run multi-agent réussi avec tests générés n'a été trouvé.")
    return max(candidates, key=lambda item: item[0])[1]


def _docker_build(log_path: Path) -> tuple[int, str]:
    result = subprocess.run(
        ["docker", "build", "-t", IMAGE, "-f", str(DOCKERFILE), str(DOCKERFILE.parent)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900,
    )
    output = result.stdout + "\n" + result.stderr
    log_path.write_text(output, encoding="utf-8")
    return result.returncode, output


def _prepare_case(case_dir: Path, include_generated: bool, generated_file: Path) -> None:
    (case_dir / "src" / "shop").mkdir(parents=True, exist_ok=True)
    (case_dir / "tests").mkdir(parents=True, exist_ok=True)
    shutil.copy2(PROJECT_DIR / "checkout.py", case_dir / "src" / "shop" / "checkout.py")
    shutil.copy2(PROJECT_DIR / "__init__.py", case_dir / "src" / "shop" / "__init__.py")
    shutil.copy2(TESTS_DIR / "test_checkout.py", case_dir / "tests" / "test_checkout.py")
    if include_generated:
        shutil.copy2(generated_file, case_dir / "tests" / "test_generated_checkout.py")
    config = '''[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_functions = ["test_*"]

[tool.mutmut]
source_paths = ["src/shop"]
pytest_add_cli_args_test_selection = ["tests"]
'''
    (case_dir / "pyproject.toml").write_text(config, encoding="utf-8")


def _run_mutmut(case_dir: Path, logs_dir: Path, mode: str) -> dict[str, Any]:
    mount_path = str(case_dir.resolve())
    common = [
        "docker", "run", "--rm", "--network", "none",
        "--mount", f"type=bind,source={mount_path},target=/workspace",
        "-w", "/workspace", IMAGE,
    ]
    started = time.perf_counter()
    result = subprocess.run(
        common + ["mutmut", "run"], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=3600,
    )
    duration = round(time.perf_counter() - started, 3)
    run_output = result.stdout + "\n" + result.stderr
    (logs_dir / f"mutmut_{mode}.txt").write_text(run_output, encoding="utf-8")

    stats_result = subprocess.run(
        common + ["mutmut", "export-cicd-stats"], capture_output=True,
        text=True, encoding="utf-8", errors="replace", timeout=60,
    )
    stats_output = stats_result.stdout + "\n" + stats_result.stderr
    (logs_dir / f"mutmut_stats_{mode}.txt").write_text(stats_output, encoding="utf-8")
    stats_path = case_dir / "mutants" / "mutmut-cicd-stats.json"
    stats = json.loads(stats_path.read_text(encoding="utf-8")) if stats_path.exists() else _extract_json(stats_result.stdout)
    return {
        "status": "completed" if result.returncode == 0 and stats_result.returncode == 0 else "error",
        "exit_code": result.returncode,
        "stats_exit_code": stats_result.returncode,
        "duration_seconds": duration,
        "stats": stats,
        "run_output_tail": run_output[-5000:],
        "stats_output": stats_output[-2000:],
    }


def _extract_json(output: str) -> Any:
    candidates = [output.strip()]
    first = output.find("{")
    last = output.rfind("}")
    if first >= 0 and last > first:
        candidates.append(output[first:last + 1])
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def _score(stats: Any) -> dict[str, Any]:
    """Normalize mutmut's CICD export fields while retaining its raw payload."""
    if not isinstance(stats, dict):
        return {"killed": None, "survived": None, "total": None, "score_percent": None}
    aliases = {
        "killed": ("killed", "killed_count"),
        "survived": ("survived", "survived_count"),
        "timeout": ("timeout", "timeout_count"),
        "suspicious": ("suspicious", "suspicious_count"),
        "skipped": ("skipped", "skipped_count"),
        "no_tests": ("no_tests", "no_tests_count"),
    }
    normalized = {}
    for key, choices in aliases.items():
        normalized[key] = next((stats[name] for name in choices if name in stats), 0)
    total = sum(normalized.get(key, 0) or 0 for key in ("killed", "survived", "timeout", "suspicious"))
    killed = normalized.get("killed") or 0
    normalized["total"] = total
    normalized["score_percent"] = round(100 * killed / total, 2) if total else None
    normalized["raw"] = stats
    generated_total = stats.get("total")
    normalized["generated_total"] = generated_total
    normalized["score_all_generated_percent"] = (
        round(100 * killed / generated_total, 2)
        if isinstance(generated_total, (int, float)) and generated_total else None
    )
    return normalized


def main() -> int:
    generated_file = _latest_successful_generated_tests()

    run = new_run("checkout", "mutation_comparison", "SmartTest-AI")
    run_dir = Path(run["run_dir"])
    logs_dir = run_dir / "logs"
    build_code, build_output = _docker_build(logs_dir / "docker_build.txt")
    if build_code:
        save_json(run_dir / "mutation_results.json", {"status": "error", "error": "Docker build failed"})
        return build_code

    cases = {}
    for mode, include_generated in (("baseline", False), ("multiagent", True)):
        case_dir = run_dir / "cases" / mode
        _prepare_case(case_dir, include_generated, generated_file)
        cases[mode] = _run_mutmut(case_dir, logs_dir, mode)
        cases[mode]["score"] = _score(cases[mode].get("stats"))

    baseline_score = cases["baseline"]["score"].get("score_percent")
    multi_score = cases["multiagent"]["score"].get("score_percent")
    baseline_all_score = cases["baseline"]["score"].get("score_all_generated_percent")
    multi_all_score = cases["multiagent"]["score"].get("score_all_generated_percent")
    comparison = {
        "run_id": run["run_id"],
        "benchmark": "checkout",
        "status": "completed" if all(case["status"] == "completed" for case in cases.values()) else "partial",
        "tool": "mutmut",
        "cases": cases,
        "mutation_score_delta_percentage_points": round(multi_score - baseline_score, 2)
        if baseline_score is not None and multi_score is not None else None,
        "all_generated_score_delta_percentage_points": round(multi_all_score - baseline_all_score, 2)
        if baseline_all_score is not None and multi_all_score is not None else None,
    }
    save_json(run_dir / "mutation_results.json", comparison)
    metadata = run["metadata"] | {
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "status": comparison["status"],
        "stage": "mutation_testing",
        "mutation_tool": "mutmut",
    }
    save_json(run_dir / "metadata.json", metadata)
    _write_report(run_dir / "mutation_report.md", comparison)
    print(f"Rapport mutation : {run_dir / 'mutation_report.md'}")
    print(f"Scores normalisés : baseline={cases['baseline']['score']}; multiagent={cases['multiagent']['score']}")
    return 0 if comparison["status"] == "completed" else 1


def _write_report(path: Path, results: dict[str, Any]) -> None:
    lines = [
        "# Mutation testing — checkout", "",
        f"- Statut : `{results['status']}`",
        f"- Outil : `{results['tool']}`", "",
        "| Suite évaluée | Tués | Survivants | Sans test | Score des exécutés | Tués / tous générés | Statut |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for mode, label in (("baseline", "Tests manuels"), ("multiagent", "Manuels + générés")):
        case = results["cases"][mode]
        score = case["score"]
        lines.append(
            f"| {label} | {score.get('killed')} | {score.get('survived')} | "
            f"{score.get('no_tests')} | {score.get('score_percent')}% | "
            f"{score.get('score_all_generated_percent')}% | {case['status']} |"
        )
    lines.extend([
        "", f"Écart multi-agent moins baseline parmi les mutants exécutés : `{results.get('mutation_score_delta_percentage_points')}` points de pourcentage.",
        f"Écart multi-agent moins baseline sur tous les mutants : `{results.get('all_generated_score_delta_percentage_points')}` points de pourcentage.",
        "", "`Score des exécutés` = tués / (tués + survivants + timeout + suspects). `Tués / tous générés` inclut les mutants `no_tests` dans le dénominateur; il reflète la capacité totale de la suite à atteindre et détecter les mutations. Consulte les sorties brutes dans `cases/` et `logs/`.",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
