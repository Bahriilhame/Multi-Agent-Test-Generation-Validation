"""Central, version-controlled LLM prompt templates."""

import json


def build_generic_generation_prompt(*, source: str, uncovered: list[dict], existing_tests: str, feedback: str, task_context: str) -> str:
    return f"""You are a senior Python test engineer. Generate additional pytest tests for this project.
Return only Python test code. Do not alter production code. Use behavior justified by the source; cover normal, boundary, invalid and exception cases where source semantics support them. Use meaningful assertions, deterministic data and parametrization where useful. Avoid duplicating existing tests. Do not use filesystem, process, network or shell access. Tests must import project code correctly.

Existing tests (avoid duplicating covered behaviors):
{existing_tests[:12000]}
Uncovered source lines/functions (coverage is not a behavior specification):
{json.dumps(uncovered, ensure_ascii=False, indent=2)}
Critic feedback to address on this iteration:
{feedback[:5000]}
Issue/task context (if supplied; source code remains authoritative for visible behavior):
{task_context[:6000]}
Source context:
{source[:12000]}
"""


def build_generic_critic_prompt(*, source: str, task_context: str, tests: str, execution: dict | None = None) -> str:
    return f"""Review whether these generated tests meaningfully verify the supplied Python source. Return only compact JSON matching exactly this schema:
{{"score":0,"dimensions":{{"contract":0,"assertions":0,"edge_cases":0,"independence":0}},"issues":[{{"test_name":"exact test function name","severity":"critical|major|minor","evidence":"exact non-empty substring copied from the test code","reason":"short factual issue","suggestion":"short fix"}}],"summary":"short summary"}}
Each dimension is an integer 0-25 and score MUST equal their sum. For a generally sound suite, scores should usually be 18-25 per dimension; do not use very low scores for a localized improvement. Every issue must cite an exact substring and exact test function name. Omit any issue without direct textual evidence. Do not claim a scenario is absent if it is present. A test for an invalid input is relevant when the source explicitly validates and rejects it. Do not critique filename conventions or style. Flag incorrect expected values, trivial checks, redundancy, unjustified inputs and missing meaningful edge cases. Passing pytest is not sufficient evidence of relevance.

SOURCE:
{source[:5000]}

ISSUE CONTEXT:
{task_context[:3000]}

GENERATED TESTS:
{tests[:5000]}

OBJECTIVE EXECUTION EVIDENCE:
{json.dumps(execution or {}, ensure_ascii=False)[:2000]}
"""
