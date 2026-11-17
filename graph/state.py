from typing import TypedDict, Any


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
