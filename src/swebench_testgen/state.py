"""Typed shared state for the LangGraph workflow; no gold fields are allowed."""

from typing import Literal, NotRequired, TypedDict


class TaskInput(TypedDict):
    instance_id: str
    repo: str
    base_commit: str
    environment_setup_commit: str
    problem_statement: str
    hints_text: str
    version: str


class CoverageReport(TypedDict, total=False):
    line_percent: float
    branch_percent: float
    covered_lines: int
    total_lines: int
    covered_branches: int
    total_branches: int
    command: list[str]
    exit_code: int
    report_path: str


class WorkflowState(TypedDict):
    task: TaskInput
    workspace_path: str
    initial_coverage: NotRequired[CoverageReport]
    coverage_gaps: NotRequired[list[dict[str, object]]]
    generated_test_paths: NotRequired[list[str]]
    validation_results: NotRequired[dict[str, object]]
    critique: NotRequired[dict[str, object]]
    iteration: int
    status: Literal["ready", "validated", "needs_regeneration", "rejected", "infrastructure_error"]

