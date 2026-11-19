from typing import Any, TypedDict


class TestingState(TypedDict, total=False):

    # Informations sur le projet
    project_path: str
    project_name: str
    benchmark: str
    mode: str
    run_id: str
    run_dir: str

    # Résultats de l'analyse de couverture
    coverage_before: float
    uncovered_functions: list[str]
    uncovered_lines: list[int]
    uncovered_details: list[dict[str, Any]]
    coverage_report_path: str
    branch_coverage_before: float
    branch_coverage_after: float
    test_exit_code: int

    # Génération des tests
    generated_tests: str
    generated_test_file: str
    generated_test_count: int

    # Résultats de validation
    test_results: dict[str, Any]
    coverage_after: float
    coverage_after_report_path: str

    # Critique des tests
    relevance_score: float
    relevance_feedback: str
    critic_result: dict[str, Any]

    # Gestion du workflow
    validation_status: str
    iteration: int
    max_iterations: int

    # Rapport final
    final_report: dict[str, Any]

    # Generic workflow fields (kept optional for legacy checkout state)
    project_info: dict[str, Any]
    adapter: str
    source_context: str
    existing_test_files: list[str]
    existing_test_names: list[str]
    existing_tests_context: str
    baseline_results: dict[str, Any]
    execution_result: dict[str, Any]
    critic_feedback: str
    critic_repair_targets: list[str]
    accepted: bool
    min_quality_score: float
    run_error: str
    errors: list[str]
    stage: str
    task_context: str
    generation_duration_seconds: float
    coverage_before_report: dict[str, Any]
    source_kind: str
    docker_image: str
    timeout_seconds: int
    coverage_available: bool
    coverage_saturated: bool
    coverage_status: str
    coverage_goal_met: bool
    best_candidate: dict[str, Any]
