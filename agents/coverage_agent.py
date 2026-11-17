
import json
from pathlib import Path
import subprocess
import sys

from config.settings import (
    BASE_DIR,
    PROJECT_DIR,
    TESTS_DIR,
    GENERATED_TESTS_DIR,
    REPORTS_DIR
)


def coverage_agent(state):

    print("\n[Agent 1] Analyse de couverture...")

    # 1. Vérifier les dossiers nécessaires
    if not PROJECT_DIR.exists():
        raise FileNotFoundError(
            f"Projet introuvable : {PROJECT_DIR}"
        )

    if not TESTS_DIR.exists():
        raise FileNotFoundError(
            f"Dossier des tests introuvable : {TESTS_DIR}"
        )

    # 2. Créer le dossier des rapports
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    report_path = (
        Path(state["run_dir"]) / "coverage_before.json"
        if state.get("run_dir") else REPORTS_DIR / "coverage_before.json"
    )

    # 3. Préparer la commande pytest avec coverage
    coverage_target = PROJECT_DIR.relative_to(BASE_DIR).as_posix()

    command = [
        sys.executable,
        "-m",
        "pytest",
        str(TESTS_DIR),
        "--ignore=" + str(GENERATED_TESTS_DIR),
        f"--cov={coverage_target}",
        "--cov-branch",
        f"--cov-report=json:{report_path}",
        "--cov-report=term-missing"
    ]

    print("\nExécution des tests et mesure de couverture...")

    # 4. Exécuter les tests
    result = subprocess.run(
        command,
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace"
    )

    print(result.stdout)

    if result.stderr:
        print(result.stderr)

    # 5. Vérifier que le rapport existe
    if not report_path.exists():
        raise RuntimeError(
            "Impossible de générer le rapport de couverture. "
            "Vérifie pytest et pytest-cov."
        )

    # 6. Lire le rapport JSON
    with open(report_path, "r", encoding="utf-8") as file:
        report = json.load(file)

    if state.get("run_dir"):
        (Path(state["run_dir"]) / "logs" / "coverage_baseline.txt").write_text(
            result.stdout + "\n" + result.stderr, encoding="utf-8"
        )

    # 7. Récupérer le taux global de couverture
    totals = report.get("totals", {})

    coverage_percent = totals.get(
        "percent_covered",
        0.0
    )

    # 8. Identifier les fonctions et lignes non couvertes
    uncovered_functions = []
    uncovered_lines = []
    uncovered_details = []

    for file_path, file_data in report.get("files", {}).items():

        missing_lines = file_data.get("missing_lines", [])

        uncovered_lines.extend(missing_lines)

        functions = file_data.get("functions", {})

        for function_name, function_data in functions.items():

            missing_count = function_data.get(
                "summary", {}
            ).get("missing_lines", 0)

            if missing_count > 0:

                uncovered_functions.append(
                    f"{file_path}::{function_name}"
                )

        if missing_lines:

            uncovered_details.append({
                "file": file_path,
                "missing_lines": missing_lines
            })

    # 9. Ajouter les résultats à l'état partagé
    state["coverage_before"] = round(
        coverage_percent, 2
    )
    state["branch_coverage_before"] = round(
        totals.get("percent_branches_covered", 0.0), 2
    )

    state["uncovered_functions"] = uncovered_functions

    state["uncovered_lines"] = uncovered_lines

    state["uncovered_details"] = uncovered_details

    state["coverage_report_path"] = str(report_path)

    state["test_exit_code"] = result.returncode

    # 10. Afficher le résumé
    print("\n========== COVERAGE ANALYSIS ==========")

    print(f"Couverture initiale : {coverage_percent:.2f}%")

    print(
        f"Fonctions avec lignes non couvertes : "
        f"{len(uncovered_functions)}"
    )

    print(
        f"Lignes non couvertes : "
        f"{len(uncovered_lines)}"
    )

    print("\nFonctions à améliorer :")

    for function in uncovered_functions:
        print(f" - {function}")

    print("\nLignes non couvertes :")

    for detail in uncovered_details:
        print(
            f" - {detail['file']} : "
            f"{detail['missing_lines']}"
        )

    if result.returncode != 0:
        print(
            "\nAttention : certains tests ont échoué "
            "ou pytest a rencontré une erreur."
        )

    print("\n=======================================")

    return state
