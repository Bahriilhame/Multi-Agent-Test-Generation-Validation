# HumanEval — évaluation de génération de tests

- Statut : `baseline_only`
- Tâches : 1
- Référence réussie : 1/1
- Multi-agent réussi : 0/1

| Mesure moyenne par tâche | Baseline | Multi-agent | Écart |
|---|---:|---:|---:|
| Couverture lignes (%) | 100.0 | None | None |
| Critique heuristique (/100) | — | None | — |

> Protocole : reference tests vs reference + generated unit tests; not official pass@k. Le score de critique est une heuristique déterministe, pas un score LLM.

## Résultats par tâche

| Task ID | Baseline | Multi-agent | Couverture baseline | Couverture après | Delta | Tests générés | Critique |
|---|---|---|---:|---:|---:|---:|---:|
| HumanEval/61 | passed | non exécuté | 100.0 | None | None | None | None |

HumanEval fournit des tâches et des tests de référence; ce protocole mesure l'ajout de tests unitaires à une solution de référence. Il ne calcule pas le score officiel de génération de solutions pass@k.
