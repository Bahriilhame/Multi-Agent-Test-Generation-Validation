# SmartTest-AI

Prototype multi-agent de génération et de validation de tests Python. La version actuelle utilise le projet local `checkout` comme premier benchmark reproductible.

## État du support générique

Un moteur de découverte de projet est disponible : il repère les fichiers source, tests, configurations, gestionnaires de paquets, langages et quelques frameworks. Lancer l'inspection sans modifier le projet :

```powershell
python platform_cli.py inspect chemin\vers\projet
python platform_cli.py inspect chemin\vers\projet --output report.json
```

L'API d'adaptateur commune se trouve dans `adapters/`. Python est l'unique adaptateur d'exécution implémenté; JavaScript/TypeScript et Java sont détectés à titre informatif et ne sont pas déclarés supportés. Le flux historique `python main.py` reste une démonstration `checkout`; le flux générique ci-dessous est le point d'entrée pour d'autres projets Python.

## Workflow générique Python

Un pipeline générique (LangGraph, boucle bornée, Ollama, copie temporaire et Docker hors réseau) est maintenant disponible pour les dossiers, ZIP et dépôts Git HTTPS/SSH :

```powershell
python platform_cli.py run .\chemin\vers\projet --iterations 2
python platform_cli.py run .\projet.zip --model qwen2.5-coder:7b
python platform_cli.py run https://github.com/organisation/projet.git --docker-image mon-runner:latest
```

Le runner standard fournit Python, pytest et coverage. Les dépendances applicatives doivent déjà être présentes dans l'image Docker indiquée par `--docker-image`; le système ne lance pas d'installation arbitraire de paquets du projet. Les résultats, tests générés et journaux vont dans `experiments/projects/<projet>/<run_id>/`. Le score du critique combine une revue sémantique Ollama avec AST et résultat pytest; si Ollama est indisponible, il conserve un score heuristique mais ne marque pas le run accepté. Docker fournit une isolation utile, sans constituer une garantie contre les vulnérabilités du noyau ou du daemon.

Pour un dépôt Flask ayant un `requirements.txt`, bâtis d'abord l'image de base depuis la racine de SmartTest-AI :

```powershell
docker build -t smarttest-runner:latest -f sandbox/runner/Dockerfile sandbox/runner
```

Ajoute ensuite ce `Dockerfile` à la racine du dépôt Flask et bâtis son image :

```dockerfile
FROM smarttest-runner:latest
USER root
COPY requirements.txt /tmp/project-requirements.txt
RUN pip install --no-cache-dir -r /tmp/project-requirements.txt
USER tester
```

```powershell
docker build -t flasktasks-runner .
python platform_cli.py run https://github.com/organisation/flasktasks.git --docker-image flasktasks-runner
```

Dans l'interface, saisis `flasktasks-runner` dans le champ de l'image Docker. L'analyse s'arrête avec le nom des modules manquants si l'image ne contient pas les dépendances nécessaires.

Pour recalculer la décision après mise à jour des règles du critique, sans rappeler le modèle ni réexécuter les tests : `python -m experiments.review_project_run --run-dir experiments/projects/<projet>/<run_id>`. Cette commande écrit `critic_result_v2.json` sans modifier le rapport d'origine; ajoute `--response-file <fichier>` si la réponse brute a été conservée sous un autre nom.

Projets de démonstration indépendants : `demos/python_functions`, `demos/python_modules`, `demos/flask_api`, `demos/low_coverage` et `demos/edge_cases`. Flask nécessite une image bâtie avec son `Dockerfile` avant l'exécution (`docker build -t smarttest-flask-demo demos/flask_api`, puis `--docker-image smarttest-flask-demo`).

Interface locale (dépendance facultative) :

```powershell
python -m pip install -r requirements-ui.txt
streamlit run ui/app.py
```

L'interface prend un chemin local, une archive ZIP ou une URL Git, permet de choisir Ollama, le nombre de cycles, le timeout, le seuil de pertinence et l'image Docker, puis affiche les résultats et rapports.

## SWE-bench Lite

L'adaptateur télécharge/filtre le split officiel sans exporter les champs `patch` et `test_patch` vers les prompts. Il distingue la recherche de génération de tests sur la révision de base de la résolution officielle de patchs : seul l'outil upstream peut produire la métrique « resolved ». Le mode officiel nécessite WSL2/Linux, Docker et la dépendance `swebench`.

```powershell
python -m pip install -r requirements-swebench.txt
python -m experiments.swebench prepare --limit 1 --seed 42
python -m experiments.swebench run-tests --instance-id sympy__sympy-20590 --iterations 1
```

Pour une vraie évaluation officielle de patchs (format JSONL `instance_id`, `model_name_or_path`, `model_patch`), dans WSL2/Linux :

```bash
python -m experiments.swebench official-eval --predictions predictions.jsonl --instance-id sympy__sympy-20590 --workers 1
```

## Prérequis

- Python et dépendances de `requirements.txt`
- Docker Desktop démarré
- Ollama disponible à l’adresse configurée dans `.env` pour le mode multi-agent
- Image Docker construite par `experiments/run_baseline.py` ou par `docker build -t smarttest-runner:latest -f sandbox/runner/Dockerfile .`

## Comparer baseline et multi-agent

1. Baseline : tests écrits à la main, sans appel au LLM.

   ```powershell
   python -m experiments.run_baseline
   ```

2. Multi-agent : couverture initiale, génération, validation Docker et critique.

   ```powershell
   python main.py
   ```

Chaque commande crée un identifiant unique et stocke ses résultats dans `experiments/checkout/<run_id>/`. Une expérience contient `metadata.json`, `benchmark_results.json`, `report.md`, les rapports de couverture et les journaux. Les résultats des exécutions restent séparés.

3. Synthèse CSV et Markdown de tous les runs disponibles :

   ```powershell
   python -m experiments.compare
   ```

   Les fichiers `experiments/comparison.csv` et `experiments/comparison.md` sont régénérables à partir des résultats individuels.

4. Mutation testing sur le dernier run multi-agent réussi, comparé aux seuls tests écrits à la main :

   ```powershell
   python -m experiments.run_mutation
   ```

   `mutmut` s'exécute dans un conteneur Linux, car son exécution native Windows n'est pas prise en charge. Le rapport se trouve dans `experiments/checkout/<run_id>/mutation_report.md`; les résultats bruts et journaux restent dans le même dossier. Le premier lancement construit une image Docker et nécessite l'accès réseau pour installer `mutmut`.

5. HumanEval sur trois tâches sélectionnées de façon reproductible :

   ```powershell
   python -m experiments.humaneval --limit 3 --seed 42
   ```

   Le premier lancement télécharge le jeu officiel dans `datasets/humaneval/`. Les rapports individuels et de synthèse sont écrits sous `experiments/humaneval/<run_id>/`. Le protocole mesure l'effet des tests générés sur la solution de référence; il ne calcule pas le pass@k officiel de génération de solutions. Pour valider le téléchargement et Docker sans appeler Ollama : `python -m experiments.humaneval --limit 1 --baseline-only`.

   Runner commun pour lancer HumanEval et MBPP séparément ou successivement avec même modèle, limite et graine : `python -m experiments.run_benchmarks --benchmarks all --limit 3 --seed 42 --model qwen2.5-coder:7b`. Les journaux consolidés sont dans `experiments/benchmark-suites/<run_id>/`; les résultats détaillés restent dans chaque benchmark.

6. MBPP sur le split de test officiel (IDs 11–510) :

   ```powershell
   python -m experiments.mbpp --limit 3 --seed 42
   ```

   Le premier lancement télécharge le jeu sanitized officiel dans `datasets/mbpp/`. Chaque run conserve le hash du jeu, les IDs choisis, les réponses du générateur et du critique, les tests, les résultats pytest, la couverture et un rapport sous `experiments/mbpp/<run_id>/`. Le Critique-Pertinence Ollama évalue la pertinence, les valeurs attendues, le domaine et la diversité; son rapport inclut aussi les échecs pytest et les imports manquants détectés par AST. Le score combiné pondère la revue sémantique à 70 % et le taux de réussite pytest à 30 %. Cela ajoute un appel Ollama par tâche, limité à 120 secondes au total et 256 tokens; en cas d'échec, les constats pytest/AST et le score heuristique sont conservés. `--critic-mode heuristic` désactive ce second appel et conserve l’ancien score déterministe. Pour valider le jeu de données et Docker sans appeler Ollama : `python -m experiments.mbpp --limit 1 --baseline-only`.

   Pour analyser les artefacts déjà sauvegardés sans régénérer ni réexécuter les suites : `python -m experiments.review_mbpp --run-id <run_id> --task-id <id>`. Le mode par défaut produit les constats déterministes AST/pytest sans Ollama. Ajoute `--critic-mode llm` pour la revue sémantique v2. Les résultats sont écrits dans des fichiers `critic_result_<version>.json` et `critic_response_<version>.txt`; le score historique reste inchangé.

## Métriques

- Couverture des lignes et des branches avant/après, mesurées par coverage.py avec la même configuration.
- Delta de couverture en points de pourcentage.
- Résumé pytest et durée de l’exécution Docker.
- Nombre de tests générés et analyse du critique quand disponible.

La couverture mesure l’exécution du code, pas la capacité des tests à détecter une faute. Le rapport garde donc cette limite explicite. Les comparaisons futures devront garder le même commit, les mêmes versions et la même configuration, et les essais du LLM devraient être répétés pour mesurer la variabilité.

## Benchmarks

Le format de run est organisé par benchmark : `experiments/<benchmark>/<run_id>/`. Checkout, HumanEval et MBPP ont des parcours d'évaluation de génération de tests. SWE-bench Lite dispose d'un adaptateur de préparation et d'essai de génération de tests, ainsi qu'un appel au harness officiel pour les patchs. Ces deux protocoles sont rapportés séparément; les métriques HumanEval/MBPP ne sont pas assimilées à SWE-bench.
