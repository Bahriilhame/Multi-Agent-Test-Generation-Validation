
import ast
import re

from config.settings import (
    BASE_DIR,
    PROJECT_DIR,
    TESTS_DIR,
    GENERATED_TESTS_DIR
)

from tools.llm_client import ask_llm


# ============================================================
# 1. LECTURE DES FICHIERS
# ============================================================

def read_file(file_path):
    """Lit un fichier Python et retourne son contenu."""

    if not file_path.exists():
        raise FileNotFoundError(
            f"Fichier introuvable : {file_path}"
        )

    return file_path.read_text(encoding="utf-8")


def read_existing_tests():
    """
    Récupère les tests humains existants.
    Exclut les tests précédemment générés par l'IA.
    """

    existing_tests = []

    for file_path in TESTS_DIR.rglob("test_*.py"):

        if GENERATED_TESTS_DIR in file_path.parents:
            continue

        content = read_file(file_path)

        existing_tests.append(
            f"\n# Fichier : {file_path.name}\n{content}"
        )

    return "\n".join(existing_tests)


# ============================================================
# 2. EXTRACTION DU CODE PYTHON
# ============================================================

def extract_python_code(response):
    """
    Extrait le code Python d'une réponse du LLM.

    Le modèle peut entourer son code avec
    des balises Markdown.
    """

    matches = re.findall(
        r"```(?:python)?\s*(.*?)```",
        response,
        flags=re.DOTALL | re.IGNORECASE
    )

    if matches:
        return "\n\n".join(matches).strip()

    return response.strip()


# ============================================================
# 3. VALIDATION DU CODE GÉNÉRÉ
# ============================================================


def validate_generated_code(code):
    """
    Vérifie :
    - La syntaxe Python.
    - La présence de fonctions de test pytest.
    - Les noms de tests dupliqués.
    - Les tests strictement identiques.
    - Certaines constructions suspectes ou dangereuses.
    """

    try:
        syntax_tree = ast.parse(code)

    except SyntaxError as error:
        raise ValueError(
            f"Erreur syntaxique dans le code généré : {error}"
        )

    test_nodes = [
        node
        for node in ast.walk(syntax_tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    ]

    if not test_nodes:
        raise ValueError(
            "Aucune fonction de test pytest détectée."
        )

    # 1. Détecter les noms de tests dupliqués
    test_names = [node.name for node in test_nodes]

    if len(test_names) != len(set(test_names)):
        raise ValueError(
            "Des fonctions de test possèdent le même nom."
        )

    # 2. Détecter les tests strictement identiques
    test_bodies = [
        ast.dump(node, include_attributes=False)
        for node in test_nodes
    ]

    if len(test_bodies) != len(set(test_bodies)):
        raise ValueError(
            "Des fonctions de test sont strictement identiques."
        )

    # 3. Détecter certaines erreurs de génération
    for node in ast.walk(syntax_tree):

        if isinstance(node, ast.Name):

            if node.id.lower() in {
                "assertnot",
                "asserttrue",
                "assertfalse"
            }:
                raise ValueError(
                    f"Instruction suspecte détectée : {node.id}"
                )

        # 4. Détecter certaines fonctions dangereuses
        if isinstance(node, ast.Call):

            if isinstance(node.func, ast.Name):

                if node.func.id in {
                    "exec",
                    "eval",
                    "compile",
                    "__import__"
                }:
                    raise ValueError(
                        f"Instruction interdite : {node.func.id}"
                    )

            if isinstance(node.func, ast.Attribute):

                if node.func.attr in {
                    "system",
                    "popen",
                    "Popen",
                    "run",
                    "call",
                    "check_output"
                }:
                    raise ValueError(
                        "Appel système ou subprocess détecté."
                    )

        # 5. Détecter certains imports interdits
        if isinstance(node, (ast.Import, ast.ImportFrom)):

            if isinstance(node, ast.Import):
                modules = [
                    alias.name.split(".")[0]
                    for alias in node.names
                ]
            else:
                modules = [
                    node.module.split(".")[0]
                ] if node.module else []

            forbidden_modules = {
                "subprocess",
                "socket",
                "requests",
                "urllib",
                "http",
                "ftplib",
                "shutil"
            }

            for module in modules:
                if module in forbidden_modules:
                    raise ValueError(
                        f"Module interdit détecté : {module}"
                    )

    return test_names

# ============================================================
# 4. CONSTRUCTION DU PROMPT
# ============================================================

def build_prompt(
    source_code,
    existing_tests,
    uncovered_functions,
    uncovered_lines,
    coverage_before
):
    """Construit le prompt destiné à Qwen2.5-Coder."""

    return f"""
Tu es un ingénieur logiciel senior spécialisé en :
- Tests unitaires Python.
- Tests d'intégration.
- Pytest.
- Qualité logicielle.
- Analyse de couverture de code.

Ta mission est de générer des tests supplémentaires
pour une application e-commerce Python.

============================================================
OBJECTIF PRINCIPAL
============================================================

Améliorer la couverture du code en testant les parties
non couvertes de l'application.

Tu dois générer uniquement des tests supplémentaires.

Tu ne dois jamais modifier le code source de l'application.

============================================================
1. CODE SOURCE DE L'APPLICATION
============================================================

{source_code}


============================================================
2. TESTS MANUELS EXISTANTS
============================================================

{existing_tests}


============================================================
3. FONCTIONS NON COUVERTES
============================================================

{uncovered_functions}


============================================================
4. LIGNES NON COUVERTES
============================================================

{uncovered_lines}


============================================================
5. COUVERTURE INITIALE
============================================================

{coverage_before}%


============================================================
6. RÈGLES MÉTIER
============================================================

Les règles suivantes doivent être respectées :

CALCUL DU PANIER :
- Un panier vide déclenche ValueError.
- Un prix négatif déclenche ValueError.
- Une quantité inférieure ou égale à zéro déclenche ValueError.
- Un panier valide retourne la somme des prix multipliés
  par les quantités.

RÉDUCTION :
- Le montant ne peut pas être négatif.
- La réduction doit être comprise entre 0 et 100.
- Une réduction de 0 % ne change pas le montant.
- Une réduction de 100 % donne un montant égal à zéro.

LIVRAISON :
- La livraison est gratuite à partir de 500.
- La livraison coûte 30 lorsque le montant est inférieur à 500.
- Tester notamment les montants 499 et 500.

VALIDATION CLIENT :
- Un nom vide est invalide.
- Un nom composé uniquement d'espaces est invalide.
- Un email sans caractère @ est invalide.
- Un client valide doit être accepté.

CRÉATION DE COMMANDE :
- Un client invalide doit déclencher ValueError.
- Une commande valide doit retourner :
  subtotal,
  discounted_total,
  shipping,
  final_total.

============================================================
7. CONSIGNES DE GÉNÉRATION
============================================================

1. Génère des tests supplémentaires ciblant les fonctions
   et lignes non couvertes.

2. Ne reproduis pas inutilement les tests manuels existants.

3. Utilise obligatoirement pytest.raises pour vérifier
   les exceptions attendues.

4. Importe pytest si nécessaire.

5. Utilise exactement les noms de fonctions et les paramètres
   présents dans le code source.

6. Respecte la convention d'importation des tests existants.

7. Vérifie les cas normaux, les cas limites et les cas invalides.

8. Vérifie les résultats numériques exacts.

9. Vérifie les valeurs limites importantes :
   - Réduction de 0 %.
   - Réduction de 100 %.
   - Livraison à 499.
   - Livraison à 500.
   - Quantité égale à zéro.
   - Prix négatif.

10. N'écris aucune fonction de production.

11. Ne modifie jamais le code source de l'application.

12. N'utilise pas :
    - subprocess
    - os.system
    - eval
    - exec
    - accès réseau
    - accès au système de fichiers
    - commandes système.

13. Respecte strictement l'indentation Python.

14. Utilise des noms explicites pour les fonctions de test.

15. Chaque test doit vérifier un comportement précis.

16. N'invente aucune règle métier absente du code source.

17. Ne retourne aucun texte explicatif.

18. Retourne uniquement le code Python dans un seul bloc

19. N'écris jamais des expressions incorrectes comme :
    assertnot, asserttrue ou assertfalse.

20. Pour une assertion négative, utilise :
    assert not expression

21. Ne génère jamais deux fonctions de test
    qui vérifient exactement le même comportement.

22. Chaque test doit apporter une vérification différente.

23. Avant de répondre, relis chaque ligne d'assertion
    et vérifie sa syntaxe et sa logique.

    ```python
    ...
    ```

============================================================
8. VÉRIFICATION AVANT LA RÉPONSE
============================================================

Avant de retourner le code, vérifie :

- Que tous les imports sont corrects.
- Que toutes les fonctions de test commencent par test_.
- Que l'indentation est correcte.
- Que les assertions correspondent au code source.
- Que les exceptions utilisent pytest.raises.
- Que les tests ne sont pas inutilement redondants.
- Que le code respecte la syntaxe Python.

Retourne maintenant uniquement le code des tests.
"""


# ============================================================
# 5. AGENT DE GÉNÉRATION
# ============================================================

def test_generator_agent(state):

    print("\n[Agent 2] Génération des tests...")

    # --------------------------------------------------------
    # Étape 1 : récupérer le code source
    # --------------------------------------------------------

    source_file = PROJECT_DIR / "checkout.py"

    source_code = read_file(source_file)

    # --------------------------------------------------------
    # Étape 2 : récupérer les tests manuels existants
    # --------------------------------------------------------

    existing_tests = read_existing_tests()

    # --------------------------------------------------------
    # Étape 3 : récupérer les informations de couverture
    # --------------------------------------------------------

    uncovered_functions = state.get(
        "uncovered_functions", []
    )

    uncovered_lines = state.get(
        "uncovered_lines", []
    )

    coverage_before = state.get(
        "coverage_before", 0.0
    )

    # --------------------------------------------------------
    # Étape 4 : construire le prompt
    # --------------------------------------------------------

    prompt = build_prompt(
        source_code=source_code,
        existing_tests=existing_tests,
        uncovered_functions=uncovered_functions,
        uncovered_lines=uncovered_lines,
        coverage_before=coverage_before
    )

    # --------------------------------------------------------
    # Étape 5 : envoyer le prompt à Qwen
    # --------------------------------------------------------

    print("\nEnvoi du prompt à Qwen2.5-Coder...")

    response = ask_llm(prompt)

    # --------------------------------------------------------
    # Étape 6 : extraire le code Python
    # --------------------------------------------------------

    generated_code = extract_python_code(response)

    if not generated_code:
        raise ValueError(
            "Qwen n'a retourné aucun code Python."
        )

    # --------------------------------------------------------
    # Étape 7 : valider le code généré
    # --------------------------------------------------------

    test_functions = validate_generated_code(
        generated_code
    )

    # --------------------------------------------------------
    # Étape 8 : créer le dossier de destination
    # --------------------------------------------------------

    GENERATED_TESTS_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    # --------------------------------------------------------
    # Étape 9 : enregistrer les tests générés
    # --------------------------------------------------------

    generated_file = (
        GENERATED_TESTS_DIR / "test_generated_checkout.py"
    )

    generated_file.write_text(
        generated_code + "\n",
        encoding="utf-8"
    )

    # --------------------------------------------------------
    # Étape 10 : mettre à jour l'état LangGraph
    # --------------------------------------------------------

    state["generated_tests"] = generated_code

    state["generated_test_file"] = str(
        generated_file.relative_to(BASE_DIR)
    )

    state["generated_test_count"] = len(test_functions)

    # --------------------------------------------------------
    # Étape 11 : afficher le résumé
    # --------------------------------------------------------

    print("\n========== TEST GENERATION ==========")

    print(f"Fichier généré : {generated_file}")

    print(
        f"Nombre de tests générés : {len(test_functions)}"
    )

    print("\nTests créés :")

    for function_name in test_functions:
        print(f" - {function_name}")

    print("\n=====================================")

    return state
