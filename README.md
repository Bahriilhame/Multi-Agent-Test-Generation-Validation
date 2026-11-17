# SmartTest-AI

Prototype multi-agent de génération et de validation de tests Python. La version actuelle utilise le projet local `checkout` comme premier benchmark reproductible.

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

## Métriques

- Couverture des lignes et des branches avant/après, mesurées par coverage.py avec la même configuration.
- Delta de couverture en points de pourcentage.
- Résumé pytest et durée de l’exécution Docker.
- Nombre de tests générés et analyse du critique quand disponible.

La couverture mesure l’exécution du code, pas la capacité des tests à détecter une faute. Le rapport garde donc cette limite explicite. Les comparaisons futures devront garder le même commit, les mêmes versions et la même configuration, et les essais du LLM devraient être répétés pour mesurer la variabilité.

## Benchmarks prévus

Le format de run est organisé par benchmark : `experiments/<benchmark>/<run_id>/`. Le projet checkout valide aujourd’hui le protocole et le stockage. HumanEval, MBPP et SWE-bench nécessitent encore leurs adaptateurs et leurs critères d’évaluation; aucun résultat n’est produit pour eux par les commandes actuelles.
