# MBPP — évaluation de génération de tests

- Statut : `completed`
- Split : tâches officielles 11–510
- Tâches : 3
- Référence réussie : 3/3
- Multi-agent réussi : 3/3

| Mesure moyenne par tâche | Baseline | Multi-agent | Écart |
|---|---:|---:|---:|
| Couverture lignes (%) | 100.0 | 100.0 | 0.0 |
| Critique heuristique (/100) | — | 80.0 | — |

> Protocole : MBPP test_list baseline vs baseline + LLM-generated pytest tests; not official pass@k. Le critique est une heuristique; ce résultat n'est pas un score pass@k.

## Résultats par tâche

| ID | Baseline | Multi-agent | Couverture avant | Couverture après | Delta | Tests générés | Critique |
|---:|---|---|---:|---:|---:|---:|---:|
| 234 | passed | passed | 100.0 | 100.0 | 0.0 | 6 | 80.0 |
| 395 | passed | passed | 100.0 | 100.0 | 0.0 | 6 | 80.0 |
| 405 | passed | passed | 100.0 | 100.0 | 0.0 | 6 | 80.0 |

Le split de test MBPP utilise les tâches 11–510. La couverture mesure l'exécution, pas à elle seule la pertinence ou la capacité des tests à détecter des défauts.
