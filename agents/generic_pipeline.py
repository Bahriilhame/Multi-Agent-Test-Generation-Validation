"""Project-agnostic agent nodes for the generic Python workflow."""

from __future__ import annotations

import ast
import builtins
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from adapters import detect_project
from adapters.python import PythonAdapter
from sandbox.dependency_image import IMPORT_TO_DISTRIBUTION, build_project_image
from sandbox.generic_runner import (
    ensure_runner_image,
    run_in_docker,
    summarize_failure_details,
)
from tools.critic_schema import validate_critic_response
from tools.llm_client import ask_llm
from tools.ollama_json import ask_llm_json
from tools.prompt_templates import (
    build_generic_critic_prompt,
    build_generic_generation_prompt,
)


def _record_phase(state: dict[str, Any], node: str, status: str, detail: str | None = None) -> None:
    run_dir = state.get("run_dir")
    if not run_dir:
        return
    folder = Path(run_dir)
    folder.mkdir(parents=True, exist_ok=True)
    event = {
        "timestamp": datetime.now(UTC).isoformat(),
        "node": node,
        "status": status,
        "iteration": int(state.get("iteration", 0)),
    }
    if detail:
        event["detail"] = detail
    with (folder / "events.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        stream.flush()


def analyze_node(state: dict[str, Any]) -> dict[str, Any]:
    root = Path(state["project_path"]).expanduser().resolve()
    info = detect_project(root)
    if not info.supported or info.adapter != "python":
        raise ValueError(info.unsupported_reason or f"No executable adapter for {info.languages}")
    adapter = PythonAdapter()
    run_dir = Path(state["run_dir"])
    requested_image = state.get("docker_image", "auto")
    _record_phase(state, "environment", "started", "Détection des dépendances du projet")
    if requested_image == "auto":
        _record_phase(state, "dependencies", "started", "Lecture des manifests et imports Python")
        try:
            ensure_runner_image()
            docker_image, inferred_modules = build_project_image(
                root,
                run_dir,
                progress=lambda status, detail, error: _record_phase(
                    state, "dependencies", status, error or detail
                ),
            )
        except Exception as error:
            _record_phase(state, "dependencies", "failed", f"{type(error).__name__}: {error}")
            _record_phase(state, "environment", "failed", f"{type(error).__name__}: {error}")
            raise
        environment_detail = f"Image prête : {docker_image}"
        if inferred_modules:
            environment_detail += f" · {len(inferred_modules)} import(s) pris en compte"
        _record_phase(state, "dependencies", "completed", environment_detail)
    else:
        docker_image = requested_image
        inferred_modules = []
        environment_detail = f"Image personnalisée : {docker_image}"
    _record_phase(state, "environment", "completed", environment_detail)
    _record_phase(state, "baseline", "started", "Exécution des tests existants et mesure de couverture")
    baseline = run_in_docker(root, run_dir / "baseline", "", image=docker_image)
    missing_dependencies = baseline.get("missing_dependencies", [])
    if missing_dependencies and requested_image == "auto":
        _record_phase(
            state,
            "baseline",
            "completed",
            "Imports dynamiques manquants détectés : " + ", ".join(missing_dependencies),
        )
        _record_phase(state, "dependencies", "started", "Résolution automatique des imports manquants")
        try:
            docker_image, inferred_modules = build_project_image(
                root,
                run_dir,
                extra_modules=missing_dependencies,
                progress=lambda status, detail, error: _record_phase(
                    state, "dependencies", status, error or detail
                ),
            )
        except Exception as error:
            _record_phase(state, "dependencies", "failed", f"{type(error).__name__}: {error}")
            raise
        _record_phase(state, "dependencies", "completed", f"Image mise à jour : {docker_image}")
        _record_phase(state, "baseline", "started", "Nouvelle exécution après installation des dépendances détectées")
        baseline = run_in_docker(root, run_dir / "baseline", "", image=docker_image)
    _record_phase(
        state,
        "baseline",
        "completed" if baseline.get("exit_code") == 0 else "failed",
        f"{baseline.get('passed', 0)} réussi(s), {baseline.get('failed', 0) + baseline.get('errors', 0)} échec(s)",
    )
    missing_dependencies = baseline.get("missing_dependencies", [])
    if missing_dependencies:
        names = ", ".join(
            f"{module} (pip: {IMPORT_TO_DISTRIBUTION[module]})" if module in IMPORT_TO_DISTRIBUTION else module
            for module in missing_dependencies
        )
        raise RuntimeError(
            f"Dependencies still missing from the prepared runner image: {names}. "
            "Check the project dependency manifest or provide a compatible --docker-image."
        )
    coverage = baseline.get("coverage") or {}
    uncovered = []
    for filename, data in coverage.get("files", {}).items():
        lines = data.get("missing_lines", [])
        branches = data.get("missing_branches", [])
        functions = []
        for name, fn in data.get("functions", {}).items():
            summary = fn.get("summary", {})
            missing_lines = fn.get("missing_lines", [])
            missing_branches = fn.get("missing_branches", [])
            if summary.get("missing_lines", 0) or summary.get("missing_branches", 0):
                functions.append({"name": name, "missing_lines": missing_lines, "missing_branches": missing_branches, "priority": summary.get("missing_lines", 0) + summary.get("missing_branches", 0)})
        functions.sort(key=lambda function: (-function["priority"], function["name"]))
        if lines or branches:
            uncovered.append({"file": filename, "missing_lines": lines, "missing_branches": branches, "functions": functions, "priority": len(lines) + len(branches)})
    uncovered.sort(key=lambda item: (-item["priority"], item["file"]))
    test_paths = adapter.discover_tests(root)
    existing_test_names = []
    existing_test_summaries = []
    for path in test_paths:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        names_in_file = [
            node.name for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
        ]
        existing_test_names.extend(names_in_file)
        existing_test_summaries.append(
            f"{path.relative_to(root).as_posix()}: {', '.join(sorted(set(names_in_file))) or 'no test functions detected'}"
        )
    return {
        "project_info": info.to_dict(), "adapter": "python", "coverage_before": coverage.get("totals", {}).get("percent_covered", 0),
        "branch_coverage_before": coverage.get("totals", {}).get("percent_branches_covered", 0),
        "uncovered_details": uncovered, "coverage_before_report": {"totals": coverage.get("totals", {}), "files": coverage.get("files", {})},
        "baseline_results": {k: v for k, v in baseline.items() if k != "output"},
        "docker_image": docker_image,
        "source_context": adapter.generate_test_context(root, info, limit=12_000),
        "existing_test_files": [str(p.relative_to(root)) for p in test_paths],
        "existing_test_names": sorted(set(existing_test_names)),
        "existing_tests_context": "\n".join(existing_test_summaries[:50]),
        "stage": "analyzed",
    }


def _module_importable_symbols(project_root: Path) -> dict[str, str]:
    """Map top-level project symbols to safe Python import statements."""
    symbols: dict[str, str] = {}
    for path in sorted(project_root.rglob("*.py")):
        relative = path.relative_to(project_root)
        if any(part in {".git", ".venv", "venv", "tests", "test", "smarttest_generated", "__pycache__"} for part in relative.parts):
            continue
        if path.name.startswith("test_"):
            continue
        module_parts = list(relative.with_suffix("").parts)
        if module_parts[-1] == "__init__":
            module_parts.pop()
        if not module_parts or not all(part.isidentifier() for part in module_parts):
            continue
        module = ".".join(module_parts)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, SyntaxError):
            continue
        for node in tree.body:
            names = []
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.append(node.name)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                names.extend(target.id for target in targets if isinstance(target, ast.Name))
            elif isinstance(node, ast.Import):
                names.extend(alias.asname or alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.extend(alias.asname or alias.name for alias in node.names if alias.name != "*")
            for name in names:
                symbols.setdefault(name, f"from {module} import {name}")
    return symbols


def _undefined_test_names(tree: ast.Module) -> set[str]:
    """Find unresolved names referenced by generated pytest functions."""
    module_names = set(dir(builtins))
    has_star_import = False
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            module_names.add(node.name)
        elif isinstance(node, ast.Import):
            module_names.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            has_star_import = has_star_import or any(alias.name == "*" for alias in node.names)
            module_names.update(alias.asname or alias.name for alias in node.names if alias.name != "*")
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            module_names.update(target.id for target in targets if isinstance(target, ast.Name))

    if has_star_import:
        return set()

    undefined = set()
    for test in (
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and (
            node.name.startswith("test_")
            or any(isinstance(decorator, ast.Attribute) and decorator.attr == "fixture" for decorator in node.decorator_list)
        )
    ):
        local_names = {
            arg.arg
            for arg in (*test.args.posonlyargs, *test.args.args, *test.args.kwonlyargs)
        }
        if test.args.vararg:
            local_names.add(test.args.vararg.arg)
        if test.args.kwarg:
            local_names.add(test.args.kwarg.arg)
        loaded_names = set()
        for node in ast.walk(test):
            if isinstance(node, ast.Name):
                if isinstance(node.ctx, ast.Load):
                    loaded_names.add(node.id)
                elif isinstance(node.ctx, ast.Store):
                    local_names.add(node.id)
            elif isinstance(node, ast.Import):
                local_names.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                local_names.update(alias.asname or alias.name for alias in node.names if alias.name != "*")
        undefined.update(loaded_names - module_names - local_names)
    return undefined


def _failure_repair_context(code: str, failure_details: str) -> str:
    """Give the next generation the exact failed test and tell it to replace that case."""
    headers = re.findall(r"(?m)^_{3,}\s*(.*?)\s*_{3,}\s*$", failure_details)
    names = sorted({
        match.group(1)
        for header in headers
        if (match := re.match(r"(test_[A-Za-z0-9_]+)", header.strip()))
    })
    if not names:
        return "Replace the failing test(s); do not repeat the same failing operation unchanged."
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return "Replace the failing test(s); do not repeat the same failing operation unchanged."
    definitions = {
        node.name: ast.get_source_segment(code, node)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names
    }
    context = [
        (
        "These generated tests failed and must be replaced or corrected. Do not copy them unchanged. "
        "Use the observed exception as evidence of actual behavior; avoid repeating a side effect "
        "unless the test explicitly expects that exception."
        )
    ]
    for name in names[:3]:
        context.append(f"Failing test {name}:\n{definitions.get(name, '(source unavailable)')}")
    return "\n".join(context)[:900]


def _merge_retry_tests(
    previous_code: str,
    replacement_code: str,
    failed_names: list[str],
    existing_test_names: list[str] | None = None,
    project_root: Path | None = None,
) -> str:
    """Retain prior passing tests and swap only functions pytest marked as failing."""
    if not failed_names:
        return replacement_code
    previous_tree = ast.parse(previous_code)
    replacement_tree = ast.parse(replacement_code)
    failed = set(failed_names)
    body = []
    previous_test_names = set()
    for node in previous_tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            if node.name in failed:
                continue
            previous_test_names.add(node.name)
        body.append(node)

    seen_imports = {ast.dump(node, include_attributes=False) for node in body if isinstance(node, (ast.Import, ast.ImportFrom))}
    seen_definitions = {
        node.name for node in body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    for node in replacement_tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            signature = ast.dump(node, include_attributes=False)
            if signature not in seen_imports:
                body.append(node)
                seen_imports.add(signature)
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            if node.name in previous_test_names or node.name in (existing_test_names or []):
                continue
            body.append(node)
            previous_test_names.add(node.name)
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in seen_definitions:
                continue
            seen_definitions.add(node.name)
        body.append(node)
    merged = ast.unparse(ast.fix_missing_locations(ast.Module(body=body, type_ignores=[])))
    return _extract_code(merged, existing_test_names, project_root)


def _extract_code(
    response: str,
    existing_test_names: list[str] | None = None,
    project_root: Path | None = None,
) -> str:
    blocks = re.findall(r"```(?:python)?\s*(.*?)```", response, re.IGNORECASE | re.DOTALL)
    code = "\n\n".join(blocks).strip() if blocks else response.strip()
    tree = ast.parse(code)
    tests = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")]
    if not tests:
        raise ValueError("The model response contains no pytest test functions.")
    if len({node.name for node in tests}) != len(tests):
        raise ValueError("Generated tests contain duplicate function names.")
    duplicate_names = sorted({node.name for node in tests}.intersection(existing_test_names or []))
    if duplicate_names:
        lines = code.splitlines()
        remove_lines = set()
        for node in tests:
            if node.name in duplicate_names:
                start = min((decorator.lineno for decorator in node.decorator_list), default=node.lineno)
                remove_lines.update(range(start - 1, node.end_lineno))
        code = "\n".join(line for index, line in enumerate(lines) if index not in remove_lines).strip()
        tree = ast.parse(code)
        tests = [
            node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
        ]
        if not tests:
            raise ValueError(
                "The response only repeated existing test functions; generate genuinely new tests."
            )
    if project_root is not None:
        unresolved = _undefined_test_names(tree)
        available_symbols = _module_importable_symbols(project_root)
        import_lines = [available_symbols[name] for name in sorted(unresolved) if name in available_symbols]
        unresolved -= set(available_symbols)
        if unresolved:
            raise ValueError(f"Generated tests reference undefined name(s): {', '.join(sorted(unresolved))}.")
        if import_lines:
            code = "\n".join(import_lines) + "\n" + code
            tree = ast.parse(code)
    forbidden_calls = {"eval", "exec", "compile", "__import__"}
    forbidden_imports = {"os", "subprocess", "socket", "requests", "urllib", "http", "ftplib", "shutil", "ctypes"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in forbidden_calls:
            raise ValueError(f"Forbidden generated code call: {node.func.id}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr.lower() in {"system", "popen", "popen2", "check_call", "check_output"}:
            raise ValueError(f"Forbidden generated process call: {node.func.attr}")
        if isinstance(node, ast.Import):
            names = [alias.name.split(".")[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [(node.module or "").split(".")[0]]
        else:
            names = []
        blocked = forbidden_imports.intersection(names)
        if blocked:
            raise ValueError(f"Forbidden generated test import: {sorted(blocked)}")
    return code


def generate_node(state: dict[str, Any]) -> dict[str, Any]:
    context = state.get("source_context", "")
    prior = state.get("critic_feedback", "")
    previous_code = state.get("generated_tests", "")
    previous_execution = state.get("execution_result", {})
    failed_names = previous_execution.get("generated_failed_tests", [])
    passing_names = previous_execution.get("generated_passed_tests", [])
    if previous_code and failed_names:
        prior = (
            prior
            + "\nReplace only these failed generated tests: " + ", ".join(failed_names)
            + "\nThe passing generated tests are retained automatically: " + ", ".join(passing_names)
            + "\n"
            + _failure_repair_context(previous_code, previous_execution.get("failure_details", ""))
        )
    existing = state.get("existing_tests_context", "") or "\n".join(state.get("existing_test_files", []))
    prompt = build_generic_generation_prompt(
        source=context, uncovered=state.get("uncovered_details", []), existing_tests=existing,
        existing_test_names=state.get("existing_test_names", []), feedback=prior,
        task_context=state.get("task_context", ""),
        repair_targets=failed_names if previous_code else [],
        passing_generated_tests=passing_names if previous_code else [],
    )
    generation_started = time.perf_counter()
    response = ask_llm(prompt, timeout_seconds=180, max_retries=0, wall_timeout_seconds=240, max_output_tokens=600)
    try:
        code = _extract_code(response, state.get("existing_test_names", []), Path(state["project_path"]))
    except (SyntaxError, ValueError) as first_error:
        repair_prompt = (
            prompt + "\n\nYour previous response was invalid: " + str(first_error)
            + "\nRepair it and return only one syntactically valid Python module containing pytest test functions."
        )
        response = ask_llm(repair_prompt, timeout_seconds=180, max_retries=0, wall_timeout_seconds=240, max_output_tokens=600)
        code = _extract_code(response, state.get("existing_test_names", []), Path(state["project_path"]))
    if previous_code and failed_names:
        code = _merge_retry_tests(
            previous_code,
            code,
            failed_names,
            state.get("existing_test_names", []),
            Path(state["project_path"]),
        )
    generation_duration = round(time.perf_counter() - generation_started, 3)
    destination = Path(state["run_dir"]) / "generated_tests" / "test_generated.py"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and state.get("iteration", 0) == 0:
        raise FileExistsError(f"Refusing to overwrite generated test file: {destination}")
    iteration_file = destination.with_name(f"test_generated_iteration-{state.get('iteration', 0)}.py")
    iteration_file.write_text(code + "\n", encoding="utf-8")
    destination.write_text(code + "\n", encoding="utf-8")
    return {"generated_tests": code, "generated_test_file": str(destination), "generated_test_iteration_file": str(iteration_file), "generated_test_count": sum(1 for n in ast.walk(ast.parse(code)) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_")), "generation_duration_seconds": generation_duration, "stage": "generated"}


def execute_node(state: dict[str, Any]) -> dict[str, Any]:
    result = run_in_docker(state["project_path"], Path(state["run_dir"]) / f"iteration-{state.get('iteration', 0)}", state["generated_tests"], timeout_seconds=int(state.get("timeout_seconds", 120)), image=state.get("docker_image", "smarttest-runner:latest"))
    result.pop("output", None)
    return {"execution_result": result, "coverage_after": (result.get("coverage") or {}).get("totals", {}).get("percent_covered"), "stage": "executed"}


def critic_node(state: dict[str, Any]) -> dict[str, Any]:
    code = state.get("generated_tests", "")
    tree = ast.parse(code)
    tests = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_")]
    assertions = sum(1 for test in tests for n in ast.walk(test) if isinstance(n, ast.Assert) or isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in {"raises", "approx", "warns"})
    execution = state.get("execution_result", {})
    passed, failed = int(execution.get("passed", 0)), int(execution.get("failed", 0)) + int(execution.get("errors", 0))
    executed_ratio = passed / max(1, passed + failed)
    generated_passed = int(execution.get("generated_passed", 0))
    generated_failed = int(execution.get("generated_failed", 0))
    objective_failures = execution.get("exit_code") != 0 or failed > 0 or generated_failed > 0
    if generated_passed + generated_failed:
        executed_ratio = generated_passed / (generated_passed + generated_failed)
    assertion_ratio = min(1, assertions / max(1, len(tests)))
    meaningful = sum(1 for test in tests if any(isinstance(n, ast.Assert) for n in ast.walk(test))) / max(1, len(tests))
    raw_heuristic_score = round(100 * (0.45 * executed_ratio + 0.35 * assertion_ratio + 0.20 * meaningful), 2)
    heuristic_score = min(raw_heuristic_score, 49.0) if objective_failures else raw_heuristic_score
    feedback = []
    if failed:
        feedback.append(f"{failed} generated/existing tests failed or errored; repair the concrete assertion failures below.")
        details = execution.get("failure_details", "")
        if details:
            feedback.append("Concise pytest failure summary:\n" + summarize_failure_details(details))
            feedback.append(_failure_repair_context(code, details))
        failed_names = execution.get("generated_failed_tests", [])
        if failed_names:
            feedback.append("Replace only these failed generated tests: " + ", ".join(failed_names))
        passed_names = execution.get("generated_passed_tests", [])
        if passed_names:
            feedback.append("Keep these passing generated tests unchanged: " + ", ".join(passed_names))
    if execution.get("missing_dependencies"):
        feedback.append("Container dependency errors (install these in a custom image, not at runtime): " + ", ".join(execution["missing_dependencies"]))
    if not assertions: feedback.append("Add meaningful assertions or exception checks; tests currently do not verify outcomes.")
    if len(tests) == 0: feedback.append("No test functions were found.")
    semantic_score = None
    semantic_issues: list[str] = []
    semantic_unsupported: list[dict[str, Any]] = []
    semantic_dimensions: dict[str, float] = {}
    semantic_method = "unavailable"
    critic_started = time.perf_counter()
    if objective_failures:
        semantic_method = "Skipped semantic review because pytest reported failures; objective feedback retained"
    else:
        try:
            raw = ask_llm_json(
                build_generic_critic_prompt(source=state.get("source_context", ""), task_context=state.get("task_context", ""), tests=code, execution={key: execution.get(key) for key in ("exit_code", "passed", "failed", "errors", "generated_passed", "generated_failed")}),
                timeout_seconds=180, wall_timeout_seconds=180, max_output_tokens=350,
            )
            run_dir = state.get("run_dir")
            if run_dir:
                (Path(run_dir) / f"critic_response_iteration-{state.get('iteration', 0)}.txt").write_text(raw, encoding="utf-8")
            parsed = validate_critic_response(raw, code)
            if parsed:
                semantic_score = parsed["score"]
                semantic_unsupported = parsed["unsupported_issues"]
                semantic_dimensions = parsed["dimensions"]
                semantic_issues = [
                    f"{issue['severity']} issue in {issue['test_name']}: {issue['reason']} Fix: {issue['suggestion']} Evidence: {issue['evidence']}"
                    for issue in parsed["issues"][:8]
                ]
                semantic_method = "Ollama semantic review plus deterministic AST/pytest evidence"
        except Exception as error:  # noqa: BLE001 - critic falls back to objective evidence for any Ollama/schema failure.
            semantic_method = f"Ollama review unavailable: {type(error).__name__}; heuristic retained"
    critic_duration = round(time.perf_counter() - critic_started, 3)
    score = round(0.25 * semantic_score + 0.75 * heuristic_score, 2) if semantic_score is not None else heuristic_score
    feedback.extend(semantic_issues)
    threshold = float(state.get("min_quality_score", 70))
    if score < threshold:
        feedback.append(f"Combined quality score {score:.1f} is below the required {threshold:.1f}.")
    before = state.get("coverage_before")
    after = state.get("coverage_after")
    coverage_not_regressed = before is None or after is None or float(after) >= float(before)
    if not coverage_not_regressed:
        feedback.append(f"Coverage regressed from {before}% to {after}%; add tests to retain baseline coverage.")
    critic_blockers = [issue for issue in semantic_issues if issue.startswith("critical issue")]
    if critic_blockers:
        feedback.append("The critic found a grounded critical/major issue; repair it before acceptance.")
    accepted = execution.get("exit_code") == 0 and len(tests) > 0 and score >= threshold and semantic_score is not None and coverage_not_regressed and not critic_blockers
    if semantic_score is None:
        feedback.append("Semantic review was skipped because pytest failures must be repaired first.")
    result = {"score": score, "heuristic_score": heuristic_score, "raw_heuristic_score": raw_heuristic_score, "semantic_score": semantic_score, "semantic_dimensions": semantic_dimensions, "semantic_unsupported_issues": semantic_unsupported, "accepted": accepted, "test_functions": len(tests), "assertions": assertions, "generated_tests_passed": generated_passed, "generated_tests_failed": generated_failed, "generated_passed_tests": execution.get("generated_passed_tests", []), "generated_failed_tests": execution.get("generated_failed_tests", []), "execution_pass_rate": round(100 * executed_ratio, 2), "feedback": feedback, "method": semantic_method, "duration_seconds": critic_duration}
    return {"critic_result": result, "critic_feedback": "\n".join(feedback), "accepted": accepted, "stage": "criticized"}


def finalize_node(state: dict[str, Any]) -> dict[str, Any]:
    run_dir = Path(state["run_dir"])
    report = {
        "run_id": state.get("run_id"), "project": state.get("project_info"), "adapter": state.get("adapter"),
        "status": "error" if state.get("run_error") else ("accepted" if state.get("accepted") else "not_accepted"), "coverage_before": state.get("coverage_before"),
        "coverage_after": state.get("coverage_after"), "branch_coverage_before": state.get("branch_coverage_before"),
        "branch_coverage_after": (state.get("execution_result", {}).get("coverage") or {}).get("totals", {}).get("percent_branches_covered"),
        "coverage_delta_percentage_points": round(float(state.get("coverage_after", 0)) - float(state.get("coverage_before", 0)), 2) if state.get("coverage_after") is not None else None,
        "generation_duration_seconds": state.get("generation_duration_seconds"),
        "critic": state.get("critic_result"), "execution": state.get("execution_result"), "iterations": state.get("iteration", 0) + 1,
        "errors": state.get("errors", []), "limitations": ["Python adapter only", "quality score is deterministic heuristic, not a semantic proof", "container isolation depends on Docker daemon/kernel security"],
    }
    (run_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "report.md").write_text(
        "# SmartTest-AI run\n\n" + "```json\n" + json.dumps(report, ensure_ascii=False, indent=2) + "\n```\n", encoding="utf-8"
    )
    return {"final_report": report, "stage": "completed"}
