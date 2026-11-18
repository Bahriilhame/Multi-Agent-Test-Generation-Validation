# SmartTest-AI

Prototype multi-agent de génération et de validation de tests Python. La version actuelle utilise le projet local `checkout` comme premier benchmark reproductible.

## État du support générique

Un moteur de découverte de projet est disponible : il repère les fichiers source, tests, configurations, gestionnaires de paquets, langages et quelques frameworks. Lancer l'inspection sans modifier le projet :

```powershell
python platform_cli.py inspect chemin\vers\projet
python platform_cli.py inspect chemin\vers\projet --output report.json
```

L'API d'adaptateur commune se trouve dans `adapters/`. Python est l'unique adaptateur d'exécution implémenté; JavaScript/TypeScript et Java sont actuellement détectés à titre informatif et ne sont pas déclarés supportés. Cette découverte est une première brique : le workflow multi-agent historique et son runner Docker restent liés à `checkout.py`. La génération, l'exécution isolée et la critique génériques pour un chemin arbitraire, l'import ZIP/Git, une interface graphique et SWE-bench restent à réaliser. Ne pas confondre détection de langage et support complet.

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

## Benchmarks prévus

Le format de run est organisé par benchmark : `experiments/<benchmark>/<run_id>/`. Checkout, HumanEval et MBPP ont maintenant des premiers parcours d'évaluation. SWE-bench nécessite encore un adaptateur et des critères d'évaluation adaptés à ses patchs logiciels.
