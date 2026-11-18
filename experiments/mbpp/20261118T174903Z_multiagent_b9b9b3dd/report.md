# MBPP — évaluation de génération de tests

- Statut : `completed`
- Split : tâches officielles 11–510
- Tâches : 3
- Référence réussie : 3/3
- Multi-agent réussi : 1/3

| Mesure moyenne par tâche | Baseline | Multi-agent | Écart |
|---|---:|---:|---:|
| Couverture lignes (%) | 90.48 | 100.0 | 9.52 |
| Critique heuristique (/100) | — | 66.67 | — |

> Protocole : MBPP test_list baseline vs baseline + LLM-generated pytest tests; not official pass@k. Le critique est une heuristique; ce résultat n'est pas un score pass@k.

## Résultats par tâche

| ID | Baseline | Multi-agent | Couverture avant | Couverture après | Delta | Tests générés | Critique |
|---:|---|---|---:|---:|---:|---:|---:|
| 145 | passed | failed | 100.0 | 100.0 | 0.0 | 6 | 50.0 |
| 396 | passed | passed | 100.0 | 100.0 | 0.0 | 6 | 80.0 |
| 93 | passed | failed | 71.42857142857143 | 100.0 | 28.57 | 6 | 70.0 |

Le split de test MBPP utilise les tâches 11–510. La couverture mesure l'exécution, pas à elle seule la pertinence ou la capacité des tests à détecter des défauts.
