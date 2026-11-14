
import json
import re
import shutil
import subprocess
from pathlib import Path

from config.settings import (
    BASE_DIR,
    PROJECT_DIR,
    TESTS_DIR,
    GENERATED_TESTS_DIR,
)


def prepare_runtime(generated_test_file):
    """Prépare uniquement les fichiers autorisés pour Docker."""

    runtime_dir = BASE_DIR / "sandbox" / "runtime"
    app_dir = runtime_dir / "app"
    results_dir = runtime_dir / "results"

    # Repartir d'un environnement propre
    if app_dir.exists():
        shutil.rmtree(app_dir)

    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / "shop").mkdir()
    (app_dir / "tests" / "generated").mkdir(parents=True)

    results_dir.mkdir(parents=True, exist_ok=True)

    # Supprimer les anciens résultats
    for filename in ["coverage_after.json", ".coverage"]:
        old_file = results_dir / filename
        if old_file.exists():
            old_file.unlink()

    # Copier uniquement les fichiers nécessaires
    shutil.copy2(
        PROJECT_DIR / "checkout.py",
        app_dir / "shop" / "checkout.py"
    )

    shutil.copy2(
        TESTS_DIR / "test_checkout.py",
        app_dir / "tests" / "test_checkout.py"
    )

    generated_path = Path(generated_test_file)

    if not generated_path.is_absolute():
        generated_path = BASE_DIR / generated_path

    if not generated_path.exists():
        raise FileNotFoundError(
            f"Tests générés introuvables : {generated_path}"
        )

    shutil.copy2(
        generated_path,
        app_dir / "tests" / "generated" / "test_generated_checkout.py"
    )

    return app_dir, results_dir


def run_docker_tests(app_dir, results_dir):
    """Exécute les tests dans le conteneur isolé."""

    app_path = str(app_dir.resolve())
    results_path = str(results_dir.resolve())

    command = [
        "docker", "run", "--rm",
        "--network", "none",
        "--read-only",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--pids-limit", "64",
        "--memory", "512m",
        "--cpus", "1",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m,mode=1777",

        "--mount",
        f"type=bind,source={app_path},target=/app,readonly",

        "--mount",
        f"type=bind,source={results_path},target=/tmp/test-results",

        "smarttest-runner:latest"
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120
    )

    output = result.stdout + "\n" + result.stderr

    print("\n[Agent 3] Résultat de l'exécution Docker :")
    print(output)

    return result.returncode, output


def read_coverage_report(results_dir):
    """Lit le rapport JSON produit par coverage.py."""

    report_path = results_dir / "coverage_after.json"

    if not report_path.exists():
        return None

    with open(report_path, "r", encoding="utf-8") as file:
        report = json.load(file)

    totals = report.get("totals", {})

    return {
        "percent_covered": totals.get("percent_covered", 0),
        "num_statements": totals.get("num_statements", 0),
        "missing_lines": totals.get("missing_lines", 0),
        "covered_lines": totals.get("covered_lines", 0)
    }


def parse_test_results(output):
    """Extrait les résultats du résumé pytest."""

    results = {
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0
    }

    for key in results:
        match = re.search(
            rf"(\d+)\s+{key}",
            output
        )

        if match:
            results[key] = int(match.group(1))

    return results


def validation_agent(state):
    """Agent 3 : exécution et validation des tests générés."""

    print("\n[Agent 3] Préparation de l'environnement Docker...")

    generated_test_file = state.get("generated_test_file")

    if not generated_test_file:
        raise ValueError("Aucun fichier de tests générés fourni.")

    app_dir, results_dir = prepare_runtime(generated_test_file)

    print("[Agent 3] Fichiers préparés.")
    print("[Agent 3] Lancement des tests dans Docker...")

    exit_code, output = run_docker_tests(
        app_dir,
        results_dir
    )

    test_results = parse_test_results(output)
    coverage = read_coverage_report(results_dir)

    if coverage is None:
        validation_status = "error"
        coverage_after = 0
    else:
        coverage_after = coverage["percent_covered"]
        validation_status = (
            "passed" if exit_code == 0 else "failed"
        )

    print("\n[Agent 3] Résumé :")
    print(f"Tests réussis : {test_results['passed']}")
    print(f"Tests échoués : {test_results['failed']}")
    print(f"Tests en erreur : {test_results['errors']}")

    if coverage:
        print(f"Couverture après : {coverage_after:.2f}%")
    else:
        print("Rapport de couverture indisponible.")

    return {
        "test_exit_code": exit_code,
        "test_results": {
            **test_results,
            "output": output,
            "coverage": coverage
        },
        "coverage_after": coverage_after,
        "validation_status": validation_status,
        "coverage_report_path": str(
            results_dir / "coverage_after.json"
        )
    }
