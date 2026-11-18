"""Recompute a generic run's critic decision from saved tests and evidence."""

import argparse
import ast
import json
from pathlib import Path

from tools.critic_schema import validate_critic_response


def review(run_dir: Path, response_file: Path | None, threshold: float) -> dict:
    report_path = run_dir / "report.json"
    generated_path = run_dir / "generated_tests" / "test_generated.py"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    code = generated_path.read_text(encoding="utf-8")
    critic_iteration = int(report.get("iterations", 1)) - 1
    response_path = response_file or run_dir / f"critic_response_iteration-{critic_iteration}.txt"
    semantic = validate_critic_response(response_path.read_text(encoding="utf-8"), code)
    tree = ast.parse(code)
    tests = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")]
    execution = report.get("execution", {})
    passed = int(execution.get("generated_passed", 0))
    failed = int(execution.get("generated_failed", 0))
    assertions = sum(1 for test in tests for node in ast.walk(test) if isinstance(node, ast.Assert) or isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"raises", "approx", "warns"})
    pass_ratio = passed / max(1, passed + failed)
    assertion_ratio = min(1, assertions / max(1, len(tests)))
    meaningful_ratio = sum(1 for test in tests if any(isinstance(node, ast.Assert) for node in ast.walk(test))) / max(1, len(tests))
    heuristic = round(100 * (0.45 * pass_ratio + 0.35 * assertion_ratio + 0.20 * meaningful_ratio), 2)
    score = round(0.25 * semantic["score"] + 0.75 * heuristic, 2)
    coverage_before = report.get("coverage_before")
    coverage_after = report.get("coverage_after")
    no_regression = coverage_before is None or coverage_after is None or float(coverage_after) >= float(coverage_before)
    blockers = [issue for issue in semantic["issues"] if issue.get("severity") == "critical"]
    execution_ok = execution.get("exit_code") == 0 and not execution.get("missing_dependencies")
    accepted = execution_ok and bool(tests) and score >= threshold and no_regression and not blockers
    result = {
        "version": "generic-critic-review-v2",
        "status": "accepted" if accepted else "not_accepted",
        "score": score,
        "semantic_score": semantic["score"],
        "semantic_dimensions": semantic["dimensions"],
        "heuristic_score": heuristic,
        "threshold": threshold,
        "generated_test_count": len(tests),
        "generated_tests_passed": passed,
        "generated_tests_failed": failed,
        "assertion_count": assertions,
        "coverage_before": coverage_before,
        "coverage_after": coverage_after,
        "semantic_issues": semantic["issues"],
        "unsupported_critic_issues": semantic["unsupported_issues"],
        "critic_summary": semantic["summary"],
        "critic_response": str(response_path),
        "protocol_note": "Replayed from saved pytest/coverage evidence and JSON-mode critic response; not a proof of defect detection.",
    }
    output = run_dir / "critic_result_v2.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"result": result, "path": output}


def main() -> int:
    parser = argparse.ArgumentParser(description="Re-evaluate a generic run without running tests or calling Ollama")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--response-file", type=Path)
    parser.add_argument("--threshold", type=float, default=70)
    args = parser.parse_args()
    if not 0 <= args.threshold <= 100:
        parser.error("--threshold must be between 0 and 100")
    result = review(args.run_dir.expanduser().resolve(), args.response_file, args.threshold)
    print(json.dumps({"status": result["result"]["status"], "score": result["result"]["score"], "critic_result": str(result["path"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
