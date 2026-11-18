"""Run a small HumanEval test-generation evaluation using reference tests."""

from __future__ import annotations

import argparse
import ast
import gzip
import hashlib
import json
import random
import re
import shutil
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import BASE_DIR
from experiments.tracking import new_run, save_json
from tools.llm_client import MAX_OUTPUT_TOKENS, ask_llm
from agents.test_generator_agent import extract_python_code, validate_generated_code


DATA_URL = "https://raw.githubusercontent.com/openai/human-eval/master/data/HumanEval.jsonl.gz"
DATA_PATH = BASE_DIR / "datasets" / "humaneval" / "HumanEval.jsonl.gz"
DOCKER_IMAGE = "smarttest-runner:latest"
DOCKERFILE = BASE_DIR / "sandbox" / "runner" / "Dockerfile"


def load_tasks() -> tuple[list[dict[str, Any]], str]:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not DATA_PATH.exists():
        print(f"Téléchargement du jeu HumanEval depuis {DATA_URL}")
        request = urllib.request.Request(DATA_URL, headers={"User-Agent": "SmartTest-AI/1.0"})
        with urllib.request.urlopen(request, timeout=60) as response:
            DATA_PATH.write_bytes(response.read())
    digest = hashlib.sha256(DATA_PATH.read_bytes()).hexdigest()
    with gzip.open(DATA_PATH, "rt", encoding="utf-8") as handle:
        tasks = [json.loads(line) for line in handle if line.strip()]
    return tasks, digest


def select_tasks(tasks: list[dict[str, Any]], limit: int, seed: int) -> list[dict[str, Any]]:
    selected = list(tasks)
    random.Random(seed).shuffle(selected)
    return selected[: min(limit, len(selected))]


def _solution_source(task: dict[str, Any]) -> str:
    return task["prompt"] + task["canonical_solution"].rstrip() + "\n"


def _reference_test_source(task: dict[str, Any]) -> str:
    return (
        f"from solution import {task['entry_point']}\n\n"
        + task["test"].strip()
        + f"\n\ndef test_humaneval_reference():\n    check({task['entry_point']})\n"
    )


def _generator_prompt(task: dict[str, Any], source: str, reference_tests: str, missing_lines: list[int]) -> str:
    return f"""Tu écris des tests pytest supplémentaires pour une fonction Python.

Fonction testée : {task['entry_point']}

Code source de référence :
```python
{source}
```

Tests de référence HumanEval déjà présents :
```python
{reference_tests}
```

Lignes non couvertes par les tests de référence : {missing_lines}

Génère au maximum 6 tests supplémentaires, courts et indépendants, qui importent la fonction ainsi :
`from solution import {task['entry_point']}`
Vérifie des comportements distincts et des cas limites dans le domaine documenté. Ne suppose pas qu'une entrée invalide lève une exception, sauf si la spécification l'exige ou si le code la vérifie explicitement. Ne recopie pas les tests de référence. N'écris aucun code de production. Retourne uniquement du code Python contenant des fonctions `test_*`, avec des assertions explicites. N'utilise ni réseau, ni fichiers, ni processus, ni commandes système.
Garde la réponse sous 300 tokens. Évite les chaînes multilignes, les messages d'erreur exacts et les longues explications. Si tu utilises `pytest.raises`, ajoute `import pytest`.
"""


def _build_runner_image() -> None:
    result = subprocess.run(
        ["docker", "build", "-t", DOCKER_IMAGE, "-f", str(DOCKERFILE), str(DOCKERFILE.parent)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
    )
    if result.returncode:
        raise RuntimeError("Échec de construction de l'image pytest:\n" + result.stdout + result.stderr)


def _prepare_case(task_dir: Path, source: str, reference_tests: str, generated_tests: str | None) -> tuple[Path, Path]:
    app_dir = task_dir / "app"
    results_dir = task_dir / "results"
    tests_dir = app_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / "solution.py").write_text(source, encoding="utf-8")
    (tests_dir / "test_reference.py").write_text(reference_tests, encoding="utf-8")
    if generated_tests is not None:
        (tests_dir / "test_generated.py").write_text(generated_tests, encoding="utf-8")
    return app_dir, results_dir


def _run_pytest(app_dir: Path, results_dir: Path, log_path: Path) -> dict[str, Any]:
    command = [
        "docker", "run", "--rm", "--network", "none", "--read-only",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--pids-limit", "64", "--memory", "512m", "--cpus", "1",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m,mode=1777",
        "--mount", f"type=bind,source={app_dir.resolve()},target=/app,readonly",
        "--mount", f"type=bind,source={results_dir.resolve()},target=/tmp/test-results",
        DOCKER_IMAGE, "python", "-m", "pytest", "/app/tests", "-v",
        "-p", "no:cacheprovider", "--cov=solution", "--cov-branch",
        "--cov-report=json:/tmp/test-results/coverage.json", "--cov-report=term-missing",
    ]
    started = time.perf_counter()
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    duration = round(time.perf_counter() - started, 3)
    output = result.stdout + "\n" + result.stderr
    log_path.write_text(output, encoding="utf-8")
    report_path = results_dir / "coverage.json"
    coverage = json.loads(report_path.read_text(encoding="utf-8")).get("totals", {}) if report_path.exists() else None
    counts = {name: int(match.group(1)) if (match := re.search(rf"(\d+)\s+{name}", output)) else 0
              for name in ("passed", "failed", "errors", "skipped")}
    return {
        "status": "passed" if result.returncode == 0 and coverage is not None else "failed",
        "exit_code": result.returncode,
        "duration_seconds": duration,
        "tests": counts,
        "coverage": coverage,
        "output_tail": output[-4000:],
    }


def _critic_summary(code: str, execution: dict[str, Any], before: dict[str, Any] | None, after: dict[str, Any] | None) -> dict[str, Any]:
    tree = ast.parse(code)
    tests = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")]
    checks_by_test = []
    for test in tests:
        checks_by_test.append(any(
            isinstance(node, ast.Assert)
            or (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "raises")
            for node in ast.walk(test)
        ))
    syntax_and_count = 20 if tests else 0
    explicit_checks = 30 * (sum(checks_by_test) / len(checks_by_test)) if checks_by_test else 0
    execution_score = 30 if execution["status"] == "passed" else 0
    before_cov = (before or {}).get("percent_covered", 0)
    after_cov = (after or {}).get("percent_covered", 0)
    coverage_score = 20 if after_cov > before_cov else 0
    return {
        "method": "heuristique AST + exécution + gain de couverture (score sur 100)",
        "score": round(syntax_and_count + explicit_checks + execution_score + coverage_score, 2),
        "generated_tests": len(tests),
        "tests_with_explicit_check": sum(checks_by_test),
        "execution_passed": execution["status"] == "passed",
        "coverage_gain": round(after_cov - before_cov, 2),
        "limitation": "Ce critique déterministe vérifie la structure et les effets mesurés; il ne remplace pas une revue sémantique humaine ou LLM.",
    }


def run(args: argparse.Namespace) -> int:
    tasks, dataset_hash = load_tasks()
    selected = select_tasks(tasks, args.limit, args.seed)
    experiment = new_run("humaneval", "multiagent", "OpenAI HumanEval")
    run_dir = Path(experiment["run_dir"])
    metadata = experiment["metadata"] | {
        "benchmark_version": "openai/human-eval master",
        "dataset_url": DATA_URL,
        "dataset_sha256": dataset_hash,
        "selected_task_ids": [task["task_id"] for task in selected],
        "selection_seed": args.seed,
        "evaluation_protocol": "reference tests vs reference + generated unit tests; not official pass@k",
    }
    save_json(run_dir / "metadata.json", metadata)
    _build_runner_image()
    task_results = []
    interrupted = False

    for task in selected:
        task_id = task["task_id"]
        safe_id = task_id.replace("/", "_")
        task_dir = run_dir / "tasks" / safe_id
        (task_dir / "logs").mkdir(parents=True, exist_ok=True)
        source = _solution_source(task)
        reference_tests = _reference_test_source(task)
        reference_app, reference_results = _prepare_case(task_dir / "reference", source, reference_tests, None)
        baseline = _run_pytest(reference_app, reference_results, task_dir / "logs" / "pytest_reference.txt")
        task_result: dict[str, Any] = {
            "task_id": task_id,
            "entry_point": task["entry_point"],
            "baseline": baseline,
            "multiagent": None,
        }

        if not args.baseline_only:
            try:
                baseline_coverage_path = reference_results / "coverage.json"
                coverage_data = json.loads(baseline_coverage_path.read_text(encoding="utf-8")) if baseline_coverage_path.exists() else {}
                uncovered_lines = coverage_data.get("files", {}).get("solution.py", {}).get("missing_lines", [])
                prompt = _generator_prompt(task, source, reference_tests, uncovered_lines)
                print(f"{task_id}: génération Ollama en cours (maximum {MAX_OUTPUT_TOKENS} tokens)...", flush=True)
                raw_response = ask_llm(prompt)
                (task_dir / "generated_response.txt").write_text(raw_response, encoding="utf-8")
                generated = extract_python_code(raw_response)
                (task_dir / "generated_tests.py").write_text(generated + "\n", encoding="utf-8")
                test_names = validate_generated_code(generated)
                executable_tests = generated
                if re.search(r"\bpytest\.", generated) and not re.search(r"^\s*import\s+pytest\b|^\s*from\s+pytest\s+import\b", generated, re.MULTILINE):
                    executable_tests = "import pytest\n" + generated
                app_dir, results_dir = _prepare_case(task_dir / "multiagent", source, reference_tests, executable_tests)
                after = _run_pytest(app_dir, results_dir, task_dir / "logs" / "pytest_multiagent.txt")
                task_result["multiagent"] = {
                    "status": after["status"],
                    "execution": after,
                    "generated_test_count": len(test_names),
                    "critic": _critic_summary(generated, after, baseline.get("coverage"), after.get("coverage")),
                }
                task_result["coverage_delta_percentage_points"] = round(
                    (after.get("coverage") or {}).get("percent_covered", 0)
                    - (baseline.get("coverage") or {}).get("percent_covered", 0), 2
                )
            except KeyboardInterrupt:
                task_result["multiagent"] = {
                    "status": "interrupted",
                    "error": "Interrompu par l'utilisateur pendant l'appel au modèle.",
                }
                save_json(task_dir / "task_results.json", task_result)
                task_results.append(task_result)
                interrupted = True
                print(f"{task_id}: génération interrompue; baseline conservée")
                break
            except Exception as error:
                task_result["multiagent"] = {
                    "status": "error",
                    "error": f"{type(error).__name__}: {error}",
                }
        save_json(task_dir / "task_results.json", task_result)
        task_results.append(task_result)
        print(f"{task_id}: baseline={baseline['status']}" + (
            f", multiagent={task_result['multiagent']['status']}"
            if task_result["multiagent"] else ""
        ))

    completed = sum(1 for result in task_results if result["baseline"]["status"] == "passed")
    multi_results = [r["multiagent"] for r in task_results if r.get("multiagent") and r["multiagent"].get("execution")]
    summary = {
        "run_id": experiment["run_id"],
        "benchmark": "humaneval",
        "mode": "multiagent",
        "status": "baseline_only" if args.baseline_only else (
            "interrupted" if interrupted else
            "completed" if len(multi_results) == len(selected) else "partial"
        ),
        "protocol": metadata["evaluation_protocol"],
        "tasks_requested": len(selected),
        "baseline_tasks_passed": completed,
        "multiagent_tasks_passed": sum(1 for r in multi_results if r["execution"]["status"] == "passed"),
        "mean_coverage_before": _mean([(r["baseline"].get("coverage") or {}).get("percent_covered") for r in task_results]),
        "mean_coverage_after": _mean([((r.get("multiagent") or {}).get("execution", {}).get("coverage") or {}).get("percent_covered") for r in task_results]),
        "mean_coverage_delta_percentage_points": _mean([r.get("coverage_delta_percentage_points") for r in task_results]),
        "coverage_before": _mean([(r["baseline"].get("coverage") or {}).get("percent_covered") for r in task_results]),
        "coverage_after": _mean([((r.get("multiagent") or {}).get("execution", {}).get("coverage") or {}).get("percent_covered") for r in task_results]),
        "coverage_delta_percentage_points": _mean([r.get("coverage_delta_percentage_points") for r in task_results]),
        "branch_coverage_before": _mean([(r["baseline"].get("coverage") or {}).get("percent_branches_covered") for r in task_results]),
        "branch_coverage_after": _mean([((r.get("multiagent") or {}).get("execution", {}).get("coverage") or {}).get("percent_branches_covered") for r in task_results]),
        "mean_critic_score": _mean([((r.get("multiagent") or {}).get("critic") or {}).get("score") for r in task_results]),
        "tasks": task_results,
    }
    save_json(run_dir / "benchmark_results.json", summary)
    metadata["finished_at"] = datetime.now(timezone.utc).isoformat()
    metadata["status"] = summary["status"]
    save_json(run_dir / "metadata.json", metadata)
    _write_report(run_dir / "report.md", summary)
    print(f"Rapport HumanEval : {run_dir / 'report.md'}")
    return 0 if summary["status"] in {"completed", "baseline_only"} else 1


def _mean(values: list[Any]) -> float | None:
    numeric = [float(value) for value in values if isinstance(value, (int, float))]
    return round(sum(numeric) / len(numeric), 2) if numeric else None


def _write_report(path: Path, results: dict[str, Any]) -> None:
    def shown(value: Any) -> str:
        return "non mesuré" if value is None else str(value)

    lines = [
        "# HumanEval — évaluation de génération de tests", "",
        f"- Statut : `{results['status']}`",
        f"- Tâches : {results['tasks_requested']}",
        f"- Référence réussie : {results['baseline_tasks_passed']}/{results['tasks_requested']}",
        f"- Multi-agent réussi : {results.get('multiagent_tasks_passed', 'non exécuté')}/{results['tasks_requested']}",
        "", "| Mesure moyenne par tâche | Baseline | Multi-agent | Écart |",
        "|---|---:|---:|---:|",
        f"| Couverture lignes (%) | {shown(results.get('mean_coverage_before'))} | {shown(results.get('mean_coverage_after'))} | {shown(results.get('mean_coverage_delta_percentage_points'))} |",
        f"| Critique heuristique (/100) | — | {shown(results.get('mean_critic_score'))} | — |",
        "", f"> Protocole : {results['protocol']}. Le score de critique est une heuristique déterministe, pas un score LLM.",
        "", "## Résultats par tâche", "",
        "| Task ID | Baseline | Multi-agent | Couverture baseline | Couverture après | Delta | Tests générés | Critique |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for task in results["tasks"]:
        baseline = task["baseline"]
        multi = task.get("multiagent") or {}
        execution = multi.get("execution") or {}
        lines.append(
            f"| {task['task_id']} | {baseline['status']} | {multi.get('status', 'non exécuté')} | "
            f"{shown((baseline.get('coverage') or {}).get('percent_covered'))} | "
            f"{shown((execution.get('coverage') or {}).get('percent_covered'))} | "
            f"{shown(task.get('coverage_delta_percentage_points'))} | {shown(multi.get('generated_test_count'))} | "
            f"{shown((multi.get('critic') or {}).get('score'))} |"
        )
    lines.extend(["", "HumanEval fournit des tâches et des tests de référence; ce protocole mesure l'ajout de tests unitaires à une solution de référence. Il ne calcule pas le score officiel de génération de solutions pass@k.", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=3, help="Nombre de tâches (défaut : 3).")
    parser.add_argument("--seed", type=int, default=42, help="Graine de sélection déterministe.")
    parser.add_argument("--baseline-only", action="store_true", help="Valide le téléchargement et l'exécuteur sans appel LLM.")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit doit être supérieur ou égal à 1")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
