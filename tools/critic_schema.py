"""Validate and ground structured relevance-critic responses."""

import ast
import json
import re
from typing import Any

DIMENSIONS = ("contract", "assertions", "edge_cases", "independence")
SEVERITIES = {"critical", "major", "minor"}


def validate_critic_response(raw: str, tests_source: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError("Critic response contains no JSON object.")
    report = json.loads(match.group(0))
    score = report.get("score")
    dimensions = report.get("dimensions")
    if not isinstance(score, (int, float)) or not 0 <= score <= 100 or not isinstance(dimensions, dict):
        raise ValueError("Critic score or dimensions are missing/invalid.")
    for key in DIMENSIONS:
        value = dimensions.get(key)
        if not isinstance(value, (int, float)) or not 0 <= value <= 25:
            raise ValueError(f"Invalid critic dimension: {key}")
    expected_score = sum(float(dimensions[key]) for key in DIMENSIONS)
    if abs(float(score) - expected_score) > 0.5:
        raise ValueError("Critic score does not equal the sum of its dimensions.")
    tree = ast.parse(tests_source)
    test_nodes = {node.name: node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")}
    names = set(test_nodes)
    issues = report.get("issues")
    if not isinstance(issues, list):
        raise TypeError("Critic issues must be a JSON list.")
    grounded, unsupported = [], []
    for issue in issues:
        valid_shape = (
            isinstance(issue, dict)
            and issue.get("test_name") in names
            and issue.get("severity") in SEVERITIES
            and isinstance(issue.get("evidence"), str)
            and bool(issue["evidence"].strip())
            and issue["evidence"] in tests_source
            and isinstance(issue.get("reason"), str)
            and isinstance(issue.get("suggestion"), str)
        )
        if valid_shape:
            node = test_nodes[issue["test_name"]]
            claim = (issue.get("reason", "") + " " + issue.get("suggestion", "")).lower()
            denies_exception_check = bool(re.search(r"(?:does not|doesn't|fails to|lacks?|missing|not)\b.{0,100}\b(?:verify|test|check|raise|exception)", claim))
            explicitly_checks_value_error = any(
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr == "raises"
                and call.args
                and isinstance(call.args[0], ast.Name)
                and call.args[0].id == "ValueError"
                for call in ast.walk(node)
            )
            if denies_exception_check and "valueerror" in claim and explicitly_checks_value_error:
                valid_shape = False
        (grounded if valid_shape else unsupported).append(issue)
    return {
        "score": round(float(score), 2),
        "dimensions": {key: round(float(dimensions[key]), 2) for key in DIMENSIONS},
        "issues": grounded,
        "unsupported_issues": unsupported,
        "summary": str(report.get("summary", ""))[:2000],
    }
