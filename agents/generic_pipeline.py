"""Project-agnostic agent nodes for the generic Python workflow."""

from __future__ import annotations

import ast
import json
import re
import time
from pathlib import Path
from typing import Any

from adapters import detect_project
from adapters.python import PythonAdapter
from sandbox.generic_runner import run_in_docker
from tools.critic_schema import validate_critic_response
from tools.llm_client import ask_llm
from tools.ollama_json import ask_llm_json
from tools.prompt_templates import (
    build_generic_critic_prompt,
    build_generic_generation_prompt,
)


def analyze_node(state: dict[str, Any]) -> dict[str, Any]:
    root = Path(state["project_path"]).expanduser().resolve()
    info = detect_project(root)
    if not info.supported or info.adapter != "python":
        raise ValueError(info.unsupported_reason or f"No executable adapter for {info.languages}")
    adapter = PythonAdapter()
    run_dir = Path(state["run_dir"])
    baseline = run_in_docker(root, run_dir / "baseline", "", image=state.get("docker_image", "smarttest-runner:latest"))
    missing_dependencies = baseline.get("missing_dependencies", [])
    if missing_dependencies:
        names = ", ".join(missing_dependencies)
        raise RuntimeError(
            f"Runner image is missing project dependencies: {names}. "
            "Build a custom Docker image with the project's requirements installed, "
            "then select that image in the UI."
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
    return {
        "project_info": info.to_dict(), "adapter": "python", "coverage_before": coverage.get("totals", {}).get("percent_covered", 0),
        "branch_coverage_before": coverage.get("totals", {}).get("percent_branches_covered", 0),
        "uncovered_details": uncovered, "coverage_before_report": {"totals": coverage.get("totals", {}), "files": coverage.get("files", {})},
        "baseline_results": {k: v for k, v in baseline.items() if k != "output"},
        "source_context": adapter.generate_test_context(root, info, limit=12_000),
        "existing_test_files": [str(p.relative_to(root)) for p in adapter.discover_tests(root)],
        "existing_tests_context": "\n\n".join(
            f"# {path.relative_to(root).as_posix()}\n{path.read_text(encoding='utf-8', errors='replace')[:5000]}"
            for path in adapter.discover_tests(root)[:8]
        )[:12_000],
        "stage": "analyzed",
    }


def _extract_code(response: str) -> str:
    blocks = re.findall(r"```(?:python)?\s*(.*?)```", response, re.IGNORECASE | re.DOTALL)
    code = "\n\n".join(blocks).strip() if blocks else response.strip()
    tree = ast.parse(code)
    tests = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")]
    if not tests:
        raise ValueError("The model response contains no pytest test functions.")
    if len({node.name for node in tests}) != len(tests):
        raise ValueError("Generated tests contain duplicate function names.")
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
    existing = state.get("existing_tests_context", "") or "\n".join(state.get("existing_test_files", []))
    prompt = build_generic_generation_prompt(source=context, uncovered=state.get("uncovered_details", []), existing_tests=existing, feedback=prior, task_context=state.get("task_context", ""))
    generation_started = time.perf_counter()
    response = ask_llm(prompt, timeout_seconds=180, max_retries=0, wall_timeout_seconds=240, max_output_tokens=700)
    try:
        code = _extract_code(response)
    except (SyntaxError, ValueError) as first_error:
        repair_prompt = (
            prompt + "\n\nYour previous response was invalid: " + str(first_error)
            + "\nRepair it and return only one syntactically valid Python module containing pytest test functions."
        )
        response = ask_llm(repair_prompt, timeout_seconds=180, max_retries=0, wall_timeout_seconds=240, max_output_tokens=700)
        code = _extract_code(response)
    generation_duration = round(time.perf_counter() - generation_started, 3)
    destination = Path(state["run_dir"]) / "generated_tests" / "test_generated.py"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and state.get("iteration", 0) == 0:
        raise FileExistsError(f"Refusing to overwrite generated test file: {destination}")
    destination.write_text(code + "\n", encoding="utf-8")
    return {"generated_tests": code, "generated_test_file": str(destination), "generated_test_count": sum(1 for n in ast.walk(ast.parse(code)) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_")), "generation_duration_seconds": generation_duration, "stage": "generated"}


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
    if generated_passed + generated_failed:
        executed_ratio = generated_passed / (generated_passed + generated_failed)
    assertion_ratio = min(1, assertions / max(1, len(tests)))
    meaningful = sum(1 for test in tests if any(isinstance(n, ast.Assert) for n in ast.walk(test))) / max(1, len(tests))
    heuristic_score = round(100 * (0.45 * executed_ratio + 0.35 * assertion_ratio + 0.20 * meaningful), 2)
    feedback = []
    if failed:
        feedback.append(f"{failed} generated/existing tests failed or errored; repair the concrete assertion failures below.")
        details = execution.get("failure_details", "")
        if details:
            feedback.append("Observed pytest failure detail:\n" + details[:5000])
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
        feedback.append("Semantic review was unavailable; this run cannot be accepted automatically.")
    result = {"score": score, "heuristic_score": heuristic_score, "semantic_score": semantic_score, "semantic_dimensions": semantic_dimensions, "semantic_unsupported_issues": semantic_unsupported, "accepted": accepted, "test_functions": len(tests), "assertions": assertions, "generated_tests_passed": generated_passed, "generated_tests_failed": generated_failed, "execution_pass_rate": round(100 * executed_ratio, 2), "feedback": feedback, "method": semantic_method, "duration_seconds": critic_duration}
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
