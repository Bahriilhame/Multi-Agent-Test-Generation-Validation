"""Run test-generation experiments on the official sanitized MBPP test split."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import random
import re
import textwrap
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import BASE_DIR
from experiments.humaneval import (
    _build_runner_image,
    _critic_summary,
    _mean,
    _prepare_case,
    _run_pytest,
)
from experiments.tracking import new_run, save_json
from tools.llm_client import MAX_OUTPUT_TOKENS, ask_llm
from agents.test_generator_agent import extract_python_code, validate_generated_code


DATA_URL = "https://raw.githubusercontent.com/google-research/google-research/master/mbpp/sanitized-mbpp.json"
DATA_PATH = BASE_DIR / "datasets" / "mbpp" / "sanitized-mbpp.json"
TEST_TASK_MIN = 11
TEST_TASK_MAX = 510


def load_tasks() -> tuple[list[dict[str, Any]], str]:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not DATA_PATH.exists():
        print(f"Téléchargement de MBPP depuis {DATA_URL}")
        request = urllib.request.Request(DATA_URL, headers={"User-Agent": "SmartTest-AI/1.0"})
        with urllib.request.urlopen(request, timeout=60) as response:
            DATA_PATH.write_bytes(response.read())

    raw = DATA_PATH.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    decoded = raw.decode("utf-8")
    try:
        tasks = json.loads(decoded)
        if isinstance(tasks, dict):
            tasks = tasks.get("data", tasks.get("tasks", []))
    except json.JSONDecodeError:
        tasks = [json.loads(line) for line in decoded.splitlines() if line.strip()]

    if not isinstance(tasks, list):
        raise ValueError("Format MBPP inattendu : une liste de tâches était attendue.")
    test_tasks = [
        task for task in tasks
        if TEST_TASK_MIN <= int(task.get("task_id", -1)) <= TEST_TASK_MAX
        and task.get("code") and task.get("test_list")
    ]
    if not test_tasks:
        raise ValueError("Aucune tâche du split officiel MBPP test (IDs 11–510) trouvée.")
    return test_tasks, digest


def select_tasks(tasks: list[dict[str, Any]], limit: int, seed: int) -> list[dict[str, Any]]:
    selected = list(tasks)
    random.Random(seed).shuffle(selected)
    return selected[: min(limit, len(selected))]


def _solution_source(task: dict[str, Any]) -> str:
    return task["code"].rstrip() + "\n"


def _reference_test_source(task: dict[str, Any]) -> str:
    helper_imports = "\n".join(task.get("test_imports", [])).strip()
    functions = _function_names(task["code"])
    solution_import = f"from solution import {', '.join(functions)}" if functions else "import solution"
    assertions = "\n".join(task.get("test_list", [])).strip()
    if not assertions:
        raise ValueError(f"La tâche MBPP/{task['task_id']} ne contient aucun test de référence.")
    test_body = textwrap.indent(assertions, "    ")
    imports = "\n".join(part for part in (helper_imports, solution_import) if part)
    prefix = imports + "\n\n"
    return prefix + f"def test_mbpp_reference():\n{test_body}\n"


def _function_names(source: str) -> list[str]:
    tree = ast.parse(source)
    return [
        node.name for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    ]


def _generator_prompt(task: dict[str, Any], source: str, reference_tests: str, missing_lines: list[int]) -> str:
    functions = _function_names(source)
    return f"""Tu écris des tests pytest supplémentaires pour une fonction Python.

Énoncé MBPP : {task['prompt']}
Fonction(s) disponible(s) dans le module `solution` : {functions}

Code de référence :
```python
{source}
```

Tests de référence déjà présents :
```python
{reference_tests}
```

Lignes non couvertes : {missing_lines}

Génère au maximum 6 tests courts pour les fonctions indiquées. Importe-les avec `from solution import nom_fonction`. Couvre des comportements distincts et des limites du domaine décrit par l'énoncé. Ne répète pas les tests de référence. N'invente pas de comportement pour des entrées hors domaine. Les valeurs attendues doivent être calculées correctement. Retourne uniquement des fonctions `test_*`, sans code de production, fichier, réseau, processus ou commande système.
Garde la réponse sous 300 tokens. Si tu utilises `pytest.raises`, ajoute `import pytest`.
"""


def _write_report(path: Path, results: dict[str, Any]) -> None:
    def shown(value: Any) -> str:
        return "non mesuré" if value is None else str(value)

    lines = [
        "# MBPP — évaluation de génération de tests", "",
        f"- Statut : `{results['status']}`",
        f"- Split : tâches officielles {TEST_TASK_MIN}–{TEST_TASK_MAX}",
        f"- Tâches : {results['tasks_requested']}",
        f"- Référence réussie : {results['baseline_tasks_passed']}/{results['tasks_requested']}",
        f"- Multi-agent réussi : {results['multiagent_tasks_passed']}/{results['tasks_requested']}",
        "", "| Mesure moyenne par tâche | Baseline | Multi-agent | Écart |",
        "|---|---:|---:|---:|",
        f"| Couverture lignes (%) | {shown(results.get('mean_coverage_before'))} | {shown(results.get('mean_coverage_after'))} | {shown(results.get('mean_coverage_delta_percentage_points'))} |",
        f"| Critique heuristique (/100) | — | {shown(results.get('mean_critic_score'))} | — |",
        "", f"> Protocole : {results['protocol']}. Le critique est une heuristique; ce résultat n'est pas un score pass@k.",
        "", "## Résultats par tâche", "",
        "| ID | Baseline | Multi-agent | Couverture avant | Couverture après | Delta | Tests générés | Critique |",
        "|---:|---|---|---:|---:|---:|---:|---:|",
    ]
    for task in results["tasks"]:
        baseline = task["baseline"]
        multi = task.get("multiagent") or {}
        execution = multi.get("execution") or {}
        lines.append(
            f"| {task['task_id']} | {baseline['status']} | {multi.get('status', 'non exécuté')} | "
            f"{shown((baseline.get('coverage') or {}).get('percent_covered'))} | "
            f"{shown((execution.get('coverage') or {}).get('percent_covered'))} | "
            f"{shown(task.get('coverage_delta_percentage_points'))} | "
            f"{shown(multi.get('generated_test_count'))} | {shown((multi.get('critic') or {}).get('score'))} |"
        )
    lines.extend([
        "", "Le split de test MBPP utilise les tâches 11–510. La couverture mesure l'exécution, pas à elle seule la pertinence ou la capacité des tests à détecter des défauts.", "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    tasks, dataset_hash = load_tasks()
    selected = select_tasks(tasks, args.limit, args.seed)
    experiment = new_run("mbpp", "multiagent", "Google Research MBPP sanitized")
    run_dir = Path(experiment["run_dir"])
    metadata = experiment["metadata"] | {
        "benchmark_version": "google-research/google-research mbpp/sanitized-mbpp.json",
        "dataset_url": DATA_URL,
        "dataset_sha256": dataset_hash,
        "official_test_task_id_range": [TEST_TASK_MIN, TEST_TASK_MAX],
        "selected_task_ids": [task["task_id"] for task in selected],
        "selection_seed": args.seed,
        "evaluation_protocol": "MBPP test_list baseline vs baseline + LLM-generated pytest tests; not official pass@k",
    }
    save_json(run_dir / "metadata.json", metadata)
    _build_runner_image()
    task_results = []
    interrupted = False

    for task in selected:
        task_id = int(task["task_id"])
        safe_id = f"MBPP_{task_id}"
        task_dir = run_dir / "tasks" / safe_id
        (task_dir / "logs").mkdir(parents=True, exist_ok=True)
        source = _solution_source(task)
        reference_tests = _reference_test_source(task)
        reference_app, reference_results = _prepare_case(task_dir / "reference", source, reference_tests, None)
        baseline = _run_pytest(reference_app, reference_results, task_dir / "logs" / "pytest_reference.txt")
        task_result: dict[str, Any] = {
            "task_id": task_id,
            "prompt": task["prompt"],
            "baseline": baseline,
            "multiagent": None,
        }

        if not args.baseline_only:
            try:
                coverage_path = reference_results / "coverage.json"
                coverage_data = json.loads(coverage_path.read_text(encoding="utf-8")) if coverage_path.exists() else {}
                missing_lines = coverage_data.get("files", {}).get("solution.py", {}).get("missing_lines", [])
                prompt = _generator_prompt(task, source, reference_tests, missing_lines)
                print(f"MBPP/{task_id}: génération Ollama en cours (maximum {MAX_OUTPUT_TOKENS} tokens)...", flush=True)
                raw_response = ask_llm(prompt)
                (task_dir / "generated_response.txt").write_text(raw_response, encoding="utf-8")
                generated = extract_python_code(raw_response)
                (task_dir / "generated_tests.py").write_text(generated + "\n", encoding="utf-8")
                test_names = validate_generated_code(generated)
                executable = generated
                if re.search(r"\bpytest\.", generated) and not re.search(
                    r"^\s*import\s+pytest\b|^\s*from\s+pytest\s+import\b", generated, re.MULTILINE
                ):
                    executable = "import pytest\n" + generated
                app_dir, results_dir = _prepare_case(task_dir / "multiagent", source, reference_tests, executable)
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
                task_result["multiagent"] = {"status": "interrupted", "error": "Interrompu pendant l'appel Ollama."}
                save_json(task_dir / "task_results.json", task_result)
                task_results.append(task_result)
                interrupted = True
                print(f"MBPP/{task_id}: génération interrompue; baseline conservée", flush=True)
                break
            except Exception as error:
                task_result["multiagent"] = {"status": "error", "error": f"{type(error).__name__}: {error}"}

        save_json(task_dir / "task_results.json", task_result)
        task_results.append(task_result)
        multi = task_result.get("multiagent")
        print(f"MBPP/{task_id}: baseline={baseline['status']}" + (f", multiagent={multi['status']}" if multi else ""), flush=True)

    baseline_passed = sum(1 for result in task_results if result["baseline"]["status"] == "passed")
    multi_results = [result["multiagent"] for result in task_results if result.get("multiagent") and result["multiagent"].get("execution")]
    summary = {
        "run_id": experiment["run_id"],
        "benchmark": "mbpp",
        "mode": "multiagent",
        "status": "baseline_only" if args.baseline_only else (
            "interrupted" if interrupted else "completed" if len(multi_results) == len(selected) else "partial"
        ),
        "protocol": metadata["evaluation_protocol"],
        "tasks_requested": len(selected),
        "baseline_tasks_passed": baseline_passed,
        "multiagent_tasks_passed": sum(1 for item in multi_results if item["execution"]["status"] == "passed"),
        "mean_coverage_before": _mean([(item["baseline"].get("coverage") or {}).get("percent_covered") for item in task_results]),
        "mean_coverage_after": _mean([((item.get("multiagent") or {}).get("execution", {}).get("coverage") or {}).get("percent_covered") for item in task_results]),
        "mean_coverage_delta_percentage_points": _mean([item.get("coverage_delta_percentage_points") for item in task_results]),
        "coverage_before": _mean([(item["baseline"].get("coverage") or {}).get("percent_covered") for item in task_results]),
        "coverage_after": _mean([((item.get("multiagent") or {}).get("execution", {}).get("coverage") or {}).get("percent_covered") for item in task_results]),
        "coverage_delta_percentage_points": _mean([item.get("coverage_delta_percentage_points") for item in task_results]),
        "branch_coverage_before": _mean([(item["baseline"].get("coverage") or {}).get("percent_branches_covered") for item in task_results]),
        "branch_coverage_after": _mean([((item.get("multiagent") or {}).get("execution", {}).get("coverage") or {}).get("percent_branches_covered") for item in task_results]),
        "mean_critic_score": _mean([((item.get("multiagent") or {}).get("critic") or {}).get("score") for item in task_results]),
        "tasks": task_results,
    }
    save_json(run_dir / "benchmark_results.json", summary)
    metadata["finished_at"] = datetime.now(timezone.utc).isoformat()
    metadata["status"] = summary["status"]
    save_json(run_dir / "metadata.json", metadata)
    _write_report(run_dir / "report.md", summary)
    print(f"Rapport MBPP : {run_dir / 'report.md'}")
    return 0 if summary["status"] in {"completed", "baseline_only"} else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=3, help="Nombre de tâches MBPP (défaut : 3).")
    parser.add_argument("--seed", type=int, default=42, help="Graine de sélection reproductible.")
    parser.add_argument("--baseline-only", action="store_true", help="Exécute uniquement les tests de référence, sans Ollama.")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit doit être supérieur ou égal à 1")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
