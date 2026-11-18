# HumanEval — évaluation de génération de tests

- Statut : `completed`
- Tâches : 1
- Référence réussie : 1/1
- Multi-agent réussi : 0/1

| Mesure moyenne par tâche | Baseline | Multi-agent | Écart |
|---|---:|---:|---:|
| Couverture lignes (%) | 100.0 | 100.0 | 0.0 |
| Critique heuristique (/100) | — | 50.0 | — |

> Protocole : reference tests vs reference + generated unit tests; not official pass@k. Le score de critique est une heuristique déterministe, pas un score LLM.

## Résultats par tâche

| Task ID | Baseline | Multi-agent | Couverture baseline | Couverture après | Delta | Tests générés | Critique |
|---|---|---|---:|---:|---:|---:|---:|
| HumanEval/49 | passed | failed | 100.0 | 100.0 | 0.0 | 6 | 50.0 |

HumanEval fournit des tâches et des tests de référence; ce protocole mesure l'ajout de tests unitaires à une solution de référence. Il ne calcule pas le score officiel de génération de solutions pass@k.
