import ast
import json
import re
from pathlib import Path
from typing import Any

from tools.llm_client import ask_llm
from config.settings import PROJECT_DIR, GENERATED_TESTS_DIR


# ============================================================
# 1. LECTURE DES FICHIERS
# ============================================================

def read_python_file(file_path: Path) -> str:
    if not file_path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {file_path}")
    return file_path.read_text(encoding="utf-8")


# ============================================================
# 2. ANALYSE AST DES TESTS
# ============================================================

def analyze_test_file(file_path: Path) -> dict[str, Any]:
    """
    Analyse les fonctions test_* avec l'AST.
    Le code source réel de chaque test est conservé pour le rapport final.
    """

    source_code = read_python_file(file_path)

    try:
        tree = ast.parse(source_code)
    except SyntaxError as error:
        return {
            "file": str(file_path),
            "syntax_valid": False,
            "syntax_error": str(error),
            "total_tests": 0,
            "total_assertions": 0,
            "total_pytest_raises": 0,
            "tests": [],
            "issues": ["Syntaxe Python invalide."],
        }

    lines = source_code.splitlines()
    tests: list[dict[str, Any]] = []

    # ast.walk ne garantit pas toujours l'ordre du fichier.
    function_nodes = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    ]
    function_nodes.sort(key=lambda node: node.lineno)

    for node in function_nodes:
        assertions = 0
        pytest_raises = 0

        for child in ast.walk(node):
            if isinstance(child, ast.Assert):
                assertions += 1

            if isinstance(child, ast.Call):
                if (
                    isinstance(child.func, ast.Attribute)
                    and child.func.attr == "raises"
                    and isinstance(child.func.value, ast.Name)
                    and child.func.value.id == "pytest"
                ):
                    pytest_raises += 1

        test_source = "\n".join(lines[node.lineno - 1:node.end_lineno])

        tests.append({
            "name": node.name,
            "line": node.lineno,
            "assertions": assertions,
            "pytest_raises": pytest_raises,
            "has_check": assertions > 0 or pytest_raises > 0,
            "source": test_source,
        })

    issues: list[str] = []
    names = [test["name"] for test in tests]

    if len(names) != len(set(names)):
        issues.append("Des noms de tests sont dupliqués.")

    for test in tests:
        if not test["has_check"]:
            issues.append(
                f"{test['name']} ne contient aucune vérification détectable."
            )

    return {
        "file": str(file_path),
        "syntax_valid": True,
        "total_tests": len(tests),
        "total_assertions": sum(test["assertions"] for test in tests),
        "total_pytest_raises": sum(test["pytest_raises"] for test in tests),
        "tests": tests,
        "issues": issues,
    }


# ============================================================
# 2 BIS. ANALYSE AST DETERMINISTE DES CONDITIONS SIMPLES
# ============================================================

def _safe_condition_value(node: ast.AST, env: dict[str, Any]) -> tuple[bool, Any]:
    """Interprète un sous-ensemble sûr de Python, sans eval()."""
    if isinstance(node, ast.Constant):
        return True, node.value
    if isinstance(node, ast.Name):
        return (True, env[node.id]) if node.id in env else (False, None)
    if isinstance(node, (ast.List, ast.Tuple)):
        values = []
        for item in node.elts:
            ok, value = _safe_condition_value(item, env)
            if not ok: return False, None
            values.append(value)
        return True, values if isinstance(node, ast.List) else tuple(values)
    if isinstance(node, ast.UnaryOp):
        ok, value = _safe_condition_value(node.operand, env)
        if not ok: return False, None
        if isinstance(node.op, ast.Not): return True, not value
        if isinstance(node.op, ast.USub): return True, -value
        if isinstance(node.op, ast.UAdd): return True, +value
    if isinstance(node, ast.BoolOp):
        values = [_safe_condition_value(x, env) for x in node.values]
        if not all(ok for ok, _ in values): return False, None
        booleans = [bool(value) for _, value in values]
        return True, all(booleans) if isinstance(node.op, ast.And) else any(booleans)
    if isinstance(node, ast.Compare):
        ok, left = _safe_condition_value(node.left, env)
        if not ok: return False, None
        ops = {ast.Eq: lambda a,b:a==b, ast.NotEq: lambda a,b:a!=b,
               ast.Lt: lambda a,b:a<b, ast.LtE: lambda a,b:a<=b,
               ast.Gt: lambda a,b:a>b, ast.GtE: lambda a,b:a>=b,
               ast.In: lambda a,b:a in b, ast.NotIn: lambda a,b:a not in b}
        for op, right_node in zip(node.ops, node.comparators):
            ok, right = _safe_condition_value(right_node, env)
            fn = ops.get(type(op))
            if not ok or fn is None: return False, None
            try:
                if not fn(left, right): return True, False
            except (TypeError, ValueError): return False, None
            left = right
        return True, True
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'strip':
        ok, value = _safe_condition_value(node.func.value, env)
        if ok and isinstance(value, str) and not node.args and not node.keywords:
            return True, value.strip()
    return False, None

def analyze_deterministic_scenarios(source_code: str, tests: list[dict[str, Any]]) -> dict[str, Any]:
    """Vérifie les deux issues des if simples du premier niveau des fonctions."""
    try:
        tree = ast.parse(source_code)
    except SyntaxError as error:
        return {"available": False, "error": str(error), "total_conditions": 0,
                "covered_conditions": 0, "coverage_ratio": None, "conditions": [], "not_evaluated": []}

    functions = {n.name:n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    outcomes: dict[tuple[str,str], set[bool]] = {}
    lines: dict[tuple[str,str], int] = {}
    skipped: set[str] = set()
    for test in tests:
        try: test_tree = ast.parse(test['source'])
        except (SyntaxError, KeyError): continue
        for call in ast.walk(test_tree):
            if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name): continue
            name = call.func.id
            function = functions.get(name)
            if function is None: continue
            params = [a.arg for a in function.args.posonlyargs + function.args.args]
            env = {}
            valid = len(call.args) <= len(params)
            for param, arg in zip(params, call.args):
                try: env[param] = ast.literal_eval(arg)
                except (ValueError, TypeError): valid = False
            for kw in call.keywords:
                if kw.arg is None: valid = False; continue
                try: env[kw.arg] = ast.literal_eval(kw.value)
                except (ValueError, TypeError): valid = False
            if not valid:
                skipped.add(f'{name}: arguments non littéraux ou non pris en charge')
                continue
            # Limite volontaire : uniquement les if directement dans la fonction.
            for statement in function.body:
                if not isinstance(statement, ast.If): continue
                text_condition = ast.unparse(statement.test)
                key = (name, text_condition)
                lines[key] = statement.lineno
                ok, value = _safe_condition_value(statement.test, env)
                if ok and isinstance(value, bool): outcomes.setdefault(key, set()).add(value)
                else: skipped.add(f'{name}, ligne {statement.lineno}: condition non interprétable ({text_condition})')

    details=[]
    for (name, condition), line in lines.items():
        seen=outcomes.get((name,condition), set())
        # Une condition non interprétable n'entre pas dans le dénominateur.
        # Elle reste visible dans not_evaluated pour éviter de la présenter
        # comme couverte ou non couverte.
        if not seen:
            continue
        details.append({"function":name, "line":line, "condition":condition,
                        "observed_true":True in seen, "observed_false":False in seen,
                        "covered_both_branches":seen == {True,False}})
    total=len(details)
    covered=sum(1 for x in details if x['covered_both_branches'])
    return {"available":True, "method":"AST conditionnel simplifié",
            "total_conditions":total, "covered_conditions":covered,
            "coverage_ratio":round(covered/total,4) if total else None,
            "conditions":details, "not_evaluated":sorted(skipped),
            "limitation":"Seuls les if simples du premier niveau et les arguments littéraux sont évalués. Les boucles et appels complexes sont ignorés."}


# ============================================================
# 3. EXTRACTION JSON
# ============================================================

def extract_json_response(response: str) -> dict[str, Any]:
    """
    Extrait le premier objet JSON valide, même si Qwen ajoute
    des balises Markdown ou du texte autour de sa réponse.
    """

    if not isinstance(response, str) or not response.strip():
        raise ValueError("Réponse vide du modèle.")

    cleaned = response.strip()
    cleaned = re.sub(
        r"^\s*```(?:json)?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s*```\s*$", "", cleaned)

    decoder = json.JSONDecoder()

    # On essaie chaque accolade ouvrante. raw_decode gère les objets
    # imbriqués et les accolades présentes dans les chaînes JSON.
    for position, character in enumerate(cleaned):
        if character != "{":
            continue

        try:
            result, _ = decoder.raw_decode(cleaned[position:])
        except json.JSONDecodeError:
            continue

        if isinstance(result, dict):
            return result

    raise ValueError("Aucun objet JSON valide trouvé dans la réponse.")


# ============================================================
# 4. NORMALISATION ET VALIDATION
# ============================================================

REQUIRED_REPORT_FIELDS = [
    "overall_assessment",
    "tests_analysis",
    "detected_issues",
    "missing_scenarios",
    "recommendations",
    "redundant_tests",
]

ALLOWED_STATUSES = {"good", "weak", "incorrect"}


def validate_string_list(report: dict[str, Any], field: str,
                         errors: list[str]) -> None:
    value = report.get(field)

    if not isinstance(value, list):
        errors.append(f"{field} doit être une liste.")
        return

    for index, item in enumerate(value):
        if not isinstance(item, str):
            errors.append(
                f"{field}[{index}] doit être une chaîne de caractères."
            )


def validate_relevance_report(
    report: dict[str, Any],
    expected_tests: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Vérifie la structure du rapport et la présence exacte de chaque test.
    La preuve du test n'est PAS demandée à Qwen : elle est ajoutée
    directement depuis le code réel par Python.
    """

    errors: list[str] = []

    if not isinstance(report, dict):
        return {
            "valid": False,
            "expected_tests": len(expected_tests),
            "analyzed_tests": 0,
            "validation_errors": ["Le rapport doit être un objet JSON."],
            "missing_tests": [test["name"] for test in expected_tests],
            "unknown_tests": [],
            "report": None,
        }

    for field in REQUIRED_REPORT_FIELDS:
        if field not in report:
            errors.append(f"Champ obligatoire manquant : {field}")

    if not isinstance(report.get("overall_assessment"), str):
        errors.append("overall_assessment doit être une chaîne.")

    analyses = report.get("tests_analysis", [])
    if not isinstance(analyses, list):
        errors.append("tests_analysis doit être une liste.")
        analyses = []

    for field in [
        "detected_issues",
        "missing_scenarios",
        "recommendations",
    ]:
        validate_string_list(report, field, errors)

    expected_by_name = {
        test["name"]: test for test in expected_tests
    }

    received_names: list[str] = []

    for index, analysis in enumerate(analyses):
        if not isinstance(analysis, dict):
            errors.append(f"Analyse numéro {index + 1} invalide.")
            continue

        name = analysis.get("test_name")

        if not isinstance(name, str) or not name.strip():
            errors.append(f"Nom de test invalide dans l'analyse {index + 1}.")
            continue

        received_names.append(name)

        if name not in expected_by_name:
            errors.append(f"Test inconnu : {name}")
            continue

        if analysis.get("status") not in ALLOWED_STATUSES:
            errors.append(f"Statut invalide pour {name}.")

        for field in ["reason", "suggestion"]:
            if not isinstance(analysis.get(field), str):
                errors.append(f"Champ {field} invalide pour {name}.")

    duplicates = sorted({
        name for name in received_names
        if received_names.count(name) > 1
    })

    for name in duplicates:
        errors.append(f"Test analysé plusieurs fois : {name}")

    missing = sorted(set(expected_by_name) - set(received_names))
    unknown = sorted(set(received_names) - set(expected_by_name))

    for name in missing:
        errors.append(f"Test non analysé : {name}")

    if len(analyses) != len(expected_tests):
        errors.append(
            "Le nombre d'analyses ne correspond pas au nombre de tests."
        )

    redundant_tests = report.get("redundant_tests", [])

    if not isinstance(redundant_tests, list):
        errors.append("redundant_tests doit être une liste.")
        redundant_tests = []

    for index, pair in enumerate(redundant_tests):
        if not isinstance(pair, dict):
            errors.append(
                f"La paire redondante numéro {index + 1} doit être un objet."
            )
            continue

        test_1 = pair.get("test_1")
        test_2 = pair.get("test_2")
        reason = pair.get("reason")

        if not isinstance(test_1, str) or test_1 not in expected_by_name:
            errors.append(
                f"Nom test_1 invalide dans la redondance numéro {index + 1}."
            )

        if not isinstance(test_2, str) or test_2 not in expected_by_name:
            errors.append(
                f"Nom test_2 invalide dans la redondance numéro {index + 1}."
            )

        if isinstance(test_1, str) and isinstance(test_2, str):
            if test_1 == test_2:
                errors.append(
                    "Une paire redondante ne peut pas contenir deux fois "
                    "le même test."
                )

        if not isinstance(reason, str) or not reason.strip():
            errors.append(
                f"Justification manquante pour la redondance numéro {index + 1}."
            )

    return {
        "valid": len(errors) == 0,
        "expected_tests": len(expected_tests),
        "analyzed_tests": len(analyses),
        "validation_errors": errors,
        "missing_tests": missing,
        "unknown_tests": unknown,
        "report": report,
    }


def attach_real_evidence(
    report: dict[str, Any],
    batch: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Ajoute une preuve issue du code réel.
    On ne demande pas à Qwen de recopier du code, ce qui évite
    les erreurs de guillemets, d'indentation et de reformulation.
    """

    source_by_name = {
        test["name"]: test["source"] for test in batch
    }

    enriched_analyses = []

    for analysis in report.get("tests_analysis", []):
        item = dict(analysis)
        test_name = item.get("test_name")

        if test_name in source_by_name:
            item["evidence"] = source_by_name[test_name]

        enriched_analyses.append(item)

    report["tests_analysis"] = enriched_analyses
    return report


# ============================================================
# 5. PROMPT QWEN POUR UN GROUPE
# ============================================================

def build_batch_prompt(
    source_code: str,
    batch: list[dict[str, Any]],
    batch_number: int,
    total_batches: int,
) -> str:

    tests_text = "\n\n".join(
        f"TEST : {test['name']}\n"
        f"CODE DU TEST :\n{test['source']}"
        for test in batch
    )

    names = [test["name"] for test in batch]

    return f"""
Tu es un auditeur senior spécialisé en tests Python et pytest.

MISSION
Analyse uniquement les {len(batch)} tests du groupe
{batch_number}/{total_batches}.

CODE SOURCE DE L'APPLICATION :
```python
{source_code}
```

TESTS À ANALYSER :
{tests_text}

LISTE EXACTE DES NOMS À ANALYSER :
{json.dumps(names, ensure_ascii=False)}

POUR CHAQUE TEST :
- Vérifie ce que le test exécute réellement.
- Compare le résultat attendu avec le code source.
- Vérifie si l'assertion ou l'exception vérifie le bon comportement.
- Détecte les erreurs logiques.
- Évalue si le scénario est utile et pertinent.
- Propose une amélioration uniquement si elle est utile.

STATUTS AUTORISÉS :
- good : le test vérifie correctement un comportement utile.
- weak : le test est utile, mais sa vérification est partielle.
- incorrect : le test vérifie un résultat erroné ou un mauvais comportement.

RÈGLES STRICTES :
1. Analyse exactement les tests de la liste.
2. Chaque nom doit apparaître une seule fois.
3. N'invente aucun nom de test.
4. Ne retourne aucun test qui n'est pas dans la liste.
5. Ne fournis PAS de champ evidence : Python ajoutera le code réel.
6. missing_scenarios doit être une liste de chaînes.
7. detected_issues doit être une liste de chaînes.
8. recommendations doit être une liste de chaînes.
9. redundant_tests doit être une liste d'objets contenant test_1, test_2 et reason.
10. Si tu ne détectes aucune redondance, retourne [].
11. Si tu ne détectes aucun scénario manquant, retourne [].
12. Ne confonds pas 0 % et 100 % de réduction.
13. Vérifie les valeurs numériques à partir du code source.

FORMAT OBLIGATOIRE :
Retourne UNIQUEMENT un objet JSON valide, sans Markdown et sans texte avant
ou après le JSON.

{{
  "overall_assessment": "Évaluation concise du groupe",
  "tests_analysis": [
    {{
      "test_name": "nom exact du test",
      "status": "good",
      "reason": "Explication technique",
      "suggestion": "Amélioration ou chaîne vide"
    }}
  ],
  "detected_issues": [],
  "missing_scenarios": [],
  "recommendations": [],
  "redundant_tests": []
}}
"""


# ============================================================
# 6. ANALYSE D'UN GROUPE AVEC UNE TENTATIVE DE CORRECTION
# ============================================================

def analyze_batch(
    prompt: str,
    batch: list[dict[str, Any]],
    batch_number: int,
    total_batches: int,
) -> dict[str, Any]:

    print(
        f"[Agent 4] Analyse du groupe {batch_number}/{total_batches} "
        f"({len(batch)} tests)..."
    )

    response = ask_llm(prompt)

    for attempt in range(2):
        try:
            report = extract_json_response(response)

            # Validation de la réponse telle que produite par Qwen.
            validation = validate_relevance_report(report, batch)

            if validation["valid"]:
                # Ajout de la preuve depuis le code réel, pas depuis Qwen.
                report = attach_real_evidence(report, batch)
                validation["report"] = report

                print(f"[Agent 4] Groupe {batch_number} validé.")
                return validation

            errors = "\n".join(
                f"- {error}" for error in validation["validation_errors"]
            )

            if attempt == 0:
                print(
                    f"[Agent 4] Groupe {batch_number} invalide. "
                    "Demande de correction..."
                )
                print("[Agent 4] Erreurs détectées :")
                for error in validation["validation_errors"]:
                    print(f"  - {error}")

                correction_prompt = f"""
Ta réponse précédente n'a pas respecté le format demandé.

ERREURS À CORRIGER :
{errors}

RAPPORT PRÉCÉDENT :
{json.dumps(report, ensure_ascii=False, indent=2)}

Reprends les mêmes tests et retourne un rapport COMPLET.
Respecte exactement les noms de tests fournis dans le prompt initial.
N'ajoute aucun champ evidence.
missing_scenarios, detected_issues et recommendations doivent être
des listes de chaînes.
redundant_tests doit être une liste d'objets avec test_1, test_2 et reason.
Retourne uniquement du JSON valide.
"""
                response = ask_llm(prompt + "\n\n" + correction_prompt)

            else:
                print(
                    f"[Agent 4] Groupe {batch_number} toujours invalide "
                    "après correction."
                )
                print("\n========== RÉPONSE BRUTE QWEN ==========")
                print(response)
                return validation

        except ValueError as error:
            if attempt == 0:
                print(
                    f"[Agent 4] JSON invalide pour le groupe {batch_number}. "
                    "Nouvelle tentative..."
                )
                correction_prompt = f"""
Ta réponse précédente n'est pas un JSON valide.
Erreur détectée : {error}

Retourne le rapport complet demandé dans le prompt initial.
Retourne uniquement un objet JSON valide, sans Markdown.
"""
                response = ask_llm(prompt + "\n\n" + correction_prompt)
            else:
                print("\n========== RÉPONSE BRUTE QWEN ==========")
                print(response)
                return {
                    "valid": False,
                    "expected_tests": len(batch),
                    "analyzed_tests": 0,
                    "validation_errors": [str(error)],
                    "missing_tests": [test["name"] for test in batch],
                    "unknown_tests": [],
                    "report": None,
                }

    return {
        "valid": False,
        "expected_tests": len(batch),
        "analyzed_tests": 0,
        "validation_errors": ["Échec inattendu de l'analyse."],
        "missing_tests": [test["name"] for test in batch],
        "unknown_tests": [],
        "report": None,
    }


# ============================================================
# 7. ANALYSE SÉMANTIQUE COMPLÈTE
# ============================================================

def analyze_test_relevance(
    source_file: Path,
    test_file: Path,
) -> dict[str, Any]:

    source_code = read_python_file(source_file)
    ast_result = analyze_test_file(test_file)

    if not ast_result["syntax_valid"]:
        return {
            "valid": False,
            "expected_tests": 0,
            "analyzed_tests": 0,
            "validation_errors": ["Syntaxe des tests invalide."],
            "missing_tests": [],
            "unknown_tests": [],
            "report": None,
        }

    tests = ast_result["tests"]

    if not tests:
        return {
            "valid": False,
            "expected_tests": 0,
            "analyzed_tests": 0,
            "validation_errors": ["Aucun test détecté."],
            "missing_tests": [],
            "unknown_tests": [],
            "report": None,
        }

    # Petits groupes pour limiter la longueur des réponses de Qwen.
    batch_size = 5
    batches = [
        tests[index:index + batch_size]
        for index in range(0, len(tests), batch_size)
    ]

    total_batches = len(batches)

    all_analyses: list[dict[str, Any]] = []
    all_issues: list[str] = []
    all_missing_scenarios: list[str] = []
    all_recommendations: list[str] = []
    all_redundant_tests: list[dict[str, str]] = []
    batch_errors: list[str] = []

    for index, batch in enumerate(batches, start=1):
        prompt = build_batch_prompt(
            source_code=source_code,
            batch=batch,
            batch_number=index,
            total_batches=total_batches,
        )

        result = analyze_batch(
            prompt=prompt,
            batch=batch,
            batch_number=index,
            total_batches=total_batches,
        )

        if not result["valid"]:
            batch_errors.extend(result["validation_errors"])
            continue

        report = result["report"]

        all_analyses.extend(report["tests_analysis"])
        all_issues.extend(report["detected_issues"])
        all_missing_scenarios.extend(report["missing_scenarios"])
        all_recommendations.extend(report["recommendations"])
        all_redundant_tests.extend(report["redundant_tests"])

    if batch_errors:
        analyzed_names = {
            item["test_name"] for item in all_analyses
            if isinstance(item, dict) and "test_name" in item
        }

        return {
            "valid": False,
            "expected_tests": len(tests),
            "analyzed_tests": len(all_analyses),
            "validation_errors": batch_errors,
            "missing_tests": sorted(
                {test["name"] for test in tests} - analyzed_names
            ),
            "unknown_tests": [],
            "report": None,
        }

    # Élimination des doublons textuels dans les listes.
    all_issues = list(dict.fromkeys(all_issues))
    all_missing_scenarios = list(dict.fromkeys(all_missing_scenarios))
    all_recommendations = list(dict.fromkeys(all_recommendations))

    # Nettoyage et déduplication des paires de redondance.
    unique_pairs = []
    seen_pairs = set()

    for pair in all_redundant_tests:
        name_1 = pair["test_1"]
        name_2 = pair["test_2"]
        pair_key = tuple(sorted((name_1, name_2)))

        if pair_key not in seen_pairs:
            seen_pairs.add(pair_key)
            unique_pairs.append(pair)

    deterministic_scenarios = analyze_deterministic_scenarios(source_code, tests)

    final_report = {
        "overall_assessment": (
            f"Analyse complète de {len(all_analyses)} tests "
            f"répartis en {total_batches} groupes."
        ),
        "tests_analysis": all_analyses,
        "detected_issues": all_issues,
        "missing_scenarios": all_missing_scenarios,
        "llm_missing_scenarios": all_missing_scenarios,
        "deterministic_scenarios": deterministic_scenarios,
        "recommendations": all_recommendations,
        "redundant_tests": unique_pairs,
    }

    # Validation globale : tous les tests doivent être présents une fois.
    final_validation = validate_relevance_report(final_report, tests)

    if final_validation["valid"]:
        print(
            "[Agent 4] Tous les groupes ont été analysés et validés."
        )
    else:
        print("[Agent 4] Le rapport global est invalide.")
        for error in final_validation["validation_errors"]:
            print(f"  - {error}")

    return final_validation


# ============================================================
# 8. CALCUL DU SCORE DE PERTINENCE
# ============================================================

def calculate_relevance_score(
    ast_result: dict[str, Any],
    validation_result: dict[str, Any],
) -> dict[str, Any]:
    """
    Score sur 100.
    Le score n'est calculé que si le rapport sémantique est valide.

    La couverture des conditions simples est évaluée par une heuristique AST.
    La pertinence fonctionnelle et les redondances restent en partie évaluées
    par le LLM. Le score reste un indicateur, pas une preuve mathématique.
    """

    if not validation_result.get("valid"):
        return {
            "score": None,
            "status": "incomplete",
            "details": {},
            "message": "Score impossible : rapport invalide.",
        }

    tests = ast_result.get("tests", [])
    report = validation_result["report"]
    analyses = report["tests_analysis"]

    total = len(tests)

    if total == 0:
        return {
            "score": 0,
            "status": "incorrect",
            "details": {},
            "message": "Aucun test détecté.",
        }

    # A. Qualité des vérifications : 25 points.
    tests_with_checks = sum(
        1 for test in tests if test["has_check"]
    )
    verification_score = (tests_with_checks / total) * 25

    # B. Couverture des scénarios : 25 points.
    # Les scénarios manquants de Qwen restent informatifs ; le score
    # repose sur les issues True/False évaluées par l'analyse AST.
    scenario_analysis = report.get("deterministic_scenarios", {})
    total_conditions = scenario_analysis.get("total_conditions", 0)
    covered_conditions = scenario_analysis.get("covered_conditions", 0)
    scenario_score = (25 * covered_conditions / total_conditions) if total_conditions else 0
    missing_count = len(report.get("llm_missing_scenarios", report["missing_scenarios"]))

    # C. Pertinence fonctionnelle : 20 points.
    good = sum(
        1 for item in analyses if item["status"] == "good"
    )
    weak = sum(
        1 for item in analyses if item["status"] == "weak"
    )
    incorrect = sum(
        1 for item in analyses if item["status"] == "incorrect"
    )

    functional_score = (
        (good + 0.5 * weak) / total
    ) * 20

    # D. Indépendance : 15 points.
    redundant_pairs = len(report["redundant_tests"])
    independence_score = max(
        0,
        15 - min(redundant_pairs * 5, 15),
    )

    # E. Lisibilité et structure : 15 points.
    structure_score = 0

    if ast_result.get("syntax_valid"):
        structure_score += 5

    if all(test["name"].startswith("test_") for test in tests):
        structure_score += 3

    if not ast_result.get("issues"):
        structure_score += 4

    if tests_with_checks == total:
        structure_score += 3

    total_score = round(
        verification_score
        + scenario_score
        + functional_score
        + independence_score
        + structure_score,
        2,
    )

    if total_score >= 75:
        status = "good"
    elif total_score >= 50:
        status = "weak"
    else:
        status = "incorrect"

    return {
        "score": total_score,
        "status": status,
        "details": {
            "verification_quality": round(verification_score, 2),
            "scenario_quality": round(scenario_score, 2),
            "functional_relevance": round(functional_score, 2),
            "independence": round(independence_score, 2),
            "readability": round(structure_score, 2),
        },
        "statistics": {
            "total_tests": total,
            "good_tests": good,
            "weak_tests": weak,
            "incorrect_tests": incorrect,
            "redundant_pairs": redundant_pairs,
            "llm_missing_scenarios": missing_count,
            "deterministic_conditions": total_conditions,
            "deterministic_conditions_covered": covered_conditions,
            "deterministic_coverage_ratio": scenario_analysis.get("coverage_ratio"),
            "scenario_analysis_not_evaluated": scenario_analysis.get("not_evaluated", []),
        },
        "scenario_score_note": (
            "La couverture est calculée à partir des conditions simples évaluées par AST. "
            "Les scénarios manquants proposés par Qwen restent informatifs."
        ),
    }


def relevance_critic_agent(state):
    """Evaluate generated test relevance and attach a serializable summary."""
    test_file = Path(state["generated_test_file"])
    if not test_file.is_absolute():
        from config.settings import BASE_DIR
        test_file = BASE_DIR / test_file
    source_file = PROJECT_DIR / "checkout.py"
    ast_result = analyze_test_file(test_file)
    semantic_result = analyze_test_relevance(source_file, test_file)
    score_result = calculate_relevance_score(ast_result, semantic_result)
    summary = {
        "valid": semantic_result.get("valid"),
        "score": score_result.get("score"),
        "status": score_result.get("status"),
        "details": score_result.get("details"),
        "statistics": score_result.get("statistics"),
        "feedback": semantic_result.get("report"),
        "validation_errors": semantic_result.get("validation_errors", []),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    run_dir = state.get("run_dir")
    if run_dir:
        (Path(run_dir) / "critic_result.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    return {
        "critic_result": summary,
        "relevance_score": score_result.get("score"),
        "relevance_feedback": score_result.get("status", "incomplete"),
    }


# ============================================================
# 9. EXÉCUTION INDIVIDUELLE
# ============================================================

if __name__ == "__main__":

    source_file = PROJECT_DIR / "checkout.py"
    test_file = GENERATED_TESTS_DIR / "test_generated_checkout.py"

    print("\n========== ANALYSE AST ==========\n")

    ast_result = analyze_test_file(test_file)

    ast_summary = {
        key: value
        for key, value in ast_result.items()
        if key != "tests"
    }

    ast_summary["tests"] = [
        {
            key: value
            for key, value in test.items()
            if key != "source"
        }
        for test in ast_result["tests"]
    ]

    print(json.dumps(ast_summary, indent=4, ensure_ascii=False))

    if not ast_result["syntax_valid"]:
        raise SystemExit("Arrêt : le fichier de tests contient une erreur de syntaxe.")

    print("\n========== ANALYSE QWEN ==========\n")

    relevance_result = analyze_test_relevance(
        source_file=source_file,
        test_file=test_file,
    )

    print(
        json.dumps(
            relevance_result,
            indent=4,
            ensure_ascii=False,
        )
    )

    print("\n========== SCORE DE PERTINENCE ==========\n")

    score_result = calculate_relevance_score(
        ast_result=ast_result,
        validation_result=relevance_result,
    )

    print(
        json.dumps(
            score_result,
            indent=4,
            ensure_ascii=False,
        )
    )
