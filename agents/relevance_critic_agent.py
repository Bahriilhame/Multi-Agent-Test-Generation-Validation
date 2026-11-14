import json
import re
import ast
from pathlib import Path
from typing import Any

from tools.llm_client import ask_llm

from config.settings import (
    PROJECT_DIR,
    GENERATED_TESTS_DIR,
)


def read_python_file(file_path: Path) -> str:
    """
    Lit un fichier Python et retourne son contenu.
    """
    if not file_path.exists():
        raise FileNotFoundError(
            f"Fichier introuvable : {file_path}"
        )

    return file_path.read_text(encoding="utf-8")


def analyze_test_file(file_path: Path) -> dict[str, Any]:
    """
    Analyse la structure d'un fichier de tests avec AST.

    Cette fonction ne lance pas les tests.
    Elle examine uniquement leur structure :
    - Validité syntaxique
    - Nombre de fonctions de test
    - Nombre d'assertions
    - Nombre de pytest.raises()
    """

    source_code = read_python_file(file_path)

    try:
        syntax_tree = ast.parse(source_code)

    except SyntaxError as error:
        return {
            "file": str(file_path),
            "syntax_valid": False,
            "syntax_error": str(error),
            "total_tests": 0,
            "total_assertions": 0,
            "total_pytest_raises": 0,
            "tests": [],
            "issues": [
                "Le fichier contient une erreur de syntaxe."
            ],
        }

    test_functions = []

    for node in ast.walk(syntax_tree):

        if not isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue

        if not node.name.startswith("test_"):
            continue

        assertions = 0
        pytest_raises = 0

        for child in ast.walk(node):

            # Détecter les assertions Python.
            if isinstance(child, ast.Assert):
                assertions += 1

            # Détecter les appels à pytest.raises().
            if isinstance(child, ast.Call):
                if (
                    isinstance(child.func, ast.Attribute)
                    and child.func.attr == "raises"
                    and isinstance(child.func.value, ast.Name)
                    and child.func.value.id == "pytest"
                ):
                    pytest_raises += 1

        test_functions.append({
            "name": node.name,
            "line": node.lineno,
            "assertions": assertions,
            "pytest_raises": pytest_raises,
        })

    total_assertions = sum(
        test["assertions"] for test in test_functions
    )

    total_pytest_raises = sum(
        test["pytest_raises"] for test in test_functions
    )

    issues = []

    for test in test_functions:

        if (
            test["assertions"] == 0
            and test["pytest_raises"] == 0
        ):
            issues.append(
                f"{test['name']} ne contient aucune vérification détectée."
            )

    return {
        "file": str(file_path),
        "syntax_valid": True,
        "total_tests": len(test_functions),
        "total_assertions": total_assertions,
        "total_pytest_raises": total_pytest_raises,
        "tests": test_functions,
        "issues": issues,
    }


def extract_json_response(response: str) -> dict[str, Any]:
    """
    Extrait un objet JSON depuis la réponse de Qwen.

    Accepte :
    - Un JSON brut.
    - Un JSON entouré de balises Markdown ```json.
    """

    cleaned_response = response.strip()

    # Retirer les balises Markdown si elles existent.
    cleaned_response = re.sub(
        r"^```(?:json)?\s*",
        "",
        cleaned_response,
        flags=re.IGNORECASE
    )

    cleaned_response = re.sub(
        r"\s*```$",
        "",
        cleaned_response
    )

    # Si du texte entoure le JSON, récupérer l'objet.
    start = cleaned_response.find("{")
    end = cleaned_response.rfind("}")

    if start == -1 or end == -1 or end < start:
        raise ValueError(
            "Aucun objet JSON valide trouvé dans la réponse de Qwen."
        )

    json_text = cleaned_response[start:end + 1]

    try:
        data = json.loads(json_text)

    except json.JSONDecodeError as error:
        raise ValueError(
            f"Le JSON retourné par Qwen est invalide : {error}"
        ) from error

    if not isinstance(data, dict):
        raise ValueError(
            "La réponse JSON doit être un objet."
        )

    return data


def validate_relevance_report(
    report: dict[str, Any],
    ast_result: dict[str, Any]
) -> dict[str, Any]:
    """
    Vérifie la structure et la cohérence du rapport de Qwen.

    Compare notamment les noms des tests avec ceux
    détectés par l'analyse AST.
    """

    validation_errors = []

    required_fields = [
        "overall_assessment",
        "tests_analysis",
        "detected_issues",
        "missing_scenarios",
        "recommendations",
    ]

    # 1. Vérifier la présence des champs obligatoires.
    for field in required_fields:
        if field not in report:
            validation_errors.append(
                f"Champ obligatoire manquant : {field}"
            )

    # 2. Vérifier les types des champs principaux.
    if not isinstance(
        report.get("overall_assessment"),
        str
    ):
        validation_errors.append(
            "overall_assessment doit être une chaîne de caractères."
        )

    tests_analysis = report.get("tests_analysis")

    if not isinstance(tests_analysis, list):
        validation_errors.append(
            "tests_analysis doit être une liste."
        )
        tests_analysis = []

    for field in [
        "detected_issues",
        "missing_scenarios",
        "recommendations",
    ]:
        if (
            field in report
            and not isinstance(report[field], list)
        ):
            validation_errors.append(
                f"{field} doit être une liste."
            )

    # 3. Récupérer les noms de tests détectés par AST.
    expected_names = {
        test["name"]
        for test in ast_result.get("tests", [])
    }

    received_names = []
    allowed_statuses = {
        "good",
        "weak",
        "incorrect",
    }

    # 4. Vérifier chaque analyse individuelle.
    for index, test_analysis in enumerate(tests_analysis):

        if not isinstance(test_analysis, dict):
            validation_errors.append(
                f"L'analyse numéro {index + 1} n'est pas un objet."
            )
            continue

        test_name = test_analysis.get("test_name")

        if not isinstance(test_name, str) or not test_name:
            validation_errors.append(
                f"Nom de test invalide dans l'analyse numéro {index + 1}."
            )
            continue

        received_names.append(test_name)

        # Vérifier le statut.
        status = test_analysis.get("status")

        if (
            not isinstance(status, str)
            or status not in allowed_statuses
        ):
            validation_errors.append(
                f"Statut invalide pour {test_name} : {status}"
            )

        # Vérifier les champs textuels.
        for field in [
            "reason",
            "evidence",
            "suggestion",
        ]:
            if not isinstance(test_analysis.get(field), str):
                validation_errors.append(
                    f"Champ {field} invalide pour {test_name}."
                )

    # 5. Détecter les noms dupliqués.
    duplicates = sorted({
        name
        for name in received_names
        if received_names.count(name) > 1
    })

    for name in duplicates:
        validation_errors.append(
            f"Test analysé plusieurs fois : {name}"
        )

    # 6. Détecter les tests inventés par Qwen.
    unknown_tests = sorted(
        set(received_names) - expected_names
    )

    for name in unknown_tests:
        validation_errors.append(
            f"Test inconnu ou inventé par Qwen : {name}"
        )

    # 7. Détecter les tests oubliés par Qwen.
    missing_tests = sorted(
        expected_names - set(received_names)
    )

    for name in missing_tests:
        validation_errors.append(
            f"Test non analysé par Qwen : {name}"
        )

    # 8. Vérifier le nombre de tests analysés.
    if len(tests_analysis) != len(expected_names):
        validation_errors.append(
            "Le nombre de tests analysés par Qwen "
            "ne correspond pas au nombre détecté par AST."
        )

    return {
        "valid": len(validation_errors) == 0,
        "expected_tests": len(expected_names),
        "analyzed_tests": len(tests_analysis),
        "validation_errors": validation_errors,
        "missing_tests": missing_tests,
        "unknown_tests": unknown_tests,
        "report": report,
    }

def analyze_test_relevance(
    source_file: Path,
    test_file: Path
) -> str:
    """
    Analyse la pertinence fonctionnelle des tests avec Qwen.
    Compare le code source avec les tests générés.
    """

    source_code = read_python_file(source_file)
    test_code = read_python_file(test_file)

    # Analyse structurelle préalable avec AST.
    ast_result = analyze_test_file(test_file)

    prompt = f"""
Tu es un auditeur senior spécialisé en qualité logicielle,
tests unitaires Python et pytest.

Tu dois effectuer un audit critique des tests.
Ton objectif n'est PAS de féliciter le générateur,
mais de détecter objectivement les défauts éventuels.

CODE SOURCE :

```python
{source_code}
```

TESTS À AUDITER :

```python
{test_code}
```

ANALYSE STRUCTURELLE AST :

{ast_result}

Pour chaque test, vérifie les éléments suivants :

1. ASSERTIONS
- Quelle fonction du code source est testée ?
- Quelle valeur est réellement attendue ?
- Cette valeur correspond-elle au comportement du code source ?
- L'assertion vérifie-t-elle suffisamment le résultat ?
- Pour pytest.raises(), l'exception attendue est-elle correcte ?
- Le message d'erreur devrait-il également être vérifié ?

2. SCÉNARIOS
- Le scénario est-il réellement pertinent ?
- Les valeurs limites sont-elles testées ?
- Les valeurs juste avant et après les limites sont-elles testées ?
- Les cas normaux et invalides sont-ils présents ?

3. QUALITÉ
- Le test pourrait-il réussir alors que le comportement attendu est incorrect ?
- Le test vérifie-t-il plusieurs comportements indépendants ?
- Existe-t-il des scénarios redondants ?
- Des branches importantes du code ne sont-elles pas testées ?

4. SCÉNARIOS MANQUANTS
Examine chaque fonction du code source.
Compare ses conditions et ses branches avec les tests existants.
Liste les comportements importants qui ne sont pas testés.

RÈGLES STRICTES :

- Analyse réellement le contenu de chaque fonction de test.
- Ne classe pas automatiquement tous les tests comme good.
- Un test qui passe n'est pas nécessairement un bon test.
- Une couverture de 100 % ne garantit pas la qualité.
- Ne signale pas un problème sans justification technique.
- N'invente aucune assertion ou valeur qui ne figure pas dans les fichiers.
- Si les informations sont insuffisantes, indique-le explicitement.
- Donne le nom exact du test concerné.
- Justifie chaque problème avec le comportement du code source.

FORMAT DE RÉPONSE :

Retourne uniquement un JSON valide, sans Markdown.

Respecte cette structure :

{{
    "overall_assessment": "Évaluation générale argumentée",
    "tests_analysis": [
        {{
            "test_name": "nom exact du test",
            "status": "good, weak ou incorrect",
            "reason": "Justification technique précise",
            "evidence": "Assertion ou comportement du code source examiné",
            "suggestion": "Amélioration concrète ou chaîne vide"
        }}
    ],
    "detected_issues": [
        "Problème réellement identifié"
    ],
    "missing_scenarios": [
        "Scénario important non testé et justification"
    ],
    "recommendations": [
        "Amélioration technique concrète"
    ]
}}

IMPORTANT :
Tu dois analyser individuellement tous les tests présents.
Le nombre d'éléments dans tests_analysis doit être égal
au nombre de fonctions de test détectées par AST.
"""

    print("[Agent 4] Analyse sémantique avec Qwen...")

    response = ask_llm(prompt)

    try:
        # Extraire le JSON de la réponse de Qwen.
        report = extract_json_response(response)

        # Vérifier le rapport avec les résultats AST.
        validation_result = validate_relevance_report(
            report,
            ast_result
        )

        return validation_result

    except ValueError as error:

        return {
            "valid": False,
            "expected_tests": ast_result["total_tests"],
            "analyzed_tests": 0,
            "validation_errors": [str(error)],
            "missing_tests": [
                test["name"]
                for test in ast_result["tests"]
            ],
            "unknown_tests": [],
            "report": None,
            "raw_response": response,
        }


if __name__ == "__main__":

    source_file = PROJECT_DIR / "checkout.py"

    test_file = (
        GENERATED_TESTS_DIR
        / "test_generated_checkout.py"
    )

    print("\n========== ANALYSE AST ==========\n")

    ast_result = analyze_test_file(test_file)

    import json

    print(
        json.dumps(
            ast_result,
            indent=4,
            ensure_ascii=False
        )
    )

    print("\n========== ANALYSE QWEN ==========\n")

    relevance_result = analyze_test_relevance(
        source_file,
        test_file
    )

    print(
        json.dumps(
            relevance_result,
            indent=4,
            ensure_ascii=False
        )
    )
