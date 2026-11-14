
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

    return response


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

    print(relevance_result)
