# MBPP — évaluation de génération de tests

- Statut : `baseline_only`
- Split : tâches officielles 11–510
- Tâches : 1
- Référence réussie : 0/1
- Multi-agent réussi : 0/1

| Mesure moyenne par tâche | Baseline | Multi-agent | Écart |
|---|---:|---:|---:|
| Couverture lignes (%) | non mesuré | non mesuré | non mesuré |
| Critique heuristique (/100) | — | non mesuré | — |

> Protocole : MBPP test_list baseline vs baseline + LLM-generated pytest tests; not official pass@k. Le critique est une heuristique; ce résultat n'est pas un score pass@k.

## Résultats par tâche

| ID | Baseline | Multi-agent | Couverture avant | Couverture après | Delta | Tests générés | Critique |
|---:|---|---|---:|---:|---:|---:|---:|
| 455 | failed | non exécuté | non mesuré | non mesuré | non mesuré | non mesuré | non mesuré |

Le split de test MBPP utilise les tâches 11–510. La couverture mesure l'exécution, pas à elle seule la pertinence ou la capacité des tests à détecter des défauts.
