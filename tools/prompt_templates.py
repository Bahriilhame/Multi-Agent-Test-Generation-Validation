"""Central, version-controlled LLM prompt templates."""

import json


def _compact_uncovered(uncovered: list[dict], *, max_chars: int = 1500) -> str:
    """Keep the highest priority coverage facts within a small prompt budget."""
    selected = []
    for item in uncovered[:12]:
        functions = [
            {
                "name": str(function.get("name", ""))[:100],
                "missing_lines": function.get("missing_lines", [])[:8],
                "missing_branches": function.get("missing_branches", [])[:5],
            }
            for function in item.get("functions", [])[:3]
        ]
        compact = {
            "file": str(item.get("file", ""))[:160],
            "missing_lines": item.get("missing_lines", [])[:12],
            "missing_branches": item.get("missing_branches", [])[:8],
            "functions": functions,
        }
        if len(json.dumps(selected + [compact], ensure_ascii=False)) > max_chars:
            break
        selected.append(compact)
    return json.dumps(selected, ensure_ascii=False, separators=(",", ":"))


def build_generic_generation_prompt(
    *, source: str, uncovered: list[dict], existing_tests: str,
    existing_test_names: list[str] | None = None, feedback: str, task_context: str,
    repair_targets: list[str] | None = None,
    passing_generated_tests: list[str] | None = None,
) -> str:
    repair_mode = bool(repair_targets)
    task = (
        "Generate only replacement pytest functions for these failed tests: "
        + ", ".join(repair_targets or [])
        + ". Successful generated tests are kept by the workflow; do not regenerate or rename them."
        if repair_mode
        else "Generate 2-4 concise additional pytest tests for this project."
    )
    return f"""You are a senior Python test engineer.
{task}
Return only Python test code, under 600 tokens. Do not alter production code. On retries, replace or correct every failed generated test identified in the feedback; do not repeat its failing operation or test body unchanged. Treat pytest exceptions as evidence of actual source behavior, and only assert an exception when the test explicitly expects it. Successful generated tests are retained automatically: {", ".join((passing_generated_tests or [])[:20]) or "none yet"}. Do not copy fixtures from existing test modules into this separate generated module; include every import for fixtures you define. Use behavior justified by the source; cover normal, boundary, invalid and exception cases where source semantics support them. Use meaningful assertions, deterministic data and parametrization where useful. Avoid duplicating existing tests. Do not use filesystem, process, network or shell access. Tests must import project code correctly.

Existing tests (avoid duplicating covered behaviors):
Existing test function names (never repeat these): {", ".join((existing_test_names or [])[:100])}
{existing_tests[:1000]}
Uncovered source lines/functions (coverage is not a behavior specification):
{_compact_uncovered(uncovered, max_chars=900)}
Critic feedback to address on this iteration:
{feedback[:1600]}
Issue/task context (if supplied; source code remains authoritative for visible behavior):
{task_context[:300]}
Source context:
{source[:2000]}
"""


def build_generic_critic_prompt(*, source: str, task_context: str, tests: str, execution: dict | None = None) -> str:
    return f"""Review whether these generated tests meaningfully verify the supplied Python source. Return only compact JSON matching exactly this schema:
{{"score":0,"dimensions":{{"contract":0,"assertions":0,"edge_cases":0,"independence":0}},"issues":[{{"test_name":"exact test function name","severity":"critical|major|minor","evidence":"exact non-empty substring copied from the test code","reason":"short factual issue","suggestion":"short fix"}}],"summary":"short summary"}}
Each dimension is an integer 0-25 and score MUST equal their sum. For a generally sound suite, scores should usually be 18-25 per dimension; do not use very low scores for a localized improvement. Report at most the two highest-impact issues. Keep the summary and each reason/suggestion brief. Every issue must cite an exact substring and exact test function name. Omit any issue without direct textual evidence. Do not claim a scenario is absent if it is present. A test for an invalid input is relevant when the source explicitly validates and rejects it. Do not critique filename conventions or style. Flag incorrect expected values, trivial checks, redundancy, unjustified inputs and missing meaningful edge cases. Passing pytest is not sufficient evidence of relevance.

SOURCE:
{source[:5000]}

ISSUE CONTEXT:
{task_context[:3000]}

GENERATED TESTS:
{tests[:5000]}

OBJECTIVE EXECUTION EVIDENCE:
{json.dumps(execution or {}, ensure_ascii=False)[:2000]}
"""
