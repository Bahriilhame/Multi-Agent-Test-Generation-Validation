
from typing import TypedDict, Any


class TestingState(TypedDict, total=False):

    # Informations du projet
    project_path: str
    project_name: str

    # Analyse de couverture
    coverage_before: float
    uncovered_functions: list[str]
    uncovered_lines: list[int]

    # Génération des tests
    generated_tests: str
    generated_test_file: str

    # Validation
    test_results: dict[str, Any]
    coverage_after: float

    # Critique
    relevance_score: float
    relevance_feedback: str
    validation_status: str

    # Gestion des tentatives
    iteration: int
    max_iterations: int

    # Rapport final
    final_report: dict[str, Any]
