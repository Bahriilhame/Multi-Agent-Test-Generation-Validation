from typing import TypedDict, Any


class TestingState(TypedDict, total=False):

    # Informations sur le projet
    project_path: str
    project_name: str

    # Résultats de l'analyse de couverture
    coverage_before: float
    uncovered_functions: list[str]
    uncovered_lines: list[int]
    uncovered_details: list[dict[str, Any]]
    coverage_report_path: str
    test_exit_code: int

    # Génération des tests
    generated_tests: str
    generated_test_file: str

    # Résultats de validation
    test_results: dict[str, Any]
    coverage_after: float

    # Critique des tests
    relevance_score: float
    relevance_feedback: str

    # Gestion du workflow
    validation_status: str
    iteration: int
    max_iterations: int

    # Rapport final
    final_report: dict[str, Any]